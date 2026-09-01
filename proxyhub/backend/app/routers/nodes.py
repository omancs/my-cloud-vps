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

    try:
        # Total count
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        try:
            query = query.order_by(Node.id.desc()).offset((page - 1) * page_size).limit(page_size)
            result = await db.execute(query)
            nodes = result.scalars().all()
        except Exception:
            # Fallback if query fails
            query = select(Node).offset((page - 1) * page_size).limit(page_size)
            result = await db.execute(query)
            nodes = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_node_to_dict(n) for n in nodes],
        }
    except Exception as e:
        print(f"[Nodes] Error list_nodes: {e}")
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "items": [],
        }


def _node_to_dict(n: Node) -> dict:
    import json
    raw_tags = getattr(n, "tags", None)
    if isinstance(raw_tags, list):
        tags = raw_tags
    elif isinstance(raw_tags, str):
        try:
            tags = json.loads(raw_tags)
        except Exception:
            tags = []
    else:
        tags = []

    return {
        "id": n.id,
        "subscription_id": n.subscription_id,
        "name": n.name,
        "protocol": n.protocol,
        "address": n.address,
        "port": n.port,
        "enabled": n.enabled,
        "latency_ms": getattr(n, "latency_ms", None),
        "real_latency_ms": getattr(n, "real_latency_ms", None),
        "download_speed": getattr(n, "download_speed", None),
        "status": getattr(n, "status", "unknown"),
        "ip_address": getattr(n, "ip_address", None),
        "ip_country": getattr(n, "ip_country", None),
        "ip_org": getattr(n, "ip_org", None),
        "is_residential": getattr(n, "is_residential", False),
        "netflix_unlock": getattr(n, "netflix_unlock", False),
        "openai_unlock": getattr(n, "openai_unlock", False),
        "youtube_unlock": getattr(n, "youtube_unlock", False),
        "purity_status": getattr(n, "purity_status", "unknown"),
        "fail_count": getattr(n, "fail_count", 0) or 0,
        "is_quarantined": bool(getattr(n, "is_quarantined", False)),
        "tags": tags,
        "last_tested": getattr(n, "last_tested", None),
        "created_at": getattr(n, "created_at", None),
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
