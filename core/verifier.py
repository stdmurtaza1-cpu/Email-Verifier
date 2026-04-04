from cache import cache_get, cache_set
import re
import os
import dns.resolver
import smtplib
import socket
import ssl
import asyncio
import random
import time
import logging
from typing import List, Tuple, Optional, Dict, Any
from functools import wraps

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
HELO_DOMAIN = os.getenv("HELO_DOMAIN", "mail.verification-service.com")
EHLO_HOST = HELO_DOMAIN          # kept for backward-compat references
MAIL_FROM = f"verify@{HELO_DOMAIN}"

# SMTP source IP rotation — set SMTP_SOURCE_IPS in .env as a comma-separated list
# Leave unset to use the server's default outbound IP
_raw_ips = os.getenv("SMTP_SOURCE_IPS", "").strip()
SMTP_IPS: List[str] = [ip.strip() for ip in _raw_ips.split(",") if ip.strip()] if _raw_ips else []

DOMAIN_STATS = {}

ROLE_PATTERNS = [
    r'^admin', r'^support', r'^info', r'^sales', r'^contact', r'^billing',
    r'^help', r'^hello', r'^team', r'^jobs', r'^hr', r'^marketing',
    r'^webmaster', r'^postmaster', r'^abuse', r'^reply', r'^noreply', r'^no-reply',
    r'^dev', r'^office', r'^press', r'^pr', r'^ceo'
]

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "yopmail.com", "throwawaymail.com", "dispostable.com", "getairmail.com"
}

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

def async_cache(ttl=3600):
    cache = {}
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
            result = await func(*args, **kwargs)
            cache[key] = (result, time.time())
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

async def _attempt_smtp_connection(target: str, port: int, mode: str, timeout_val: int, source_ip: Optional[str] = None):
    loop = asyncio.get_running_loop()
    def _connect():
        # If source_ip is configured to a valid string, map it. OS default is used if None.
        src_addr = (source_ip, 0) if source_ip and source_ip not in ["IP1", "IP2", "IP3"] else None
        
        if mode == 'ssl':
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return smtplib.SMTP_SSL(target, port, timeout=timeout_val, context=context, source_address=src_addr)
        else:
            return smtplib.SMTP(target, port, timeout=timeout_val, source_address=src_addr)
    return await loop.run_in_executor(None, _connect)

async def _smtp_handshake(smtp, mode: str):
    loop = asyncio.get_running_loop()
    def _handshake():
        smtp.ehlo(EHLO_HOST)
        if mode == 'starttls':
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                smtp.starttls(context=ctx)
                smtp.ehlo(EHLO_HOST)
            except Exception as e:
                logger.debug(f"STARTTLS failed: {str(e)}")
    await loop.run_in_executor(None, _handshake)

async def _smtp_verify_email(smtp, domain: str, email: str) -> Tuple[int, str, int]:
    loop = asyncio.get_running_loop()
    def _exchange():
        smtp.mail(MAIL_FROM)
        c, m = smtp.rcpt(email)
        if c == 250:
            fake = f"test{random.randint(10000, 99999)}@{domain}"
            smtp.mail(MAIL_FROM)
            fc, _ = smtp.rcpt(fake)
            return c, m, fc
        return c, m, 0
    return await loop.run_in_executor(None, _exchange)

# ── Per-domain SMTP rate limiter ──────────────────────────────────────────────
SMTP_RATE_LIMIT = int(os.getenv("SMTP_RATE_LIMIT_PER_MIN", "5"))   # requests per domain per minute

async def _check_smtp_rate_limit(domain: str) -> bool:
    """
    Returns True (allowed) or False (rate-limited).
    Uses Redis incr+expire counter keyed per domain per minute window.
    Falls back to True (allow) if Redis is unavailable, so verifier never
    blocks completely just because Redis is down.
    """
    key = f"smtp_rate:{domain}"
    try:
        import redis as _redis
        import os as _os
        r = _redis.from_url(_os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)
        count = r.incr(key)
        if count == 1:
            r.expire(key, 60)   # start the 60-second window on first hit
        if count > SMTP_RATE_LIMIT:
            logger.warning(f"SMTP rate limit reached for {domain} ({count}/{SMTP_RATE_LIMIT} per min)")
            return False
        return True
    except Exception as exc:
        logger.debug(f"Rate-limit Redis unavailable, allowing request: {exc}")
        return True   # fail open — never hard-block due to Redis issues


