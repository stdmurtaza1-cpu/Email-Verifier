import os
from dotenv import load_dotenv

load_dotenv()

from routes.auth import send_email_smtp

def test():
    email = "jhonalbert950@gmail.com"
    subject = "VerifyNinja — Auth Logic Test"
    html_content = "<div style='padding:20px;'><h1>It Works!</h1><p>Auth module logic is perfectly executing.</p></div>"
    
    print("Testing send_email_smtp from routes.auth...")
    try:
        send_email_smtp(email, subject, html_content)
        print("✅ SUCCESS: Background email function in auth.py is working 100%!")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    test()
