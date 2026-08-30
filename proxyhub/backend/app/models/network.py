import secrets
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


def _gen_token() -> str:
    return secrets.token_hex(8)


class Network(Base):
    __tablename__ = "networks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    sort_by = Column(String(20), default="latency")   # latency / real_latency / manual
    token = Column(String(64), default=_gen_token)     # Security token for subscription link
    auto_update = Column(Boolean, default=False)       # Auto update top 50 daily
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    network_nodes = relationship("NetworkNode", back_populates="network",
                                  cascade="all, delete-orphan")


class NetworkNode(Base):
    """Many-to-many: Network <-> Node with priority ordering."""
    __tablename__ = "network_nodes"

    id = Column(Integer, primary_key=True, index=True)
    network_id = Column(Integer, ForeignKey("networks.id", ondelete="CASCADE"))
    node_id = Column(Integer, ForeignKey("nodes.id", ondelete="CASCADE"))
    priority = Column(Integer, default=0)

    network = relationship("Network", back_populates="network_nodes")
    node = relationship("Node", back_populates="network_nodes")
