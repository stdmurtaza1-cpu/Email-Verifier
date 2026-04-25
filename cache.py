import os
import json
import logging
import asyncio
import time
from redis.asyncio import Redis, ConnectionPool

logger = logging.getLogger("cache")

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Create a shared connection pool
redis_pool = ConnectionPool.from_url(REDIS_URL, decode_responses=True)

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.expires = {}

    def _cleanup(self):
        now = time.time()
        expired = [k for k, v in self.expires.items() if v < now]
        for k in expired:
            self.store.pop(k, None)
            self.expires.pop(k, None)

    async def get(self, key):
        self._cleanup()
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self._cleanup()
        self.store[key] = value
        if ex:
            self.expires[key] = time.time() + ex
            
    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
            self.expires.pop(k, None)

    async def hset(self, key, mapping):
        self._cleanup()
        if key not in self.store or not isinstance(self.store[key], dict):
            self.store[key] = {}
        self.store[key].update(mapping)

    async def hdel(self, key, *fields):
        self._cleanup()
        if key in self.store and isinstance(self.store[key], dict):
            for f in fields:
                self.store[key].pop(f, None)

    async def hgetall(self, key):
        self._cleanup()
        return self.store.get(key, {})

    async def sadd(self, key, *values):
        self._cleanup()
        if key not in self.store or not isinstance(self.store[key], set):
            self.store[key] = set()
        self.store[key].update(values)

    async def srem(self, key, *values):
        self._cleanup()
        if key in self.store and isinstance(self.store[key], set):
            self.store[key].difference_update(values)

    async def smembers(self, key):
        self._cleanup()
        return self.store.get(key, set())

    async def incr(self, key):
        self._cleanup()
        val = self.store.get(key, 0)
        try:
            val = int(val) + 1
        except:
            val = 1
        self.store[key] = val
        return val

    async def expire(self, key, time_seconds):
        if key in self.store:
            self.expires[key] = time.time() + time_seconds

    async def exists(self, key):
        self._cleanup()
        return 1 if key in self.store else 0


class RedisProxy:
    def __init__(self):
        self.real_redis = Redis(connection_pool=redis_pool)
        self.fake_redis = FakeRedis()
        self.use_fake = False

    def __getattr__(self, name):
        async def wrapper(*args, **kwargs):
            if self.use_fake:
                func = getattr(self.fake_redis, name)
                return await func(*args, **kwargs)
            try:
                func = getattr(self.real_redis, name)
                return await func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Redis connection failed, switching to in-memory fallback. Error: {e}")
                self.use_fake = True
                func = getattr(self.fake_redis, name)
                return await func(*args, **kwargs)
        return wrapper

proxy_instance = RedisProxy()

def get_redis():
    return proxy_instance

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
