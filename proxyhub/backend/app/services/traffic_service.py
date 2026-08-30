"""
Traffic monitoring service.
Reads cumulative bytes from /host_proc/net/dev (mounted from host) or /proc/net/dev,
persists monthly snapshots to SQLite, and computes month-to-date usage delta.
"""
import os
import platform
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.traffic import TrafficRecord, TrafficConfig


def _get_proc_net_dev_path() -> Optional[str]:
    """Find available net/dev path (prioritizing host mounted path)."""
    if os.path.exists("/host_proc/net/dev"):
        return "/host_proc/net/dev"
    if os.path.exists("/proc/net/dev"):
        return "/proc/net/dev"
    return None


def get_available_interfaces() -> List[Dict[str, Any]]:
    """Scan and return all active network interfaces with non-zero traffic."""
    path = _get_proc_net_dev_path()
    interfaces = []
    if not path:
        return interfaces

    ignored_prefixes = ("lo", "docker", "br-", "veth", "tailscale", "tun", "wg")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" not in line or line.startswith("Inter-") or line.startswith("face"):
                    continue
                name, data = line.split(":", 1)
                name = name.strip()
                if any(name.startswith(p) for p in ignored_prefixes):
                    continue
                parts = data.split()
                if len(parts) >= 10:
                    recv_bytes = int(parts[0])
                    sent_bytes = int(parts[8])
                    interfaces.append({
                        "name": name,
                        "recv_bytes": recv_bytes,
                        "sent_bytes": sent_bytes,
                        "total_bytes": recv_bytes + sent_bytes,
                    })
    except Exception:
        pass

    # Sort by total traffic descending
    interfaces.sort(key=lambda x: x["total_bytes"], reverse=True)
    return interfaces


def _read_proc_net_dev(interface: str = "auto") -> Optional[Dict[str, int]]:
    """
    Read bytes_sent / bytes_recv. If interface is 'auto' or not found,
    automatically pick the primary physical interface with the highest traffic.
    """
    path = _get_proc_net_dev_path()
    if not path:
        # Non-linux fallback (e.g. Windows dev)
        try:
            import psutil
            net = psutil.net_io_counters()
            return {"bytes_recv": net.bytes_recv, "bytes_sent": net.bytes_sent}
        except Exception:
            return None

    interfaces = get_available_interfaces()
    if not interfaces:
        return None

    # If specific interface is requested and exists
    if interface and interface != "auto":
        for iface in interfaces:
            if iface["name"] == interface:
                return {"bytes_recv": iface["recv_bytes"], "bytes_sent": iface["sent_bytes"]}

    # Default to the most active physical interface (e.g. eth0, ens4)
    primary = interfaces[0]
    return {"bytes_recv": primary["recv_bytes"], "bytes_sent": primary["sent_bytes"], "detected_iface": primary["name"]}


async def _get_or_create_config(db: AsyncSession) -> TrafficConfig:
    result = await db.execute(select(TrafficConfig).limit(1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = TrafficConfig(interface="auto", monthly_quota_bytes=1_073_741_824, alert_threshold_pct=80.0, reset_day=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def snapshot_traffic():
    """Called by scheduler every 10 minutes to persist a traffic snapshot."""
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        stats = _read_proc_net_dev(cfg.interface)
        if not stats:
            return
        month_tag = datetime.now(timezone.utc).strftime("%Y-%m")
        record = TrafficRecord(
            bytes_sent=stats["bytes_sent"],
            bytes_recv=stats["bytes_recv"],
            month_tag=month_tag,
        )
        db.add(record)
        await db.commit()


async def get_monthly_usage() -> Dict[str, Any]:
    """Calculate current month's egress usage, remaining quota, and alert level."""
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        now = datetime.now(timezone.utc)

        # Billing month start calculation
        reset_day = min(cfg.reset_day or 1, 28)
        if now.day >= reset_day:
            month_start = now.replace(day=reset_day, hour=0, minute=0, second=0, microsecond=0)
        else:
            if now.month == 1:
                month_start = now.replace(year=now.year - 1, month=12, day=reset_day, hour=0, minute=0, second=0, microsecond=0)
            else:
                month_start = now.replace(month=now.month - 1, day=reset_day, hour=0, minute=0, second=0, microsecond=0)

        # Current live stats
        current = _read_proc_net_dev(cfg.interface)
        actual_iface = current.get("detected_iface", cfg.interface) if current else (cfg.interface or "auto")

        # Earliest snapshot in current billing month
        result = await db.execute(
            select(TrafficRecord)
            .where(TrafficRecord.recorded_at >= month_start)
            .order_by(TrafficRecord.recorded_at.asc())
            .limit(1)
        )
        earliest = result.scalar_one_or_none()

        quota = cfg.monthly_quota_bytes or 1_073_741_824
        used_bytes = 0

        if current and earliest:
            if current["bytes_sent"] >= earliest.bytes_sent:
                used_bytes = current["bytes_sent"] - earliest.bytes_sent
            else:
                # Counter wrapped / rebooted
                used_bytes = current["bytes_sent"]
        elif current:
            # First time running: record initial baseline
            init_record = TrafficRecord(
                bytes_sent=current["bytes_sent"],
                bytes_recv=current["bytes_recv"],
                month_tag=now.strftime("%Y-%m"),
            )
            db.add(init_record)
            await db.commit()
            used_bytes = 0

        used_gb = round(used_bytes / (1024 ** 3), 3)
        quota_gb = round(quota / (1024 ** 3), 2)
        pct = round((used_bytes / quota * 100), 1) if quota > 0 else 0
        remaining_bytes = max(0, quota - used_bytes)
        remaining_gb = round(remaining_bytes / (1024 ** 3), 3)

        alert = "normal"
        if pct >= 100:
            alert = "exceeded"
        elif pct >= (cfg.alert_threshold_pct or 80.0):
            alert = "warning"

        available_ifaces = [i["name"] for i in get_available_interfaces()]

        return {
            "interface": actual_iface,
            "configured_interface": cfg.interface,
            "available_interfaces": available_ifaces,
            "month_start": month_start.isoformat(),
            "used_bytes": used_bytes,
            "used_gb": used_gb,
            "quota_bytes": quota,
            "quota_gb": quota_gb,
            "remaining_gb": remaining_gb,
            "usage_pct": pct,
            "alert": alert,
            "alert_threshold_pct": cfg.alert_threshold_pct or 80.0,
            "is_live": current is not None,
        }


async def get_traffic_config() -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        return {
            "interface": cfg.interface or "auto",
            "monthly_quota_bytes": cfg.monthly_quota_bytes,
            "monthly_quota_gb": round(cfg.monthly_quota_bytes / (1024 ** 3), 2),
            "alert_threshold_pct": cfg.alert_threshold_pct,
            "reset_day": cfg.reset_day,
            "available_interfaces": [i["name"] for i in get_available_interfaces()],
        }


async def update_traffic_config(
    interface: str = None,
    monthly_quota_gb: float = None,
    alert_threshold_pct: float = None,
    reset_day: int = None,
):
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        if interface is not None:
            cfg.interface = interface
        if monthly_quota_gb is not None:
            cfg.monthly_quota_bytes = int(monthly_quota_gb * (1024 ** 3))
        if alert_threshold_pct is not None:
            cfg.alert_threshold_pct = alert_threshold_pct
        if reset_day is not None:
            cfg.reset_day = max(1, min(28, reset_day))
        await db.commit()
