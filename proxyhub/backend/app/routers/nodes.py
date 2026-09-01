from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from pydantic import BaseModel
from typing import Optional, List
from collections import defaultdict

from app.database import get_db
from app.auth import get_current_user
from app.models.node import Node
from app.services.node_enhancer import clean_node_name, standardize_node_name, compute_smart_tags

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


class NodeCreate(BaseModel):
    name: str
    protocol: str
    address: str
    port: int
    raw_config: Optional[str] = None
    extra: Optional[dict] = None


class BatchActionRequest(BaseModel):
    node_ids: Optional[List[int]] = None   # None = all nodes


@router.get("/")
async def list_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    subscription_id: Optional[int] = None,
    protocol: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    is_quarantined: Optional[bool] = None,
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
    if is_quarantined is not None:
        query = query.where(Node.is_quarantined == is_quarantined)
    if search:
        query = query.where(
            (Node.name.ilike(f"%{search}%")) | (Node.address.ilike(f"%{search}%"))
        )

    # Total count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(Node.is_quarantined.asc(), Node.latency_ms.asc().nullslast()).offset((page - 1) * page_size).limit(page_size)
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
        "fail_count": getattr(n, "fail_count", 0),
        "is_quarantined": getattr(n, "is_quarantined", False),
        "tags": getattr(n, "tags", []) or [],
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
    node.tags = compute_smart_tags(node)
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return {"id": node.id, "message": "节点已添加"}


@router.post("/batch/rename")
async def batch_rename_nodes(
    body: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Clean advertising keywords and standardize names with Country Flags."""
    query = select(Node)
    if body.node_ids:
        query = query.where(Node.id.in_(body.node_ids))
    result = await db.execute(query)
    nodes = result.scalars().all()

    # Group by country to assign sequential numbers
    country_counters = defaultdict(int)
    for node in nodes:
        c = (node.ip_country or "").upper()
        country_counters[c] += 1
        node.name = standardize_node_name(node.name, country_counters[c], node.ip_country)
        node.tags = compute_smart_tags(node)

    await db.commit()
    return {"message": f"已成功净化重命名 {len(nodes)} 个节点"}


@router.post("/batch/tag")
async def batch_tag_nodes(
    body: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Automatically recalculate smart tags for nodes."""
    query = select(Node)
    if body.node_ids:
        query = query.where(Node.id.in_(body.node_ids))
    result = await db.execute(query)
    nodes = result.scalars().all()

    for node in nodes:
        node.tags = compute_smart_tags(node)

    await db.commit()
    return {"message": f"已成功生成 {len(nodes)} 个节点的智能标签"}


@router.post("/batch/unquarantine")
async def batch_unquarantine_nodes(
    body: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Release nodes from quarantine pool."""
    query = select(Node)
    if body.node_ids:
        query = query.where(Node.id.in_(body.node_ids))
    else:
        query = query.where(Node.is_quarantined == True)
    result = await db.execute(query)
    nodes = result.scalars().all()

    for node in nodes:
        node.is_quarantined = False
        node.fail_count = 0

    await db.commit()
    return {"message": f"已成功将 {len(nodes)} 个节点移出隔离区"}


@router.delete("/{node_id}")
async def delete_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    from app.models.network import NetworkNode
    from app.models.test_result import TestResult

    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    await db.execute(delete(NetworkNode).where(NetworkNode.node_id == node_id))
    await db.execute(delete(TestResult).where(TestResult.node_id == node_id))
    await db.delete(node)
    await db.commit()
    return {"message": "节点已删除"}
