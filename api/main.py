import json
import logging
import os
import secrets
import string
import time

import redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

_LOG_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"taskName", "message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            {k: v for k, v in record.__dict__.items() if k not in _LOG_RESERVED}
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=LOG_LEVEL, handlers=[_handler])
logger = logging.getLogger("api")

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


@app.middleware("http")
async def access_log(request: Request, call_next):
    if request.url.path == "/healthz":
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return response


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
            # Log the target host only: query strings may carry sensitive data
            logger.info("url_shortened", extra={"code": code, "target_host": req.url.host})
            return {"code": code, "short_url": f"/r/{code}"}
    logger.error("code_generation_exhausted", extra={"retries": MAX_COLLISION_RETRIES})
    raise HTTPException(status_code=500, detail="Could not generate a unique code")


@app.get("/r/{code}")
def redirect(code: str):
    """Redirect a short code to its original URL."""
    url = r.get(f"url:{code}")
    if url is None:
        logger.warning("code_not_found", extra={"code": code})
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
        logger.error("redis_unavailable")
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ok"}
