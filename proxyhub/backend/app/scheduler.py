"""
APScheduler background tasks:
- Auto-refresh subscriptions based on their interval
- Scheduled TCP ping sweep
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.node import Node
from app.services.speed_test import tcp_ping_batch

scheduler = AsyncIOScheduler(timezone="UTC")


async def auto_refresh_subscriptions():
    """Check all auto-refresh subscriptions and refresh if due."""
    from app.routers.subscriptions import _do_refresh
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                Subscription.auto_refresh == True,
                Subscription.enabled == True,
            )
        )
        subs = result.scalars().all()
        now = datetime.now(timezone.utc)
        for sub in subs:
            if sub.last_fetched is None:
                due = True
            else:
                last = sub.last_fetched.replace(tzinfo=timezone.utc) if sub.last_fetched.tzinfo is None else sub.last_fetched
                due = (now - last) >= timedelta(minutes=sub.interval_minutes)
            if due:
                try:
                    await _do_refresh(sub.id, db)
                    print(f"[Scheduler] Refreshed subscription: {sub.name}")
                except Exception as e:
                    print(f"[Scheduler] Failed to refresh {sub.name}: {e}")


async def scheduled_tcp_ping():
    """Run TCP ping on all enabled nodes."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Node).where(Node.enabled == True))
        nodes = result.scalars().all()
        if not nodes:
            return
        node_dicts = [{"id": n.id, "address": n.address, "port": n.port} for n in nodes]
        results = await tcp_ping_batch(node_dicts)
        node_map = {n.id: n for n in nodes}
        now = datetime.now(timezone.utc)
        for r in results:
            node = node_map.get(r["id"])
            if node:
                node.latency_ms = r["latency_ms"]
                node.status = r["status"]
                node.last_tested = now
        await db.commit()
        print(f"[Scheduler] TCP ping completed for {len(nodes)} nodes")


def start_scheduler():
    # Check subscriptions every 5 minutes
    scheduler.add_job(
        auto_refresh_subscriptions,
        trigger=IntervalTrigger(minutes=5),
        id="auto_refresh",
        replace_existing=True,
    )
    # TCP ping every 30 minutes
    scheduler.add_job(
        scheduled_tcp_ping,
        trigger=IntervalTrigger(minutes=30),
        id="tcp_ping_sweep",
        replace_existing=True,
    )
    # Traffic snapshot every 10 minutes
    from app.services.traffic_service import snapshot_traffic
    scheduler.add_job(
        snapshot_traffic,
        trigger=IntervalTrigger(minutes=10),
        id="traffic_snapshot",
        replace_existing=True,
    )
    scheduler.start()
    print("[Scheduler] Started")



def stop_scheduler():
    scheduler.shutdown(wait=False)
