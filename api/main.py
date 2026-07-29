import os
import secrets
import string

import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

app = FastAPI(
    title="URL Shortener API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 6
MAX_COLLISION_RETRIES = 5


class ShortenRequest(BaseModel):
    url: HttpUrl


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@app.post("/api/shorten")
def shorten(req: ShortenRequest):
    """Generate a short code for the given URL."""
    for _ in range(MAX_COLLISION_RETRIES):
        code = generate_code()
        if r.set(f"url:{code}", str(req.url), nx=True):
            r.incr("stats:total_urls")
            return {"code": code, "short_url": f"/r/{code}"}
    raise HTTPException(status_code=500, detail="Could not generate a unique code")


@app.get("/r/{code}")
def redirect(code: str):
    """Redirect a short code to its original URL."""
    url = r.get(f"url:{code}")
    if url is None:
        raise HTTPException(status_code=404, detail="Code not found")
    r.incr(f"stats:hits:{code}")
    return RedirectResponse(url, status_code=307)


@app.get("/api/stats/{code}")
def stats(code: str):
    """Return the hit count for a short code."""
    if r.get(f"url:{code}") is None:
        raise HTTPException(status_code=404, detail="Code not found")
    return {"code": code, "hits": int(r.get(f"stats:hits:{code}") or 0)}


@app.get("/healthz")
def healthz():
    """Health check verifying Redis connectivity."""
    try:
        r.ping()
    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ok"}
