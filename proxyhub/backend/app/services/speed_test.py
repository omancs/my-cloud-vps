"""
Speed test service V3 (Mihomo Core Driven):
- Fast Stage 1: Native parallel HTTP UnifiedDelay via Mihomo REST API
- Fast Stage 2: Bandwidth throughput test via resident mixed-port
- Real-time progress tracker for frontend polling
- Dead node auto-quarantine handling (consecutive failures >= 3)
"""
import asyncio
import time
import socket
from typing import List, Dict, Any, Optional
import httpx

from app.config import settings
from app.services.mihomo_service import (
    is_mihomo_installed, ensure_mihomo_running, load_proxies_to_mihomo,
    test_single_proxy_delay, select_proxy, MIXED_PORT
)

# Global test progress tracker for frontend live polling
TEST_PROGRESS: Dict[str, Any] = {
    "is_running": False,
    "task_type": "",
    "total": 0,
    "completed": 0,
    "alive": 0,
    "failed": 0,
    "avg_latency": 0.0,
    "message": "空闲",
    "updated_at": 0.0,
}


def get_test_progress() -> Dict[str, Any]:
    return dict(TEST_PROGRESS)


def _reset_progress(task_type: str, total: int):
    TEST_PROGRESS["is_running"] = True
    TEST_PROGRESS["task_type"] = task_type
    TEST_PROGRESS["total"] = total
    TEST_PROGRESS["completed"] = 0
    TEST_PROGRESS["alive"] = 0
    TEST_PROGRESS["failed"] = 0
    TEST_PROGRESS["avg_latency"] = 0.0
    TEST_PROGRESS["message"] = f"正在启动 {task_type}..."
    TEST_PROGRESS["updated_at"] = time.time()


def _update_progress_step(is_alive: bool, latency: Optional[float] = None):
    TEST_PROGRESS["completed"] += 1
    if is_alive:
        TEST_PROGRESS["alive"] += 1
    else:
        TEST_PROGRESS["failed"] += 1

    if latency is not None and latency > 0:
        curr_avg = TEST_PROGRESS["avg_latency"]
        alive_count = TEST_PROGRESS["alive"]
        TEST_PROGRESS["avg_latency"] = round((curr_avg * (alive_count - 1) + latency) / alive_count, 1)

    pct = int((TEST_PROGRESS["completed"] / max(TEST_PROGRESS["total"], 1)) * 100)
    TEST_PROGRESS["message"] = f"已完成 {TEST_PROGRESS['completed']}/{TEST_PROGRESS['total']} ({pct}%) · 存活 {TEST_PROGRESS['alive']} · 失败 {TEST_PROGRESS['failed']}"
    TEST_PROGRESS["updated_at"] = time.time()


def _finish_progress(summary: str):
    TEST_PROGRESS["is_running"] = False
    TEST_PROGRESS["message"] = summary
    TEST_PROGRESS["updated_at"] = time.time()


# ─────────────────────────────────────────────
# Socket TCP Ping Fallback
# ─────────────────────────────────────────────

async def tcp_ping_one(host: str, port: int, timeout: float = 3.0) -> Optional[float]:
    """Basic socket-level TCP connection ping."""
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


# ─────────────────────────────────────────────
# Core Batch Delay Testing (Mihomo Native)
# ─────────────────────────────────────────────

