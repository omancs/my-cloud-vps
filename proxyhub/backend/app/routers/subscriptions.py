from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.auth import get_current_user
from app.models.subscription import Subscription
from app.models.node import Node
from app.services.parser import fetch_subscription, parse_subscription_content

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


class SubscriptionCreate(BaseModel):
    name: str
    url: str
    auto_refresh: bool = True
    interval_minutes: int = 360


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    auto_refresh: Optional[bool] = None
    interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None


async def _do_refresh(sub_id: int, db: AsyncSession):
    """Background task: fetch subscription and upsert nodes."""
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        return
    try:
        content = await fetch_subscription(sub.url)
        nodes_data = parse_subscription_content(content)

        # Delete old nodes from this subscription
        await db.execute(delete(Node).where(Node.subscription_id == sub_id))

        # Insert new nodes
        new_nodes = []
        for nd in nodes_data:
            node = Node(
                subscription_id=sub_id,
                name=nd["name"],
                protocol=nd["protocol"],
                address=nd["address"],
                port=nd["port"],
                raw_config=nd.get("raw_config"),
                extra=nd.get("extra"),
            )
            new_nodes.append(node)
        db.add_all(new_nodes)

        sub.last_fetched = datetime.now(timezone.utc)
        sub.node_count = len(new_nodes)
        await db.commit()
    except Exception as e:
        sub.last_fetched = datetime.now(timezone.utc)
        await db.commit()
        raise e


@router.get("/")
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Subscription).order_by(Subscription.created_at.desc()))
    subs = result.scalars().all()
    return [
        {
            "id": s.id, "name": s.name, "url": s.url,
            "auto_refresh": s.auto_refresh, "interval_minutes": s.interval_minutes,
            "last_fetched": s.last_fetched, "node_count": s.node_count,
            "enabled": s.enabled, "created_at": s.created_at,
        }
        for s in subs
    ]


@router.post("/", status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    sub = Subscription(**body.model_dump())
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    # Auto-fetch on creation
    background_tasks.add_task(_do_refresh, sub.id, db)
    return {"id": sub.id, "message": "订阅已添加，正在后台拉取节点..."}


@router.put("/{sub_id}")
async def update_subscription(
    sub_id: int,
    body: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sub, field, value)
    await db.commit()
    return {"message": "更新成功"}


@router.delete("/{sub_id}")
async def delete_subscription(
    sub_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    await db.delete(sub)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/{sub_id}/refresh")
async def refresh_subscription(
    sub_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    background_tasks.add_task(_do_refresh, sub_id, db)
    return {"message": "正在后台刷新..."}
