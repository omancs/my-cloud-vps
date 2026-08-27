from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Network(Base):
    __tablename__ = "networks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    sort_by = Column(String(20), default="latency")   # latency / real_latency / manual
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    network_nodes = relationship("NetworkNode", back_populates="network",
                                  cascade="all, delete-orphan")


class NetworkNode(Base):
    """Many-to-many: Network <-> Node with priority ordering."""
    __tablename__ = "network_nodes"

    id = Column(Integer, primary_key=True, index=True)
    network_id = Column(Integer, ForeignKey("networks.id", ondelete="CASCADE"))
    node_id = Column(Integer, ForeignKey("nodes.id", ondelete="CASCADE"))
    priority = Column(Integer, default=0)  # lower = higher priority

    network = relationship("Network", back_populates="network_nodes")
    node = relationship("Node", back_populates="network_nodes")
