import re

with open("d:/Quantx/Email Verifier/core/verifier.py", "r", encoding='utf-8') as f:
    text = f.read()

# We need to remove these local overrides and calculate the dynamic score right before the return statement.
text = re.sub(r'result\["quality_score"\]\s*=\s*\d+', '', text)
text = re.sub(r'result\["confidence"\]\s*=\s*\d+', '', text)

# Insert it before the logger.debug return
target = "logger.debug(f\"--- Verification completed for {email} -> {result['status']}"
insertion = """
    # Calculate final quality score based on all accumulated knowledge and SMTP status
    final_score = calculate_quality_score(
        domain=domain,
        has_mx=has_mx,
        is_disposable=result.get("disposable", False),
        smtp_status=smtp_status if 'smtp_status' in locals() else result["status"],
        syntax_valid=result.get("syntax", False)
    )
    result["quality_score"] = final_score
    result["confidence"] = final_score

    """

text = text.replace(target, insertion + target)

with open("d:/Quantx/Email Verifier/core/verifier.py", "w", encoding='utf-8') as f:
    f.write(text)

print("Saved")
