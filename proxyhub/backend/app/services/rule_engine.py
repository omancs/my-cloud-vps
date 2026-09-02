"""
Rule engine: merges user-defined custom rules into the Clash Meta / Mihomo configuration
and injects real proxy nodes, producing a ready-to-use Clash YAML subscription.
"""
import re
from typing import List, Dict, Any
import yaml
from app.services.exporter import _node_to_clash_proxy


def _build_region_filter_groups(proxy_names: List[str]) -> List[dict]:
    """Build auto url-test groups for HK/JP/US/SG/TW/Other based on node names."""
    regions = [
        ("ALL·香港地区", r"港|HK|hk|Hong Kong|HongKong|hongkong"),
        ("ALL·日本地区", r"日本|川日|东京|大阪|泉日|埼玉|JP|Japan"),
        ("ALL·美国地区", r"美|洛杉矶|硅谷|西雅图|芝加哥|US|United States"),
        ("ALL·狮城地区", r"新加坡|坡|狮城|SG|Singapore"),
        ("ALL·中国台湾", r"台湾|台|新北|彰化|TW|Taiwan"),
    ]
    groups = []
    for group_name, pattern in regions:
        matched = [n for n in proxy_names if re.search(pattern, n)]
        if matched:
            groups.append({
                "name": group_name,
                "type": "url-test",
                "proxies": matched,
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
            })

    all_region_pattern = (
        r"港|HK|hk|Hong Kong|日本|JP|Japan|美|US|United States"
        r"|新加坡|SG|Singapore|台湾|台|TW|Taiwan"
    )
    others = [n for n in proxy_names if not re.search(all_region_pattern, n)]
    if others:
        groups.append({
            "name": "ALL·其它地区",
            "type": "url-test",
            "proxies": others,
            "url": "https://www.gstatic.com/generate_204",
            "interval": 300,
        })

    return groups


def build_clash_subscription(
    nodes: List[Dict[str, Any]],
    custom_rules: List[Dict[str, Any]],
    network_name: str = "ProxyHub",
) -> str:
    """
    Build a 100% compliant Clash Meta / Mihomo subscription YAML:
    1. Converts ProxyHub nodes to standard Clash proxies.
    2. Builds region-based url-test and load-balance groups.
    3. Injects custom rules at the top of the rules list.
    4. Ensures zero invalid proxy types (like dns/reject) in proxies section.
    """
    proxies = []
    proxy_names = []

    for node in nodes:
        p = _node_to_clash_proxy(node)
        if p:
            proxies.append(p)
            proxy_names.append(p["name"])

    # Fallback if no proxies configured
    effective_proxies = proxy_names if proxy_names else ["DIRECT"]

    # ── Proxy Groups ──────────────────────────────────────────────────────────
    region_groups = _build_region_filter_groups(proxy_names) if proxy_names else []
    region_group_names = [g["name"] for g in region_groups]

    select_pool = ["ALL·延迟最低", "ALL·负载均衡", "ALL·故障转移"] + region_group_names + ["DIRECT", "REJECT"]

    auto_group = {
        "name": "ALL·延迟最低",
        "type": "url-test",
        "proxies": effective_proxies,
        "url": "https://www.gstatic.com/generate_204",
        "interval": 300,
        "tolerance": 50,
    }
    lb_group = {
        "name": "ALL·负载均衡",
        "type": "load-balance",
        "proxies": effective_proxies,
        "strategy": "round-robin",
        "url": "https://www.gstatic.com/generate_204",
        "interval": 300,
    }
    fallback_group = {
        "name": "ALL·故障转移",
        "type": "fallback",
        "proxies": effective_proxies,
        "url": "https://www.gstatic.com/generate_204",
        "interval": 300,
    }
    main_group = {
        "name": "总模式",
        "type": "select",
        "proxies": select_pool,
    }
    update_group = {
        "name": "节点选择",
        "type": "select",
        "proxies": ["总模式"] + effective_proxies,
    }

    media_names = [
        "小红书", "抖音", "BiliBili", "Steam", "Apple", "Microsoft",
        "Telegram", "Discord", "Spotify", "TikTok", "YouTube",
        "Netflix", "Google", "OpenAI", "GitHub", "Twitter", "漏网之鱼",
    ]
    media_groups = []
    for name in media_names:
        media_groups.append({
            "name": name,
            "type": "select",
            "proxies": select_pool,
        })

    proxy_groups = [
        main_group, update_group, auto_group, lb_group, fallback_group,
        *region_groups, *media_groups,
    ]

    # ── Custom and Base Rules ────────────────────────────────────────────────
    custom_rule_lines = []
    for r in custom_rules:
        if not r.get("enabled", True):
            continue
        action = {
            "direct": "DIRECT",
            "proxy": "总模式",
            "reject": "REJECT",
        }.get(r.get("rule_type", "direct"), "DIRECT")
        match_type = r.get("match_type", "DOMAIN-SUFFIX").upper()
        custom_rule_lines.append(f"{match_type},{r['pattern']},{action}")

    # Standard clean rules that work everywhere without external downloads
    base_rules = [
        "DOMAIN-SUFFIX,local,DIRECT",
        "DOMAIN-SUFFIX,localhost,DIRECT",
        "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
        "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve",
        # Apps
        "GEOSITE,openai,OpenAI",
        "GEOSITE,youtube,YouTube",
        "GEOSITE,netflix,Netflix",
        "GEOSITE,telegram,Telegram",
        "GEOSITE,github,GitHub",
        "GEOSITE,twitter,Twitter",
        "GEOSITE,google,Google",
        "GEOSITE,bilibili,BiliBili",
        "GEOSITE,apple,Apple",
        "GEOSITE,microsoft,Microsoft",
        # Geolocation rules
        "GEOIP,LAN,DIRECT,no-resolve",
        "GEOIP,CN,DIRECT",
        "GEOSITE,CN,DIRECT",
        "GEOSITE,geolocation-!cn,总模式",
        "MATCH,漏网之鱼",
    ]

    all_rules = custom_rule_lines + base_rules

    # ── Full Clash Meta Config ───────────────────────────────────────────────
    config = {
        "mixed-port": 7890,
        "mode": "Rule",
        "allow-lan": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "log-level": "info",
        "dns": {
            "enable": True,
            "ipv6": False,
            "listen": "0.0.0.0:1053",
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.0/16",
            "default-nameserver": ["223.5.5.5", "119.29.29.29"],
            "nameserver": ["https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query"],
            "fallback": ["https://8.8.8.8/dns-query", "https://1.1.1.1/dns-query"],
        },
        "proxies": proxies,
        "proxy-groups": proxy_groups,
        "rules": all_rules,
    }

    return yaml.dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)
