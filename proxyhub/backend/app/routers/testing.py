from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.auth import get_current_user
from app.models.node import Node
from app.models.test_result import TestResult
from app.services.speed_test import tcp_ping_batch, proxy_speed_test_batch
from app.services.purity_test import purity_test_batch

router = APIRouter(prefix="/api/test", tags=["testing"])


class TestRequest(BaseModel):
    node_ids: Optional[List[int]] = None   # None = test all enabled nodes
    subscription_id: Optional[int] = None


async def _get_nodes(db: AsyncSession, node_ids=None, subscription_id=None) -> list:
    query = select(Node).where(Node.enabled == True)
    if node_ids:
        query = query.where(Node.id.in_(node_ids))
    elif subscription_id:
        query = query.where(Node.subscription_id == subscription_id)
    result = await db.execute(query)
    return result.scalars().all()


def _node_to_dict(n: Node) -> dict:
    return {
        "id": n.id, "name": n.name, "protocol": n.protocol,
        "address": n.address, "port": n.port,
        "extra": n.extra, "raw_config": n.raw_config,
    }


async def _run_tcp_ping(node_ids, subscription_id, db: AsyncSession):
    nodes = await _get_nodes(db, node_ids, subscription_id)
    if not nodes:
        return
    node_dicts = [_node_to_dict(n) for n in nodes]
    results = await tcp_ping_batch(node_dicts)

    node_map = {n.id: n for n in nodes}
    now = datetime.now(timezone.utc)
    for r in results:
        node = node_map.get(r["id"])
        if node:
            node.latency_ms = r["latency_ms"]
            node.status = r["status"]
            node.last_tested = now
            tr = TestResult(
                node_id=r["id"],
                test_type="tcp_ping",
                success=r["status"] == "ok",
                latency_ms=r["latency_ms"],
            )
            db.add(tr)
    await db.commit()


async def _run_proxy_test(node_ids, subscription_id, db: AsyncSession):
    nodes = await _get_nodes(db, node_ids, subscription_id)
    # Only test nodes that passed TCP ping
    nodes = [n for n in nodes if n.status == "ok"]
    if not nodes:
        return
    node_dicts = [_node_to_dict(n) for n in nodes]
    results = await proxy_speed_test_batch(node_dicts)

    node_map = {n.id: n for n in nodes}
    now = datetime.now(timezone.utc)
    for r in results:
        node = node_map.get(r["id"])
        if node:
            node.real_latency_ms = r.get("latency_ms")
            node.download_speed = r.get("download_mbps")
            node.last_tested = now
            tr = TestResult(
                node_id=r["id"],
                test_type="proxy_speed",
                success=r.get("success", False),
                latency_ms=r.get("latency_ms"),
                download_mbps=r.get("download_mbps"),
                details={"error": r.get("error")},
            )
            db.add(tr)
    await db.commit()


async def _run_purity(node_ids, subscription_id, db: AsyncSession):
    nodes = await _get_nodes(db, node_ids, subscription_id)
    nodes = [n for n in nodes if n.status == "ok"]
    if not nodes:
        return
    node_dicts = [_node_to_dict(n) for n in nodes]
    results = await purity_test_batch(node_dicts)

    node_map = {n.id: n for n in nodes}
    now = datetime.now(timezone.utc)
    for r in results:
        node = node_map.get(r["id"])
        if node:
            node.ip_address = r.get("ip_address")
            node.ip_country = r.get("ip_country")
            node.ip_org = r.get("ip_org")
            node.is_residential = r.get("is_residential")
            node.netflix_unlock = r.get("netflix_unlock")
            node.openai_unlock = r.get("openai_unlock")
            node.purity_status = r.get("purity_status", "unknown")
            node.last_tested = now
            tr = TestResult(
                node_id=r["id"],
                test_type="purity",
                success=r.get("success", False),
                details={k: v for k, v in r.items() if k != "id"},
            )
            db.add(tr)
    await db.commit()


@router.post("/tcp-ping")
async def start_tcp_ping(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_tcp_ping, body.node_ids, body.subscription_id, db)
    return {"message": "TCP Ping 测试已开始，请稍后刷新节点列表查看结果"}


@router.post("/proxy-speed")
async def start_proxy_speed(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_proxy_test, body.node_ids, body.subscription_id, db)
    return {"message": "代理测速已开始（仅测 TCP Ping 通过的节点）"}


@router.post("/purity")
async def start_purity_test(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_purity, body.node_ids, body.subscription_id, db)
    return {"message": "纯净度检测已开始"}


@router.post("/full")
async def start_full_test(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Run TCP ping → proxy speed → purity in sequence."""
    async def full_pipeline(node_ids, subscription_id, db):
        await _run_tcp_ping(node_ids, subscription_id, db)
        await _run_proxy_test(node_ids, subscription_id, db)
        await _run_purity(node_ids, subscription_id, db)

    background_tasks.add_task(full_pipeline, body.node_ids, body.subscription_id, db)
    return {"message": "全量测试已开始（TCP Ping → 代理测速 → 纯净度检测）"}


@router.get("/results")
async def get_test_results(
    node_id: Optional[int] = None,
    test_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = select(TestResult).order_by(TestResult.tested_at.desc()).limit(limit)
    if node_id:
        query = query.where(TestResult.node_id == node_id)
    if test_type:
        query = query.where(TestResult.test_type == test_type)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "id": r.id, "node_id": r.node_id, "test_type": r.test_type,
            "success": r.success, "latency_ms": r.latency_ms,
            "download_mbps": r.download_mbps, "details": r.details,
            "tested_at": r.tested_at,
        }
        for r in rows
    ]
