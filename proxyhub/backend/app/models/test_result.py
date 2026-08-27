from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, JSON, ForeignKey
from datetime import datetime, timezone
from app.database import Base


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("nodes.id", ondelete="CASCADE"))
    test_type = Column(String(20), nullable=False)   # tcp_ping / proxy_speed / purity
    success = Column(Boolean, nullable=False)
    latency_ms = Column(Float, nullable=True)
    download_mbps = Column(Float, nullable=True)
    details = Column(JSON, nullable=True)
    tested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
