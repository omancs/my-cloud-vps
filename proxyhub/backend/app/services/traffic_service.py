"""
Traffic monitoring service.
Reads cumulative bytes from /proc/net/dev (Linux), persists monthly
snapshots to SQLite, and computes month-to-date usage delta.

Falls back gracefully on non-Linux (Windows dev environment).
"""
import asyncio
import platform
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.traffic import TrafficRecord, TrafficConfig


def _read_proc_net_dev(interface: str = "eth0") -> Optional[Dict[str, int]]:
    """Read bytes_sent / bytes_recv from /proc/net/dev for the given interface."""
    if platform.system() != "Linux":
        return None
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                line = line.strip()
                if line.startswith(interface + ":"):
                    parts = line.split()
                    # Format: iface: recv_bytes recv_pkts ... send_bytes ...
                    return {
                        "bytes_recv": int(parts[1]),
                        "bytes_sent": int(parts[9]),
                    }
    except Exception:
        pass
    return None


async def _get_or_create_config(db: AsyncSession) -> TrafficConfig:
    result = await db.execute(select(TrafficConfig).limit(1))
    cfg = result.scalar_one_or_none()
    if not cfg:
        cfg = TrafficConfig()
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
    """
    Returns current month's egress usage and quota status.
    Logic:
      - Find the earliest and latest snapshots for the current billing month.
      - Delta = latest_sent - earliest_sent (handles counter wraps poorly but OK for monthly scale)
      - Returns structured dict for the API.
    """
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        now = datetime.now(timezone.utc)

        # Determine billing month start
        reset_day = min(cfg.reset_day, 28)
        if now.day >= reset_day:
            month_start = now.replace(day=reset_day, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Previous month
            if now.month == 1:
                month_start = now.replace(year=now.year - 1, month=12, day=reset_day,
                                          hour=0, minute=0, second=0, microsecond=0)
            else:
                month_start = now.replace(month=now.month - 1, day=reset_day,
                                          hour=0, minute=0, second=0, microsecond=0)

        # Read snapshots from /proc/net/dev directly for current value
        current = _read_proc_net_dev(cfg.interface)

        # Get earliest snapshot after month_start
        result = await db.execute(
            select(TrafficRecord)
            .where(TrafficRecord.recorded_at >= month_start)
            .order_by(TrafficRecord.recorded_at.asc())
            .limit(1)
        )
        earliest = result.scalar_one_or_none()

        quota = cfg.monthly_quota_bytes
        used_bytes = 0

        if current and earliest:
            # Delta egress since billing start
            sent_delta = max(0, current["bytes_sent"] - earliest.bytes_sent)
            used_bytes = sent_delta
        elif current:
            used_bytes = 0  # No baseline yet

        used_gb = round(used_bytes / (1024 ** 3), 3)
        quota_gb = round(quota / (1024 ** 3), 2)
        pct = round(used_bytes / quota * 100, 1) if quota > 0 else 0
        remaining_bytes = max(0, quota - used_bytes)
        remaining_gb = round(remaining_bytes / (1024 ** 3), 3)

        alert = "normal"
        if pct >= 100:
            alert = "exceeded"
        elif pct >= cfg.alert_threshold_pct:
            alert = "warning"

        return {
            "interface": cfg.interface,
            "month_start": month_start.isoformat(),
            "used_bytes": used_bytes,
            "used_gb": used_gb,
            "quota_bytes": quota,
            "quota_gb": quota_gb,
            "remaining_gb": remaining_gb,
            "usage_pct": pct,
            "alert": alert,
            "alert_threshold_pct": cfg.alert_threshold_pct,
            "is_linux": platform.system() == "Linux",
        }


async def get_traffic_config() -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        return {
            "interface": cfg.interface,
            "monthly_quota_bytes": cfg.monthly_quota_bytes,
            "monthly_quota_gb": round(cfg.monthly_quota_bytes / (1024 ** 3), 2),
            "alert_threshold_pct": cfg.alert_threshold_pct,
            "reset_day": cfg.reset_day,
        }


async def update_traffic_config(interface: str = None, monthly_quota_gb: float = None,
                                alert_threshold_pct: float = None, reset_day: int = None):
    async with AsyncSessionLocal() as db:
        cfg = await _get_or_create_config(db)
        if interface is not None:
            cfg.interface = interface
        if monthly_quota_gb is not None:
            cfg.monthly_quota_bytes = int(monthly_quota_gb * 1024 ** 3)
        if alert_threshold_pct is not None:
            cfg.alert_threshold_pct = alert_threshold_pct
        if reset_day is not None:
            cfg.reset_day = max(1, min(28, reset_day))
        await db.commit()
