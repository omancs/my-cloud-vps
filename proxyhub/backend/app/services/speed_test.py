"""
Speed test service V2:
  Layer 1: Fast TCP Ping (asyncio socket connection)
  Layer 2: Real proxy speed test via dynamic xray-core subprocess
"""
import asyncio
import time
import json
import os
import tempfile
import socket
from typing import List, Dict, Any, Optional
from app.config import settings


def _find_free_port() -> int:
    """Find a random available local port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ─────────────────────────────────────────────
# Layer 1: TCP Ping
# ─────────────────────────────────────────────

async def tcp_ping_one(host: str, port: int, timeout: float = None) -> Optional[float]:
    """Attempt TCP connection to host:port. Returns latency in ms, or None on failure."""
    timeout = timeout or settings.TCP_PING_TIMEOUT or 3.5
    try:
        start = time.monotonic()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)), timeout=timeout
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
    concurrency: int = 50,
) -> List[Dict[str, Any]]:
    """Run TCP ping on a list of node dicts [{id, address, port}]."""
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

    await asyncio.gather(*[ping_node(n) for n in nodes], return_exceptions=True)
    return results


# ─────────────────────────────────────────────
# Layer 2: Real proxy speed test via xray-core
# ─────────────────────────────────────────────

def _build_xray_config(node: Dict[str, Any], local_port: int) -> Optional[Dict[str, Any]]:
    """Build a minimal xray-core config for VMess, VLESS, SS, Trojan, Hysteria 2."""
    protocol = (node.get("protocol") or "").lower()
    extra = node.get("extra") or {}
    address = node.get("address", "")
    port = int(node.get("port", 0) or 0)

    if protocol == "vmess":
        outbound = {
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": address,
                    "port": port,
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
                "wsSettings": {"path": extra.get("path", "/"), "headers": {"Host": extra.get("host", "")}} if extra.get("network") == "ws" else None,
                "tlsSettings": {"serverName": extra.get("sni", extra.get("host", address)), "allowInsecure": True},
            }
        }
        # Clean None values in streamSettings
        outbound["streamSettings"] = {k: v for k, v in outbound["streamSettings"].items() if v is not None}

    elif protocol == "vless":
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": address,
                    "port": port,
                    "users": [{"id": extra.get("uuid", ""), "encryption": "none", "flow": extra.get("flow", "")}]
                }]
            },
            "streamSettings": {
                "network": extra.get("type", extra.get("network", "tcp")),
                "security": extra.get("security", ""),
                "tlsSettings": {"serverName": extra.get("sni", address), "allowInsecure": True} if extra.get("security") == "tls" else None,
                "realitySettings": {
                    "serverName": extra.get("sni", address),
                    "fingerprint": extra.get("fp", "chrome"),
                    "publicKey": extra.get("pbk", ""),
                    "shortId": extra.get("sid", ""),
                } if extra.get("security") == "reality" else None,
            }
        }
        outbound["streamSettings"] = {k: v for k, v in outbound["streamSettings"].items() if v is not None}

    elif protocol == "ss":
        outbound = {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": address,
                    "port": port,
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
                    "address": address,
                    "port": port,
                    "password": extra.get("password", ""),
                }]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {"serverName": extra.get("sni", address), "allowInsecure": True},
            }
        }

    else:
        return None

    return {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "port": local_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False},
        }],
        "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}],
    }


async def proxy_speed_test_one(
    node: Dict[str, Any],
    test_url: str = "http://cp.cloudflare.com/generate_204",
    timeout: int = 8,
) -> Dict[str, Any]:
    """Start isolated xray instance, test HTTP latency and basic throughput."""
    import httpx

    xray_bin = settings.XRAY_BINARY_PATH
    if not os.path.exists(xray_bin):
        tcp_lat = await tcp_ping_one(node.get("address", ""), node.get("port", 0))
        return {
            "success": tcp_lat is not None,
            "latency_ms": tcp_lat,
            "download_mbps": None,
            "error": "xray binary not found",
        }

    local_port = _find_free_port()
    config = _build_xray_config(node, local_port)
    if config is None:
        return {"success": False, "error": f"Protocol {node.get('protocol')} not supported"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        config_path = f.name

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            xray_bin, "run", "-config", config_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(1.0)

        proxies = {
            "http://": f"socks5://127.0.0.1:{local_port}",
            "https://": f"socks5://127.0.0.1:{local_port}",
        }

        # Step 1: Multi-target Latency test
        elapsed_ms = None
        targets = [
            test_url,
            "https://www.gstatic.com/generate_204",
            "https://1.1.1.1/cdn-cgi/trace",
        ]
        async with httpx.AsyncClient(proxies=proxies, timeout=timeout, follow_redirects=True) as client:
            for target in targets:
                try:
                    start = time.monotonic()
                    resp = await client.get(target)
                    if resp.status_code in (200, 204):
                        elapsed_ms = (time.monotonic() - start) * 1000
                        break
                except Exception:
                    continue

            if elapsed_ms is None:
                return {"success": False, "error": "Connection timed out to all test targets"}

            # Step 2: Quick throughput test
            download_mbps = None
            try:
                sp_start = time.monotonic()
                chunk_resp = await client.get("https://speed.cloudflare.com/__down?bytes=300000", timeout=4)
                sp_time = time.monotonic() - sp_start
                if sp_time > 0 and chunk_resp.status_code == 200:
                    download_mbps = round((len(chunk_resp.content) * 8) / (sp_time * 1_000_000), 2)
            except Exception:
                pass

        return {
            "success": True,
            "latency_ms": round(elapsed_ms, 2),
            "download_mbps": download_mbps,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if proc:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2)
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
) -> List[Dict[str, Any]]:
    """Run proxy speed test with controlled concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def test_node(node: Dict[str, Any]):
        async with semaphore:
            res = await proxy_speed_test_one(node)
            results.append({"id": node["id"], **res})

    await asyncio.gather(*[test_node(n) for n in nodes], return_exceptions=True)
    return results
