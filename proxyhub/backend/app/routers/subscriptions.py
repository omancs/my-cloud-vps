from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.models.subscription import Subscription
from app.models.node import Node
from app.services.parser import fetch_subscription, parse_subscription_content

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


class SubscriptionCreate(BaseModel):
    name: Optional[str] = None
    url: str
    auto_refresh: bool = True
    interval_minutes: int = 360


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    auto_refresh: Optional[bool] = None
    interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None


async def _do_refresh(sub_id: int):
    """Background task: fetch subscription and upsert nodes using an isolated DB session."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return
        try:
            content, auto_name = await fetch_subscription(sub.url)
            # Auto-fill name if empty or default placeholder
            if auto_name and (not sub.name or sub.name in ("未命名", "", "新订阅源", "外部订阅")):
                sub.name = auto_name
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
            print(f"[Subscription] Fetched {len(new_nodes)} nodes for subscription: {sub.name}")
        except Exception as e:
            sub.last_fetched = datetime.now(timezone.utc)
            await db.commit()
            print(f"[Subscription] Failed to fetch {sub.url}: {e}")


@router.get("/")
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    try:
        result = await db.execute(select(Subscription).order_by(Subscription.id.desc()))
        subs = result.scalars().all()
        return [
            {
                "id": s.id,
                "name": getattr(s, "name", "未命名订阅") or "未命名订阅",
                "url": getattr(s, "url", ""),
                "auto_refresh": getattr(s, "auto_refresh", True),
                "interval_minutes": getattr(s, "interval_minutes", 360),
                "last_fetched": getattr(s, "last_fetched", None),
                "node_count": getattr(s, "node_count", 0),
                "enabled": getattr(s, "enabled", True),
                "created_at": getattr(s, "created_at", None),
            }
            for s in subs
        ]
    except Exception as e:
        print(f"[Subscription] Error listing subscriptions: {e}")
        return []


@router.post("/", status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    name = (body.name or "").strip() or "外部订阅"
    sub = Subscription(
        name=name,
        url=body.url.strip(),
        auto_refresh=body.auto_refresh,
        interval_minutes=body.interval_minutes or 360,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    # Auto-fetch nodes in background
    background_tasks.add_task(_do_refresh, sub.id)
    return {"id": sub.id, "name": sub.name, "message": "订阅已添加，正在后台拉取节点..."}


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
    from app.models.network import NetworkNode
    from app.models.test_result import TestResult

    result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")

    # Clean up associated nodes and relational references
    nodes_res = await db.execute(select(Node.id).where(Node.subscription_id == sub_id))
    node_ids = [r[0] for r in nodes_res.fetchall()]

    if node_ids:
        await db.execute(delete(NetworkNode).where(NetworkNode.node_id.in_(node_ids)))
        await db.execute(delete(TestResult).where(TestResult.node_id.in_(node_ids)))
        await db.execute(delete(Node).where(Node.id.in_(node_ids)))

    await db.delete(sub)
    await db.commit()
    return {"message": "订阅及其关联节点已成功删除"}



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
    background_tasks.add_task(_do_refresh, sub_id)
    return {"message": "正在后台刷新订阅..."}
