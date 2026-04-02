import re

with open("d:/Quantx/Email Verifier/core/verifier.py", "r", encoding='utf-8') as f:
    text = f.read()

# Replace all occurrences of "score":
text = text.replace('"score"', '"quality_score"')
text = text.replace("['score']", "['quality_score']")
text = text.replace('["score"]', '["quality_score"]')

# Replace variable h_score
text = text.replace("h_score", "q_score")

# Replace function names
text = text.replace("calculate_heuristic_score", "calculate_quality_score")

# Replace the definition of the function
old_def = """def calculate_quality_score(email: str, domain: str, has_mx: bool, has_spf: bool, has_dmarc: bool, is_role: bool, is_disposable: bool) -> int:
    if is_disposable:
        quality_score = -50
    else:
        quality_score = 0
        
    domain_lower = domain.lower()
    
    # +30 -> Free providers (gmail, yahoo, outlook, hotmail)
    free_providers = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com'}
    if domain_lower in free_providers:
        quality_score += 30
        
    # +25 -> Valid MX records
    if has_mx:
        quality_score += 25
        
    # +20 -> SPF + DMARC both present, +10 -> SPF only, -10 -> No SPF
    if has_spf and has_dmarc:
        quality_score += 20
    elif has_spf:
        quality_score += 10
    else:
        quality_score -= 10
        
    # -10 -> Role accounts (admin, info, support, etc.)
    if is_role:
        quality_score -= 10
        
    # -15 -> Random numeric patterns (e.g. 12345 in local)
    local_part = email.split('@')[0]
    if re.search(r'\d{5,}', local_part):
        quality_score -= 15
        
    # Domain Intelligence Check (Advanced)
    if domain_lower in DOMAIN_STATS:
        stats = DOMAIN_STATS.get(domain_lower, {})
        if stats.get('invalid_count', 0) >= 2:
            quality_score -= 15
            
    return max(0, min(quality_score, 100))"""

new_def = """def calculate_quality_score(
    domain: str, 
    has_mx: bool, 
    is_disposable: bool, 
    smtp_status: str,
    syntax_valid: bool = True
) -> int:
    \"\"\"
    Rule-based heuristic quality score (0-100).
    NOTE: This is a purely logical, deterministic scoring system 
    based on fixed rules and DNS/SMTP outcomes. It is NOT Machine Learning or AI.

    Scoring logic:
    +25 if SMTP responded 250 OK (confirmed mailbox)
    +20 if valid MX records found
    +15 if domain is a known reputable provider (gmail, outlook, yahoo...)
    +10 if syntax is perfectly valid
    -30 if domain is disposable/throwaway
    -20 if SMTP returned 550 (user not found)
    -15 if no MX records found
    \"\"\"
    score = 0
    domain_lower = domain.lower()
    
    # +10 if syntax is perfectly valid
    if syntax_valid:
        score += 10
        
    # +20 if valid MX records found
    # -15 if no MX records found
    if has_mx:
        score += 20
    else:
        score -= 15
        
    # +15 if domain is a known reputable provider (gmail, outlook, yahoo, hotmail)
    reputable_providers = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com'}
    if domain_lower in reputable_providers:
        score += 15
        
    # -30 if domain is disposable/throwaway
    if is_disposable:
        score -= 30
        
    # +25 if SMTP responded 250 OK (confirmed mailbox)
    if smtp_status in ["VALID", "ACCEPTED", "CATCH_ALL"]:
        score += 25
        
    # -20 if SMTP returned 550 (user not found)
    if smtp_status in ["INVALID", "LIKELY_INVALID", "REJECTED"]:
        score -= 20
        
    return max(0, min(score, 100))"""

text = text.replace(old_def, new_def)

# Fix the calls
text = re.sub(
    r'result\["quality_score"\] = calculate_quality_score\(.*?email, domain, False, spf_exists, dmarc_exists, result\["role"\], result\["disposable"\]\)', 
    r'result["quality_score"] = calculate_quality_score(domain, False, result["disposable"], "UNKNOWN", result["syntax"])', 
    text
)

text = re.sub(
    r'q_score = calculate_quality_score\(\s*email=email,\s*domain=domain,\s*has_mx=has_mx,\s*has_spf=spf_exists,\s*has_dmarc=dmarc_exists,\s*is_role=result\["role"\],\s*is_disposable=result\["disposable"\]\s*\)',
    r'q_score = calculate_quality_score(domain, has_mx, result["disposable"], "UNKNOWN", result["syntax"])',
    text
)

with open("d:/Quantx/Email Verifier/core/verifier.py", "w", encoding='utf-8') as f:
    f.write(text)

print("Saved")
