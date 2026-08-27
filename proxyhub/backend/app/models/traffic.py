from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Float
from datetime import datetime, timezone
from app.database import Base


class TrafficRecord(Base):
    """Monthly traffic snapshot stored every 10 minutes."""
    __tablename__ = "traffic_records"

    id = Column(Integer, primary_key=True, index=True)
    # Total bytes sent/received at the time of snapshot (from /proc/net/dev)
    bytes_sent = Column(BigInteger, default=0)
    bytes_recv = Column(BigInteger, default=0)
    # Month tag e.g. "2026-08"
    month_tag = Column(String(7), nullable=False, index=True)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrafficConfig(Base):
    """Per-interface traffic quota configuration."""
    __tablename__ = "traffic_config"

    id = Column(Integer, primary_key=True, index=True)
    # Network interface to monitor (default: eth0)
    interface = Column(String(20), default="eth0")
    # Monthly egress quota in bytes (default 1 GB = 1_073_741_824)
    monthly_quota_bytes = Column(BigInteger, default=1_073_741_824)
    # Alert threshold percentage (0-100)
    alert_threshold_pct = Column(Float, default=80.0)
    # Day of month when billing resets (1-28)
    reset_day = Column(Integer, default=1)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
