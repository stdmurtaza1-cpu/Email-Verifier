import os
import socket
import asyncio
import logging
from cache import get_redis

logger = logging.getLogger("worker_registry")

_WORKER_NAME = None

def get_worker_name(worker_type: str = "web"):
    global _WORKER_NAME
    if _WORKER_NAME is None:
        host = socket.gethostname()
        uuid_short = os.urandom(4).hex()
        # Using env variable WORKER_NAME if passed, else host-based
        raw_name = os.getenv("WORKER_NAME", f"{host}-{uuid_short}")
        _WORKER_NAME = f"{worker_type}_{raw_name}"
        logger.info(f"[WORKER_REGISTRY] Initialized Identity: {_WORKER_NAME}")
    return _WORKER_NAME

async def start_worker_heartbeat(worker_type: str):
    worker_name = get_worker_name(worker_type)
    r = get_redis()
    
    # Register explicitly in active cluster
    await r.sadd("active_workers", worker_name)
    
    while True:
        try:
            # 45 second expiry, renewed every 30 seconds
            await r.set(f"worker:{worker_name}:heartbeat", "alive", ex=45)
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            # Clean shutdown removal
            try:
                await r.srem("active_workers", worker_name)
                await r.delete(f"worker:{worker_name}:heartbeat")
            except Exception:
                pass
            break
        except Exception as e:
            logger.error(f"[WORKER_REGISTRY] Heartbeat fault for {worker_name}: {e}")
            await asyncio.sleep(10)
