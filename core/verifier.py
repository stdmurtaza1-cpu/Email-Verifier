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

def resolve_host(hostname):
    # Best-effort resolution.
    timeout_count = 0
    for dns_ip in ['8.8.8.8', '1.1.1.1', '9.9.9.9']:
        try:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [dns_ip]
            resolver.timeout = 3
            resolver.lifetime = 5
            answers = resolver.resolve(hostname, 'A')
            return str(answers[0])
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.resolver.Timeout:
            timeout_count += 1
            if timeout_count >= 2:
                break
        except Exception:
            continue
    try:
        answers = get_system_resolver().resolve(hostname, 'A')
        return str(answers[0])
    except Exception:
        return hostname

def get_mx(domain):
    # Try configured public resolvers, then fall back to system resolver.
    timeout_count = 0
    for nameserver in DNS_SERVERS:
        try:
            resolver = get_resolver(nameserver)
            answers = resolver.resolve(domain, 'MX')
            mx = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
            return [h for _, h in mx]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.resolver.Timeout:
            timeout_count += 1
            if timeout_count >= 2:
                break
        except Exception:
            continue
    try:
        answers = get_system_resolver().resolve(domain, 'MX')
        mx = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
        return [h for _, h in mx]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except Exception:
        return None

def get_a_record(domain):
    timeout_count = 0
    for nameserver in DNS_SERVERS:
        try:
            resolver = get_resolver(nameserver)
            answers = resolver.resolve(domain, 'A')
            return [str(r) for r in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.resolver.Timeout:
            timeout_count += 1
            if timeout_count >= 2:
                break
        except Exception:
            continue
    try:
        answers = get_system_resolver().resolve(domain, 'A')
        return [str(r) for r in answers]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return []
    except Exception:
        return None

def check_spf(domain):
    timeout_count = 0
    for nameserver in DNS_SERVERS:
        try:
            resolver = get_resolver(nameserver)
            answers = resolver.resolve(domain, 'TXT')
            for r in answers:
                txt = str(r).lower()
                if "spf1" in txt:
                    return True
            return False
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return False
        except dns.resolver.Timeout:
            timeout_count += 1
            if timeout_count >= 2:
                break
        except:
            continue
    return False

def check_dmarc(domain):
    timeout_count = 0
    for nameserver in DNS_SERVERS:
        try:
            resolver = get_resolver(nameserver)
            resolver.resolve(f"_dmarc.{domain}", 'TXT')
            return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return False
        except dns.resolver.Timeout:
            timeout_count += 1
            if timeout_count >= 2:
                break
        except:
            continue
    return False

def smtp_verify(email, mx_hosts):
    domain = email.split("@")[1]
    
    ports = [
        (25, 'plain'),
        (587, 'starttls'),
        (465, 'ssl')
    ]
    
    last_status = "UNKNOWN"
    timeout_count = 0

    for mx_host in mx_hosts[:3]:
        # Resolve MX hostname to IP via public DNS to bypass broken Windows DNS
        target = resolve_host(mx_host)

        for port, mode in ports:
            smtp = None
            try:
                if mode == 'ssl':
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    smtp = smtplib.SMTP_SSL(target, port, timeout=SMTP_TIMEOUT, context=context)
                else:
                    smtp = smtplib.SMTP(target, port, timeout=SMTP_TIMEOUT)
                
                smtp.ehlo(EHLO_HOST)
                
                if mode == 'starttls':
                    try:
                        context = ssl.create_default_context()
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                        smtp.starttls(context=context)
                        smtp.ehlo(EHLO_HOST)
                    except:
                        pass
                
                smtp.mail(MAIL_FROM)
                code, msg = smtp.rcpt(email)
                msg_str = str(msg).lower()

                if code == 250:
                    fake = f"test{random.randint(10000, 99999)}@{domain}"
                    smtp.mail(MAIL_FROM)
                    fake_code, _ = smtp.rcpt(fake)
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

    mx_hosts = get_mx(domain)

    if mx_hosts is None:
        result["status"] = "MX ERROR"
        result["score"] = 2
        return result

    if len(mx_hosts) == 0:
        a_records = get_a_record(domain)
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
        
        result["spf"] = check_spf(domain)
        result["dmarc"] = check_dmarc(domain)
        return result

    result["spf"] = check_spf(domain)
    result["dmarc"] = check_dmarc(domain)

    loop = asyncio.get_running_loop()

    try:
        status = await asyncio.wait_for(
            loop.run_in_executor(None, smtp_verify, email, mx_hosts),
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