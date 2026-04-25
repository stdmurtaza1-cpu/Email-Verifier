from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import logging
import asyncio
import smtplib
from contextlib import asynccontextmanager
from database import SessionLocal, SmtpIp
from cache import cache_hset, cache_hgetall, get_redis
import core.worker_registry as worker_registry
from routes.api import router as api_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router
from routes.storage import router as storage_router
from routes.partner import router as partner_router
from routes.billing import router as billing_router

logger = logging.getLogger("main")

async def ip_health_monitor_daemon():
    while True:
        try:
            await asyncio.sleep(60) # Accelerated sweep rate for multi-node monitoring
            r = get_redis()
            
            # ── 1. Parent Orchestrator: Dead Worker Detection ─────────────────
            active_cluster = await r.smembers("active_workers")
            for node in active_cluster:
                if not await r.exists(f"worker:{node}:heartbeat"):
                    logger.warning(f"[PARENT MONITOR] 💀 Dead Worker Detected: {node} - Reclaiming IP resources!")
                    orphaned_ips = await cache_hgetall(f"worker:{node}:ips")
                    
                    if orphaned_ips:
                        for ip_addr, health_score in orphaned_ips.items():
                            logger.info(f"[PARENT MONITOR] Reassigned Orphaned IP {ip_addr} back to Global Gateway.")
                            await cache_hset("smtp:active_ips", {ip_addr: health_score})
                        await r.delete(f"worker:{node}:ips")
                        
                    await r.srem("active_workers", node)
                    await r.incr("system:worker_crashes")
            
            # ── 2. Cooldown Autonomous Recovery Matrix ────────────────────────
            loop = asyncio.get_running_loop()
            
            def _check():
                db = SessionLocal()
                try:
                    cooldown_ips = db.query(SmtpIp).filter(SmtpIp.status == "cooldown").all()
                    if not cooldown_ips: return []
                    
                    recovered = []
                    target = "gmail-smtp-in.l.google.com"
                    for ip_record in cooldown_ips:
                        try:
                            # Verify outbound socket cleanly opens
                            smtp = smtplib.SMTP(timeout=5, source_address=(ip_record.ip_address, 0))
                            smtp.connect(target, 25)
                            smtp.quit()
                            
                            ip_record.status = "active"
                            recovered.append((ip_record.ip_address, ip_record.health_score))
                        except Exception as e:
                            pass # Still dead
                            
                    if recovered:
                        db.commit()
                    return recovered
                except Exception as e:
                    logger.error(f"[DAEMON] DB error: {e}")
                    return []
                finally:
                    db.close()
            
            recovered_ips = await loop.run_in_executor(None, _check)
            
            if recovered_ips:
                for ip, score in recovered_ips:
                    logger.info(f"[DAEMON] 🏥 IP {ip} successfully recovered! Re-added to dynamic rotation.")
                    await r.delete(f"ip_fails:{ip}")
                    await cache_hset("smtp:active_ips", {ip: score})
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[DAEMON] General execution fault: {e}")


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
    
    if "154.38.182.28" in SMTP_IPS:
        try:
            import socket
            s = socket.create_connection(("154.38.182.28", 25), timeout=5)
            s.recv(1024)
            s.close()
            logger.info("SMTP IP 154.38.182.28 verified and ready")
        except Exception as e:
            logger.warning(f"SMTP IP unreachable: {e}")
    
    daemon_task = asyncio.create_task(ip_health_monitor_daemon())
    heartbeat_task = asyncio.create_task(worker_registry.start_worker_heartbeat("web"))
    
    yield
    # ── Shutdown (nothing to clean up yet) ───────────────────────────────────
    daemon_task.cancel()
    heartbeat_task.cancel()
    
    try:
        await asyncio.gather(daemon_task, heartbeat_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

limiter = Limiter(key_func=get_remote_address, default_limits=["10000/minute"])

app = FastAPI(title="Veridrax", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    # Apply permissive CSP to Admin Panel to prevent blocking of Chart.js and other assets
    if "/admin-panel" in request.url.path or request.url.path.endswith(".js") or request.url.path.endswith(".css"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' * 'unsafe-inline' 'unsafe-eval'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https:;"
        )
    return response

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

@app.get("/developer/docs", include_in_schema=False)
async def serve_api_docs():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "api-docs.html"))

app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(storage_router, prefix="/api/storage")
app.include_router(partner_router, prefix="/api/partner")
app.include_router(billing_router, prefix="/billing")

# Ensure static and upload dirs exist (jobs dir for bulk 1M results)
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs(os.path.join("uploads", "jobs"), exist_ok=True)
os.makedirs(os.path.join("uploads", "images"), exist_ok=True)

app.mount("/uploads/images", StaticFiles(directory="uploads/images"), name="images")

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
