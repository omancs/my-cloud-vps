"""
Subscription & Node parser V3:
  - Smart deduplication (Protocol + Address + Port + Auth/UUID/Password)
  - NekoBox-style universal parser (URLs, Base64, Clash YAML, single/multi URIs, mixed text)
  - Auto subscription naming & metadata extraction
"""
import base64
import json
import re
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple

import httpx
import yaml


async def fetch_subscription(url: str, timeout: int = 15) -> Tuple[str, Optional[str]]:
    """Fetch raw subscription content from URL and auto-detect name."""
    headers = {
        "User-Agent": "ClashForWindows/0.20.39",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

    auto_name: Optional[str] = None

    # 1. Content-Disposition: attachment; filename="xxx.yaml"
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename[*]?=["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
    if m:
        raw = m.group(1).strip().strip('"\'')
        auto_name = re.sub(r'\.(yaml|yml|txt|json)$', '', raw, flags=re.IGNORECASE) or None

    # 2. subscription-userinfo profile-name
    if not auto_name:
        profile = resp.headers.get("profile-title", "") or resp.headers.get("profile-name", "")
        if profile:
            try:
                auto_name = base64.b64decode(profile + "==").decode("utf-8").strip() or None
            except Exception:
                auto_name = profile.strip() or None

    # 3. Derive from URL domain
    if not auto_name:
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ""
            parts = host.split(".")
            if len(parts) >= 2:
                auto_name = parts[-2].capitalize()
            else:
                auto_name = host or None
        except Exception:
            auto_name = None

    return resp.text, auto_name


def parse_vmess(uri: str) -> Optional[Dict[str, Any]]:
    """Parse vmess://... URI."""
    try:
        b64 = uri[len("vmess://"):]
        padded = b64 + "=" * (-len(b64) % 4)
        data = json.loads(base64.b64decode(padded).decode("utf-8"))
        return {
            "protocol": "vmess",
            "name": str(data.get("ps", data.get("add", "VMess Node"))).strip(),
            "address": str(data.get("add", "")).strip(),
            "port": int(data.get("port", 0)),
            "extra": {
                "uuid": str(data.get("id", "")).strip(),
                "alterId": int(data.get("aid", 0)),
                "network": str(data.get("net", "tcp")).strip(),
                "tls": str(data.get("tls", "")).strip(),
                "path": str(data.get("path", "")).strip(),
                "host": str(data.get("host", "")).strip(),
                "sni": str(data.get("sni", "")).strip(),
            },
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_vless(uri: str) -> Optional[Dict[str, Any]]:
    """Parse vless://uuid@host:port?params#name"""
    try:
        without_scheme = uri[len("vless://"):]
        name = "VLESS Node"
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name).strip()
        uuid, rest = without_scheme.split("@", 1)
        if "?" in rest:
            host_port, params_str = rest.split("?", 1)
        else:
            host_port, params_str = rest, ""
        host, port = host_port.rsplit(":", 1)
        params = dict(urllib.parse.parse_qsl(params_str))
        return {
            "protocol": "vless",
            "name": name or host,
            "address": host.strip(),
            "port": int(port),
            "extra": {"uuid": uuid.strip(), **params},
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_ss(uri: str) -> Optional[Dict[str, Any]]:
    """Parse ss://... URI (SIP002 and legacy)."""
    try:
        without_scheme = uri[len("ss://"):]
        name = "Shadowsocks Node"
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name).strip()
        if "@" in without_scheme:
            userinfo, hostinfo = without_scheme.split("@", 1)
            try:
                padded = userinfo + "=" * (-len(userinfo) % 4)
                decoded = base64.b64decode(padded).decode("utf-8")
                method, password = decoded.split(":", 1)
            except Exception:
                method, password = userinfo.split(":", 1)
            host, port = hostinfo.rsplit(":", 1)
        else:
            padded = without_scheme + "=" * (-len(without_scheme) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
            method_pass, hostport = decoded.rsplit("@", 1)
            method, password = method_pass.split(":", 1)
            host, port = hostport.rsplit(":", 1)
        return {
            "protocol": "ss",
            "name": name or host,
            "address": host.strip(),
            "port": int(port),
            "extra": {"method": method.strip(), "password": password.strip()},
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_trojan(uri: str) -> Optional[Dict[str, Any]]:
    """Parse trojan://password@host:port?params#name"""
    try:
        without_scheme = uri[len("trojan://"):]
        name = "Trojan Node"
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name).strip()
        password, rest = without_scheme.split("@", 1)
        if "?" in rest:
            host_port, params_str = rest.split("?", 1)
        else:
            host_port, params_str = rest, ""
        host, port = host_port.rsplit(":", 1)
        params = dict(urllib.parse.parse_qsl(params_str))
        return {
            "protocol": "trojan",
            "name": name or host,
            "address": host.strip(),
            "port": int(port),
            "extra": {"password": password.strip(), **params},
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_hy2(uri: str) -> Optional[Dict[str, Any]]:
    """Parse hy2://password@host:port?params#name (Hysteria 2)."""
    try:
        prefix = "hy2://" if uri.startswith("hy2://") else "hysteria2://"
        without_scheme = uri[len(prefix):]
        name = "Hysteria 2 Node"
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name).strip()
        auth, rest = without_scheme.split("@", 1)
        if "?" in rest:
            host_port, params_str = rest.split("?", 1)
        else:
            host_port, params_str = rest, ""
        host, port = host_port.rsplit(":", 1)
        params = dict(urllib.parse.parse_qsl(params_str))
        return {
            "protocol": "hy2",
            "name": name or host,
            "address": host.strip(),
            "port": int(port),
            "extra": {"auth": auth.strip(), **params},
            "raw_config": uri,
        }
    except Exception:
        return None


PARSERS = {
    "vmess://": parse_vmess,
    "vless://": parse_vless,
    "ss://": parse_ss,
    "trojan://": parse_trojan,
    "hy2://": parse_hy2,
    "hysteria2://": parse_hy2,
}


def parse_uri(uri: str) -> Optional[Dict[str, Any]]:
    """Dispatch URI to appropriate protocol parser."""
    uri = uri.strip()
    for prefix, parser in PARSERS.items():
        if uri.lower().startswith(prefix):
            return parser(uri)
    return None


def parse_clash_yaml(content: str) -> List[Dict[str, Any]]:
    """
    Industrial-grade Clash YAML parser:
    1. Strips BOM and replaces tabs with spaces.
    2. Handles dict with 'proxies' / 'Proxy' / 'payload', OR direct list of proxies.
    3. Extracts only the proxies block first to prevent huge rules/dns syntax errors.
    4. If PyYAML fails, uses regex block & flow-style fallback to extract nodes.
    """
    if not content or not content.strip():
        return []

    cleaned = content.lstrip('\ufeff').replace('\t', '  ')
    nodes = []

    def _convert_proxy_dict(p: dict) -> Optional[Dict[str, Any]]:
        if not isinstance(p, dict):
            return None
        ptype = str(p.get("type", "")).lower().strip()
        if ptype in ("hysteria2", "hy2"):
            proto = "hy2"
        elif ptype in ("ss", "shadowsocks"):
            proto = "ss"
        elif ptype in ("vmess", "vless", "trojan", "tuic", "wireguard", "socks5", "http", "snell"):
            proto = ptype
        else:
            return None

        name = str(p.get("name") or p.get("server") or "Clash Node").strip()
        server = str(p.get("server") or "").strip()
        try:
            port = int(p.get("port") or 0)
        except Exception:
            port = 0

        if not server or port <= 0:
            return None

        extra = {k: v for k, v in p.items() if k not in ("name", "server", "port", "type")}
        return {
            "protocol": proto,
            "name": name,
            "address": server,
            "port": port,
            "extra": extra,
            "raw_config": None,
        }

    # Strategy 1: Extract proxies block lines only
    proxy_block_lines = []
    in_proxies = False
    base_indent = 0
    for line in cleaned.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if not in_proxies:
            if lower in ("proxies:", "proxy:", "payload:") or lower.startswith("proxies:") or lower.startswith("proxy:"):
                in_proxies = True
                proxy_block_lines.append(line)
                base_indent = len(line) - len(line.lstrip())
        else:
            current_indent = len(line) - len(line.lstrip())
            if stripped and not stripped.startswith("-") and not stripped.startswith("#") and current_indent <= base_indent:
                break
            proxy_block_lines.append(line)

    if proxy_block_lines:
        try:
            proxies_yaml = "\n".join(proxy_block_lines)
            data = yaml.safe_load(proxies_yaml)
            raw_list = []
            if isinstance(data, dict):
                raw_list = data.get("proxies") or data.get("Proxy") or data.get("payload") or []
            elif isinstance(data, list):
                raw_list = data
            for p in raw_list:
                item = _convert_proxy_dict(p)
                if item:
                    nodes.append(item)
            if nodes:
                return nodes
        except Exception as e:
            print(f"[Parser] Proxies block YAML parse warning: {e}")

    # Strategy 2: Attempt full document YAML safe_load
    try:
        data = yaml.safe_load(cleaned)
        raw_list = []
        if isinstance(data, dict):
            raw_list = data.get("proxies") or data.get("Proxy") or data.get("payload") or []
        elif isinstance(data, list):
            raw_list = data
        for p in raw_list:
            item = _convert_proxy_dict(p)
            if item:
                nodes.append(item)
        if nodes:
            return nodes
    except Exception as e:
        print(f"[Parser] Full document YAML parse warning: {e}")

    # Strategy 3: Regex Flow-style: - { name: ..., server: ..., port: ..., type: ... }
    flow_pattern = re.compile(r'-\s*\{([^}]+)\}')
    for match in flow_pattern.finditer(cleaned):
        inside = match.group(1)
        p = {}
        kv_pairs = re.findall(r'(\b[a-zA-Z0-9_\-]+)\s*:\s*([^,]+(?:\(.*?\))?)', inside)
        for k, v in kv_pairs:
            val = v.strip().strip("'\"")
            if val.isdigit():
                val = int(val)
            p[k.strip()] = val
        item = _convert_proxy_dict(p)
        if item:
            nodes.append(item)

    if nodes:
        return nodes

    # Strategy 4: Regex Block-style: - name: ...\n  server: ...
    blocks = re.split(r'\n\s*-\s+', cleaned)
    for block in blocks[1:]:
        p = {}
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                val = v.strip().strip("'\"")
                if val.isdigit():
                    val = int(val)
                p[k] = val
        item = _convert_proxy_dict(p)
        if item:
            nodes.append(item)

    return nodes


def _multi_layer_base64_decode(text: str) -> Optional[str]:
    """Recursively decode up to 3 layers of Base64."""
    candidate = text.strip()
    candidate = re.sub(r'^data:[^;]+;base64,', '', candidate, flags=re.IGNORECASE)

    for _ in range(3):
        for variant in [candidate, candidate.replace("-", "+").replace("_", "/")]:
            padded = variant + "=" * (-len(variant) % 4)
            try:
                decoded = base64.b64decode(padded).decode("utf-8")
                if any(k in decoded.lower() for k in ("vmess://", "vless://", "ss://", "trojan://", "hy2://", "hysteria2://", "proxies:")):
                    return decoded
                if re.match(r'^[A-Za-z0-9+/\-_=\n\r]+$', decoded.strip()) and len(decoded.strip()) > 10:
                    candidate = decoded.strip()
                    break
            except Exception:
                continue
    return None


def deduplicate_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate nodes by (protocol, address, port, auth, name)."""
    seen = set()
    unique = []
    for n in nodes:
        addr = str(n.get("address", "")).lower().strip()
        port = str(n.get("port", 0))
        proto = str(n.get("protocol", "")).lower().strip()
        name = str(n.get("name", "")).strip()
        extra = n.get("extra") or {}
        auth = str(extra.get("uuid") or extra.get("password") or extra.get("auth") or extra.get("method") or "").strip()
        
        fingerprint = f"{proto}:{addr}:{port}:{auth}:{name}"
        if fingerprint not in seen and addr and port != "0":
            seen.add(fingerprint)
            unique.append(n)
    return unique


def parse_subscription_content(content: str) -> List[Dict[str, Any]]:
    """Universal parser for all subscription/node content types."""
    if not content or not content.strip():
        return []
    stripped = content.lstrip('\ufeff').strip()

    # 1. Check if content looks like Clash YAML or list of proxies
    lower = stripped.lower()
    if any(k in lower for k in ("proxies:", "proxy:", "payload:")) or stripped.startswith("- ") or stripped.startswith("-\t"):
        yaml_nodes = parse_clash_yaml(stripped)
        if yaml_nodes:
            return deduplicate_nodes(yaml_nodes)

    # 2. Base64
    decoded = _multi_layer_base64_decode(stripped)
    lines_source = decoded if decoded else stripped
    lower_source = lines_source.lower()
    if any(k in lower_source for k in ("proxies:", "proxy:", "payload:")) or lines_source.strip().startswith("- "):
        yaml_nodes = parse_clash_yaml(lines_source)
        if yaml_nodes:
            return deduplicate_nodes(yaml_nodes)

    # 3. Line-by-line parsing with per-line Base64 fallback
    nodes = []
    for line in lines_source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        node = parse_uri(line)
        if node:
            nodes.append(node)
            continue
        if len(line) > 20 and re.match(r'^[A-Za-z0-9+/\-_=]+$', line):
            inner = _multi_layer_base64_decode(line)
            if inner:
                for sub_line in inner.splitlines():
                    sub_node = parse_uri(sub_line.strip())
                    if sub_node:
                        nodes.append(sub_node)

    return deduplicate_nodes(nodes)


def parse_text_or_base64(text: str) -> List[Dict[str, Any]]:
    """Public helper for clipboard / bulk text parsing."""
    return parse_subscription_content(text)
