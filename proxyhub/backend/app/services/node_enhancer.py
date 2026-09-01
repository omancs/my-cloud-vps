"""
Node Enhancer Service:
- Smart Ad Cleaning (removes airport advertisements, remaining traffic, URLs)
- National Flag Emoji & Standardized Renaming (🇭🇰 🇯🇵 🇺🇸 🇸🇬 🇹🇼 ...)
- Smart Tags Generation (#AI解锁, #Netflix全解, #原生住宅, #极速, #Hysteria2)
"""
import re
from typing import List, Dict, Any, Tuple

FLAG_MAP = {
    "HK": ("🇭🇰", "香港"),
    "JP": ("🇯🇵", "日本"),
    "US": ("🇺🇸", "美国"),
    "SG": ("🇸🇬", "新加坡"),
    "TW": ("🇹🇼", "台湾"),
    "KR": ("🇰🇷", "韩国"),
    "GB": ("🇬🇧", "英国"),
    "UK": ("🇬🇧", "英国"),
    "DE": ("🇩🇪", "德国"),
    "FR": ("🇫🇷", "法国"),
    "CA": ("🇨🇦", "加拿大"),
    "AU": ("🇦🇺", "澳大利亚"),
}

AD_KEYWORDS = [
    r"官网[：:\s\w\.\-]+",
    r"https?://\S+",
    r"t\.me/\S+",
    r"禁止BT[下载]*",
    r"剩余流量[:\s\w\.\-]+",
    r"到期[:\s\w\.\-]+",
    r"本站[\w\.\-]+",
    r"通知群[:\s\w\.\-]+",
    r"防失联[:\s\w\.\-]+",
    r"群组[:\s\w\.\-]+",
]


def detect_country_code(name: str, ip_country: str = None) -> Tuple[str, str, str]:
    """Detect 2-letter country code, flag emoji, and Chinese country name."""
    if ip_country and ip_country.upper() in FLAG_MAP:
        cc = ip_country.upper()
        flag, cname = FLAG_MAP[cc]
        return cc, flag, cname

    n = (name or "").lower()
    if any(k in n for k in ("hk", "hongkong", "hong kong", "香港")):
        return "HK", "🇭🇰", "香港"
    if any(k in n for k in ("jp", "japan", "tokyo", "osaka", "日本", "东京")):
        return "JP", "🇯🇵", "日本"
    if any(k in n for k in ("us", "united states", "america", "美国", "洛杉矶", "圣何塞", "纽约")):
        return "US", "🇺🇸", "美国"
    if any(k in n for k in ("sg", "singapore", "新加坡", "狮城")):
        return "SG", "🇸🇬", "新加坡"
    if any(k in n for k in ("tw", "taiwan", "台湾", "台北")):
        return "TW", "🇹🇼", "台湾"
    if any(k in n for k in ("kr", "korea", "韩国", "首尔")):
        return "KR", "🇰🇷", "韩国"
    if any(k in n for k in ("uk", "gb", "britain", "london", "英国", "伦敦")):
        return "GB", "🇬🇧", "英国"
    if any(k in n for k in ("de", "germany", "德国", "法兰克福")):
        return "DE", "🇩🇪", "德国"
    if any(k in n for k in ("fr", "france", "法国")):
        return "FR", "🇫🇷", "法国"
    if any(k in n for k in ("ca", "canada", "加拿大")):
        return "CA", "🇨🇦", "加拿大"
    if any(k in n for k in ("au", "australia", "澳大利亚", "悉尼")):
        return "AU", "🇦🇺", "澳大利亚"

    return "GLOBAL", "🌐", "全球"


def clean_node_name(name: str) -> str:
    """Clean advertising noise and URL junk from node name."""
    cleaned = name
    for pattern in AD_KEYWORDS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    # Remove excessive whitespace, brackets, trailing symbols
    cleaned = re.sub(r"[\[\]【】|·\-_\s]+$", "", cleaned)
    cleaned = re.sub(r"^[\[\]【】|·\-_\s]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else name


def standardize_node_name(name: str, index: int, ip_country: str = None) -> str:
    """Format into standard: 🇭🇰 香港 01 | 原名/专线."""
    cc, flag, cname = detect_country_code(name, ip_country)
    cleaned = clean_node_name(name)

    # If original name had special descriptors (e.g. 专线, BGP, IPLC, 原生), retain them
    extra_tags = []
    for tag in ("IPLC", "BGP", "IEPL", "专线", "原生", "优化", "住宅", "Relay"):
        if tag.lower() in name.lower():
            extra_tags.append(tag)
    extra_str = f" | {' '.join(extra_tags)}" if extra_tags else ""

    return f"{flag} {cname} {index:02d}{extra_str}"


def compute_smart_tags(node: Any) -> List[str]:
    """Compute smart tags for a node based on unlock status, speed, protocol, and country."""
    tags = []

    # Country tag
    cc, flag, cname = detect_country_code(getattr(node, "name", ""), getattr(node, "ip_country", ""))
    tags.append(f"#{cname}")

    # Unlock tags
    if getattr(node, "openai_unlock", False):
        tags.append("#AI解锁")
    if getattr(node, "netflix_unlock", False):
        tags.append("#Netflix全解")
    if getattr(node, "youtube_unlock", False):
        tags.append("#YouTube")

    # IP Quality
    if getattr(node, "is_residential", False):
        tags.append("#原生住宅")

    # Speed & Latency
    latency = getattr(node, "latency_ms", None) or getattr(node, "real_latency_ms", None)
    if latency and latency > 0:
        if latency < 150:
            tags.append("#极速(<150ms)")
        elif latency < 250:
            tags.append("#优良(<250ms)")

    download = getattr(node, "download_speed", None)
    if download and download >= 10:
        tags.append("#高速(>10M)")

    # Protocol
    proto = getattr(node, "protocol", "").lower()
    if proto == "hy2":
        tags.append("#Hysteria2")
    elif proto == "vless":
        tags.append("#Reality")

    return tags
