from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from datetime import datetime, timezone
from app.database import Base


class CustomRule(Base):
    """User-defined domain/IP rules for Clash export."""
    __tablename__ = "custom_rules"

    id = Column(Integer, primary_key=True, index=True)
    # Rule type: direct / proxy / reject / comment
    rule_type = Column(String(20), nullable=False, default="direct")
    # Rule pattern: DOMAIN-SUFFIX,example.com or DOMAIN,api.example.com
    # Stored as plain domain; prefix is added on export
    pattern = Column(String(512), nullable=False)
    # Match type: DOMAIN / DOMAIN-SUFFIX / DOMAIN-KEYWORD / IP-CIDR
    match_type = Column(String(30), default="DOMAIN-SUFFIX")
    # Description / note
    remark = Column(String(200), nullable=True)
    enabled = Column(Boolean, default=True)
    # Display sort order (lower = higher priority = placed earlier in rules)
    priority = Column(Integer, default=100)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
