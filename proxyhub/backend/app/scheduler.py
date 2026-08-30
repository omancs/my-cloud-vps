"""
APScheduler background tasks:
- Auto-refresh subscriptions based on their interval
- Scheduled TCP ping sweep
- Traffic snapshotting
- Daily automated node testing & smart network optimization
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.node import Node
from app.models.network import Network
from app.services.speed_test import tcp_ping_batch
from app.services.purity_test import purity_test_batch
from app.services.traffic_service import snapshot_traffic


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
                due = (now - last) >= timedelta(minutes=sub.interval_minutes or 360)
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
        results = await tcp_ping_batch(node_dicts, concurrency=50)
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


async def daily_maintenance_and_optimization():
    """Daily cron: test purity & auto-optimize networks with auto_update=True."""
    from app.routers.networks import _execute_smart_select
    print("[Scheduler] Running daily automated maintenance...")
    async with AsyncSessionLocal() as db:
        # 1. TCP ping
        await scheduled_tcp_ping()

        # 2. Purity check online nodes
        res = await db.execute(select(Node).where(Node.enabled == True, Node.status == "ok"))
        online_nodes = res.scalars().all()
        if online_nodes:
            dicts = [
                {"id": n.id, "name": n.name, "protocol": n.protocol, "address": n.address, "port": n.port, "extra": n.extra}
                for n in online_nodes[:100]  # Cap daily batch test
            ]
            purity_results = await purity_test_batch(dicts, concurrency=4)
            node_map = {n.id: n for n in online_nodes}
            for r in purity_results:
                node = node_map.get(r["id"])
                if node:
                    node.ip_country = r.get("ip_country") or node.ip_country
                    node.ip_org = r.get("ip_org")
                    node.is_residential = r.get("is_residential")
                    node.netflix_unlock = r.get("netflix_unlock")
                    node.openai_unlock = r.get("openai_unlock")
                    node.purity_status = r.get("purity_status", "unknown")
            await db.commit()

        # 3. Auto-update auto-managed networks
        net_res = await db.execute(select(Network).where(Network.auto_update == True))
        auto_nets = net_res.scalars().all()
        for net in auto_nets:
            count = await _execute_smart_select(net.id, max_total=50, max_per_country=5, db=db)
            print(f"[Scheduler] Auto-updated network '{net.name}' with {count} optimal nodes")


def start_scheduler():
    # Check subscriptions every 5 minutes
    scheduler.add_job(
        auto_refresh_subscriptions,
        trigger=IntervalTrigger(minutes=5),
        id="auto_refresh",
        replace_existing=True,
    )
    # TCP ping sweep every 30 minutes
    scheduler.add_job(
        scheduled_tcp_ping,
        trigger=IntervalTrigger(minutes=30),
        id="tcp_ping_sweep",
        replace_existing=True,
    )
    # Traffic snapshot every 10 minutes
    scheduler.add_job(
        snapshot_traffic,
        trigger=IntervalTrigger(minutes=10),
        id="traffic_snapshot",
        replace_existing=True,
    )
    # Daily full maintenance & smart optimization at 04:00 UTC
    scheduler.add_job(
        daily_maintenance_and_optimization,
        trigger=CronTrigger(hour=4, minute=0),
        id="daily_maintenance",
        replace_existing=True,
    )
    scheduler.start()
    print("[Scheduler] All scheduled tasks started.")


def stop_scheduler():
    scheduler.shutdown(wait=False)
