from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.auth import get_current_user
from app.models.network import Network, NetworkNode
from app.models.node import Node
from app.services.exporter import export_clash, export_v2ray

router = APIRouter(prefix="/api/networks", tags=["networks"])


class NetworkCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sort_by: str = "latency"


class NetworkUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_by: Optional[str] = None


class AddNodeToNetwork(BaseModel):
    node_ids: List[int]


@router.get("/")
async def list_networks(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(Network).options(selectinload(Network.network_nodes))
    )
    networks = result.scalars().all()
    return [
        {
            "id": n.id, "name": n.name, "description": n.description,
            "sort_by": n.sort_by, "node_count": len(n.network_nodes),
            "created_at": n.created_at,
        }
        for n in networks
    ]


@router.post("/", status_code=201)
async def create_network(
    body: NetworkCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    net = Network(**body.model_dump())
    db.add(net)
    await db.commit()
    await db.refresh(net)
    return {"id": net.id, "message": "网络分组已创建"}


@router.put("/{network_id}")
async def update_network(
    network_id: int,
    body: NetworkUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Network).where(Network.id == network_id))
    net = result.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="网络分组不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(net, field, value)
    await db.commit()
    return {"message": "更新成功"}


@router.delete("/{network_id}")
async def delete_network(
    network_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Network).where(Network.id == network_id))
    net = result.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="网络分组不存在")
    await db.delete(net)
    await db.commit()
    return {"message": "删除成功"}


@router.get("/{network_id}/nodes")
async def get_network_nodes(
    network_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(NetworkNode)
        .where(NetworkNode.network_id == network_id)
        .options(selectinload(NetworkNode.node))
        .order_by(NetworkNode.priority.asc())
    )
    nns = result.scalars().all()
    return [
        {
            "id": nn.node.id, "name": nn.node.name, "protocol": nn.node.protocol,
            "address": nn.node.address, "port": nn.node.port,
            "latency_ms": nn.node.latency_ms, "status": nn.node.status,
            "priority": nn.priority,
        }
        for nn in nns
    ]


@router.post("/{network_id}/nodes")
async def add_nodes_to_network(
    network_id: int,
    body: AddNodeToNetwork,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Network).where(Network.id == network_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="网络分组不存在")

    # Get current max priority
    existing = await db.execute(
        select(NetworkNode).where(NetworkNode.network_id == network_id)
    )
    current = existing.scalars().all()
    existing_ids = {nn.node_id for nn in current}
    max_priority = max((nn.priority for nn in current), default=-1)

    added = 0
    for i, node_id in enumerate(body.node_ids):
        if node_id in existing_ids:
            continue
        nn = NetworkNode(network_id=network_id, node_id=node_id, priority=max_priority + i + 1)
        db.add(nn)
        added += 1
    await db.commit()
    return {"message": f"已添加 {added} 个节点"}


@router.delete("/{network_id}/nodes/{node_id}")
async def remove_node_from_network(
    network_id: int,
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    await db.execute(
        delete(NetworkNode).where(
            NetworkNode.network_id == network_id,
            NetworkNode.node_id == node_id,
        )
    )
    await db.commit()
    return {"message": "已从分组移除"}


# ─── Subscription export endpoints (no auth needed for client use) ───

subscribe_router = APIRouter(prefix="/subscribe", tags=["subscribe"])


async def _get_network_node_dicts(network_id: int, db: AsyncSession) -> list:
    result = await db.execute(
        select(NetworkNode)
        .where(NetworkNode.network_id == network_id)
        .options(selectinload(NetworkNode.node))
        .order_by(NetworkNode.priority.asc())
    )
    nns = result.scalars().all()
    return [
        {
            "id": nn.node.id,
            "name": nn.node.name,
            "protocol": nn.node.protocol,
            "address": nn.node.address,
            "port": nn.node.port,
            "extra": nn.node.extra,
            "raw_config": nn.node.raw_config,
        }
        for nn in nns
        if nn.node.enabled
    ]


@subscribe_router.get("/{network_id}/clash")
async def subscribe_clash(network_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import PlainTextResponse
    nodes = await _get_network_node_dicts(network_id, db)
    content = export_clash(nodes)
    return PlainTextResponse(content, media_type="text/yaml; charset=utf-8")


@subscribe_router.get("/{network_id}/v2ray")
async def subscribe_v2ray(network_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import PlainTextResponse
    nodes = await _get_network_node_dicts(network_id, db)
    content = export_v2ray(nodes)
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")
