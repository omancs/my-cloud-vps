"""
Subscription parser: supports Base64-encoded V2Ray subscription lists,
Clash YAML format, multi-layer Base64, mixed-text inputs.
Parses vmess/vless/ss/trojan/hy2 URIs.
"""
import base64
import json
import re
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple

import httpx
import yaml


async def fetch_subscription(url: str, timeout: int = 15) -> Tuple[str, Optional[str]]:
    """
    Fetch raw subscription content from URL.
    Returns (content_text, auto_detected_name).
    auto_detected_name priority:
      1. Content-Disposition filename
      2. subscription-userinfo profile-name
      3. URL domain name
    """
    headers = {
        "User-Agent": "ClashForWindows/0.20.39",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

    # Auto-detect name
    auto_name: Optional[str] = None

    # 1. Content-Disposition: attachment; filename="xxx.yaml"
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename[*]?=["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
    if m:
        raw = m.group(1).strip().strip('"\'')
        # Strip extension
        auto_name = re.sub(r'\.(yaml|yml|txt|json)$', '', raw, flags=re.IGNORECASE) or None

    # 2. subscription-userinfo (some providers send profile-name header)
    if not auto_name:
        profile = resp.headers.get("profile-title", "") or resp.headers.get("profile-name", "")
        if profile:
            try:
                # May be base64-encoded
                auto_name = base64.b64decode(profile + "==").decode("utf-8").strip() or None
            except Exception:
                auto_name = profile.strip() or None

    # 3. Derive from URL domain
    if not auto_name:
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ""
            # Take second-level domain: api.example.com → example
            parts = host.split(".")
            if len(parts) >= 2:
                auto_name = parts[-2]
            else:
                auto_name = host or None
        except Exception:
            auto_name = None

    return resp.text, auto_name



def _try_base64_decode(text: str) -> Optional[str]:
    """Try to base64-decode, return None if not valid base64."""
    try:
        # Add padding if needed
        padded = text + "=" * (-len(text) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        return decoded
    except Exception:
        return None


def parse_vmess(uri: str) -> Optional[Dict[str, Any]]:
    """Parse vmess://... URI."""
    try:
        b64 = uri[len("vmess://"):]
        padded = b64 + "=" * (-len(b64) % 4)
        data = json.loads(base64.b64decode(padded).decode("utf-8"))
        return {
            "protocol": "vmess",
            "name": data.get("ps", data.get("add", "Unknown")),
            "address": data.get("add", ""),
            "port": int(data.get("port", 0)),
            "extra": {
                "uuid": data.get("id", ""),
                "alterId": data.get("aid", 0),
                "network": data.get("net", "tcp"),
                "tls": data.get("tls", ""),
                "path": data.get("path", ""),
                "host": data.get("host", ""),
                "sni": data.get("sni", ""),
            },
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_vless(uri: str) -> Optional[Dict[str, Any]]:
    """Parse vless://uuid@host:port?params#name"""
    try:
        without_scheme = uri[len("vless://"):]
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name)
        else:
            name = "vless"
        uuid, rest = without_scheme.split("@", 1)
        if "?" in rest:
            host_port, params_str = rest.split("?", 1)
        else:
            host_port, params_str = rest, ""
        host, port = host_port.rsplit(":", 1)
        params = dict(urllib.parse.parse_qsl(params_str))
        return {
            "protocol": "vless",
            "name": name,
            "address": host,
            "port": int(port),
            "extra": {"uuid": uuid, **params},
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_ss(uri: str) -> Optional[Dict[str, Any]]:
    """Parse ss://... URI (SIP002 and legacy)."""
    try:
        without_scheme = uri[len("ss://"):]
        name = ""
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name)
        # SIP002: ss://BASE64(method:password)@host:port
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
            # Legacy: ss://BASE64(method:password@host:port)
            padded = without_scheme + "=" * (-len(without_scheme) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
            method_pass, hostport = decoded.rsplit("@", 1)
            method, password = method_pass.split(":", 1)
            host, port = hostport.rsplit(":", 1)
        return {
            "protocol": "ss",
            "name": name or host,
            "address": host,
            "port": int(port),
            "extra": {"method": method, "password": password},
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_trojan(uri: str) -> Optional[Dict[str, Any]]:
    """Parse trojan://password@host:port?params#name"""
    try:
        without_scheme = uri[len("trojan://"):]
        name = ""
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name)
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
            "address": host,
            "port": int(port),
            "extra": {"password": password, **params},
            "raw_config": uri,
        }
    except Exception:
        return None


def parse_hy2(uri: str) -> Optional[Dict[str, Any]]:
    """Parse hy2://password@host:port?params#name (Hysteria2)."""
    try:
        without_scheme = uri[len("hy2://"):]
        name = ""
        if "#" in without_scheme:
            without_scheme, name = without_scheme.rsplit("#", 1)
            name = urllib.parse.unquote(name)
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
            "address": host,
            "port": int(port),
            "extra": {"auth": auth, **params},
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
    """Dispatch URI to the appropriate parser."""
    uri = uri.strip()
    for prefix, parser in PARSERS.items():
        if uri.lower().startswith(prefix):
            return parser(uri)
    return None


def parse_clash_yaml(content: str) -> List[Dict[str, Any]]:
    """Parse Clash YAML proxies section into node dicts."""
    nodes = []
    try:
        data = yaml.safe_load(content)
        proxies = data.get("proxies", []) or []
        for p in proxies:
            ptype = p.get("type", "").lower()
            if ptype not in ("vmess", "vless", "ss", "trojan", "hysteria2", "hy2"):
                continue
            node = {
                "protocol": "hy2" if ptype in ("hysteria2", "hy2") else ptype,
                "name": p.get("name", p.get("server", "Unknown")),
                "address": p.get("server", ""),
                "port": int(p.get("port", 0)),
                "extra": {k: v for k, v in p.items()
                          if k not in ("name", "server", "port", "type")},
                "raw_config": None,
            }
            nodes.append(node)
    except Exception:
        pass
    return nodes


def _extract_uris_from_text(text: str) -> List[str]:
    """Extract all proxy URIs from any text (handles comment lines, blank lines)."""
    uris = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        node = parse_uri(line)
        if node:
            uris.append(line)
    return uris


def _multi_layer_base64_decode(text: str) -> Optional[str]:
    """
    Try up to 3 rounds of Base64 decoding.
    Handles: plain Base64, URL-safe Base64, padded/unpadded variants.
    Returns the first decoded string that contains proxy URIs.
    """
    candidate = text.strip()
    # Remove potential data: URI prefix
    candidate = re.sub(r'^data:[^;]+;base64,', '', candidate, flags=re.IGNORECASE)

    for _ in range(3):
        # Try standard and URL-safe variants
        for variant in [candidate, candidate.replace("-", "+").replace("_", "/")]:
            padded = variant + "=" * (-len(variant) % 4)
            try:
                decoded = base64.b64decode(padded).decode("utf-8")
                # Check if it contains proxy URIs → if yes, return it
                if any(decoded.lstrip().startswith(p) for p in
                       ("vmess://", "vless://", "ss://", "trojan://", "hy2://",
                        "hysteria2://", "proxies:", "socks5://")):
                    return decoded
                # Continue decoding if result looks like base64
                if re.match(r'^[A-Za-z0-9+/\-_=\n\r]+$', decoded.strip()):
                    candidate = decoded.strip()
                    break
            except Exception:
                continue
    return None


def parse_subscription_content(content: str) -> List[Dict[str, Any]]:
    """
    Auto-detect subscription format and parse all nodes.
    Supports:
    1. Clash YAML (proxies: key)
    2. Plain-text list of proxy URIs
    3. Single-layer Base64-encoded list
    4. Multi-layer / URL-safe Base64
    5. Mixed text with embedded URIs and Base64 blocks
    """
    nodes = []
    stripped = content.strip()

    # 1. Clash YAML
    if stripped.startswith("proxies:") or "\nproxies:" in stripped:
        return parse_clash_yaml(stripped)

    # 2. Try multi-layer base64 on the whole content
    decoded = _multi_layer_base64_decode(stripped)
    if decoded:
        if decoded.strip().startswith("proxies:") or "\nproxies:" in decoded:
            return parse_clash_yaml(decoded)
        lines_source = decoded
    else:
        lines_source = stripped

    # 3. Parse line-by-line, also trying Base64 per-line for mixed inputs
    for line in lines_source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Direct URI
        node = parse_uri(line)
        if node:
            nodes.append(node)
            continue
        # Try this line as standalone base64 block
        if len(line) > 20 and re.match(r'^[A-Za-z0-9+/\-_=]+$', line):
            inner = _multi_layer_base64_decode(line)
            if inner:
                for sub_line in inner.splitlines():
                    sub_node = parse_uri(sub_line.strip())
                    if sub_node:
                        nodes.append(sub_node)

    return nodes


def parse_text_or_base64(text: str) -> List[Dict[str, Any]]:
    """
    Public API: parse arbitrary user-pasted text (clipboard input).
    Handles all formats: URIs, Base64, mixed, Clash YAML.
    """
    return parse_subscription_content(text)
