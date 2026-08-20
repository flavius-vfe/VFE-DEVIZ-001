import os
import time
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
INTERVAL = int(os.getenv("REFRESH_INTERVAL_SECONDS", "86400"))
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def tick():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"[{datetime.now(timezone.utc).isoformat()}] worker OK; adaptoarele retailerilor se activează în M4.", flush=True)

if __name__ == "__main__":
    while True:
        try:
            tick()
        except Exception as exc:
            print(f"worker error: {exc}", flush=True)
        time.sleep(INTERVAL)
