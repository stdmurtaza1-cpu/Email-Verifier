import os
import json
import logging
from redis.asyncio import Redis, ConnectionPool

logger = logging.getLogger("cache")

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Create a shared connection pool
redis_pool = ConnectionPool.from_url(REDIS_URL, decode_responses=True)

def get_redis() -> Redis:
    return Redis(connection_pool=redis_pool)

async def cache_set(key: str, value, ttl: int = 3600):
    try:
        r = get_redis()
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        await r.set(key, val_str, ex=ttl)
    except Exception as e:
        logger.warning(f"Redis cache_set error for {key}: {e}")

async def cache_get(key: str):
    try:
        r = get_redis()
        val = await r.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
    except Exception as e:
        logger.warning(f"Redis cache_get error for {key}: {e}")
    return None

async def cache_delete(key: str):
    try:
        r = get_redis()
        await r.delete(key)
    except Exception as e:
        logger.warning(f"Redis cache_delete error for {key}: {e}")

async def cache_hset(key: str, mapping: dict, ttl: int = None):
    try:
        r = get_redis()
        safe_mapping = {str(k): str(v) for k, v in mapping.items() if v is not None}
        if safe_mapping:
            await r.hset(key, mapping=safe_mapping)
        if ttl:
            await r.expire(key, ttl)
    except Exception as e:
        logger.warning(f"Redis cache_hset error for {key}: {e}")

async def cache_hdel(key: str, *fields):
    try:
        if not fields: return
        r = get_redis()
        await r.hdel(key, *fields)
    except Exception as e:
        logger.warning(f"Redis cache_hdel error for {key}: {e}")

async def cache_hgetall(key: str):
    try:
        r = get_redis()
        data = await r.hgetall(key)
        return data if data else None
    except Exception as e:
        logger.warning(f"Redis cache_hgetall error for {key}: {e}")
        return None

async def cache_sadd(key: str, *values):
    try:
        if not values: return
        r = get_redis()
        await r.sadd(key, *values)
    except Exception as e:
        logger.warning(f"Redis cache_sadd error for {key}: {e}")

async def cache_srem(key: str, *values):
    try:
        if not values: return
        r = get_redis()
        await r.srem(key, *values)
    except Exception as e:
        logger.warning(f"Redis cache_srem error for {key}: {e}")

async def cache_smembers(key: str) -> set:
    try:
        r = get_redis()
        return await r.smembers(key)
    except Exception as e:
        logger.warning(f"Redis cache_smembers error for {key}: {e}")
        return set()