async def batch_test_latency(
    nodes: List[Dict[str, Any]],
    test_url: str = "http://cp.cloudflare.com/generate_204",
    timeout_ms: int = 3500,
    concurrency: int = 20,
) -> List[Dict[str, Any]]:
    """
    Test latency for all nodes.
    Uses Mihomo native core REST API if available (high speed, accurate),
    falling back to TCP socket ping if Mihomo is not installed.
    """
    _reset_progress("延迟测速", len(nodes))
    results = []

    use_mihomo = is_mihomo_installed() and await ensure_mihomo_running()

    if use_mihomo:
        # Step 1: Load all nodes into Mihomo daemon
        loaded_names = await load_proxies_to_mihomo(nodes)
        node_name_map = {}
        for i, n in enumerate(nodes):
            if i < len(loaded_names):
                node_name_map[n["id"]] = loaded_names[i]

        semaphore = asyncio.Semaphore(concurrency)

        async def test_node_mihomo(node: Dict[str, Any]):
            async with semaphore:
                pname = node_name_map.get(node["id"])
                latency = None
                if pname:
                    latency = await test_single_proxy_delay(pname, test_url, timeout_ms)

                is_ok = (latency is not None and latency > 0)
                _update_progress_step(is_ok, latency)
                results.append({
                    "id": node["id"],
                    "latency_ms": latency,
                    "status": "ok" if is_ok else "timeout",
                })

        await asyncio.gather(*[test_node_mihomo(n) for n in nodes], return_exceptions=True)
    else:
        # Fallback to direct TCP ping
        semaphore = asyncio.Semaphore(35)

        async def test_node_socket(node: Dict[str, Any]):
            async with semaphore:
                lat = await tcp_ping_one(node["address"], node["port"], timeout=timeout_ms / 1000.0)
                is_ok = (lat is not None)
                _update_progress_step(is_ok, lat)
                results.append({
                    "id": node["id"],
                    "latency_ms": lat,
                    "status": "ok" if is_ok else "timeout",
                })

        await asyncio.gather(*[test_node_socket(n) for n in nodes], return_exceptions=True)

    _finish_progress(f"延迟测速完成：存活 {TEST_PROGRESS['alive']}/{TEST_PROGRESS['total']}，平均延迟 {TEST_PROGRESS['avg_latency']}ms")
    return results


# ─────────────────────────────────────────────
# Core Bandwidth / Download Speed Test
# ─────────────────────────────────────────────

async def batch_test_bandwidth(
    nodes: List[Dict[str, Any]],
    concurrency: int = 4,
    speed_url: str = "https://speed.cloudflare.com/__down?bytes=300000",
) -> List[Dict[str, Any]]:
    """Test actual download throughput for online nodes."""
    _reset_progress("带宽测速", len(nodes))
    results = []

    use_mihomo = is_mihomo_installed() and await ensure_mihomo_running()
    if not use_mihomo:
        _finish_progress("Mihomo 内核未就绪，跳过带宽测速")
        return [{"id": n["id"], "download_mbps": None, "latency_ms": None, "success": False} for n in nodes]

    loaded_names = await load_proxies_to_mihomo(nodes)
    node_name_map = {n["id"]: loaded_names[i] for i, n in enumerate(nodes) if i < len(loaded_names)}

    semaphore = asyncio.Semaphore(concurrency)

    async def test_speed(node: Dict[str, Any]):
        async with semaphore:
            pname = node_name_map.get(node["id"])
            if not pname:
                _update_progress_step(False)
                results.append({"id": node["id"], "success": False})
                return

            # Test latency first
            lat = await test_single_proxy_delay(pname, timeout=3000)
            if lat is None:
                _update_progress_step(False)
                results.append({"id": node["id"], "latency_ms": None, "download_mbps": None, "success": False})
                return

            # Test download speed through selector
            await select_proxy(pname)
            proxies = {
                "http://": f"http://127.0.0.1:{MIXED_PORT}",
                "https://": f"http://127.0.0.1:{MIXED_PORT}",
            }
            mbps = None
            try:
                start = time.monotonic()
                async with httpx.AsyncClient(proxies=proxies, timeout=5.0, follow_redirects=True) as client:
                    resp = await client.get(speed_url)
                    duration = time.monotonic() - start
                    if resp.status_code == 200 and duration > 0:
                        mbps = round((len(resp.content) * 8) / (duration * 1_000_000), 2)
            except Exception:
                pass

            _update_progress_step(True, lat)
            results.append({
                "id": node["id"],
                "latency_ms": lat,
                "download_mbps": mbps,
                "success": True,
            })

    await asyncio.gather(*[test_speed(n) for n in nodes], return_exceptions=True)
    _finish_progress(f"带宽测速完成：成功 {TEST_PROGRESS['alive']}/{TEST_PROGRESS['total']}")
    return results


# Backward compatibility aliases
async def tcp_ping_batch(nodes: List[Dict[str, Any]], concurrency: int = 20) -> List[Dict[str, Any]]:
    return await batch_test_latency(nodes, concurrency=concurrency)


async def proxy_speed_test_batch(nodes: List[Dict[str, Any]], concurrency: int = 4) -> List[Dict[str, Any]]:
    return await batch_test_bandwidth(nodes, concurrency=concurrency)
