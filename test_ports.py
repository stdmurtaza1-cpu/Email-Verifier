import smtplib

for port in [587, 465, 25]:
    try:
        if port == 465:
            smtp = smtplib.SMTP_SSL("gmail-smtp-in.l.google.com", port, timeout=5)
        else:
            smtp = smtplib.SMTP("gmail-smtp-in.l.google.com", port, timeout=5)
        print(f"Port {port} connected")
        smtp.quit()
    except Exception as e:
        print(f"Port {port} failed: {e}")
