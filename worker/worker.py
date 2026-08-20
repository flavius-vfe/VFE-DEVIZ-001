import os
import time
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
INTERVAL = int(os.getenv("REFRESH_INTERVAL_SECONDS", "86400"))
RETRY_INTERVAL = int(os.getenv("DATABASE_RETRY_SECONDS", "5"))
HEALTH_FILE = os.getenv("HEALTH_FILE", "/tmp/vfe-deviz-worker-health")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def tick():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"[{datetime.now(timezone.utc).isoformat()}] worker OK; adaptoarele retailerilor se activează în M4.", flush=True)
    with open(HEALTH_FILE, "w", encoding="utf-8") as health_file:
        health_file.write(str(time.time()))

if __name__ == "__main__":
    while True:
        try:
            tick()
        except Exception as exc:
            print(f"worker error: {exc}", flush=True)
            time.sleep(RETRY_INTERVAL)
            continue
        time.sleep(INTERVAL)
