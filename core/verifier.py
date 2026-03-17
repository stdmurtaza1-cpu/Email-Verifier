import re
import dns.resolver
import smtplib
import socket
import ssl
import asyncio
import random

EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')

SMTP_TIMEOUT = 12
EHLO_HOST = "mail.google.com"
MAIL_FROM = "verify@gmail.com"

ROLE_ACCOUNTS = {
    "admin", "support", "info", "sales", "contact", "billing",
    "help", "hello", "team", "jobs", "hr", "marketing"
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com"
}

KNOWN_CATCHALL = [
    'yahoo.com', 'yahoo.co.uk', 'yahoo.co.in',
    'yahoo.fr', 'yahoo.de', 'yahoo.es',
    'aol.com', 'aol.co.uk',
    'msn.com',
    'hotmail.com', 'hotmail.co.uk',
    'outlook.com', 'outlook.co.uk',
    'live.com', 'live.co.uk',
    'yandex.com', 'yandex.ru',
    'mail.ru',
]

DNS_SERVERS = ['8.8.8.8', '1.1.1.1', '9.9.9.9', '8.8.4.4', '1.0.0.1']

def get_resolver(nameserver):
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [nameserver]
    resolver.timeout = 5
    resolver.lifetime = 8
    return resolver

def get_system_resolver():
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = 5
    resolver.lifetime = 8
    return resolver

async def resolve_host(hostname):
    loop = asyncio.get_running_loop()
    
    def _resolve():
        timeout_count = 0
        for dns_ip in ['8.8.8.8', '1.1.1.1', '9.9.9.9']:
            try:
                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = [dns_ip]
                resolver.timeout = 2
                resolver.lifetime = 3
                return str(resolver.resolve(hostname, 'A')[0])
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                continue
            except dns.resolver.Timeout:
                timeout_count += 1
                if timeout_count >= 2: break
            except Exception:
                continue
        try:
            return str(get_system_resolver().resolve(hostname, 'A')[0])
        except Exception:
            return hostname
            
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _resolve), timeout=5.0)
    except asyncio.TimeoutError:
        return hostname

async def get_mx(domain):
    loop = asyncio.get_running_loop()
    
    def _get():
        timeout_count = 0
        for nameserver in DNS_SERVERS:
            try:
                resolver = get_resolver(nameserver)
                resolver.timeout = 2
                resolver.lifetime = 3
                answers = resolver.resolve(domain, 'MX')
                mx = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
                return [h for _, h in mx]
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                return [] # Short-circuit if no MX
            except dns.resolver.Timeout:
                timeout_count += 1
                if timeout_count >= 2: break
            except Exception:
                continue
        try:
            resolver = get_system_resolver()
            resolver.timeout = 2
            resolver.lifetime = 3
            answers = resolver.resolve(domain, 'MX')
            mx = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
            return [h for _, h in mx]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return []
        except Exception:
            return None
            
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=6.0)
    except asyncio.TimeoutError:
        return None

async def get_a_record(domain):
    loop = asyncio.get_running_loop()
    def _get():
        timeout_count = 0
        for nameserver in DNS_SERVERS:
            try:
                resolver = get_resolver(nameserver)
                resolver.timeout = 2
                resolver.lifetime = 3
                return [str(r) for r in resolver.resolve(domain, 'A')]
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                return []
            except dns.resolver.Timeout:
                timeout_count += 1
                if timeout_count >= 2: break
            except Exception:
                continue
        try:
            resolver = get_system_resolver()
            resolver.timeout = 2
            resolver.lifetime = 3
            return [str(r) for r in resolver.resolve(domain, 'A')]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return []
        except Exception:
            return None
            
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=5.0)
    except asyncio.TimeoutError:
        return None

async def check_spf(domain):
    loop = asyncio.get_running_loop()
    def _get():
        timeout_count = 0
        for nameserver in DNS_SERVERS:
            try:
                resolver = get_resolver(nameserver)
                resolver.timeout = 2
                resolver.lifetime = 3
                for r in resolver.resolve(domain, 'TXT'):
                    if "spf1" in str(r).lower(): return True
                return False
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                return False
            except dns.resolver.Timeout:
                timeout_count += 1
                if timeout_count >= 2: break
            except Exception:
                continue
        return False
        
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=4.0)
    except asyncio.TimeoutError:
        return False

async def check_dmarc(domain):
    loop = asyncio.get_running_loop()
    def _get():
        timeout_count = 0
        for nameserver in DNS_SERVERS:
            try:
                resolver = get_resolver(nameserver)
                resolver.timeout = 2
                resolver.lifetime = 3
                resolver.resolve(f"_dmarc.{domain}", 'TXT')
                return True
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                return False
            except dns.resolver.Timeout:
                timeout_count += 1
                if timeout_count >= 2: break
            except Exception:
                continue
        return False
        
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=4.0)
    except asyncio.TimeoutError:
        return False

