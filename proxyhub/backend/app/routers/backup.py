"""
Backup & Restore router:
- Export full database snapshot as JSON file
- One-click restore from JSON backup snapshot
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.auth import get_current_user
from app.models.subscription import Subscription
from app.models.node import Node
from app.models.network import Network, NetworkNode
from app.models.rule import CustomRule
from app.models.traffic import TrafficConfig

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/export")
async def export_backup(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Export all tables as JSON backup file."""
    # 1. Subscriptions
    subs_res = await db.execute(select(Subscription))
    subs = [
        {
            "id": s.id, "name": s.name, "url": s.url,
            "auto_refresh": s.auto_refresh, "interval_minutes": s.interval_minutes,
            "enabled": s.enabled,
        }
        for s in subs_res.scalars().all()
    ]

    # 2. Nodes
    nodes_res = await db.execute(select(Node))
    nodes = [
        {
            "id": n.id, "subscription_id": n.subscription_id, "name": n.name,
            "protocol": n.protocol, "address": n.address, "port": n.port,
            "raw_config": n.raw_config, "extra": n.extra, "enabled": n.enabled,
            "ip_country": n.ip_country, "is_residential": n.is_residential,
            "netflix_unlock": n.netflix_unlock, "openai_unlock": n.openai_unlock,
            "youtube_unlock": n.youtube_unlock, "tags": n.tags,
        }
        for n in nodes_res.scalars().all()
    ]

    # 3. Networks
    nets_res = await db.execute(select(Network))
    nets = [
        {
            "id": net.id, "name": net.name, "description": net.description,
            "sort_by": net.sort_by, "token": net.token, "auto_update": net.auto_update,
        }
        for net in nets_res.scalars().all()
    ]

    # 4. Network Nodes
    nns_res = await db.execute(select(NetworkNode))
    nns = [
        {"network_id": nn.network_id, "node_id": nn.node_id, "priority": nn.priority}
        for nn in nns_res.scalars().all()
    ]

    # 5. Rules
    rules_res = await db.execute(select(CustomRule))
    rules = [
        {
            "id": r.id, "rule_type": r.rule_type, "pattern": r.pattern,
            "match_type": r.match_type, "priority": r.priority, "enabled": r.enabled,
        }
        for r in rules_res.scalars().all()
    ]

    data = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "subscriptions": subs,
        "nodes": nodes,
        "networks": nets,
        "network_nodes": nns,
        "custom_rules": rules,
    }

    content = json.dumps(data, indent=2, ensure_ascii=False)
    filename = f"proxyhub_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_backup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Restore database from JSON backup snapshot."""
    try:
        raw_bytes = await file.read()
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效的备份 JSON 文件: {e}")

    # Clear current relational links first
    await db.execute(delete(NetworkNode))
    await db.execute(delete(Node))
    await db.execute(delete(Subscription))
    await db.execute(delete(Network))
    await db.execute(delete(CustomRule))

    # Restore Subscriptions
    for s_dict in payload.get("subscriptions", []):
        sub = Subscription(**s_dict)
        db.add(sub)
    await db.flush()

    # Restore Nodes
    for n_dict in payload.get("nodes", []):
        node = Node(**n_dict)
        db.add(node)
    await db.flush()

    # Restore Networks
    for net_dict in payload.get("networks", []):
        net = Network(**net_dict)
        db.add(net)
    await db.flush()

    # Restore Network Nodes
    for nn_dict in payload.get("network_nodes", []):
        nn = NetworkNode(**nn_dict)
        db.add(nn)

    # Restore Rules
    for r_dict in payload.get("custom_rules", []):
        rule = CustomRule(**r_dict)
        db.add(rule)

    await db.commit()
    return {"message": "备份数据已成功完整恢复！"}