async def smtp_verify(email: str, mx_hosts: List[str]) -> Tuple[str, str]:
    domain = email.split("@")[1]

    # ── Per-domain rate-limit guard ───────────────────────────────────────────
    if not await _check_smtp_rate_limit(domain):
        return "RATE_LIMITED", f"Too many SMTP requests to {domain} this minute. Try again shortly."

    # Smarter port order
    ports = [
        (587, 'starttls'),
        (465, 'ssl'),
        (25, 'plain')
    ]

    last_status = "UNKNOWN"
    details = "No SMTP attempts made"

    # ── Jitter: randomised delay to appear more human-like ────────────────────
    await asyncio.sleep(random.uniform(0.5, 2.0))

    for mx_host in mx_hosts[:2]:
        logger.debug(f"Resolving MX host {mx_host}...")
        target = await resolve_host(mx_host)
        
        for port, mode in ports:
            # Multi-IP rotation: Shuffle available IPs so connections distribute load
            available_ips = list(SMTP_IPS) if SMTP_IPS else [None]
            random.shuffle(available_ips)
            
            # Use chunks of available IPs. Shorter timeout first, then longer on retry
            for attempt, source_ip in enumerate(available_ips[:3]):
                timeout_val = 8 if attempt == 0 else 12
                
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
                            return "CATCH_ALL", "Server accepts all emails for this domain"
                        return "VALID", "SMTP server confirmed email existence"

                    if code in [550, 551, 552, 553, 554]:
                        if any(w in msg_str for w in ['spam', 'block', 'banned', 'blacklisted', 'not allowed', 'rejected', 'policy', 'denied']):
                            return "SPAM BLOCK", f"Server rejected our IP/domain: {msg_str}"
                        return "INVALID", f"SMTP server rejected email: {msg_str}"

                    if code in [450, 451, 452]:
                        return "GREYLISTED", f"Temporary rejection (Greylisting): {msg_str}"

                    if code in [421, 454, 503, 521, 523] or (400 <= code < 500):
                        last_status = "GREYLISTED"
                        details = f"Server temporarily busy or unavailable: {code}"
                        break # Go to next port
                        
                    if 500 <= code < 600:
                        last_status = "UNVERIFIABLE"
                        details = f"Server returned generic error {code}: {msg_str}"
                        break # Go to next port

                except (socket.timeout, TimeoutError) as e:
                    logger.debug(f"Timeout on {target}:{port} (Attempt {attempt+1}): {str(e)}")
                    last_status = "TIMEOUT"
                    details = "Connection timed out"
                    continue # Retry with longer timeout
                    
                except ConnectionRefusedError as e:
                    logger.debug(f"Connection refused on {target}:{port}: {str(e)}")
                    last_status = "CONNECTION_REFUSED"
                    details = "Connection refused by server"
                    # Refused means actively rejected, stop retrying this port immediately
                    break
                    
                except Exception as e:
                    logger.debug(f"Error on {target}:{port}: {str(e)}")
                    last_status = "UNVERIFIABLE"
                    details = f"SMTP error: {str(e)}"
                    break
                    
                finally:
                    if smtp:
                        try:
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, smtp.quit)
                        except:
                            pass
                            
            # Stop port iteration if we actually established an SMTP communication 
            # and received a server response that isn't definitive valid/invalid.
            if last_status in ["GREYLISTED", "UNVERIFIABLE"] and "error" not in details.lower():
                return last_status, details

    return last_status, details

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
            
    # Domain intelligence check
    if domain in DOMAIN_STATS:
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
        if cached.get('catch_all'):
            result['catch_all'] = True
            
        result["spf"] = spf_exists
        result["dmarc"] = dmarc_exists
        result["mx"] = has_mx
        
        if not has_mx:
            result["quality_score"] = calculate_quality_score(email=email, domain=domain, has_mx=False, has_spf=spf_exists, has_dmarc=dmarc_exists, is_role=result["role"], is_disposable=result["disposable"])
            result["status"] = "LIKELY_INVALID" if result["quality_score"] <= 40 else "UNVERIFIED"
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
                result["status"] = "LIKELY_INVALID" if result["quality_score"] <= 40 else "UNVERIFIED"
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
        smtp_status, smtp_details = await asyncio.wait_for(
            smtp_verify(email, mx_hosts),
            timeout=15.0
        )
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
        result["status"] = "LIKELY_INVALID"
        
        
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
        logger.debug(f"SMTP unreliable due to {smtp_status}. Preserving original heuristic method identity.")
        result["verification_method"] = "heuristic"
        
        if smtp_status == "TIMEOUT":
            if has_mx and spf_exists and dmarc_exists:
                result["status"] = "UNVERIFIED"
                
                
            else:
                result["status"] = "TIMEOUT"
                
                
        else:
            result["status"] = "UNVERIFIED"
            
            
            
        result["details"] = f"SMTP unverified ({smtp_status}). Returned mapped confidence."

    
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