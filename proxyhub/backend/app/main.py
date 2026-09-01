from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.services.mihomo_service import ensure_mihomo_running
from app.routers import (
    auth_router, subscriptions_router, nodes_router,
    networks_router, subscribe_router, testing_router,
    traffic_router, rules_router, backup_router,
)
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    try:
        await ensure_mihomo_running()
    except Exception as e:
        print(f"[Mihomo] Init warning: {e}")
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    description="代理订阅聚合管理平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(subscriptions_router)
app.include_router(nodes_router)
app.include_router(networks_router)
app.include_router(subscribe_router)
app.include_router(testing_router)
app.include_router(traffic_router)
app.include_router(rules_router)
app.include_router(backup_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
