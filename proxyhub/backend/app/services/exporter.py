"""
Export nodes to Clash YAML or V2Ray (base64 URI list) format.
"""
import base64
import json
from typing import List, Dict, Any

import yaml


def _node_to_clash_proxy(node: Dict[str, Any]) -> Dict[str, Any] | None:
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


def export_clash(nodes: List[Dict[str, Any]]) -> str:
    """Export nodes as Clash YAML subscription."""
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
        "proxy-groups": [{
            "name": "PROXY",
            "type": "select",
            "proxies": ["AUTO"] + names,
        }, {
            "name": "AUTO",
            "type": "url-test",
            "proxies": names,
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
        }],
        "rules": [
            "MATCH,PROXY",
        ]
    }
    return yaml.dump(clash_config, allow_unicode=True, sort_keys=False)


def export_v2ray(nodes: List[Dict[str, Any]]) -> str:
    """Export nodes as base64-encoded URI list (V2Ray/Xray subscription)."""
    uris = []
    for node in nodes:
        raw = node.get("raw_config")
        if raw:
            uris.append(raw)
    content = "\n".join(uris)
    return base64.b64encode(content.encode("utf-8")).decode("utf-8")
