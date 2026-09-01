from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import logging

from app.database import get_db, AsyncSessionLocal
from app.auth import get_current_user
from app.models.node import Node
from app.models.test_result import TestResult
from app.services.speed_test import (
    batch_test_latency, batch_test_bandwidth, get_test_progress
)
from app.services.purity_test import purity_test_batch
from app.services.node_enhancer import compute_smart_tags

logger = logging.getLogger("testing")
router = APIRouter(prefix="/api/test", tags=["testing"])


class TestRequest(BaseModel):
    node_ids: Optional[List[int]] = None   # None = test all enabled nodes
    subscription_id: Optional[int] = None


async def _get_node_records(db, node_ids=None, subscription_id=None) -> list:
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
        "is_quarantined": getattr(n, "is_quarantined", False),
    }


async def _run_latency_test(node_ids=None, subscription_id=None):
    """Background task: execute fast UnifiedDelay and update health & smart tags."""
    async with AsyncSessionLocal() as db:
        try:
            nodes = await _get_node_records(db, node_ids, subscription_id)
            if not nodes:
                return
            node_dicts = [_node_to_dict(n) for n in nodes]
            results = await batch_test_latency(node_dicts, concurrency=25)

            node_map = {n.id: n for n in nodes}
            now = datetime.now(timezone.utc)
            for r in results:
                node = node_map.get(r["id"])
                if node:
                    is_ok = (r["status"] == "ok")
                    node.latency_ms = r["latency_ms"]
                    node.status = r["status"]
                    node.last_tested = now

                    # Health Quarantine Logic
                    if is_ok:
                        node.fail_count = 0
                        node.is_quarantined = False
                    else:
                        node.fail_count = (node.fail_count or 0) + 1
                        if node.fail_count >= 3:
                            node.is_quarantined = True

                    # Update smart tags
                    node.tags = compute_smart_tags(node)

                    tr = TestResult(
                        node_id=r["id"],
                        test_type="latency",
                        success=is_ok,
                        latency_ms=r["latency_ms"],
                    )
                    db.add(tr)
            await db.commit()
            print(f"[Testing] Latency test completed for {len(nodes)} nodes.")
        except Exception as e:
            print(f"[Testing] Latency test error: {e}")


async def _run_bandwidth_test(node_ids=None, subscription_id=None):
    """Background task: execute bandwidth download speed test."""
    async with AsyncSessionLocal() as db:
        try:
            nodes = await _get_node_records(db, node_ids, subscription_id)
            if not nodes:
                return
            candidate_nodes = [n for n in nodes if not getattr(n, "is_quarantined", False)]
            if not candidate_nodes:
                candidate_nodes = nodes
            node_dicts = [_node_to_dict(n) for n in candidate_nodes]
            results = await batch_test_bandwidth(node_dicts, concurrency=4)

            node_map = {n.id: n for n in candidate_nodes}
            now = datetime.now(timezone.utc)
            for r in results:
                node = node_map.get(r["id"])
                if node:
                    if r.get("success"):
                        node.real_latency_ms = r.get("latency_ms")
                        node.download_speed = r.get("download_mbps")
                        node.status = "ok"
                        node.fail_count = 0
                        node.is_quarantined = False
                    else:
                        node.fail_count = (node.fail_count or 0) + 1
                        if node.fail_count >= 3:
                            node.is_quarantined = True

                    node.tags = compute_smart_tags(node)
                    node.last_tested = now
                    tr = TestResult(
                        node_id=r["id"],
                        test_type="bandwidth",
                        success=r.get("success", False),
                        latency_ms=r.get("latency_ms"),
                        download_mbps=r.get("download_mbps"),
                    )
                    db.add(tr)
            await db.commit()
            print(f"[Testing] Bandwidth test completed for {len(candidate_nodes)} nodes.")
        except Exception as e:
            print(f"[Testing] Bandwidth test error: {e}")


async def _run_purity(node_ids=None, subscription_id=None):
    """Background task: execute IP purity & stream unlock test via resident Mihomo."""
    async with AsyncSessionLocal() as db:
        try:
            nodes = await _get_node_records(db, node_ids, subscription_id)
            if not nodes:
                return
            candidate_nodes = [n for n in nodes if not getattr(n, "is_quarantined", False)]
            if not candidate_nodes:
                candidate_nodes = nodes
            node_dicts = [_node_to_dict(n) for n in candidate_nodes]
            results = await purity_test_batch(node_dicts, concurrency=3)

            node_map = {n.id: n for n in candidate_nodes}
            now = datetime.now(timezone.utc)
            for r in results:
                node = node_map.get(r["id"])
                if node:
                    if r.get("ip_country"):
                        node.ip_country = r.get("ip_country")
                    node.ip_address = r.get("ip_address")
                    node.ip_org = r.get("ip_org")
                    node.is_residential = r.get("is_residential")
                    node.netflix_unlock = r.get("netflix_unlock")
                    node.openai_unlock = r.get("openai_unlock")
                    node.youtube_unlock = r.get("youtube_unlock")
                    node.purity_status = r.get("purity_status", "unknown")
                    node.tags = compute_smart_tags(node)
                    node.last_tested = now
                    tr = TestResult(
                        node_id=r["id"],
                        test_type="purity",
                        success=r.get("success", False),
                        details={k: v for k, v in r.items() if k != "id"},
                    )
                    db.add(tr)
            await db.commit()
            print(f"[Testing] Purity test completed for {len(candidate_nodes)} nodes.")
        except Exception as e:
            print(f"[Testing] Purity test error: {e}")


async def _run_full_pipeline(node_ids=None, subscription_id=None):
    """Full pipeline: fast UnifiedDelay -> Bandwidth test -> Purity unlock test."""
    await _run_latency_test(node_ids, subscription_id)
    await _run_bandwidth_test(node_ids, subscription_id)
    await _run_purity(node_ids, subscription_id)


# ─────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────

@router.get("/progress")
async def get_progress(
    _: str = Depends(get_current_user),
):
    """Poll live test task progress."""
    return get_test_progress()


@router.post("/tcp-ping")
@router.post("/latency")
async def start_latency_test(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_latency_test, body.node_ids, body.subscription_id)
    return {"message": "⚡ 毫秒级 UnifiedDelay 测试已启动（Mihomo 极速并发）"}


@router.post("/proxy-speed")
@router.post("/bandwidth")
async def start_bandwidth_test(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_bandwidth_test, body.node_ids, body.subscription_id)
    return {"message": "🚀 带宽吞吐深度测速已启动..."}


@router.post("/purity")
async def start_purity_test(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_purity, body.node_ids, body.subscription_id)
    return {"message": "🔍 节点住宅 IP 与流媒体解锁检测已启动..."}


@router.post("/full")
async def start_full_test(
    body: TestRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_current_user),
):
    background_tasks.add_task(_run_full_pipeline, body.node_ids, body.subscription_id)
    return {"message": "🔄 全量三阶段流水线测试已启动（快速延迟 → 带宽测速 → IP/流媒体检测）"}


@router.get("/results")
async def get_test_results(
    node_id: Optional[int] = None,
    test_type: Optional[str] = None,
    limit: int = 100,
    db=Depends(get_db),
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
