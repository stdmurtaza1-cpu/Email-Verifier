from cache import cache_get, cache_set, cache_hgetall, cache_hdel, get_redis
import re
import os
import dns.resolver
import smtplib
import aiosmtplib
import python_socks
from python_socks.async_.asyncio import Proxy as AsyncProxy
import socket
import ssl
import asyncio
import random
import time
import logging
import socks
import socket
from typing import List, Tuple, Optional, Dict, Any
from functools import wraps
from database import SessionLocal, SmtpIp, Proxy
from core.worker_registry import get_worker_name
import math

# Setup detailed debug logging
logger = logging.getLogger("verifier")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')

# HELO/EHLO domain — set HELO_DOMAIN in .env to your actual sending domain
HELO_DOMAIN = os.getenv("HELO_DOMAIN", "mail.quantx-estimation.net")
EHLO_HOST = HELO_DOMAIN          # kept for backward-compat references
MAIL_FROM = f"verify@{HELO_DOMAIN}"

# SMTP source IP rotation — set SMTP_SOURCE_IPS in .env as a comma-separated list
# Leave unset to use the server's default outbound IP
SMTP_IPS = [ip.strip() for ip in os.getenv("SMTP_SOURCE_IPS", "").split(",") if ip.strip()]

DOMAIN_STATS = {}

ROLE_PATTERNS = [
    r'^admin', r'^support', r'^info', r'^sales', r'^contact', r'^billing',
    r'^help', r'^hello', r'^team', r'^jobs', r'^hr', r'^marketing',
    r'^webmaster', r'^postmaster', r'^abuse', r'^reply', r'^noreply', r'^no-reply',
    r'^dev', r'^office', r'^press', r'^pr', r'^ceo'
]

def _load_disposable_domains() -> set:
    """Load disposable domains from bundled list file (5000+ domains)."""
    domains = set()
    list_path = os.path.join(os.path.dirname(__file__), "data", "disposable_domains.txt")
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            for line in f:
                domain = line.strip().lower()
                if domain and not domain.startswith("#"):
                    domains.add(domain)
        logger.info(f"Loaded {len(domains)} disposable domains from blocklist.")
    except Exception as e:
        logger.warning(f"Could not load disposable domains file: {e}. Using fallback list.")
        domains = {
            "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
            "yopmail.com", "throwawaymail.com", "dispostable.com", "getairmail.com"
        }
    return domains

DISPOSABLE_DOMAINS = _load_disposable_domains()

KNOWN_CATCHALL = {
    'yahoo.com', 'yahoo.co.uk', 'yahoo.co.in',
    'yahoo.fr', 'yahoo.de', 'yahoo.es',
    'aol.com', 'aol.co.uk',
    'msn.com',
    'hotmail.com', 'hotmail.co.uk',
    'outlook.com', 'outlook.co.uk',
    'live.com', 'live.co.uk',
    'yandex.com', 'yandex.ru',
    'mail.ru',
}

FREE_EMAIL_DOMAINS = KNOWN_CATCHALL.union({
    'gmail.com', 'googlemail.com', 'icloud.com', 'mac.com', 'me.com'
})

DNS_SERVERS = ['8.8.8.8', '1.1.1.1', '9.9.9.9', '8.8.4.4']

def async_cache(ttl=3600, maxsize=2048):
    """In-process LRU-style cache with TTL and a hard size cap to prevent memory leaks."""
    cache = {}
    order = []
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key in cache:
                result, ts = cache[key]
                if time.time() - ts < ttl:
                    return result
                else:
                    del cache[key]
                    if key in order:
                        order.remove(key)
            result = await func(*args, **kwargs)
            cache[key] = (result, time.time())
            order.append(key)
            # Evict oldest entries when over capacity
            while len(order) > maxsize:
                oldest = order.pop(0)
                cache.pop(oldest, None)
            return result
        return wrapper
    return decorator

def get_resolver(nameserver=None):
    if nameserver:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [nameserver]
    else:
        # System resolver fallback
        resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 5
    resolver.lifetime = 10
    return resolver

@async_cache(ttl=3600)
async def resolve_host(hostname: str) -> str:
    loop = asyncio.get_running_loop()
    def _resolve():
        for dns_ip in ['8.8.8.8', '1.1.1.1', '9.9.9.9', None]:
            try:
                resolver = get_resolver(dns_ip)
                return str(resolver.resolve(hostname, 'A')[0])
            except Exception:
                continue
        return hostname
    return await loop.run_in_executor(None, _resolve)

