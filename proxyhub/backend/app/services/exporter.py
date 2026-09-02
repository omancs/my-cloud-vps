"""
Export nodes to:
- Clash YAML / Mihomo (芙芙 rule-set template)
- Sing-box 1.10+ JSON (modern universal format)
- V2Ray / Base64 URI list (auto generates URI if raw_config is None)
Excludes quarantined (dead) nodes automatically.
"""
import base64
import json
import urllib.parse
from typing import List, Dict, Any, Optional
import yaml


def _is_usable(node: Dict[str, Any]) -> bool:
    """Filter out explicitly quarantined dead nodes."""
    if node.get("is_quarantined"):
        return False
    return True


def _node_to_clash_proxy(node: Dict[str, Any]) -> Dict[str, Any] | None:
    if not _is_usable(node):
        return None

    protocol = str(node.get("protocol", "")).lower().strip()
    extra = dict(node.get("extra") or {})
    name = str(node.get("name") or "Proxy Node").strip()
    address = str(node.get("address") or "").strip()
    try:
        port = int(node.get("port") or 0)
    except Exception:
        port = 0

    if not address or port <= 0:
        return None

    # Note: extra["type"] is the TRANSPORT type (tcp/ws/grpc), NOT the proxy protocol.
    # Always use the explicit protocol-based conversion below.

    if protocol == "vmess":
        p = {
            "name": name, "type": "vmess", "server": address, "port": port,
            "uuid": str(extra.get("uuid", "")).strip(),
            "alterId": int(extra.get("alterId", 0)),
            "cipher": extra.get("security", extra.get("cipher", "auto")),
            "network": extra.get("network", extra.get("net", "tcp")),
            "tls": extra.get("tls") in (True, "tls", "1"),
            "udp": True,
        }
        sni = extra.get("sni") or extra.get("host") or ""
        if sni:
            p["servername"] = sni
        net_type = str(p["network"]).lower()
        if net_type == "ws":
            p["ws-opts"] = {"path": extra.get("path", "/"), "headers": {"Host": extra.get("host", sni)}}
        elif net_type == "grpc":
            p["grpc-opts"] = {"grpc-service-name": extra.get("serviceName", extra.get("path", ""))}
        return p

    elif protocol == "vless":
        flow = str(extra.get("flow", "")).strip()
        sec = str(extra.get("security", "")).strip()
        p = {
            "name": name, "type": "vless", "server": address, "port": port,
            "uuid": str(extra.get("uuid", "")).strip(),
            "network": extra.get("type", extra.get("network", "tcp")),
            "tls": sec in ("tls", "reality") or extra.get("tls") in (True, "tls", "1"),
            "udp": True,
        }
        sni = extra.get("sni") or extra.get("host") or ""
        if sni:
            p["servername"] = sni
            p["client-fingerprint"] = extra.get("fp", "chrome")
        if sec == "reality" or "pbk" in extra:
            p["reality-opts"] = {
                "public-key": extra.get("pbk", ""),
                "short-id": extra.get("sid", ""),
            }
            p["client-fingerprint"] = extra.get("fp", "chrome")
            p["flow"] = flow or "xtls-rprx-vision"
        elif flow:
            p["flow"] = flow
        return p

    elif protocol in ("ss", "shadowsocks"):
        return {
            "name": name, "type": "ss", "server": address, "port": port,
            "cipher": extra.get("method", extra.get("cipher", "aes-256-gcm")),
            "password": str(extra.get("password", "")),
            "udp": True,
        }

    elif protocol == "trojan":
        return {
            "name": name, "type": "trojan", "server": address, "port": port,
            "password": str(extra.get("password", "")),
            "sni": extra.get("sni", address),
            "skip-cert-verify": extra.get("insecure") in (True, "1", "true"),
            "network": extra.get("type", extra.get("network", "tcp")),
            "udp": True,
        }

    elif protocol in ("hy2", "hysteria2"):
        return {
            "name": name, "type": "hysteria2", "server": address, "port": port,
            "password": str(extra.get("auth", extra.get("password", ""))),
            "sni": extra.get("sni", ""),
            "skip-cert-verify": extra.get("insecure") in (True, "1", "true"),
            "udp": True,
        }

    return None


