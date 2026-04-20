import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_EMAIL = "support@veridrax.com"
SMTP_APP_PASSWORD = "sceh mopw mvje wmhc"

# User se email input lo
TO_EMAIL = input("Jis email par OTP bhejna hai: ").strip()

# OTP generate karo — 6 digit
OTP = random.randint(100000, 999999)

print(f"Generated OTP: {OTP}")  # terminal mein bhi dikhe

subject = "Veridrax — Your OTP Code"
html_content = f"""
<div style="font-family: Arial, sans-serif; 
            max-width: 500px; margin: auto; 
            padding: 30px; 
            border: 1px solid #eee; 
            border-radius: 10px;">
            
    <h2 style="color: #333; text-align: center;">
        Veridrax
    </h2>
    
    <p style="color: #555; text-align: center;">
        Your verification code is:
    </p>
    
    <div style="text-align: center; 
                margin: 30px 0;
                padding: 20px;
                background: #f5f5f5;
                border-radius: 8px;">
        <span style="color: #4A90E2; 
                     font-size: 48px; 
                     font-weight: bold;
                     letter-spacing: 8px;">
            {OTP}
        </span>
    </div>
    
    <p style="color: #999; 
              text-align: center; 
              font-size: 13px;">
        This code expires in 10 minutes.
        Do not share this code with anyone.
    </p>
    
    <hr style="border: none; 
               border-top: 1px solid #eee; 
               margin: 20px 0;">
               
    <p style="color: #ccc; 
              text-align: center; 
              font-size: 11px;">
        Veridrax — Professional Email Validation
    </p>
</div>
"""

try:
    print(f"Sending OTP to {TO_EMAIL}...")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = TO_EMAIL
    
    part = MIMEText(html_content, "html")
    msg.attach(part)
    
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    
    print(f"✅ OTP email sent to {TO_EMAIL}")
    print(f"✅ OTP was: {OTP}")
    
    # Verify karo user se
    entered = input("Email mein jo OTP aaya woh yahan likho: ").strip()
    
    if entered == str(OTP):
        print("✅ OTP CORRECT! Verification successful!")
    else:
        print(f"❌ OTP WRONG! Expected: {OTP}, Got: {entered}")

except smtplib.SMTPAuthenticationError:
    print("❌ Authentication failed — App Password check karo!")
    
except Exception as e:
    print(f"❌ Failed: {e}")