@async_cache(ttl=3600)
async def get_mx(domain: str) -> Optional[List[str]]:
    domain_lower = domain.lower()
    if domain_lower == "gmail.com":
        return ["gmail-smtp-in.l.google.com"]
    elif domain_lower == "outlook.com":
        return ["outlook-com.olc.protection.outlook.com"]
    elif domain_lower == "yahoo.com":
        return ["mta5.am0.yahoodns.net"]

    loop = asyncio.get_running_loop()
    def _get():
        retries = 5
        for attempt in range(retries):
            servers = list(DNS_SERVERS)
            random.shuffle(servers)
            for nameserver in servers + [None]:
                try:
                    resolver = get_resolver(nameserver)
                    answers = resolver.resolve(domain, 'MX')
                    mx = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
                    return [h for _, h in mx]
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
                    logger.debug(f"DNS MX NoAnswer/NXDOMAIN for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
                except Exception as e:
                    logger.debug(f"DNS MX Error for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
        return []
    return await loop.run_in_executor(None, _get)

@async_cache(ttl=3600)
async def get_a_record(domain: str) -> Optional[List[str]]:
    loop = asyncio.get_running_loop()
    def _get():
        retries = 5
        for attempt in range(retries):
            servers = list(DNS_SERVERS)
            random.shuffle(servers)
            for nameserver in servers + [None]:
                try:
                    resolver = get_resolver(nameserver)
                    return [str(r) for r in resolver.resolve(domain, 'A')]
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
                    logger.debug(f"DNS A NoAnswer/NXDOMAIN for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
                except Exception as e:
                    logger.debug(f"DNS A Error for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
        return []
    return await loop.run_in_executor(None, _get)

@async_cache(ttl=3600)
async def check_spf(domain: str) -> bool:
    loop = asyncio.get_running_loop()
    def _get():
        retries = 5
        for attempt in range(retries):
            servers = list(DNS_SERVERS)
            random.shuffle(servers)
            for nameserver in servers + [None]:
                try:
                    resolver = get_resolver(nameserver)
                    for r in resolver.resolve(domain, 'TXT'):
                        if "spf1" in str(r).lower(): return True
                    return False
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
                    logger.debug(f"DNS TXT (SPF) NoAnswer/NXDOMAIN for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
                except Exception as e:
                    logger.debug(f"DNS TXT (SPF) Error for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
        return False
    return await loop.run_in_executor(None, _get)

@async_cache(ttl=3600)
async def check_dmarc(domain: str) -> bool:
    loop = asyncio.get_running_loop()
    def _get():
        retries = 5
        for attempt in range(retries):
            servers = list(DNS_SERVERS)
            random.shuffle(servers)
            for nameserver in servers + [None]:
                try:
                    resolver = get_resolver(nameserver)
                    resolver.resolve(f"_dmarc.{domain}", 'TXT')
                    return True
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
                    logger.debug(f"DNS TXT (DMARC) NoAnswer/NXDOMAIN for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
                except Exception as e:
                    logger.debug(f"DNS TXT (DMARC) Error for {domain} on {nameserver} (Attempt {attempt+1}): {e}")
                    continue
        return False
    return await loop.run_in_executor(None, _get)

async def _attempt_smtp_connection(target: str, port: int, mode: str, timeout_val: int, source_ip: Optional[str] = None, proxy: Optional[Proxy] = None):
    use_tls = (mode == 'ssl')
    
    tls_context = ssl.create_default_context()
    tls_context.check_hostname = False
    tls_context.verify_mode = ssl.CERT_NONE
    
    if proxy:
        try:
            proxy_type = python_socks.ProxyType.SOCKS5 if proxy.type.upper() == "SOCKS5" else python_socks.ProxyType.HTTP
            async_proxy = AsyncProxy.create(
                proxy_type=proxy_type,
                host=proxy.ip,
                port=proxy.port,
                username=proxy.username,
                password=proxy.password
            )
            sock = await async_proxy.connect(target, port, timeout=timeout_val)
            
            smtp = aiosmtplib.SMTP(
                hostname=target,
                port=port,
                timeout=timeout_val,
                use_tls=use_tls,
                tls_context=tls_context
            )
            await smtp.connect(sock=sock)
            return smtp
        except Exception as e:
            logger.debug(f"Proxy connection failed: {str(e)}")
            raise e
    else:
        src_addr = source_ip if source_ip and source_ip not in ["IP1", "IP2", "IP3"] else None
        
        smtp = aiosmtplib.SMTP(
            hostname=target,
            port=port,
            timeout=timeout_val,
            use_tls=use_tls,
            tls_context=tls_context,
            source_address=src_addr
        )
        await smtp.connect()
        return smtp

async def _smtp_handshake(smtp, mode: str):
    await smtp.ehlo(EHLO_HOST)
    if mode == 'starttls':
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            await smtp.starttls(tls_context=ctx)
            await smtp.ehlo(EHLO_HOST)
        except Exception as e:
            logger.debug(f"STARTTLS failed: {str(e)}")

async def _smtp_verify_email(smtp, domain: str, email: str) -> Tuple[int, str, int]:
    try:
        mc, mm = await smtp.mail(MAIL_FROM)
        if mc not in [250, 251]:
            return mc, mm, 0
            
        c, m = await smtp.rcpt(email)
        if c == 250:
            if domain.lower() in FREE_EMAIL_DOMAINS:
                return c, m, 0
            fake = f"test{random.randint(10000, 99999)}@{domain}"
            try:
                await smtp.rset()
                fmc, fmm = await smtp.mail(MAIL_FROM)
                if fmc in [250, 251]:
                    fc, _ = await smtp.rcpt(fake)
                else:
                    fc = 0
            except Exception:
                fc = 0
            return c, m, fc
        return c, m, 0
    except aiosmtplib.SMTPResponseException as e:
        return e.code, e.message, 0
    except Exception as e:
        raise e

# ── Dynamic IP Fault Tolerance Tracking ───────────────────────────────────────

async def mark_ip_cooldown(ip_address: str):
    logger.warning(f"CRITICAL: Marking IP {ip_address} as COOLDOWN due to excessive failures.")
    await cache_hdel("smtp:active_ips", ip_address)
    loop = asyncio.get_running_loop()
    def _db_update():
        db = SessionLocal()
        try:
            ip = db.query(SmtpIp).filter(SmtpIp.ip_address == ip_address).first()
            if ip:
                ip.status = "cooldown"
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update IP status to cooldown in DB: {e}")
        finally:
            db.close()
    await loop.run_in_executor(None, _db_update)

async def track_ip_failure(ip_address: str, domain: str):
    if not ip_address: return
    try:
        r = get_redis()
        domain_lower = domain.lower()
        key = f"ip_fails:{domain_lower}:{ip_address}"
        fails = await r.incr(key)
        if fails == 1:
            await r.expire(key, 600)  # Cooldown limits reset every 10 mins natively
            
        if "gmail.com" in domain_lower or "googlemail.com" in domain_lower:
            threshold = 2
        elif "yahoo.com" in domain_lower:
            threshold = 3
        else:
            threshold = 5
            
        logger.debug(f"IP {ip_address} logged failure {fails}/{threshold} for domain {domain}")
        if fails >= threshold:
            logger.warning(f"[MONITOR] EVENT=DOMAIN_COOLDOWN_TRIGGERED | ip={ip_address} | domain={domain_lower}")
            await r.setex(f"cooldown:{domain_lower}:{ip_address}", 600, "1")
    except Exception as e:
        logger.error(f"Error tracking IP failure for {ip_address}: {e}")

async def track_ip_success(ip_address: str):
    if not ip_address: return
    try:
        r = get_redis()
        key = f"ip_success:{ip_address}"
        successes = await r.incr(key)
        if successes == 1:
            await r.expire(key, 86400) # Reset daily
    except Exception as e:
        pass

async def track_proxy_success(proxy_id: int):
    loop = asyncio.get_running_loop()
    def _update():
        db = SessionLocal()
        try:
            p = db.query(Proxy).filter(Proxy.id == proxy_id).first()
            if p:
                p.success_count += 1
                p.health_score = min(100, p.health_score + 1)
                db.commit()
        finally:
            db.close()
    await loop.run_in_executor(None, _update)

async def track_proxy_failure(proxy_id: int, error_msg: str, is_block: bool = False):
    loop = asyncio.get_running_loop()
    def _update():
        db = SessionLocal()
        try:
            p = db.query(Proxy).filter(Proxy.id == proxy_id).first()
            if p:
                p.failure_count += 1
                p.health_score = max(0, p.health_score - 10)
                p.last_error = error_msg[:250] if error_msg else "Unknown"
                if is_block or p.health_score <= 20:
                    p.status = "blocked" if is_block else "cooldown"
                db.commit()
        finally:
            db.close()
    await loop.run_in_executor(None, _update)

async def log_verifier_result(email: str, domain: str, ip: str, target: str, port: int, result: str, details: str = ""):
    worker_id = get_worker_name()
    if not ip:
        logger.info(f"[VERIFIER_RESULT] email={email} | domain={domain} | ip=DEFAULT | target={target}:{port} | ratio=100% | fails=0 | result={result} {details}")
        return
    try:
        r = get_redis()
        # Aggregating Worker-Level Statistics
        await r.incr(f"worker:{worker_id}:processed")
        if result in ["VALID", "CATCH_ALL"]:
            await r.incr(f"worker:{worker_id}:success")
        
        await r.incr(f"ip_usage:{ip}") # Track IP Usage
        
        s, f = await r.mget(f"ip_success:{ip}", f"ip_fails:{ip}")
        s_cnt = int(s) if s else 0
        f_cnt = int(f) if f else 0
        ratio = f"{int(s_cnt/(s_cnt+f_cnt)*100)}%" if (s_cnt+f_cnt) > 0 else "100%"
        dtl = f"({details})" if details else ""
        logger.info(f"[VERIFIER_RESULT] email={email} | domain={domain} | ip={ip} | target={target}:{port} | ratio={ratio} | fails={f_cnt} | result={result} {dtl}")
    except Exception:
        logger.info(f"[VERIFIER_RESULT] email={email} | domain={domain} | ip={ip} | target={target}:{port} | result={result} {details}")

# ── Per-domain SMTP rate limiter ──────────────────────────────────────────────
SMTP_RATE_LIMIT_PER_IP = int(os.getenv("SMTP_RATE_LIMIT_PER_MIN", "5"))

async def _is_ip_cooldown_for_domain(domain: str, ip: str) -> bool:
    try:
        r = get_redis()
        return await r.exists(f"cooldown:{domain.lower()}:{ip}") > 0
    except Exception:
        return False

async def _check_smtp_rate_limit(domain: str, ip: str) -> bool:
    """
    Returns True (allowed) or False (rate-limited).
    Uses Redis incr+expire counter keyed per domain per IP per minute window.
    """
    domain_lower = domain.lower()
    
    # Domain-specific limits based on competitor analysis
    if any(d in domain_lower for d in ['icloud.com', 'mac.com', 'me.com', 'hotmail', 'outlook', 'msn.com', 'live.com']):
        limit = 1
    elif 'yahoo' in domain_lower or 'ymail' in domain_lower or 'aol' in domain_lower:
        limit = 4
    elif 'gmail' in domain_lower or 'google' in domain_lower:
        limit = 12
    else:
        limit = SMTP_RATE_LIMIT_PER_IP
        
    key = f"smtp_rate:{domain_lower}:{ip}"
    try:
        r = get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)
        if count > limit:
            logger.debug(f"SMTP rate limit reached for {domain} on IP {ip} ({count}/{limit} per min)")
            return False
        return True
    except Exception as exc:
        logger.debug(f"Rate-limit Redis unavailable, allowing request: {exc}")
        return True


async def smtp_verify(email: str, mx_hosts: List[str]) -> Tuple[str, str, Optional[str]]:
    domain = email.split("@")[1]
    
    # --- Worker-level basic traffic limiting ---
    worker_id = get_worker_name()
    try:
        r = get_redis()
        worker_reqs = await r.incr(f"worker:{worker_id}:requests_per_min")
        if worker_reqs == 1:
            await r.expire(f"worker:{worker_id}:requests_per_min", 60)
        if worker_reqs > 2000: # Max 2000 external pings per minute per Node footprint
            logger.warning(f"[MONITOR] EVENT=WORKER_OVERLOADED | worker={worker_id} | msg=Rate >2000/min. Imposing throttling.")
            await asyncio.sleep(4) 
    except Exception:
        pass

    # Smarter port order: prioritize port 25 for MX servers
    ports = [
        (25, 'plain'),
        (587, 'starttls'),
        (465, 'ssl')
    ]

    last_status = "UNKNOWN"
    details = "No SMTP attempts made"

    # ── Minimal jitter to appear more human-like without killing speed ─────────
    await asyncio.sleep(random.uniform(0.05, 0.2))

    # ── Fetch Active External Proxies ─────────────────────────────────────────
    external_proxies = []
    try:
        db = SessionLocal()
        external_proxies = db.query(Proxy).filter(Proxy.status == "active").all()
        random.shuffle(external_proxies)
        db.close()
    except Exception as e:
        logger.debug(f"Failed to fetch external proxies: {e}")

    for mx_host in mx_hosts[:2]:
        logger.debug(f"Resolving MX host {mx_host}...")
        target = await resolve_host(mx_host)
        
        for port, mode in ports:
            # ── 1. Try External Proxies First (if available) ─────────────────
            if external_proxies:
                for proxy in external_proxies[:3]: # Try up to 3 proxies per MX/Port
                    if not await _check_smtp_rate_limit(domain, proxy.ip):
                        continue
                    smtp = None
                    try:
                        logger.debug(f"Connecting to {target}:{port} via PROXY {proxy.ip}:{proxy.port} (mode: {mode})")
                        smtp = await _attempt_smtp_connection(target, port, mode, 10, proxy=proxy)
                        
                        await _smtp_handshake(smtp, mode)
                        code, msg, fake_code = await _smtp_verify_email(smtp, domain, email)
                        msg_str = str(msg).lower()
                        
                        logger.debug(f"PROXY SMTP response: code={code}, msg={msg_str}")
                        
                        if code == 250:
                            if fake_code == 250:
                                await track_proxy_success(proxy.id)
                                await log_verifier_result(email, domain, f"PROXY:{proxy.ip}", target, port, "CATCH_ALL")
                                return "CATCH_ALL", "Server accepts all emails for this domain", proxy.ip
                            await track_proxy_success(proxy.id)
                            await log_verifier_result(email, domain, f"PROXY:{proxy.ip}", target, port, "VALID")
                            return "VALID", "SMTP server confirmed email existence", proxy.ip

                        if code in [550, 551, 552, 553, 554]:
                            is_block = any(w in msg_str for w in ['spam', 'block', 'banned', 'blacklisted', 'not allowed', 'rejected', 'policy', 'denied'])
                            if is_block:
                                await track_proxy_failure(proxy.id, msg_str, is_block=True)
                                continue # Try next proxy
                            
                            await track_proxy_success(proxy.id) # Reached target but email doesn't exist
                            await log_verifier_result(email, domain, f"PROXY:{proxy.ip}", target, port, "INVALID", msg_str)
                            return "INVALID", f"SMTP server rejected email: {msg_str}", proxy.ip

                    except Exception as e:
                        logger.debug(f"Proxy attempt failed: {e}")
                        await track_proxy_failure(proxy.id, str(e))
                        continue
                    finally:
                        if smtp:
                            try:
                                await smtp.quit()
                            except: pass

            # ── 2. Fallback to Local IP Rotation (existing behavior) ──────────
            # Multi-IP rotation: Weighted shuffle strictly bound to dedicated Worker IPs
            worker_id = get_worker_name()
            active_redis_ips = await cache_hgetall(f"worker:{worker_id}:ips")
            
            # Autonomously Fallback to global pool if this node has NO dedicated IPs yet
            if not active_redis_ips:
                active_redis_ips = await cache_hgetall("smtp:active_ips")
                
            if active_redis_ips:
                r = get_redis()
                ips = list(active_redis_ips.keys())
                success_keys = [f"ip_success:{ip}" for ip in ips]
                fail_keys = [f"ip_fails:{ip}" for ip in ips]
                
                all_keys = success_keys + fail_keys
                all_values = await r.mget(all_keys) if all_keys else []
                
                ip_weights = {}
                half = len(ips)
                
                for idx, ip in enumerate(ips):
                    base_score = int(active_redis_ips[ip])
                    if base_score <= 0: continue
                    
                    s_str = all_values[idx]
                    f_str = all_values[idx + half]
                    
                    s_cnt = int(s_str) if s_str else 0
                    f_cnt = int(f_str) if f_str else 0
                    
                    total = s_cnt + f_cnt
                    ratio = max(0.1, s_cnt / total) if total > 0 else 1.0
                    
                    # Effective mathematical scaling applied securely
                    ip_weights[ip] = base_score * ratio
                
                if ip_weights:
                    available_ips = sorted(
                        ip_weights.keys(), 
                        key=lambda ip: -math.log(random.uniform(1e-10, 1.0)) / ip_weights[ip]
                    )
                else:
                    available_ips = list(SMTP_IPS) if SMTP_IPS else [None]
                    random.shuffle(available_ips)
            else:
                available_ips = list(SMTP_IPS) if SMTP_IPS else [None]
                random.shuffle(available_ips)
            
            for attempt, source_ip in enumerate(available_ips[:3]):
                if not await _check_smtp_rate_limit(domain, source_ip or "default"):
                    continue
                if source_ip and await _is_ip_cooldown_for_domain(domain, source_ip):
                    logger.debug(f"IP {source_ip} is in cooldown for {domain}. Skipping.")
                    continue
                timeout_val = 5 if attempt == 0 else 8
                
                if attempt > 0:
                    # Exponential backoff mechanism
                    await asyncio.sleep(min(2, attempt))
                
                smtp = None
                try:
                    logger.debug(f"Connecting to {target}:{port} (mode: {mode}, timeout: {timeout_val}s, bind_ip: {source_ip})")
                    smtp = await _attempt_smtp_connection(target, port, mode, timeout_val, source_ip)
                    
                    logger.debug(f"Successfully connected to {target}:{port} via {source_ip}, performing handshake...")
                    await _smtp_handshake(smtp, mode)
                    
                    logger.debug(f"Verifying {email} on {target}:{port}...")
                    code, msg, fake_code = await _smtp_verify_email(smtp, domain, email)
                    msg_str = str(msg).lower()
                    
                    logger.debug(f"SMTP response: code={code}, msg={msg_str}, fake_code={fake_code}")
                    
                    if code == 250:
                        if fake_code == 250:
                            await track_ip_success(source_ip)
                            await log_verifier_result(email, domain, source_ip, target, port, "CATCH_ALL")
                            return "CATCH_ALL", "Server accepts all emails for this domain", source_ip
                        
                        await track_ip_success(source_ip)
                        await log_verifier_result(email, domain, source_ip, target, port, "VALID")
                        return "VALID", "SMTP server confirmed email existence", source_ip

                    if code in [550, 551, 552, 553, 554]:
                        if any(w in msg_str for w in ['spam', 'block', 'banned', 'blacklisted', 'not allowed', 'rejected', 'policy', 'denied']):
                            await track_ip_failure(source_ip, domain)
                            await log_verifier_result(email, domain, source_ip, target, port, "SPAM_BLOCK", msg_str)
                            last_status = "SPAM BLOCK"
                            details = f"Server rejected our IP/domain: {msg_str}"
                            continue # Try next IP
                        
                        await track_ip_success(source_ip) # User issue, IP handshake successful
                        await log_verifier_result(email, domain, source_ip, target, port, "INVALID", msg_str)
                        return "INVALID", f"SMTP server rejected email: {msg_str}", source_ip

                    if code in [450, 451, 452]:
                        await track_ip_success(source_ip) # IP reached target, greylisting is standard
                        await log_verifier_result(email, domain, source_ip, target, port, "GREYLISTED", msg_str)
                        return "GREYLISTED", f"Temporary rejection (Greylisting): {msg_str}", source_ip

                    if code in [421, 454, 503, 521, 523] or (400 <= code < 500):
                        await track_ip_failure(source_ip, domain)
                        last_status = "GREYLISTED"
                        details = f"Server temporarily busy or unavailable: {code}"
                        continue # Try next IP
                        
                    if 500 <= code < 600:
                        await track_ip_failure(source_ip, domain)
                        last_status = "UNVERIFIABLE"
                        details = f"Server returned generic error {code}: {msg_str}"
                        continue # Try next IP

                except (socket.timeout, TimeoutError) as e:
                    logger.debug(f"Timeout on {target}:{port} via {source_ip} (Attempt {attempt+1}): {str(e)}")
                    await track_ip_failure(source_ip, domain)
                    last_status = "TIMEOUT"
                    details = "Connection timed out"
                    continue # Retry with next IP
                    
                except ConnectionRefusedError as e:
                    logger.debug(f"Connection refused on {target}:{port} via {source_ip}: {str(e)}")
                    await track_ip_failure(source_ip, domain)
                    last_status = "CONNECTION_REFUSED"
                    details = "Connection refused by server"
                    continue # Target blocked the IP, try next IP!
                    
                except Exception as e:
                    logger.debug(f"Error on {target}:{port} via {source_ip}: {str(e)}")
                    await track_ip_failure(source_ip, domain)
                    last_status = "UNVERIFIABLE"
                    details = f"SMTP error: {str(e)}"
                    continue # Try next IP
                    
                finally:
                    if smtp:
                        try:
                            await smtp.quit()
                        except:
                            pass
                            
            # Stop port iteration if we actually established an SMTP communication 
            # and received a server response that isn't definitive valid/invalid.
            if last_status in ["GREYLISTED", "UNVERIFIABLE"] and "error" not in details.lower():
                return last_status, details, source_ip

    return last_status, details, None

def calculate_quality_score(email: str, domain: str, has_mx: bool = False, has_spf: bool = False, has_dmarc: bool = False, is_role: bool = False, is_disposable: bool = False) -> int:
    if is_disposable:
        score = -50
    else:
        score = 0
        
    domain_lower = domain.lower()
    
    # +30 -> Free providers (gmail, yahoo, outlook, hotmail)
    free_providers = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com'}
    if domain_lower in free_providers:
        score += 30
        
    # +25 -> Valid MX records
    if has_mx:
        score += 25
        
    # +20 -> SPF + DMARC both present, +10 -> SPF only, -10 -> No SPF
    if has_spf and has_dmarc:
        score += 20
    elif has_spf:
        score += 10
    else:
        score -= 10
        
    # -10 -> Role accounts (admin, info, support, etc.)
    if is_role:
        score -= 10
        
    # -15 -> Random numeric patterns (e.g. 12345 in local)
    local_part = email.split('@')[0]
    if re.search(r'\d{5,}', local_part):
        score -= 15
        
    # Domain Intelligence Check (Advanced)
    if domain_lower in DOMAIN_STATS:
        stats = DOMAIN_STATS.get(domain_lower, {})
        if stats.get('invalid_count', 0) >= 2:
            score -= 15
            
    return max(0, min(score, 100))

async def verify_email(email: str) -> Dict[str, Any]:
    email = email.lower().strip()
    logger.debug(f"\n--- Starting verification for {email} ---")

    result = {
        "email": email,
        "syntax": False,
        "mx": False,
        "smtp": False,
        "catch_all": False,
        "disposable": False,
        "role": False,
        "spf": False,
        "dmarc": False,
        "quality_score": 0,
        "confidence": 0,
        "status": "REJECTED",
        "details": "",
        "verification_method": "heuristic"  # Default
    }

    if not EMAIL_REGEX.match(email):
        logger.debug(f"Syntax invalid for {email}")
        result["details"] = "Invalid email syntax"
        return result

    result["syntax"] = True
    local, domain = email.split("@")

    if domain in DISPOSABLE_DOMAINS:
        logger.debug(f"Disposable domain detected for {email}")
        result["disposable"] = True

    for pattern in ROLE_PATTERNS:
        if re.search(pattern, local):
            logger.debug(f"Role pattern {pattern} matched for {local}")
            result["role"] = True
            break
            
    # Uses global FREE_EMAIL_DOMAINS

    # Domain intelligence check
    if domain in DOMAIN_STATS and domain not in FREE_EMAIL_DOMAINS:
        stats = DOMAIN_STATS[domain]
        if stats.get('catch_all_count', 0) >= 2:
            result['catch_all'] = True

    # Domain caching check before DNS
    cached = await cache_get(f"mx:{domain}")
    if cached:
        logger.debug(f"Using cached domain data for {domain}")
        mx_hosts = cached['mx_hosts']
        spf_exists = cached['spf']
        dmarc_exists = cached['dmarc']
        has_mx = cached['has_mx']
        if cached.get('catch_all') and domain not in FREE_EMAIL_DOMAINS:
            result['catch_all'] = True
            
        result["spf"] = spf_exists
        result["dmarc"] = dmarc_exists
        result["mx"] = has_mx
        
        if not has_mx:
            result["quality_score"] = calculate_quality_score(email=email, domain=domain, has_mx=False, has_spf=spf_exists, has_dmarc=dmarc_exists, is_role=result["role"], is_disposable=result["disposable"])
            result["status"] = "REJECTED"
            result["details"] = "No MX or A records found for domain (cached)"
            return result
    else:
        # Parallelize DNS Checks
        logger.debug(f"Running parallel DNS checks for {domain}")
        dns_tasks = asyncio.gather(
            get_mx(domain),
            check_spf(domain),
            check_dmarc(domain)
        )
        mx_hosts, spf_exists, dmarc_exists = await dns_tasks
        
        result["spf"] = spf_exists
        result["dmarc"] = dmarc_exists

        if not mx_hosts:
            logger.debug(f"No MX records found for {domain}, attempting A record fallback")
            a_records = await get_a_record(domain)
            if not a_records:
                logger.debug(f"No A records found for {domain}")
                await cache_set(f"mx:{domain}", {
                    'mx_hosts': [], 'spf': spf_exists, 'dmarc': dmarc_exists,
                    'has_mx': False, 'catch_all': False
                }, ttl=3600)
                result["quality_score"] = calculate_quality_score(email=email, domain=domain, has_mx=False, has_spf=spf_exists, has_dmarc=dmarc_exists, is_role=result["role"], is_disposable=result["disposable"])
                result["status"] = "REJECTED"
                result["details"] = "No MX or A records found for domain"
                return result
            mx_hosts = a_records

        result["mx"] = True
        has_mx = True
        
        await cache_set(f"mx:{domain}", {
            'mx_hosts': mx_hosts,
            'spf': spf_exists,
            'dmarc': dmarc_exists,
            'has_mx': True,
            'catch_all': False
        }, ttl=3600)

    # 1. Calculate Score directly
    q_score = calculate_quality_score(email=email, domain=domain, has_mx=has_mx, has_spf=spf_exists, has_dmarc=dmarc_exists, is_role=result["role"], is_disposable=result["disposable"])
    result["quality_score"] = q_score
    result["confidence"] = q_score

    # Ensure redundant SMTP skips if recognized as catch-all universally via cache
    if result.get("catch_all"):
        result["smtp"] = True
        result["status"] = "CATCH_ALL"
        
        
        result["details"] = "Domain is configured as a catch-all (identified via intelligence tracking)."
        logger.debug(f"Skipping SMTP for {email} -> Identified as CATCH_ALL from cache.")
        return result

    result["verification_method"] = "smtp"
    
    try:
        logger.debug(f"Initiating SMTP checks for {email}")
        smtp_status, smtp_details, used_proxy = await asyncio.wait_for(
            smtp_verify(email, mx_hosts),
            timeout=12.0
        )
        result["used_proxy"] = used_proxy
    except asyncio.TimeoutError:
        logger.debug(f"Overall SMTP verification timed out for {email}")
        smtp_status = "TIMEOUT"
        smtp_details = "SMTP Verification took too long and was aborted"

    logger.debug(f"SMTP verification finished: {smtp_status} - {smtp_details}")

    is_google = any('google.com' in mx.lower() or 'googlemail.com' in mx.lower() for mx in mx_hosts)

    # Process SMTP results
    if smtp_status == "VALID":
        result["status"] = "ACCEPTED"
        result["smtp"] = True
        
        
        result["details"] = smtp_details
    elif smtp_status == "CATCH_ALL":
        result["smtp"] = True
        result["catch_all"] = True
        result["status"] = "CATCH_ALL"
        
        
        result["details"] = "Domain is configured as a catch-all (accepts any prefix)."
        
        # Domain Intelligence Tracking
        DOMAIN_STATS.setdefault(domain, {})
        DOMAIN_STATS[domain]['catch_all_count'] = DOMAIN_STATS[domain].get('catch_all_count', 0) + 1
        
        # Immediately update the global domain cache for future emails in this chunk
        cached = await cache_get(f"mx:{domain}")
        if cached:
            cached['catch_all'] = True
            await cache_set(f"mx:{domain}", cached, ttl=3600)
    elif smtp_status == "INVALID":
        result["status"] = "REJECTED"
        
        
        result["details"] = smtp_details
        
        # Domain Intelligence Tracking
        DOMAIN_STATS.setdefault(domain, {})
        DOMAIN_STATS[domain]['invalid_count'] = DOMAIN_STATS[domain].get('invalid_count', 0) + 1
    elif smtp_status == "SPAM BLOCK":
        result["status"] = "SPAM BLOCK"
        
        
        result["details"] = smtp_details
    elif smtp_status == "GREYLISTED":
        result["status"] = "GREYLISTED"
        
        
        result["details"] = smtp_details
    elif smtp_status == "RATE_LIMITED":
        result["status"] = "RATE_LIMITED"
        result["verification_method"] = "heuristic"
        result["details"] = smtp_details
        logger.debug(f"Rate-limited for {domain}, returning without score calculation.")
        return result
    else:
        # Fallback for TIMEOUT, CONNECTION_REFUSED, UNVERIFIABLE, or UNKNOWN
        logger.debug(f"SMTP unreliable due to {smtp_status}. Mapping result based on actual state.")
        result["verification_method"] = "heuristic"
        
        if has_mx:
            result["status"] = "REJECTED"
            result["smtp"] = False  # DO NOT fake SMTP success
            result["catch_all"] = False
            result["details"] = f"Mail server exists but SMTP connection failed: {smtp_status}. Reason: {smtp_details}"
            logger.debug(f"SMTP Failed for {email}: {smtp_status}. Leaving as UNVERIFIED.")
        else:
            result["status"] = "LIKELY_INVALID"
            result["details"] = f"SMTP unverified ({smtp_status}) and no reliable mail server found."

    
    # Calculate final quality score based on all accumulated knowledge and SMTP status
    final_score = calculate_quality_score(
        email=email,
        domain=domain,
        has_mx=has_mx,
        has_spf=spf_exists,
        has_dmarc=dmarc_exists,
        is_role=result.get("role", False),
        is_disposable=result.get("disposable", False)
    )
    result["quality_score"] = final_score
    result["confidence"] = final_score

    logger.debug(f"--- Verification completed for {email} -> {result['status']} (Conf: {result['confidence']}) ---")
    return result