async def smtp_verify(email, mx_hosts):
    domain = email.split("@")[1]
    
    ports = [
        (25, 'plain'),
        (587, 'starttls'),
        (465, 'ssl')
    ]
    
    last_status = "UNKNOWN"
    timeout_count = 0
    loop = asyncio.get_running_loop()

    for mx_host in mx_hosts[:3]:
        # Await the resolution of the MX target
        target = await resolve_host(mx_host)

        for port, mode in ports:
            smtp = None
            try:
                if mode == 'ssl':
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    
                    def _connect_ssl():
                        return smtplib.SMTP_SSL(target, port, timeout=SMTP_TIMEOUT, context=context)
                    smtp = await loop.run_in_executor(None, _connect_ssl)
                else:
                    def _connect_plain():
                        return smtplib.SMTP(target, port, timeout=SMTP_TIMEOUT)
                    smtp = await loop.run_in_executor(None, _connect_plain)
                
                def _ehlo_tls():
                    smtp.ehlo(EHLO_HOST)
                    if mode == 'starttls':
                        try:
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                            smtp.starttls(context=ctx)
                            smtp.ehlo(EHLO_HOST)
                        except:
                            pass
                await loop.run_in_executor(None, _ehlo_tls)
                
                def _exchange():
                    smtp.mail(MAIL_FROM)
                    c, m = smtp.rcpt(email)
                    if c == 250:
                        fake = f"test{random.randint(10000, 99999)}@{domain}"
                        smtp.mail(MAIL_FROM)
                        fc, _ = smtp.rcpt(fake)
                        return c, m, fc
                    return c, m, 0
                
                code, msg, fake_code = await loop.run_in_executor(None, _exchange)
                msg_str = str(msg).lower()

                if code == 250:
                    if fake_code == 250:
                        return "CATCH_ALL"
                    return "VALID"

                if code in [550, 551, 552, 553, 554]:
                    if any(w in msg_str for w in ['spam', 'block', 'banned', 'blacklisted', 'not allowed', 'rejected', 'policy', 'denied']):
                        return "SPAM BLOCK"
                    return "INVALID"

                if code in [450, 451, 452]:
                    return "GREYLISTED"

                # Temporary / server busy / try later -> try next port or MX
                if code in [421, 454, 503, 521, 523]:
                    last_status = "GREYLISTED"
                    break
                if 400 <= code < 500:
                    last_status = "GREYLISTED"
                    break
                if 500 <= code < 600 and code not in [550, 551, 552, 553, 554]:
                    last_status = "UNVERIFIABLE"
                    break

                last_status = "UNVERIFIABLE"
                break

            except (socket.timeout, TimeoutError):
                last_status = "TIMEOUT"
                timeout_count += 1
                if timeout_count >= 2:
                    return "TIMEOUT"
            except Exception:
                last_status = "UNVERIFIABLE"
            finally:
                if smtp:
                    try:
                        smtp.quit()
                    except:
                        pass

    if last_status == "UNKNOWN":
        return "UNVERIFIABLE"
    return last_status

async def verify_email(email):
    email = email.lower().strip()

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
        "score": 0,
        "status": "REJECTED",
        "details": ""
    }

    if not EMAIL_REGEX.match(email):
        return result

    result["syntax"] = True

    local, domain = email.split("@")

    if domain in DISPOSABLE_DOMAINS:
        result["disposable"] = True
        result["status"] = "DISPOSABLE"
        result["score"] = 10
        return result

    if local in ROLE_ACCOUNTS:
        result["role"] = True

    mx_hosts = await get_mx(domain)

    if mx_hosts is None:
        result["status"] = "MX ERROR"
        result["score"] = 2
        return result

    if len(mx_hosts) == 0:
        a_records = await get_a_record(domain)
        if not a_records:
            result["status"] = "MX ERROR"
            result["score"] = 2
            return result
        mx_hosts = a_records

    result["mx"] = True

    if domain in KNOWN_CATCHALL:
        result["status"] = "CATCH-ALL"
        result["score"] = 60
        result["smtp"] = True
        result["details"] = "Major provider - SMTP verification not possible"
        
        result["spf"] = await check_spf(domain)
        result["dmarc"] = await check_dmarc(domain)
        return result

    result["spf"] = await check_spf(domain)
    result["dmarc"] = await check_dmarc(domain)

    try:
        status = await asyncio.wait_for(
            smtp_verify(email, mx_hosts),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        status = "TIMEOUT"

    if status == "VALID":
        result["status"] = "ACCEPTED"
        result["smtp"] = True
        result["score"] = 98
    elif status == "CATCH_ALL":
        result["status"] = "CATCH-ALL"
        result["smtp"] = True
        result["catch_all"] = True
        result["score"] = 60
    elif status == "INVALID":
        result["status"] = "REJECTED"
        result["score"] = 0
    elif status == "GREYLISTED":
        result["status"] = "GREYLISTED"
        result["score"] = 45
    elif status == "TIMEOUT":
        result["status"] = "TIMEOUT"
        result["score"] = 30
    elif status == "SPAM BLOCK":
        result["status"] = "SPAM BLOCK"
        result["score"] = 35
    elif status == "MX ERROR":
        result["status"] = "MX ERROR"
        result["score"] = 2
    elif status in ("UNVERIFIABLE", "ERROR", "UNKNOWN"):
        result["status"] = "UNVERIFIABLE"
        result["score"] = 40
        result["details"] = "Could not complete SMTP check (timeout or server did not respond). Not rejected."
    else:
        result["status"] = "REJECTED"
        result["score"] = 0

    return result