"""
Export nodes to:
- Clash YAML / Mihomo (芙芙 rule-set template)
- Sing-box 1.10+ JSON (modern universal format)
- V2Ray / Base64 URI list
Excludes quarantined (dead) nodes automatically.
"""
import base64
import json
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

    protocol = node["protocol"]
    extra = node.get("extra") or {}
    name = node["name"]
    address = node["address"]
    port = node["port"]

    if protocol == "vmess":
        return {
            "name": name, "type": "vmess", "server": address, "port": port,
            "uuid": extra.get("uuid", ""),
            "alterId": int(extra.get("alterId", 0)),
            "cipher": extra.get("security", "auto"),
            "network": extra.get("network", "tcp"),
            "tls": extra.get("tls") == "tls",
            "ws-opts": {"path": extra.get("path", "/"), "headers": {"Host": extra.get("host", "")}},
            "servername": extra.get("sni", ""),
        }
    elif protocol == "vless":
        p = {
            "name": name, "type": "vless", "server": address, "port": port,
            "uuid": extra.get("uuid", ""),
            "network": extra.get("type", "tcp"),
            "tls": extra.get("security") in ("tls", "reality"),
            "servername": extra.get("sni", ""),
        }
        if extra.get("security") == "reality":
            p["reality-opts"] = {
                "public-key": extra.get("pbk", ""),
                "short-id": extra.get("sid", ""),
            }
        return p
    elif protocol == "ss":
        return {
            "name": name, "type": "ss", "server": address, "port": port,
            "cipher": extra.get("method", "aes-256-gcm"),
            "password": extra.get("password", ""),
        }
    elif protocol == "trojan":
        return {
            "name": name, "type": "trojan", "server": address, "port": port,
            "password": extra.get("password", ""),
            "sni": extra.get("sni", address),
        }
    elif protocol == "hy2":
        return {
            "name": name, "type": "hysteria2", "server": address, "port": port,
            "password": extra.get("auth", extra.get("password", "")),
            "sni": extra.get("sni", ""),
        }
    return None


def _node_to_singbox_outbound(node: Dict[str, Any]) -> Dict[str, Any] | None:
    if not _is_usable(node):
        return None

    protocol = node["protocol"]
    extra = node.get("extra") or {}
    name = str(node["name"])
    address = node["address"]
    port = int(node["port"])

    if protocol == "vless":
        ob = {
            "type": "vless",
            "tag": name,
            "server": address,
            "server_port": port,
            "uuid": extra.get("uuid", ""),
        }
        sec = extra.get("security", "")
        if sec == "reality":
            ob["tls"] = {
                "enabled": True,
                "server_name": extra.get("sni", address),
                "reality": {
                    "enabled": True,
                    "public_key": extra.get("pbk", ""),
                    "short_id": extra.get("sid", ""),
                }
            }
        elif sec == "tls":
            ob["tls"] = {"enabled": True, "server_name": extra.get("sni", address)}
        return ob

    elif protocol == "vmess":
        return {
            "type": "vmess",
            "tag": name,
            "server": address,
            "server_port": port,
            "uuid": extra.get("uuid", ""),
            "security": "auto",
            "alter_id": int(extra.get("alterId", 0)),
            "tls": {"enabled": extra.get("tls") == "tls", "server_name": extra.get("sni", address)},
        }

    elif protocol == "ss":
        return {
            "type": "shadowsocks",
            "tag": name,
            "server": address,
            "server_port": port,
            "method": extra.get("method", "aes-256-gcm"),
            "password": extra.get("password", ""),
        }

    elif protocol == "trojan":
        return {
            "type": "trojan",
            "tag": name,
            "server": address,
            "server_port": port,
            "password": extra.get("password", ""),
            "tls": {"enabled": True, "server_name": extra.get("sni", address)},
        }

    elif protocol == "hy2":
        return {
            "type": "hysteria2",
            "tag": name,
            "server": address,
            "server_port": port,
            "password": extra.get("auth", extra.get("password", "")),
            "tls": {"enabled": True, "server_name": extra.get("sni", address)},
        }

    return None


def export_clash(nodes: List[Dict[str, Any]]) -> str:
    """Export nodes as Clash YAML subscription (auto filters dead quarantined nodes)."""
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
                {"tag": "dns-remote", "address": "https://1.1.1.1/dns-query", "detour": "Proxy"},
                {"tag": "dns-direct", "address": "223.5.5.5", "detour": "direct"}
            ]
        },
        "inbounds": [
            {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080}
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": "Proxy",
                "outbounds": ["Auto"] + tags if tags else ["direct"],
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
    """Export nodes as base64-encoded URI list (V2Ray/Xray subscription)."""
    uris = []
    for node in nodes:
        if _is_usable(node):
            raw = node.get("raw_config")
            if raw:
                uris.append(raw)
    content = "\n".join(uris)
    return base64.b64encode(content.encode("utf-8")).decode("utf-8")
