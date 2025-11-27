"""
API Gateway Service
Lightweight reverse proxy with authentication and rate limiting
"""
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import os
import time
from typing import Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import hashlib

app = FastAPI(
    title="API Gateway",
    description="Reverse proxy with auth and rate limiting",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service registry
SERVICES = {
    "task": os.getenv("TASK_API_URL", "http://localhost:8010"),
    "library": os.getenv("LIBRARY_SERVICE_URL", "http://localhost:8001"),
    "knowledge": os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8005"),
    "learning": os.getenv("LEARNING_SERVICE_URL", "http://localhost:8006"),
    "code": os.getenv("CODE_RUNNER_URL", "http://localhost:8003"),
}

# HTTP client with connection pooling
http_client = httpx.AsyncClient(
    timeout=120.0,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
)


# ============== Rate Limiting ==============

@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting"""
    tokens: float
    last_update: float
    max_tokens: int = 100
    refill_rate: float = 10  # tokens per second


class RateLimiter:
    """Simple in-memory rate limiter using token bucket algorithm"""
    
    def __init__(self):
        self.buckets: Dict[str, RateLimitBucket] = {}
        self.lock = asyncio.Lock()
    
    async def is_allowed(self, key: str, cost: int = 1) -> bool:
        """Check if request is allowed and consume tokens"""
        async with self.lock:
            now = time.time()
            
            if key not in self.buckets:
                self.buckets[key] = RateLimitBucket(
                    tokens=100,
                    last_update=now
                )
            
            bucket = self.buckets[key]
            
            # Refill tokens
            elapsed = now - bucket.last_update
            bucket.tokens = min(
                bucket.max_tokens,
                bucket.tokens + elapsed * bucket.refill_rate
            )
            bucket.last_update = now
            
            # Check and consume
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True
            
            return False
    
    def get_remaining(self, key: str) -> int:
        """Get remaining tokens for key"""
        if key not in self.buckets:
            return 100
        return int(self.buckets[key].tokens)


rate_limiter = RateLimiter()


# ============== Authentication ==============

API_KEYS = {
    os.getenv("API_KEY_ADMIN", "admin-key-123"): {"role": "admin", "rate_limit": 1000},
    os.getenv("API_KEY_USER", "user-key-456"): {"role": "user", "rate_limit": 100},
}


async def verify_api_key(request: Request) -> Optional[Dict]:
    """Verify API key from header or query param"""
    # Check header
    api_key = request.headers.get("X-API-Key")
    
    # Check query param as fallback
    if not api_key:
        api_key = request.query_params.get("api_key")
    
    # Allow unauthenticated for health checks
    if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
        return {"role": "anonymous", "rate_limit": 10}
    
    if not api_key:
        # Allow anonymous with low rate limit
        return {"role": "anonymous", "rate_limit": 10}
    
    if api_key in API_KEYS:
        return API_KEYS[api_key]
    
    raise HTTPException(status_code=401, detail="Invalid API key")


# ============== Request Logging ==============

class RequestLogger:
    """Simple request logger"""
    
    def __init__(self):
        self.requests: list = []
        self.max_entries = 1000
    
    def log(self, request: Request, response_status: int, duration: float):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "path": str(request.url.path),
            "status": response_status,
            "duration_ms": round(duration * 1000, 2),
            "client_ip": request.client.host if request.client else "unknown"
        }
        
        self.requests.append(entry)
        
        # Trim old entries
        if len(self.requests) > self.max_entries:
            self.requests = self.requests[-self.max_entries:]
    
    def get_stats(self) -> Dict:
        if not self.requests:
            return {"total": 0}
        
        total = len(self.requests)
        avg_duration = sum(r["duration_ms"] for r in self.requests) / total
        error_count = len([r for r in self.requests if r["status"] >= 400])
        
        return {
            "total_requests": total,
            "avg_duration_ms": round(avg_duration, 2),
            "error_rate": round(error_count / total, 3),
            "recent": self.requests[-10:]
        }


logger = RequestLogger()


# ============== Proxy Logic ==============

async def proxy_request(
    service: str,
    path: str,
    request: Request,
    method: str = None
) -> Response:
    """Proxy request to backend service"""
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found")
    
    url = f"{SERVICES[service]}{path}"
    method = method or request.method
    
    # Forward headers (except host)
    headers = dict(request.headers)
    headers.pop("host", None)
    
    # Get body for POST/PUT/PATCH
    body = None
    if method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    
    try:
        response = await http_client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
            params=dict(request.query_params)
        )
        
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get("content-type")
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {e}")


# ============== Middleware ==============

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting based on client IP or API key"""
    start_time = time.time()
    
    # Get rate limit key
    api_key = request.headers.get("X-API-Key", "")
    client_ip = request.client.host if request.client else "unknown"
    rate_key = api_key or client_ip
    
    # Check rate limit
    if not await rate_limiter.is_allowed(rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": 10}
        )
    
    # Process request
    response = await call_next(request)
    
    # Add rate limit headers
    remaining = rate_limiter.get_remaining(rate_key)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Limit"] = "100"
    
    # Log request
    duration = time.time() - start_time
    logger.log(request, response.status_code, duration)
    
    return response


# ============== Routes ==============

@app.get("/")
async def root():
    return {"service": "API Gateway", "version": "2.0.0"}


@app.get("/health")
async def health():
    """Health check with service status"""
    services_status = {}
    
    for name, url in SERVICES.items():
        try:
            resp = await http_client.get(f"{url}/health", timeout=3.0)
            services_status[name] = "ok" if resp.status_code == 200 else "error"
        except:
            services_status[name] = "unavailable"
    
    return {
        "status": "ok",
        "gateway": "api_gateway",
        "services": services_status,
        "stats": logger.get_stats()
    }


# ============== Task API Routes ==============

@app.api_route("/api/generate", methods=["POST"])
async def generate_task(request: Request):
    """Proxy to Task API - generate task"""
    return await proxy_request("task", "/generate", request)


@app.api_route("/api/templates", methods=["GET"])
@app.api_route("/api/templates/{path:path}", methods=["GET"])
async def templates(request: Request, path: str = ""):
    """Proxy to Task API - templates"""
    return await proxy_request("task", f"/templates/{path}" if path else "/templates", request)


# ============== Library Routes ==============

@app.api_route("/api/sections", methods=["GET"])
@app.api_route("/api/sections/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def sections(request: Request, path: str = ""):
    """Proxy to Library Service"""
    return await proxy_request("library", f"/sections/{path}" if path else "/sections", request)


@app.api_route("/api/folders", methods=["GET", "POST"])
@app.api_route("/api/folders/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def folders(request: Request, path: str = ""):
    """Proxy to Library Service"""
    return await proxy_request("library", f"/folders/{path}" if path else "/folders", request)


@app.api_route("/api/tasks", methods=["GET", "POST"])
@app.api_route("/api/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def tasks(request: Request, path: str = ""):
    """Proxy to Library Service"""
    return await proxy_request("library", f"/tasks/{path}" if path else "/tasks", request)


# ============== Knowledge Routes ==============

@app.api_route("/api/concepts", methods=["GET", "POST"])
@app.api_route("/api/concepts/{path:path}", methods=["GET", "POST"])
async def concepts(request: Request, path: str = ""):
    """Proxy to Knowledge Service"""
    return await proxy_request("knowledge", f"/concepts/{path}" if path else "/concepts", request)


@app.api_route("/api/concepts/analyze", methods=["POST"])
async def analyze_concepts(request: Request):
    """Proxy to Knowledge Service - analyze"""
    return await proxy_request("knowledge", "/analyze", request)


@app.api_route("/api/search", methods=["POST"])
async def semantic_search(request: Request):
    """Proxy to Knowledge Service - semantic search"""
    return await proxy_request("knowledge", "/search", request)


# ============== Learning Routes ==============

@app.api_route("/api/users/{user_id}", methods=["GET"])
async def user_profile(request: Request, user_id: str):
    """Proxy to Learning Service"""
    return await proxy_request("learning", f"/users/{user_id}", request)


@app.api_route("/api/users/{user_id}/progress", methods=["GET"])
async def user_progress(request: Request, user_id: str):
    """Proxy to Learning Service"""
    return await proxy_request("learning", f"/users/{user_id}/progress", request)


@app.api_route("/api/stats/{user_id}", methods=["GET"])
async def user_stats(request: Request, user_id: str):
    """Proxy to Learning Service - detailed stats"""
    return await proxy_request("learning", f"/stats/{user_id}", request)


@app.api_route("/api/attempt", methods=["POST"])
async def record_attempt(request: Request):
    """Proxy to Learning Service"""
    return await proxy_request("learning", "/attempt", request)


@app.api_route("/api/recommendations/{user_id}", methods=["GET", "POST"])
async def recommendations(request: Request, user_id: str):
    """Proxy to Learning Service"""
    return await proxy_request("learning", f"/recommendations/{user_id}", request)


@app.api_route("/api/review-queue/{user_id}", methods=["GET"])
async def review_queue(request: Request, user_id: str):
    """Proxy to Learning Service"""
    return await proxy_request("learning", f"/review-queue/{user_id}", request)


# ============== Code Runner Routes ==============

@app.api_route("/api/run", methods=["POST"])
async def run_code(request: Request):
    """Proxy to Code Runner"""
    return await proxy_request("code", "/run", request)


@app.api_route("/api/validate", methods=["POST"])
async def validate_code(request: Request):
    """Proxy to Code Runner"""
    return await proxy_request("code", "/validate", request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