def _node_to_singbox_outbound(node: Dict[str, Any]) -> Dict[str, Any] | None:
    if not _is_usable(node):
        return None

    protocol = str(node.get("protocol", "")).lower().strip()
    extra = dict(node.get("extra") or {})
    name = str(node.get("name") or "Node").strip()
    address = str(node.get("address") or "").strip()
    try:
        port = int(node.get("port") or 0)
    except Exception:
        port = 0

    if not address or port <= 0:
        return None

    if protocol == "vless":
        sec = str(extra.get("security", "")).strip()
        ob = {
            "type": "vless",
            "tag": name,
            "server": address,
            "server_port": port,
            "uuid": str(extra.get("uuid", "")).strip(),
            "flow": extra.get("flow") or ("xtls-rprx-vision" if sec == "reality" or "pbk" in extra else ""),
        }
        if not ob["flow"]:
            del ob["flow"]

        if sec == "reality" or "pbk" in extra:
            ob["tls"] = {
                "enabled": True,
                "server_name": extra.get("sni", address),
                "utls": {"enabled": True, "fingerprint": extra.get("fp", "chrome")},
                "reality": {
                    "enabled": True,
                    "public_key": extra.get("pbk", ""),
                    "short_id": extra.get("sid", ""),
                },
            }
        elif sec == "tls" or extra.get("tls"):
            ob["tls"] = {
                "enabled": True,
                "server_name": extra.get("sni", address),
                "utls": {"enabled": True, "fingerprint": extra.get("fp", "chrome")},
            }
        return ob

    elif protocol == "vmess":
        return {
            "type": "vmess",
            "tag": name,
            "server": address,
            "server_port": port,
            "uuid": str(extra.get("uuid", "")).strip(),
            "security": "auto",
            "alter_id": int(extra.get("alterId", 0)),
            "tls": {
                "enabled": extra.get("tls") in (True, "tls", "1"),
                "server_name": extra.get("sni", address),
            },
        }

    elif protocol in ("ss", "shadowsocks"):
        return {
            "type": "shadowsocks",
            "tag": name,
            "server": address,
            "server_port": port,
            "method": extra.get("method", extra.get("cipher", "aes-256-gcm")),
            "password": str(extra.get("password", "")),
        }

    elif protocol == "trojan":
        return {
            "type": "trojan",
            "tag": name,
            "server": address,
            "server_port": port,
            "password": str(extra.get("password", "")),
            "tls": {"enabled": True, "server_name": extra.get("sni", address)},
        }

    elif protocol in ("hy2", "hysteria2"):
        return {
            "type": "hysteria2",
            "tag": name,
            "server": address,
            "server_port": port,
            "password": str(extra.get("auth", extra.get("password", ""))),
            "tls": {
                "enabled": True,
                "server_name": extra.get("sni", address),
                "insecure": extra.get("insecure") in (True, "1", "true"),
            },
        }

    return None


