import os
import re

# 1. Add to requirements.txt
req_path = "d:/Quantx/Email Verifier/requirements.txt"
if os.path.exists(req_path):
    with open(req_path, "r", encoding='utf-8') as f:
        reqs = f.read()
    if "aioredis" not in reqs:
        reqs += "\naioredis"
    with open(req_path, "w", encoding='utf-8') as f:
        f.write(reqs)

# 2. Add to .env and .env.example
env_str = "\n# Redis native URL\nREDIS_URL=redis://:YOURPASSWORD@127.0.0.1:6379/0\n"
env_examples = [".env", ".env.example"]
for path in env_examples:
    full_path = f"d:/Quantx/Email Verifier/{path}"
    # create if not exists
    if not os.path.exists(full_path):
        with open(full_path, "w", encoding='utf-8') as f:
            f.write(env_str)
    else:
        with open(full_path, "r", encoding='utf-8') as f:
            content = f.read()
        if "REDIS_URL=" not in content:
            with open(full_path, "a", encoding='utf-8') as f:
                f.write(env_str)

# 3. Create cache.py
cache_code = """import os
import json
import logging
import aioredis
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

async def cache_hgetall(key: str):
    try:
        r = get_redis()
        data = await r.hgetall(key)
        return data if data else None
    except Exception as e:
        logger.warning(f"Redis cache_hgetall error for {key}: {e}")
        return None
"""
with open("d:/Quantx/Email Verifier/cache.py", "w", encoding='utf-8') as f:
    f.write(cache_code)

# 4. Modify verifier.py
with open("d:/Quantx/Email Verifier/core/verifier.py", "r", encoding='utf-8') as f:
    v_text = f.read()

v_text = "from cache import cache_get, cache_set\n" + v_text
# Remove DOMAIN_CACHE dict definitions
v_text = re.sub(r'DOMAIN_CACHE\s*=\s*\{\}\n?', '', v_text)

# Replace domain cache read behavior 
target_read = """    cached = DOMAIN_CACHE.get(domain)
    if cached and time.time() - cached['timestamp'] < 600:"""
rep_read = """    cached = await cache_get(f"mx:{domain}")
    if cached:"""
v_text = v_text.replace(target_read, rep_read)

# Replace DOMAIN_CACHE writes 
target_write1 = """                DOMAIN_CACHE[domain] = {
                    'mx_hosts': [], 'spf': spf_exists, 'dmarc': dmarc_exists,
                    'has_mx': False, 'catch_all': False, 'timestamp': time.time()
                }"""
rep_write1 = """                await cache_set(f"mx:{domain}", {
                    'mx_hosts': [], 'spf': spf_exists, 'dmarc': dmarc_exists,
                    'has_mx': False, 'catch_all': False
                }, ttl=3600)"""
v_text = v_text.replace(target_write1, rep_write1)

target_write2 = """        DOMAIN_CACHE[domain] = {
            'mx_hosts': mx_hosts,
            'spf': spf_exists,
            'dmarc': dmarc_exists,
            'has_mx': True,
            'catch_all': False,
            'timestamp': time.time()
        }"""
rep_write2 = """        await cache_set(f"mx:{domain}", {
            'mx_hosts': mx_hosts,
            'spf': spf_exists,
            'dmarc': dmarc_exists,
            'has_mx': True,
            'catch_all': False
        }, ttl=3600)"""
v_text = v_text.replace(target_write2, rep_write2)

target_write3 = """        if domain in DOMAIN_CACHE:
            DOMAIN_CACHE[domain]['catch_all'] = True"""
rep_write3 = """        cached = await cache_get(f"mx:{domain}")
        if cached:
            cached['catch_all'] = True
            await cache_set(f"mx:{domain}", cached, ttl=3600)"""
v_text = v_text.replace(target_write3, rep_write3)

with open("d:/Quantx/Email Verifier/core/verifier.py", "w", encoding='utf-8') as f:
    f.write(v_text)

# 5. Modify routes/api.py
with open("d:/Quantx/Email Verifier/routes/api.py", "r", encoding='utf-8') as f:
    a_text = f.read()

# remove global _bulk_jobs
a_text = re.sub(r'_bulk_jobs:\s*dict\[str,\s*dict\]\s*=\s*\{\}.*?\n', '', a_text)

a_text = "from cache import cache_hset, cache_hgetall\n" + a_text

target_process_bulk = """    job = _bulk_jobs.get(job_id)
    if not job or job["status"] != "processing":
        return"""
rep_process_bulk = """    job = await cache_hgetall(f"job:{job_id}")
    if not job or job.get("status") != "processing":
        return"""
a_text = a_text.replace(target_process_bulk, rep_process_bulk)

target_chunk_update = """                job["processed"] = processed
                job["status"] = "processing" """
rep_chunk_update = """                await cache_hset(f"job:{job_id}", {
                    "processed": processed,
                    "status": "processing"
                }, ttl=86400)"""
a_text = a_text.replace(target_chunk_update, rep_chunk_update)

target_final_update = """        job["status"] = "completed"
        job["processed"] = total
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)"""
rep_final_update = """        await cache_hset(f"job:{job_id}", {
            "status": "completed",
            "processed": total
        }, ttl=86400)
    except Exception as e:
        await cache_hset(f"job:{job_id}", {
            "status": "failed",
            "error": str(e)
        }, ttl=86400)"""
a_text = a_text.replace(target_final_update, rep_final_update)

target_jobs_init = """    _bulk_jobs[job_id] = {
        "status": "processing",
        "total": len(emails),
        "processed": 0,
        "results_path": None,
        "error": None,
        "user_id": getattr(current_user, 'original_id', current_user.id),
    }"""
rep_jobs_init = """    await cache_hset(f"job:{job_id}", {
        "status": "processing",
        "total": len(emails),
        "processed": 0,
        "error": "",
        "user_id": getattr(current_user, 'original_id', current_user.id),
        "created_at": datetime.utcnow().isoformat()
    }, ttl=86400)"""
if "from datetime" not in a_text:
    a_text = "from datetime import datetime\n" + a_text
a_text = a_text.replace(target_jobs_init, rep_jobs_init)

target_get_job = """    job = _bulk_jobs.get(job_id)
    if not job:"""
rep_get_job = """    job = await cache_hgetall(f"job:{job_id}")
    if not job:"""
a_text = a_text.replace(target_get_job, rep_get_job)

target_pct = '        "progress_pct": round(100 * job["processed"] / job["total"], 1) if job["total"] else 0,'
rep_pct = '        "progress_pct": round(100 * float(job["processed"]) / float(job["total"]), 1) if float(job.get("total", 0)) else 0,'
a_text = a_text.replace(target_pct, rep_pct)

# Redis stores as string, need conversion
target_stat_id = 'job.get("user_id") != true_user_id'
rep_stat_id = 'str(job.get("user_id")) != str(true_user_id)'
a_text = a_text.replace(target_stat_id, rep_stat_id)

target_tot_int = 'job["total"]'
rep_tot_int = 'int(job["total"]) if "total" in job else 0'
# We have 3 occurrences, let's just do a manual replace for the JSON return safely
target_return_status = """    return {
        "job_id": job_id,
        "status": job["status"],
        "total": job["total"],
        "processed": job["processed"],"""
rep_return_status = """    return {
        "job_id": job_id,
        "status": job.get("status"),
        "total": int(job.get("total", 0)),
        "processed": int(job.get("processed", 0)),"""
a_text = a_text.replace(target_return_status, rep_return_status)

with open("d:/Quantx/Email Verifier/routes/api.py", "w", encoding='utf-8') as f:
    f.write(a_text)

print("Saved")
