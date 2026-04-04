from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import logging
from contextlib import asynccontextmanager
from routes.api import router as api_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router
from routes.storage import router as storage_router
from routes.partner import router as partner_router
from routes.billing import router as billing_router

logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup checks ────────────────────────────────────────────────────────
    from core.verifier import SMTP_IPS, HELO_DOMAIN
    if not SMTP_IPS:
        logger.warning(
            "SMTP_IPS not configured. Using single server IP for all SMTP verifications. "
            "Risk of IP blacklisting at high volume. "
            "Set SMTP_SOURCE_IPS in .env to enable IP rotation."
        )
    else:
        logger.info(f"SMTP IP rotation active: {len(SMTP_IPS)} IP(s) configured.")
    logger.info(f"SMTP HELO domain: {HELO_DOMAIN}")
    yield
    # ── Shutdown (nothing to clean up yet) ───────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["10000/minute"])

app = FastAPI(title="Email Verifier Ninja", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
    )

@app.get("/admin-panel", include_in_schema=False)
async def serve_admin_panel():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "admin.html"))

app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(storage_router, prefix="/api/storage")
app.include_router(partner_router, prefix="/api/partner")
app.include_router(billing_router, prefix="/billing")

# Ensure static and upload dirs exist (jobs dir for bulk 1M results)
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs(os.path.join("uploads", "jobs"), exist_ok=True)

# Serve static files
# This custom StaticFiles handler serves index.html for all non-API routes,
# unless the path specifically targets /admin-panel, in which case the
# @app.get("/admin-panel") route handles it.
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, request: Request) -> FileResponse:
        if path.startswith("api/") or path.startswith("admin/"):
            # Let FastAPI handle API and admin routes. If they reached here, they are not found.
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="API route not found")
        
        # For all other paths, try to serve the requested file.
        # If not found, serve index.html for SPA routing.
        try:
            return await super().get_response(path, request)
        except Exception:
            # If the file doesn't exist, serve index.html
            return await super().get_response("index.html", request)

app.mount("/", SPAStaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
