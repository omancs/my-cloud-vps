from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ProxyHub"
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Admin credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:////app/data/proxyhub.db"

    # Xray core binary path (for real proxy speed test)
    XRAY_BINARY_PATH: str = "/usr/local/bin/xray"

    # Test settings
    TCP_PING_TIMEOUT: float = 5.0       # seconds
    TCP_PING_CONCURRENCY: int = 50      # parallel connections
    PROXY_TEST_TIMEOUT: int = 15        # seconds
    PROXY_TEST_URL: str = "https://www.google.com"
    PROXY_TEST_PORT_START: int = 10800  # local port range for xray instances

    # Purity test
    IP_CHECK_URL: str = "http://ip-api.com/json"
    NETFLIX_CHECK_URL: str = "https://www.netflix.com/title/81280792"
    OPENAI_CHECK_URL: str = "https://chat.openai.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
