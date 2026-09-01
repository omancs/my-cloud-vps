"""
Mihomo (Clash Meta) Daemon & REST API Client Service:
- Manages single resident Mihomo daemon process (low memory ~35MB, rock solid)
- Dynamic proxy reload via REST API (127.0.0.1:9090)
- High-concurrency native delay testing via /proxies/{name}/delay
- Mixed-port (127.0.0.1:7890) traffic routing for unlock & purity tests
"""
import os
import shutil
import asyncio
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
import yaml
from app.services.exporter import _node_to_clash_proxy

MIHOMO_DIR = os.getenv("MIHOMO_DIR", "/app/data/mihomo")
MIHOMO_BIN = os.getenv("MIHOMO_BIN", "/usr/local/bin/mihomo")
API_BASE = "http://127.0.0.1:9090"
MIXED_PORT = 7890

_process = None
_lock = asyncio.Lock()


def is_mihomo_installed() -> bool:
    """Check if mihomo binary is available."""
    return os.path.exists(MIHOMO_BIN) or shutil.which("mihomo") is not None


def _get_bin_path() -> str:
    if os.path.exists(MIHOMO_BIN):
        return MIHOMO_BIN
    w = shutil.which("mihomo")
    if w:
        return w
    return "mihomo"


async def ensure_mihomo_running():
    """Ensure background Mihomo daemon is running and API is responding."""
    global _process
    if not is_mihomo_installed():
        return False

    async with _lock:
        # Check if already responding
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(f"{API_BASE}/version")
                if res.status_code == 200:
                    return True
        except Exception:
            pass

        # Prepare config directory
        Path(MIHOMO_DIR).mkdir(parents=True, exist_ok=True)
        config_path = os.path.join(MIHOMO_DIR, "config.yaml")

        if not os.path.exists(config_path):
            base_config = {
                "mixed-port": MIXED_PORT,
                "allow-lan": False,
                "mode": "rule",
                "log-level": "error",
                "external-controller": "127.0.0.1:9090",
                "secret": "",
                "dns": {
                    "enable": True,
                    "nameserver": ["1.1.1.1", "8.8.8.8"],
                },
                "proxies": [],
                "proxy-groups": [
                    {
                        "name": "TEST_SELECTOR",
                        "type": "select",
                        "proxies": ["DIRECT"],
                    }
                ],
                "rules": ["MATCH,TEST_SELECTOR"],
            }
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(base_config, f, allow_unicode=True)

        # Launch process
        bin_path = _get_bin_path()
        try:
            _process = await asyncio.create_subprocess_exec(
                bin_path, "-d", MIHOMO_DIR,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Wait for API ready
            for _ in range(15):
                await asyncio.sleep(0.3)
                try:
                    async with httpx.AsyncClient(timeout=0.8) as client:
                        r = await client.get(f"{API_BASE}/version")
                        if r.status_code == 200:
                            print(f"[Mihomo] Daemon started successfully (PID {_process.pid})")
                            return True
                except Exception:
                    continue
        except Exception as e:
            print(f"[Mihomo] Failed to launch mihomo: {e}")
            return False

    return False


async def load_proxies_to_mihomo(nodes: List[Dict[str, Any]]) -> List[str]:
    """Convert nodes to Clash proxies, reload Mihomo config, and return loaded proxy names."""
    if not await ensure_mihomo_running():
        return []

    clash_proxies = []
    proxy_names = []
    seen = set()

    for n in nodes:
        cp = _node_to_clash_proxy(n)
        if cp:
            # Ensure unique proxy name for Mihomo
            orig_name = str(cp["name"])
            name = orig_name
            idx = 1
            while name in seen:
                name = f"{orig_name} ({idx})"
                idx += 1
            cp["name"] = name
            seen.add(name)
            clash_proxies.append(cp)
            proxy_names.append(name)

    config_path = os.path.join(MIHOMO_DIR, "config.yaml")
    full_config = {
        "mixed-port": MIXED_PORT,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "error",
        "external-controller": "127.0.0.1:9090",
        "secret": "",
        "dns": {
            "enable": True,
            "nameserver": ["1.1.1.1", "8.8.8.8"],
        },
        "proxies": clash_proxies,
        "proxy-groups": [
            {
                "name": "TEST_SELECTOR",
                "type": "select",
                "proxies": proxy_names if proxy_names else ["DIRECT"],
            }
        ],
        "rules": ["MATCH,TEST_SELECTOR"],
    }

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(full_config, f, allow_unicode=True)

        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.put(
                f"{API_BASE}/configs?force=true",
                json={"path": config_path},
            )
            if res.status_code in (200, 204):
                return proxy_names
    except Exception as e:
        print(f"[Mihomo] Config reload error: {e}")

    return []


async def test_single_proxy_delay(
    proxy_name: str,
    test_url: str = "http://cp.cloudflare.com/generate_204",
    timeout: int = 3500,
) -> Optional[int]:
    """Test delay for a single proxy using Mihomo's native REST API."""
    encoded_name = urllib.parse.quote(proxy_name)
    url = f"{API_BASE}/proxies/{encoded_name}/delay"
    params = {"url": test_url, "timeout": timeout}

    try:
        async with httpx.AsyncClient(timeout=(timeout / 1000.0) + 1.0) as client:
            res = await client.get(url, params=params)
            if res.status_code == 200:
                data = res.json()
                return int(data.get("delay", 0))
    except Exception:
        pass
    return None


async def select_proxy(proxy_name: str) -> bool:
    """Switch TEST_SELECTOR group to target proxy for mixed-port routing."""
    url = f"{API_BASE}/proxies/TEST_SELECTOR"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.put(url, json={"name": proxy_name})
            return res.status_code in (200, 204)
    except Exception:
        return False
