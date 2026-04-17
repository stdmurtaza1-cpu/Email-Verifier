import asyncio
from redis.asyncio import Redis, ConnectionPool

redis_pool = ConnectionPool.from_url("redis://127.0.0.1:6379/0", decode_responses=True)

def get_redis() -> Redis:
    return Redis(connection_pool=redis_pool)

async def tick(i):
    r = get_redis()
    await r.set("foo", str(i))
    val = await r.get("foo")
    print(f"Loop {i}: {val}")

for i in range(2):
    try:
        asyncio.run(tick(i))
    except Exception as e:
        print(f"Error {i}: {e}")
