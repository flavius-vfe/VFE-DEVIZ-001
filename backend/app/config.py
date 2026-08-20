from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./deviz.sqlite3")
    server_ip: str = os.getenv("SERVER_IP", "192.168.0.50")
    frontend_port: int = int(os.getenv("FRONTEND_PORT", "3080"))
    backend_port: int = int(os.getenv("BACKEND_PORT", "8030"))
    session_days: int = int(os.getenv("SESSION_DAYS", "7"))
    data_root: str = os.getenv("DATA_ROOT", "/data")

settings = Settings()
