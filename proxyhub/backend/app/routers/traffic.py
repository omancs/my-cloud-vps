from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.auth import get_current_user
from app.services.traffic_service import (
    get_monthly_usage, get_traffic_config, update_traffic_config
)

router = APIRouter(prefix="/api/traffic", tags=["traffic"])


class TrafficConfigUpdate(BaseModel):
    interface: Optional[str] = None
    monthly_quota_gb: Optional[float] = None
    alert_threshold_pct: Optional[float] = None
    reset_day: Optional[int] = None


@router.get("/usage")
async def traffic_usage(_: str = Depends(get_current_user)):
    """Get current month's egress usage, quota, and alert status."""
    return await get_monthly_usage()


@router.get("/config")
async def traffic_config(_: str = Depends(get_current_user)):
    """Get traffic monitoring configuration."""
    return await get_traffic_config()


@router.put("/config")
async def update_config(
    body: TrafficConfigUpdate,
    _: str = Depends(get_current_user),
):
    """Update traffic quota configuration."""
    await update_traffic_config(
        interface=body.interface,
        monthly_quota_gb=body.monthly_quota_gb,
        alert_threshold_pct=body.alert_threshold_pct,
        reset_day=body.reset_day,
    )
    return {"message": "配置已更新"}
