"""
Rule engine: merges user-defined custom rules into the 芙芙 Clash Meta template
and injects real proxy nodes, producing a ready-to-use Clash YAML subscription.
"""
import os
import copy
import re
from typing import List, Dict, Any

import yaml

# Path to the bundled 芙芙 config template
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "template_fufu.yaml")


def _load_template() -> dict:
    """Load and parse the 芙芙 YAML template."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    # PyYAML doesn't support all YAML anchors/aliases in complex multi-doc formats.
    # We'll do a best-effort load; unresolvable anchors are handled below.
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        return {}


def _node_to_clash_proxy(node: Dict[str, Any]) -> Dict[str, Any] | None:
    """Convert a ProxyHub node dict to Clash proxy dict."""
    from app.services.exporter import _node_to_clash_proxy as _base
    return _base(node)


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

    # Other regions: nodes not matched by any regional pattern
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
    Build a complete Clash Meta subscription YAML by:
    1. Converting ProxyHub nodes to Clash proxy format.
    2. Building region-based proxy groups.
    3. Injecting user custom rules at the top of the rules list.
    4. Using the 芙芙 template for DNS, sniffer, rule-providers etc.
    """
    # ── 1. Build proxy list ──────────────────────────────────────────────────
    proxies = []
    proxy_names = []
    # Built-in special proxies
    base_proxies = [
        {"name": "🌐 本机·本地直连", "type": "direct", "udp": True},
        {"name": "⛔️ 禁止·拒绝连接", "type": "reject"},
        {"name": "🌐 DNS_Hijack", "type": "dns"},
    ]
    proxies.extend(base_proxies)

    for node in nodes:
        p = _node_to_clash_proxy(node)
        if p:
            proxies.append(p)
            proxy_names.append(p["name"])

    if not proxy_names:
        proxy_names = ["🌐 本机·本地直连"]

    # ── 2. Build proxy groups ────────────────────────────────────────────────
    region_groups = _build_region_filter_groups(proxy_names)
    region_group_names = [g["name"] for g in region_groups]

    select_pool = ["ALL·延迟最低", "ALL·负载均衡", "ALL·故障转移"] + region_group_names + ["⛔️ 禁止·拒绝连接", "🌐 本机·本地直连"]

    auto_group = {
        "name": "ALL·延迟最低",
        "type": "url-test",
        "proxies": proxy_names,
        "url": "https://www.gstatic.com/generate_204",
        "interval": 300,
        "tolerance": 50,
    }
    lb_group = {
        "name": "ALL·负载均衡",
        "type": "load-balance",
        "proxies": proxy_names,
        "strategy": "round-robin",
        "url": "https://www.gstatic.com/generate_204",
        "interval": 300,
    }
    fallback_group = {
        "name": "ALL·故障转移",
        "type": "fallback",
        "proxies": proxy_names,
        "url": "https://www.gstatic.com/generate_204",
        "interval": 300,
    }
    main_group = {
        "name": "总模式",
        "type": "select",
        "proxies": select_pool,
    }
    update_group = {
        "name": "订阅更新",
        "type": "select",
        "proxies": ["🌐 本机·本地直连", "总模式"],
    }

    # Media / app groups all referencing 总模式 pool
    media_groups = []
    media_names = [
        "小红书", "抖音", "BiliBili", "Steam", "Apple", "Microsoft",
        "Telegram", "Discord", "Spotify", "TikTok", "YouTube",
        "Netflix", "Google", "GoogleFCM", "Facebook", "OpenAI",
        "GitHub", "Twitter(X)", "DNS连接", "漏网之鱼", "特殊地址",
    ]
    for name in media_names:
        media_groups.append({
            "name": name,
            "type": "select",
            "proxies": select_pool,
        })

    ad_group = {
        "name": "广告拦截",
        "type": "select",
        "proxies": ["PASS", "REJECT-DROP", "⛔️ 禁止·拒绝连接", "🌐 DNS_Hijack"],
    }
    webrtc_group = {
        "name": "WebRTC",
        "type": "select",
        "proxies": ["⛔️ 禁止·拒绝连接", "🌐 DNS_Hijack", "REJECT-DROP", "PASS"],
    }

    proxy_groups = [main_group, update_group, ad_group, webrtc_group,
                    auto_group, lb_group, fallback_group] + region_groups + media_groups

    # ── 3. Build custom rules (injected first) ────────────────────────────────
    custom_rule_lines = []
    for r in custom_rules:
        if not r.get("enabled", True):
            continue
        action = {
            "direct": "🌐 本机·本地直连",
            "proxy": "总模式",
            "reject": "⛔️ 禁止·拒绝连接",
        }.get(r.get("rule_type", "direct"), "🌐 本机·本地直连")
        custom_rule_lines.append(f"{r.get('match_type','DOMAIN-SUFFIX')},{r['pattern']},{action}")

    # ── 4. Base rules from 芙芙 template (hardcoded fallback) ────────────────
    base_rules = [
        "DOMAIN-SUFFIX,googleapis.cn,DIRECT",
        "DOMAIN-SUFFIX,xn--ngstr-lra8j.com,DIRECT",
        "DST-PORT,53,🌐 DNS_Hijack",
        "DST-PORT,853,DNS连接",
        "RULE-SET,自定义规则,特殊地址",
        "RULE-SET,WebRTC_端/域,WebRTC",
        "RULE-SET,No-ads-all_域,广告拦截",
        "RULE-SET,DouYin_域,抖音",
        "RULE-SET,XiaoHongShu_域,小红书",
        "RULE-SET,BiliBili_域,BiliBili",
        "RULE-SET,BiliBili_IP,BiliBili,no-resolve",
        "RULE-SET,Steam_域,Steam",
        "RULE-SET,GitHub_域,GitHub",
        "RULE-SET,Discord_域,Discord",
        "RULE-SET,TikTok_域,TikTok",
        "RULE-SET,Twitter_域,Twitter(X)",
        "RULE-SET,Twitter_IP,Twitter(X),no-resolve",
        "RULE-SET,YouTube_域,YouTube",
        "RULE-SET,GoogleFCM_域,GoogleFCM",
        "RULE-SET,Google_域,Google",
        "RULE-SET,Google_IP,Google,no-resolve",
        "RULE-SET,Netflix_域,Netflix",
        "RULE-SET,Netflix_IP,Netflix,no-resolve",
        "RULE-SET,Spotify_域,Spotify",
        "RULE-SET,Facebook_域,Facebook",
        "RULE-SET,Facebook_IP,Facebook,no-resolve",
        "RULE-SET,OpenAI_域,OpenAI",
        "RULE-SET,Apple_域,Apple",
        "RULE-SET,Apple_IP,Apple,no-resolve",
        "RULE-SET,Microsoft_域,Microsoft",
        "RULE-SET,Telegram_域,Telegram",
        "RULE-SET,Telegram_IP,Telegram,no-resolve",
        "RULE-SET,Private_域,🌐 本机·本地直连",
        "RULE-SET,Private_IP,🌐 本机·本地直连,no-resolve",
        "RULE-SET,CN_域,🌐 本机·本地直连",
        "RULE-SET,CN_IP,🌐 本机·本地直连",
        "MATCH,漏网之鱼",
    ]

    rules = custom_rule_lines + base_rules

    # ── 5. Rule providers ─────────────────────────────────────────────────────
    time_interval = 86400
    rule_providers = {
        "自定义规则": {"type": "file", "behavior": "classical", "format": "text", "path": "./etc/自定义规则.list"},
        "WebRTC_端/域": {"type": "http", "behavior": "classical", "format": "text", "interval": time_interval, "path": "./rules/WebRTC.list", "url": "https://cdn.jsdelivr.net/gh/GitMetaio/Surfing@main/box_bll/clash/rules/WebRTC.list"},
        "CN_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/CN_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/cn.mrs"},
        "CN_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/CN_域.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/cn.mrs"},
        "No-ads-all_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/No-ads-all.mrs", "url": "https://cdn.jsdelivr.net/gh/TG-Twilight/AWAvenue-Ads-Rule@main/Filters/AWAvenue-Ads-Rule-Clash.mrs"},
        "XiaoHongShu_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/XiaoHongShu.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/xiaohongshu.mrs"},
        "DouYin_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/DouYin.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/douyin.mrs"},
        "BiliBili_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/BiliBili.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/bilibili.mrs"},
        "BiliBili_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/BiliBili_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/bilibili.mrs"},
        "Steam_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Steam.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/steam.mrs"},
        "TikTok_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/TikTok.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/tiktok.mrs"},
        "Spotify_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Spotify.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/spotify.mrs"},
        "Facebook_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Facebook.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/facebook.mrs"},
        "Facebook_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Facebook_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/facebook.mrs"},
        "Telegram_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Telegram.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/telegram.mrs"},
        "Telegram_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Telegram_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/telegram.mrs"},
        "YouTube_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/YouTube.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/youtube.mrs"},
        "Google_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Google.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/google.mrs"},
        "Google_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Google_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/google.mrs"},
        "GoogleFCM_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/GoogleFCM.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/googlefcm.mrs"},
        "Microsoft_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Microsoft.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/microsoft.mrs"},
        "Apple_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Apple.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/apple.mrs"},
        "Apple_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Apple_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/apple.mrs"},
        "OpenAI_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/OpenAI.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/openai.mrs"},
        "Netflix_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Netflix.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/netflix.mrs"},
        "Netflix_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Netflix_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/netflix.mrs"},
        "Discord_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Discord.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/discord.mrs"},
        "GitHub_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/GitHub.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/github.mrs"},
        "Twitter_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Twitter.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/twitter.mrs"},
        "Twitter_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Twitter_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/twitter.mrs"},
        "Private_域": {"type": "http", "behavior": "domain", "format": "mrs", "interval": time_interval, "path": "./rules/Private.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo/geosite/private.mrs"},
        "Private_IP": {"type": "http", "behavior": "ipcidr", "format": "mrs", "interval": time_interval, "path": "./rules/Private_IP.mrs", "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@meta/geo-lite/geoip/private.mrs"},
    }

    # ── 6. Assemble full config ───────────────────────────────────────────────
    config = {
        "mixed-port": 7890,
        "redir-port": 9797,
        "tproxy-port": 9898,
        "ipv6": True,
        "mode": "Rule",
        "allow-lan": True,
        "unified-delay": True,
        "tcp-concurrent": True,
        "log-level": "silent",
        "find-process-mode": "always",
        "external-controller": "0.0.0.0:9090",
        "external-ui-url": "https://github.com/Zephyruso/zashboard/releases/latest/download/dist.zip",
        "external-ui": "./webroot/Zash/",
        "secret": "",
        "geodata-mode": False,
        "geo-auto-update": True,
        "geo-update-interval": 24,
        "profile": {
            "store-selected": True,
            "store-fake-ip": True,
        },
        "sniffer": {
            "enable": True,
            "force-dns-mapping": True,
            "parse-pure-ip": True,
            "override-destination": True,
            "sniff": {
                "HTTP": {"ports": [80, "8080-8880"]},
                "TLS": {"ports": [443, 5228, 8443]},
                "QUIC": {"ports": [443, 8443]},
            },
        },
        "tun": {
            "enable": False,
            "device": "Meta",
            "stack": "gvisor",
            "dns-hijack": ["any:53", "tcp://any:53"],
            "auto-route": True,
            "strict-route": False,
            "auto-detect-interface": True,
        },
        "dns": {
            "enable": True,
            "ipv6": True,
            "listen": "0.0.0.0:1053",
            "enhanced-mode": "redir-host",
            "fake-ip-range": "198.18.0.0/16",
            "proxy-server-nameserver": [
                "https://1.12.12.12:443/dns-query",
                "https://223.5.5.5:443/dns-query",
            ],
            "nameserver": [
                "https://8.8.8.8:443/dns-query",
                "https://1.1.1.1:443/dns-query",
            ],
            "direct-nameserver": ["1.12.12.12", "223.6.6.6"],
        },
        "proxies": proxies,
        "proxy-groups": proxy_groups,
        "rule-providers": rule_providers,
        "rules": rules,
    }

    return yaml.dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)
