"""
Purity test service:
  - IP info lookup (country, org, ISP, residential/datacenter)
  - Netflix unlock detection
  - OpenAI/ChatGPT access detection
All requests go through the node's proxy (xray-core socks5).
"""
import asyncio
import httpx
from typing import Dict, Any, Optional
from app.services.speed_test import proxy_speed_test_one, _build_xray_config
from app.config import settings
import os
import json
import tempfile
import time


async def _get_with_proxy(url: str, local_port: int, timeout: int = 10) -> Optional[httpx.Response]:
    proxies = {
        "http://": f"socks5://127.0.0.1:{local_port}",
        "https://": f"socks5://127.0.0.1:{local_port}",
    }
    try:
        async with httpx.AsyncClient(proxies=proxies, timeout=timeout, follow_redirects=True) as client:
            return await client.get(url)
    except Exception:
        return None


async def purity_test_one(node: Dict[str, Any], local_port: int) -> Dict[str, Any]:
    """
    Run full purity check through a node:
    1. Get IP info
    2. Netflix unlock
    3. OpenAI access
    Returns structured result dict.
    """
    xray_bin = settings.XRAY_BINARY_PATH
    result: Dict[str, Any] = {
        "success": False,
        "ip_address": None,
        "ip_country": None,
        "ip_org": None,
        "is_residential": None,
        "netflix_unlock": False,
        "openai_unlock": False,
        "purity_status": "unknown",
        "error": None,
    }

    if not os.path.exists(xray_bin):
        result["error"] = f"xray binary not found at {xray_bin}"
        return result

    config = _build_xray_config(node, local_port)
    if config is None:
        result["error"] = f"Protocol {node['protocol']} not supported"
        return result

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
        await asyncio.sleep(1.5)

        # 1. IP info
        ip_resp = await _get_with_proxy("http://ip-api.com/json?fields=status,country,countryCode,org,isp,hosting,query", local_port)
        if ip_resp and ip_resp.status_code == 200:
            ip_data = ip_resp.json()
            result["ip_address"] = ip_data.get("query")
            result["ip_country"] = ip_data.get("countryCode")
            result["ip_org"] = ip_data.get("org") or ip_data.get("isp")
            # hosting=True means datacenter, False means residential
            result["is_residential"] = not ip_data.get("hosting", True)
            result["success"] = True

        # 2. Netflix unlock detection
        netflix_resp = await _get_with_proxy(
            "https://www.netflix.com/title/81280792", local_port, timeout=10
        )
        if netflix_resp:
            # If redirected to a country-specific page and not geo-blocked
            final_url = str(netflix_resp.url)
            status_code = netflix_resp.status_code
            result["netflix_unlock"] = (
                status_code == 200
                and "geo-block" not in netflix_resp.text.lower()
                and "not-available" not in netflix_resp.text.lower()
            )

        # 3. OpenAI access detection
        openai_resp = await _get_with_proxy(
            "https://chat.openai.com", local_port, timeout=10
        )
        if openai_resp:
            result["openai_unlock"] = openai_resp.status_code in (200, 302, 303)

        # Determine overall purity status
        if result["success"]:
            if result["is_residential"]:
                result["purity_status"] = "clean"
            elif result["netflix_unlock"] or result["openai_unlock"]:
                result["purity_status"] = "partial"
            else:
                result["purity_status"] = "dirty"

    except Exception as e:
        result["error"] = str(e)
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

    return result


async def purity_test_batch(
    nodes: list,
    concurrency: int = 3,
    port_start: int = None,
) -> list:
    port_start = port_start or (settings.PROXY_TEST_PORT_START + 200)
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    port_counter = [port_start]

    async def test_node(node):
        async with semaphore:
            port = port_counter[0]
            port_counter[0] += 1
            r = await purity_test_one(node, port)
            results.append({"id": node["id"], **r})

    await asyncio.gather(*[test_node(n) for n in nodes])
    return results
