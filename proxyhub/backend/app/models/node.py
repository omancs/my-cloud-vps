from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"),
                             nullable=True)
    name = Column(String(200), nullable=False)
    protocol = Column(String(20), nullable=False)   # vmess/vless/ss/trojan/hy2/socks
    address = Column(String(256), nullable=False)
    port = Column(Integer, nullable=False)
    raw_config = Column(Text, nullable=True)        # original URI or json
    extra = Column(JSON, nullable=True)             # protocol-specific fields

    # Status
    enabled = Column(Boolean, default=True)
    latency_ms = Column(Float, nullable=True)       # TCP ping result
    real_latency_ms = Column(Float, nullable=True)  # actual proxy latency
    download_speed = Column(Float, nullable=True)   # Mbps
    status = Column(String(20), default="unknown")  # unknown/ok/timeout/error

    # Purity
    ip_address = Column(String(64), nullable=True)
    ip_country = Column(String(10), nullable=True)
    ip_org = Column(String(200), nullable=True)
    is_residential = Column(Boolean, nullable=True)
    netflix_unlock = Column(Boolean, nullable=True)
    openai_unlock = Column(Boolean, nullable=True)
    purity_status = Column(String(20), default="unknown")  # unknown/clean/dirty

    last_tested = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    subscription = relationship("Subscription", back_populates="nodes")
    network_nodes = relationship("NetworkNode", back_populates="node",
                                  cascade="all, delete-orphan")
