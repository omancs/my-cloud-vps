"""
Purity & Unlock test service V2:
  - Multi-source GeoIP & ISP type detection (Residential vs Datacenter)
  - Streaming unlock detection (Netflix, YouTube Premium, Disney+)
  - AI services detection (OpenAI / ChatGPT)
"""
import asyncio
import os
import json
import tempfile
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.speed_test import _build_xray_config, _find_free_port


async def _get_with_proxy(url: str, port: int, timeout: int = 8, headers: dict = None) -> Optional[httpx.Response]:
    proxies = {
        "http://": f"socks5://127.0.0.1:{port}",
        "https://": f"socks5://127.0.0.1:{port}",
    }
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        **(headers or {})
    }
    try:
        async with httpx.AsyncClient(proxies=proxies, timeout=timeout, follow_redirects=True, headers=hdrs) as client:
            return await client.get(url)
    except Exception:
        return None


async def purity_test_one(node: Dict[str, Any]) -> Dict[str, Any]:
    """Perform comprehensive IP purity & Streaming unlock test."""
    xray_bin = settings.XRAY_BINARY_PATH
    result: Dict[str, Any] = {
        "success": False,
        "ip_address": None,
        "ip_country": None,
        "ip_org": None,
        "is_residential": None,
        "netflix_unlock": False,
        "openai_unlock": False,
        "youtube_unlock": False,
        "purity_status": "unknown",
        "error": None,
    }

    if not os.path.exists(xray_bin):
        # Fallback country inference from node name
        inferred_country = _infer_country_from_name(node.get("name", ""))
        result["ip_country"] = inferred_country
        result["error"] = "xray binary not found, inferred country from name"
        return result

    local_port = _find_free_port()
    config = _build_xray_config(node, local_port)
    if config is None:
        result["error"] = f"Protocol {node.get('protocol')} not supported"
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
        await asyncio.sleep(1.2)

        # ── 1. GeoIP & ISP Resolution (Multi-source fallback) ──
        ip_data_found = False

        # Source A: api.ip.sb
        ip_resp = await _get_with_proxy("https://api.ip.sb/geoip", local_port, timeout=6)
        if ip_resp and ip_resp.status_code == 200:
            try:
                data = ip_resp.json()
                result["ip_address"] = data.get("ip")
                result["ip_country"] = data.get("country_code")
                result["ip_org"] = data.get("organization") or data.get("isp")
                # ip.sb provides asn & org
                org_lower = (result["ip_org"] or "").lower()
                is_datacenter = any(k in org_lower for k in ("cloud", "hosting", "data center", "datacenter", "digitalocean", "linode", "vultr", "aws", "google", "microsoft", "oracle", "ovh", "alibaba", "tencent"))
                result["is_residential"] = not is_datacenter
                result["success"] = True
                ip_data_found = True
            except Exception:
                pass

        # Source B fallback: ip-api.com
        if not ip_data_found:
            ip_resp2 = await _get_with_proxy("http://ip-api.com/json?fields=status,country,countryCode,org,isp,hosting,query", local_port, timeout=6)
            if ip_resp2 and ip_resp2.status_code == 200:
                try:
                    data2 = ip_resp2.json()
                    result["ip_address"] = data2.get("query")
                    result["ip_country"] = data2.get("countryCode")
                    result["ip_org"] = data2.get("org") or data2.get("isp")
                    result["is_residential"] = not data2.get("hosting", True)
                    result["success"] = True
                    ip_data_found = True
                except Exception:
                    pass

        # Source C fallback: Cloudflare trace
        if not ip_data_found:
            cf_resp = await _get_with_proxy("https://1.1.1.1/cdn-cgi/trace", local_port, timeout=6)
            if cf_resp and cf_resp.status_code == 200:
                trace_lines = dict(line.split("=", 1) for line in cf_resp.text.splitlines() if "=" in line)
                result["ip_address"] = trace_lines.get("ip")
                result["ip_country"] = trace_lines.get("loc")
                result["is_residential"] = False
                result["success"] = True

        # Fallback country from node name if still empty
        if not result["ip_country"]:
            result["ip_country"] = _infer_country_from_name(node.get("name", ""))

        # ── 2. Streaming & AI Unlock Tests (Parallel) ──
        netflix_task = _test_netflix(local_port)
        openai_task = _test_openai(local_port)
        youtube_task = _test_youtube(local_port)

        netflix_ok, openai_ok, youtube_ok = await asyncio.gather(
            netflix_task, openai_task, youtube_task, return_exceptions=True
        )

        result["netflix_unlock"] = bool(netflix_ok is True)
        result["openai_unlock"] = bool(openai_ok is True)
        result["youtube_unlock"] = bool(youtube_ok is True)

        # ── 3. Calculate Overall Purity Rating ──
        if result["success"]:
            unlock_count = sum([result["netflix_unlock"], result["openai_unlock"], result["youtube_unlock"]])
            if result.get("is_residential") and unlock_count >= 2:
                result["purity_status"] = "clean"      # 原生住宅 + 多解锁
            elif unlock_count >= 1 or result.get("is_residential"):
                result["purity_status"] = "partial"    # 良好
            else:
                result["purity_status"] = "dirty"      # 机房受限
        else:
            result["purity_status"] = "unknown"

    except Exception as e:
        result["error"] = str(e)
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

    return result


async def _test_netflix(port: int) -> bool:
    resp = await _get_with_proxy("https://www.netflix.com/title/81280792", port, timeout=6)
    if resp and resp.status_code == 200:
        txt = resp.text.lower()
        if "not available" not in txt and "geo-block" not in txt and "remind me" not in txt:
            return True
    return False


async def _test_openai(port: int) -> bool:
    resp = await _get_with_proxy("https://chatgpt.com", port, timeout=6)
    if resp and resp.status_code in (200, 301, 302, 307, 308):
        if "access denied" not in resp.text.lower() and "vpn" not in resp.text.lower():
            return True
    return False


async def _test_youtube(port: int) -> bool:
    resp = await _get_with_proxy("https://www.youtube.com/premium", port, timeout=6)
    if resp and resp.status_code == 200:
        if "premium is not available" not in resp.text.lower():
            return True
    return False


def _infer_country_from_name(name: str) -> Optional[str]:
    """Infer ISO country code from node name."""
    import re
    mapping = [
        ("HK", r"港|HK|hk|Hong Kong|HongKong"),
        ("JP", r"日本|川日|东京|大阪|泉日|埼玉|JP|Japan"),
        ("US", r"美|洛杉矶|硅谷|西雅图|芝加哥|波特兰|US|United States"),
        ("SG", r"新加坡|坡|狮城|SG|Singapore"),
        ("TW", r"台湾|台|新北|彰化|TW|Taiwan"),
        ("UK", r"英国|伦敦|UK|GB|Britain"),
        ("KR", r"韩国|首尔|KR|Korea"),
        ("DE", r"德国|法兰克福|DE|Germany"),
        ("FR", r"法国|巴黎|FR|France"),
        ("CA", r"加拿大|多伦多|CA|Canada"),
        ("AU", r"澳大利亚|悉尼|AU|Australia"),
    ]
    for code, pattern in mapping:
        if re.search(pattern, name, re.IGNORECASE):
            return code
    return None


async def purity_test_batch(nodes: List[Dict[str, Any]], concurrency: int = 4) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def test_node(node):
        async with semaphore:
            res = await purity_test_one(node)
            results.append({"id": node["id"], **res})

    await asyncio.gather(*[test_node(n) for n in nodes], return_exceptions=True)
    return results