def _node_to_uri(node: Dict[str, Any]) -> str | None:
    """Generate a standard proxy URI for a node."""
    raw = node.get("raw_config")
    if raw and isinstance(raw, str) and "://" in raw:
        return raw.strip()

    protocol = str(node.get("protocol", "")).lower().strip()
    extra = dict(node.get("extra") or {})
    name = str(node.get("name") or "Node").strip()
    address = str(node.get("address") or "").strip()
    port = int(node.get("port") or 0)
    if not address or port <= 0:
        return None

    safe_name = urllib.parse.quote(name)

    if protocol == "vless":
        uuid = extra.get("uuid", "")
        sec = extra.get("security", "none")
        flow = extra.get("flow", "")
        sni = extra.get("sni", "")
        pbk = extra.get("pbk", "")
        sid = extra.get("sid", "")
        net_type = extra.get("type", extra.get("network", "tcp"))
        params = f"type={net_type}&security={sec}"
        if sni:
            params += f"&sni={sni}"
        if flow:
            params += f"&flow={flow}"
        if pbk:
            params += f"&pbk={pbk}"
        if sid:
            params += f"&sid={sid}"
        return f"vless://{uuid}@{address}:{port}?{params}#{safe_name}"

    elif protocol == "vmess":
        v_data = {
            "v": "2",
            "ps": name,
            "add": address,
            "port": str(port),
            "id": extra.get("uuid", ""),
            "aid": str(extra.get("alterId", 0)),
            "scy": extra.get("security", "auto"),
            "net": extra.get("network", "tcp"),
            "type": "none",
            "host": extra.get("host", ""),
            "path": extra.get("path", "/"),
            "tls": "tls" if extra.get("tls") in (True, "tls", "1") else "",
            "sni": extra.get("sni", ""),
        }
        b64 = base64.b64encode(json.dumps(v_data).encode("utf-8")).decode("utf-8")
        return f"vmess://{b64}"

    elif protocol in ("ss", "shadowsocks"):
        method = extra.get("method", extra.get("cipher", "aes-256-gcm"))
        password = extra.get("password", "")
        userinfo = base64.b64encode(f"{method}:{password}".encode("utf-8")).decode("utf-8")
        return f"ss://{userinfo}@{address}:{port}#{safe_name}"

    elif protocol == "trojan":
        password = extra.get("password", "")
        sni = extra.get("sni", address)
        return f"trojan://{password}@{address}:{port}?sni={sni}#{safe_name}"

    elif protocol in ("hy2", "hysteria2"):
        password = extra.get("auth", extra.get("password", ""))
        sni = extra.get("sni", "")
        return f"hysteria2://{password}@{address}:{port}?sni={sni}&insecure=1#{safe_name}"

    return None


def export_clash(nodes: List[Dict[str, Any]]) -> str:
    """Export nodes as standard Clash YAML subscription."""
    proxies = []
    names = []
    for node in nodes:
        p = _node_to_clash_proxy(node)
        if p:
            proxies.append(p)
            names.append(p["name"])

    clash_config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "PROXY",
                "type": "select",
                "proxies": ["AUTO"] + names if names else ["DIRECT"],
            },
            {
                "name": "AUTO",
                "type": "url-test",
                "proxies": names if names else ["DIRECT"],
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": 300,
            }
        ],
        "rules": [
            "GEOIP,LAN,DIRECT",
            "GEOIP,CN,DIRECT",
            "MATCH,PROXY",
        ]
    }
    return yaml.dump(clash_config, allow_unicode=True, sort_keys=False)


def export_singbox(nodes: List[Dict[str, Any]]) -> str:
    """Export nodes as Sing-box 1.10+ JSON subscription format."""
    outbounds = []
    tags = []

    for n in nodes:
        ob = _node_to_singbox_outbound(n)
        if ob:
            outbounds.append(ob)
            tags.append(ob["tag"])

    singbox_config = {
        "version": 1,
        "log": {"level": "info"},
        "dns": {
            "servers": [
                {"tag": "dns-remote", "address": "https://1.1.1.1/dns-query", "strategy": "prefer_ipv4"},
                {"tag": "dns-direct", "address": "223.5.5.5", "strategy": "prefer_ipv4", "detour": "direct"}
            ]
        },
        "inbounds": [
            {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080}
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": "Proxy",
                "outbounds": (["Auto"] + tags) if tags else ["direct"],
            },
            {
                "type": "urltest",
                "tag": "Auto",
                "outbounds": tags if tags else ["direct"],
                "url": "http://cp.cloudflare.com/generate_204",
            },
            *outbounds,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"}
        ],
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "outbound": "dns-out"},
                {"ip_is_private": True, "outbound": "direct"},
                {"geoip": "cn", "outbound": "direct"},
                {"geosite": "cn", "outbound": "direct"}
            ],
            "final": "Proxy"
        }
    }
    return json.dumps(singbox_config, indent=2, ensure_ascii=False)


def export_v2ray(nodes: List[Dict[str, Any]]) -> str:
    """Export nodes as base64-encoded URI list (V2Ray/Xray/Shadowrocket subscription)."""
    uris = []
    for node in nodes:
        if _is_usable(node):
            uri = _node_to_uri(node)
            if uri:
                uris.append(uri)
    content = "\n".join(uris)
    return base64.b64encode(content.encode("utf-8")).decode("utf-8")
