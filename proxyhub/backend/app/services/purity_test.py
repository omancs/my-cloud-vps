"""
Purity & Unlock test service V3 (Mihomo Driven):
  - Fast, resident routing through Mihomo selector (zero temporary subprocesses)
  - Multi-source GeoIP & ISP type detection (Residential vs Datacenter)
  - Streaming unlock detection (Netflix, YouTube Premium)
  - AI services detection (OpenAI / ChatGPT)
"""
import asyncio
import re
import httpx
from typing import Dict, Any, List, Optional

from app.services.mihomo_service import (
    is_mihomo_installed, ensure_mihomo_running, load_proxies_to_mihomo,
    select_proxy, MIXED_PORT
)
from app.services.speed_test import _reset_progress, _update_progress_step, _finish_progress


def _infer_country_from_name(name: str) -> str:
    n = (name or "").lower()
    if any(k in n for k in ("hk", "hongkong", "hong kong", "香港")):
        return "HK"
    if any(k in n for k in ("jp", "japan", "tokyo", "osaka", "日本", "东京")):
        return "JP"
    if any(k in n for k in ("us", "united states", "america", "美国", "洛杉矶", "硅谷")):
        return "US"
    if any(k in n for k in ("sg", "singapore", "新加坡", "狮城")):
        return "SG"
    if any(k in n for k in ("tw", "taiwan", "台湾", "台北")):
        return "TW"
    if any(k in n for k in ("kr", "korea", "seoul", "韩国", "首尔")):
        return "KR"
    if any(k in n for k in ("uk", "gb", "britain", "london", "英国", "伦敦")):
        return "GB"
    if any(k in n for k in ("de", "germany", "frankfurt", "德国", "法兰克福")):
        return "DE"
    return "UNKNOWN"


async def purity_test_batch(nodes: List[Dict[str, Any]], concurrency: int = 3) -> List[Dict[str, Any]]:
    """Batch test IP purity & streaming unlock through resident Mihomo proxy."""
    _reset_progress("纯净度与流媒体检测", len(nodes))
    results = []

    use_mihomo = is_mihomo_installed() and await ensure_mihomo_running()

    if not use_mihomo:
        # Fallback: simple name inference
        for n in nodes:
            c = _infer_country_from_name(n.get("name", ""))
            _update_progress_step(True)
            results.append({
                "id": n["id"],
                "success": True,
                "ip_country": c,
                "ip_address": n.get("address"),
                "ip_org": "Unknown (Mihomo not running)",
                "is_residential": False,
                "netflix_unlock": False,
                "openai_unlock": False,
                "youtube_unlock": False,
                "purity_status": "datacenter",
            })
        _finish_progress("纯净度检测完成（未启动Mihomo，仅根据名称推断）")
        return results

    loaded_names = await load_proxies_to_mihomo(nodes)
    node_name_map = {n["id"]: loaded_names[i] for i, n in enumerate(nodes) if i < len(loaded_names)}

    semaphore = asyncio.Semaphore(concurrency)

    async def test_node_purity(node: Dict[str, Any]):
        async with semaphore:
            res: Dict[str, Any] = {
                "id": node["id"],
                "success": False,
                "ip_address": None,
                "ip_country": None,
                "ip_org": None,
                "is_residential": None,
                "netflix_unlock": False,
                "openai_unlock": False,
                "youtube_unlock": False,
                "purity_status": "unknown",
            }
            pname = node_name_map.get(node["id"])
            if not pname:
                _update_progress_step(False)
                results.append(res)
                return

            # Switch selector to this proxy
            await select_proxy(pname)
            proxies = {
                "http://": f"http://127.0.0.1:{MIXED_PORT}",
                "https://": f"http://127.0.0.1:{MIXED_PORT}",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            }

            try:
                async with httpx.AsyncClient(proxies=proxies, timeout=6.0, follow_redirects=True, headers=headers) as client:
                    # 1. IP & ISP Detection (api.ip.sb or ip-api.com)
                    try:
                        ip_resp = await client.get("https://api.ip.sb/geoip")
                        if ip_resp.status_code == 200:
                            data = ip_resp.json()
                            res["ip_address"] = data.get("ip")
                            res["ip_country"] = data.get("country_code")
                            res["ip_org"] = data.get("organization") or data.get("isp")
                            org_lower = (res["ip_org"] or "").lower()
                            is_datacenter = any(k in org_lower for k in (
                                "cloud", "hosting", "datacenter", "data center", "digitalocean",
                                "linode", "vultr", "aws", "google", "microsoft", "oracle", "ovh",
                                "alibaba", "tencent", "choopa", "mserver", "leaseweb"
                            ))
                            res["is_residential"] = not is_datacenter
                            res["purity_status"] = "residential" if res["is_residential"] else "datacenter"
                            res["success"] = True
                    except Exception:
                        pass

                    # Fallback to ip-api
                    if not res["ip_address"]:
                        try:
                            ip2 = await client.get("http://ip-api.com/json")
                            if ip2.status_code == 200:
                                d2 = ip2.json()
                                res["ip_address"] = d2.get("query")
                                res["ip_country"] = d2.get("countryCode")
                                res["ip_org"] = d2.get("org") or d2.get("isp")
                                res["is_residential"] = False
                                res["purity_status"] = "datacenter"
                                res["success"] = True
                        except Exception:
                            pass

                    # Fallback country from name
                    if not res["ip_country"]:
                        res["ip_country"] = _infer_country_from_name(node.get("name", ""))

                    # 2. OpenAI / ChatGPT Unlock Check
                    try:
                        ai_resp = await client.get("https://chatgpt.com", timeout=4.0)
                        res["openai_unlock"] = (ai_resp.status_code in (200, 307) and "unsupported" not in ai_resp.text.lower())
                    except Exception:
                        pass

                    # 3. Netflix Check
                    try:
                        nf_resp = await client.get("https://www.netflix.com/title/81280792", timeout=4.0)
                        res["netflix_unlock"] = (nf_resp.status_code == 200)
                    except Exception:
                        pass

                    # 4. YouTube Premium Check
                    try:
                        yt_resp = await client.get("https://www.youtube.com/premium", timeout=4.0)
                        res["youtube_unlock"] = (yt_resp.status_code == 200 and "not available" not in yt_resp.text.lower())
                    except Exception:
                        pass

            except Exception:
                pass

            _update_progress_step(res["success"])
            results.append(res)

    await asyncio.gather(*[test_node_purity(n) for n in nodes], return_exceptions=True)
    _finish_progress(f"纯净度与流媒体检测完成：成功 {TEST_PROGRESS['alive']}/{TEST_PROGRESS['total']}")
    return results
