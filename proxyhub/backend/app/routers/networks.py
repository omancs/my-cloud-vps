import secrets
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.auth import get_current_user
from app.models.network import Network, NetworkNode
from app.models.node import Node
from app.models.rule import CustomRule
from app.services.exporter import export_v2ray
from app.services.rule_engine import build_clash_subscription
from app.services.purity_test import _infer_country_from_name

router = APIRouter(prefix="/api/networks", tags=["networks"])


class NetworkCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sort_by: str = "latency"
    auto_update: bool = False


class NetworkUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_by: Optional[str] = None
    auto_update: Optional[bool] = None


class AddNodeToNetwork(BaseModel):
    node_ids: List[int]


class SmartSelectRequest(BaseModel):
    max_total: int = 50
    max_per_country: int = 5
    prefer_clean: bool = True


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
            "id": n.id,
            "name": n.name,
            "description": n.description,
            "sort_by": n.sort_by,
            "token": n.token,
            "auto_update": n.auto_update,
            "node_count": len(n.network_nodes),
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
    return {"id": net.id, "token": net.token, "message": "网络分组已创建"}


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


@router.post("/{network_id}/reset-token")
async def reset_network_token(
    network_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(Network).where(Network.id == network_id))
    net = result.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="网络分组不存在")
    net.token = secrets.token_hex(8)
    await db.commit()
    return {"token": net.token, "message": "订阅 Token 已重置"}


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
            "id": nn.node.id,
            "name": nn.node.name,
            "protocol": nn.node.protocol,
            "address": nn.node.address,
            "port": nn.node.port,
            "latency_ms": nn.node.latency_ms,
            "real_latency_ms": nn.node.real_latency_ms,
            "download_speed": nn.node.download_speed,
            "ip_country": nn.node.ip_country,
            "purity_status": nn.node.purity_status,
            "netflix_unlock": nn.node.netflix_unlock,
            "openai_unlock": nn.node.openai_unlock,
            "status": nn.node.status,
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


async def _execute_smart_select(network_id: int, max_total: int, max_per_country: int, db: AsyncSession) -> int:
    """Core smart selection algorithm: pick best max_total nodes (<= max_per_country per country)."""
    # 1. Fetch all enabled nodes
    result = await db.execute(select(Node).where(Node.enabled == True))
    all_nodes = result.scalars().all()
    if not all_nodes:
        return 0

    # 2. Score each node
    candidates = []
    for node in all_nodes:
        # Effective latency
        lat = node.real_latency_ms or node.latency_ms
        if lat is None or lat > 4000 or node.status == "timeout":
            continue

        # Country
        country = node.ip_country or _infer_country_from_name(node.name) or "OTHER"
        country = country.upper()

        # Score calculation: lower latency is better, purity adds big boost
        # Base latency score (0 to 100)
        lat_score = max(0, 100 - (lat / 30.0))

        # Purity bonus
        purity_bonus = {
            "clean": 50,
            "partial": 25,
            "dirty": 0,
            "unknown": 5,
        }.get(node.purity_status, 5)

        # Unlock bonus
        unlock_bonus = (10 if node.netflix_unlock else 0) + (10 if node.openai_unlock else 0)
        speed_bonus = min(20, (node.download_speed or 0) * 2)

        total_score = lat_score + purity_bonus + unlock_bonus + speed_bonus

        candidates.append({
            "node": node,
            "country": country,
            "latency": lat,
            "score": total_score,
        })

    if not candidates:
        return 0

    # 3. Group by country and sort by score descending
    country_groups = defaultdict(list)
    for c in candidates:
        country_groups[c["country"]].append(c)

    for country in country_groups:
        country_groups[country].sort(key=lambda x: x["score"], reverse=True)

    # 4. Pick top N per country
    selected_pool = []
    for country, group in country_groups.items():
        selected_pool.extend(group[:max_per_country])

    # 5. Sort all selected candidates by overall score and take max_total
    selected_pool.sort(key=lambda x: x["score"], reverse=True)
    final_nodes = selected_pool[:max_total]

    # 6. Replace network nodes
    await db.execute(delete(NetworkNode).where(NetworkNode.network_id == network_id))
    for priority, item in enumerate(final_nodes):
        nn = NetworkNode(network_id=network_id, node_id=item["node"].id, priority=priority)
        db.add(nn)
    await db.commit()

    return len(final_nodes)


@router.post("/{network_id}/smart-select")
async def smart_select_nodes(
    network_id: int,
    body: SmartSelectRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Auto-select top N nodes with balanced country representation (max 5 per country)."""
    net_result = await db.execute(select(Network).where(Network.id == network_id))
    net = net_result.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="网络分组不存在")

    selected_count = await _execute_smart_select(network_id, body.max_total, body.max_per_country, db)
    return {
        "message": f"已智能优选并导入 {selected_count} 个节点（单国家上限 {body.max_per_country} 个）",
        "selected_count": selected_count,
    }


# ─── Subscription Export Endpoints with Token Verification ───

subscribe_router = APIRouter(prefix="/subscribe", tags=["subscribe"])


async def _get_validated_network_nodes(network_id: int, token: Optional[str], db: AsyncSession) -> tuple:
    net_res = await db.execute(select(Network).where(Network.id == network_id))
    net = net_res.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # If network has a token configured, verify it
    if net.token and token != net.token:
        raise HTTPException(status_code=403, detail="Invalid subscription token")

    result = await db.execute(
        select(NetworkNode)
        .where(NetworkNode.network_id == network_id)
        .options(selectinload(NetworkNode.node))
        .order_by(NetworkNode.priority.asc())
    )
    nns = result.scalars().all()
    node_dicts = [
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
        if nn.node and nn.node.enabled
    ]
    return net, node_dicts


@subscribe_router.get("/{network_id}/clash")
async def subscribe_clash(
    network_id: int,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import PlainTextResponse

    net, nodes = await _get_validated_network_nodes(network_id, token, db)

    # Load custom rules
    rule_result = await db.execute(
        select(CustomRule)
        .where(CustomRule.enabled == True)
        .order_by(CustomRule.priority.asc())
    )
    custom_rules = [
        {"rule_type": r.rule_type, "pattern": r.pattern, "match_type": r.match_type, "enabled": r.enabled}
        for r in rule_result.scalars().all()
    ]

    content = build_clash_subscription(nodes, custom_rules, network_name=net.name)
    headers = {
        "Content-Disposition": f'attachment; filename="{net.name}.yaml"',
        "profile-title": net.name,
    }
    return PlainTextResponse(content, media_type="text/yaml; charset=utf-8", headers=headers)


@subscribe_router.get("/{network_id}/v2ray")
async def subscribe_v2ray(
    network_id: int,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import PlainTextResponse

    net, nodes = await _get_validated_network_nodes(network_id, token, db)
    content = export_v2ray(nodes)
    headers = {
        "Content-Disposition": f'attachment; filename="{net.name}.txt"',
        "profile-title": net.name,
    }
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8", headers=headers)
