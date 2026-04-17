import smtplib

def test_smtp_exchange():
    try:
        smtp = smtplib.SMTP("gmail-smtp-in.l.google.com", 25, timeout=5)
        smtp.ehlo("mail.quantx-estimation.net")
        print("Connected and EHLO")
        
        status, msg = smtp.mail("verify@mail.quantx-estimation.net")
        print(f"MAIL FROM: {status} {msg}")
        
        # We need a valid gmail for RCPT 1 to test Catch-All logic. Let's use generic syntax 
        # But wait, we can just see if doing rcpt -> rcpt works.
        status, msg = smtp.rcpt("test1@gmail.com")
        print(f"RCPT 1: {status} {msg}")
        
        status, msg = smtp.rcpt("test2@gmail.com")
        print(f"RCPT 2: {status} {msg}")
        
        smtp.quit()
    except Exception as e:
        print(f"General failure: {e}")

if __name__ == "__main__":
    test_smtp_exchange()
