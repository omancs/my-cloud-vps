from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.auth import get_current_user
from app.models.node import Node

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


class NodeCreate(BaseModel):
    name: str
    protocol: str
    address: str
    port: int
    raw_config: Optional[str] = None
    extra: Optional[dict] = None


@router.get("/")
async def list_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    subscription_id: Optional[int] = None,
    protocol: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = select(Node)
    if subscription_id is not None:
        query = query.where(Node.subscription_id == subscription_id)
    if protocol:
        query = query.where(Node.protocol == protocol)
    if status:
        query = query.where(Node.status == status)
    if search:
        query = query.where(
            (Node.name.ilike(f"%{search}%")) | (Node.address.ilike(f"%{search}%"))
        )

    # Total count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(Node.latency_ms.asc().nullslast()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    nodes = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_node_to_dict(n) for n in nodes],
    }


def _node_to_dict(n: Node) -> dict:
    return {
        "id": n.id,
        "subscription_id": n.subscription_id,
        "name": n.name,
        "protocol": n.protocol,
        "address": n.address,
        "port": n.port,
        "enabled": n.enabled,
        "latency_ms": n.latency_ms,
        "real_latency_ms": n.real_latency_ms,
        "download_speed": n.download_speed,
        "status": n.status,
        "ip_address": n.ip_address,
        "ip_country": n.ip_country,
        "ip_org": n.ip_org,
        "is_residential": n.is_residential,
        "netflix_unlock": n.netflix_unlock,
        "openai_unlock": n.openai_unlock,
        "youtube_unlock": getattr(n, "youtube_unlock", False),
        "purity_status": n.purity_status,
        "last_tested": n.last_tested,
        "created_at": n.created_at,
    }


@router.post("/", status_code=201)
async def create_node(
    body: NodeCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    node = Node(**body.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return {"id": node.id, "message": "节点已添加"}


@router.delete("/{node_id}")
async def delete_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    await db.delete(node)
    await db.commit()
    return {"message": "删除成功"}


@router.delete("/batch/delete")
async def batch_delete_nodes(
    node_ids: List[int],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    await db.execute(delete(Node).where(Node.id.in_(node_ids)))
    await db.commit()
    return {"message": f"已删除 {len(node_ids)} 个节点"}


@router.get("/{node_id}")
async def get_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    return _node_to_dict(node)
