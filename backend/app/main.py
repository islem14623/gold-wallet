import os

import psycopg
import redis
from fastapi import FastAPI, HTTPException

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    database_url = os.getenv("DATABASE_URL")
    redis_url = os.getenv("REDIS_URL")
    checks = {"db": "error", "redis": "error"}

    try:
        if not database_url:
            raise ValueError("DATABASE_URL is not configured")
        with psycopg.connect(database_url) as connection:
            connection.execute("SELECT 1")
        checks["db"] = "ok"
    except Exception:
        pass

    try:
        if not redis_url:
            raise ValueError("REDIS_URL is not configured")
        client = redis.Redis.from_url(redis_url)
        try:
            client.ping()
            checks["redis"] = "ok"
        finally:
            client.close()
    except Exception:
        pass

    if checks["db"] != "ok" or checks["redis"] != "ok":
        raise HTTPException(status_code=503, detail={"status": "error", **checks})

    return {"status": "ok", **checks}
