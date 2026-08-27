from app.routers.auth import router as auth_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.nodes import router as nodes_router
from app.routers.networks import router as networks_router, subscribe_router
from app.routers.testing import router as testing_router
from app.routers.traffic import router as traffic_router
from app.routers.rules import router as rules_router

__all__ = [
    "auth_router",
    "subscriptions_router",
    "nodes_router",
    "networks_router",
    "subscribe_router",
    "testing_router",
    "traffic_router",
    "rules_router",
]

