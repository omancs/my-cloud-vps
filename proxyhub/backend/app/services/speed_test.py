"""
Speed test service:
  Layer 1: TCP Ping (asyncio connection, no proxy needed)
  Layer 2: Real proxy speed test via xray-core subprocess
"""
import asyncio
import time
import json
import os
import tempfile
import subprocess
from typing import List, Dict, Any, Optional
from app.config import settings


# ─────────────────────────────────────────────
# Layer 1: TCP Ping
# ─────────────────────────────────────────────

async def tcp_ping_one(host: str, port: int, timeout: float = None) -> Optional[float]:
    """
    Attempt TCP connection to host:port.
    Returns latency in ms, or None on failure.
    """
    timeout = timeout or settings.TCP_PING_TIMEOUT
    try:
        start = time.monotonic()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        latency = (time.monotonic() - start) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return round(latency, 2)
    except Exception:
        return None


async def tcp_ping_batch(
    nodes: List[Dict[str, Any]],
    concurrency: int = None,
) -> List[Dict[str, Any]]:
    """
    Run TCP ping on a list of node dicts [{id, address, port}].
    Returns list of {id, latency_ms, status}.
    """
    concurrency = concurrency or settings.TCP_PING_CONCURRENCY
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def ping_node(node: Dict[str, Any]):
        async with semaphore:
            latency = await tcp_ping_one(node["address"], node["port"])
            results.append({
                "id": node["id"],
                "latency_ms": latency,
                "status": "ok" if latency is not None else "timeout",
            })

    await asyncio.gather(*[ping_node(n) for n in nodes])
    return results


# ─────────────────────────────────────────────
# Layer 2: Real proxy speed test via xray-core
# ─────────────────────────────────────────────

def _build_xray_config(node: Dict[str, Any], local_port: int) -> Dict[str, Any]:
    """Build a minimal xray-core inbound+outbound config for a given node."""
    protocol = node["protocol"]
    extra = node.get("extra") or {}

    # Build outbound based on protocol
    if protocol == "vmess":
        outbound = {
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": node["address"],
                    "port": node["port"],
                    "users": [{
                        "id": extra.get("uuid", ""),
                        "alterId": int(extra.get("alterId", 0)),
                        "security": extra.get("security", "auto"),
                    }]
                }]
            },
            "streamSettings": {
                "network": extra.get("network", "tcp"),
                "security": extra.get("tls", ""),
                "wsSettings": {"path": extra.get("path", "/"), "headers": {"Host": extra.get("host", "")}},
                "tlsSettings": {"serverName": extra.get("sni", extra.get("host", ""))},
            }
        }
    elif protocol == "vless":
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": node["address"],
                    "port": node["port"],
                    "users": [{"id": extra.get("uuid", ""), "encryption": "none", "flow": extra.get("flow", "")}]
                }]
            },
            "streamSettings": {
                "network": extra.get("type", "tcp"),
                "security": extra.get("security", ""),
                "tlsSettings": {"serverName": extra.get("sni", "")},
                "realitySettings": {
                    "serverName": extra.get("sni", ""),
                    "fingerprint": extra.get("fp", ""),
                    "publicKey": extra.get("pbk", ""),
                    "shortId": extra.get("sid", ""),
                } if extra.get("security") == "reality" else {},
            }
        }
    elif protocol == "ss":
        outbound = {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": node["address"],
                    "port": node["port"],
                    "method": extra.get("method", "aes-256-gcm"),
                    "password": extra.get("password", ""),
                }]
            }
        }
    elif protocol == "trojan":
        outbound = {
            "protocol": "trojan",
            "settings": {
                "servers": [{
                    "address": node["address"],
                    "port": node["port"],
                    "password": extra.get("password", ""),
                }]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {"serverName": extra.get("sni", node["address"])},
            }
        }
    else:
        # Unsupported protocol for xray test
        return None

    config = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "port": local_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False},
        }],
        "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}],
    }
    return config


async def proxy_speed_test_one(
    node: Dict[str, Any],
    local_port: int,
    test_url: str = None,
    timeout: int = None,
) -> Dict[str, Any]:
    """
    Start a temporary xray instance, measure HTTP GET latency through it.
    Returns {success, latency_ms, download_mbps, error}.
    """
    test_url = test_url or settings.PROXY_TEST_URL
    timeout = timeout or settings.PROXY_TEST_TIMEOUT
    xray_bin = settings.XRAY_BINARY_PATH

    if not os.path.exists(xray_bin):
        return {"success": False, "error": f"xray binary not found at {xray_bin}"}

    config = _build_xray_config(node, local_port)
    if config is None:
        return {"success": False, "error": f"Protocol {node['protocol']} not supported for proxy test"}

    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        config_path = f.name

    proc = None
    try:
        # Start xray
        proc = await asyncio.create_subprocess_exec(
            xray_bin, "run", "-config", config_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Wait for xray to be ready
        await asyncio.sleep(1.5)

        # Test via socks5 proxy
        import httpx
        proxies = {"http://": f"socks5://127.0.0.1:{local_port}",
                   "https://": f"socks5://127.0.0.1:{local_port}"}
        start = time.monotonic()
        async with httpx.AsyncClient(proxies=proxies, timeout=timeout) as client:
            resp = await client.get(test_url)
            elapsed = (time.monotonic() - start) * 1000
            content_len = len(resp.content)
            elapsed_sec = elapsed / 1000
            download_mbps = round((content_len * 8) / (elapsed_sec * 1_000_000), 2) if elapsed_sec > 0 else 0

        return {
            "success": True,
            "latency_ms": round(elapsed, 2),
            "download_mbps": download_mbps,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if proc:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        try:
            os.unlink(config_path)
        except Exception:
            pass


async def proxy_speed_test_batch(
    nodes: List[Dict[str, Any]],
    concurrency: int = 5,
    port_start: int = None,
) -> List[Dict[str, Any]]:
    """
    Run proxy speed tests on multiple nodes with limited concurrency.
    Each node gets a unique local port.
    """
    port_start = port_start or settings.PROXY_TEST_PORT_START
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    port_counter = [port_start]

    async def test_node(node: Dict[str, Any]):
        async with semaphore:
            port = port_counter[0]
            port_counter[0] += 1
            result = await proxy_speed_test_one(node, port)
            results.append({"id": node["id"], **result})

    await asyncio.gather(*[test_node(n) for n in nodes])
    return results
