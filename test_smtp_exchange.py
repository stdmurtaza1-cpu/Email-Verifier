import smtplib

def test_smtp_exchange():
    try:
        smtp = smtplib.SMTP("gmail-smtp-in.l.google.com", 25, timeout=5)
        smtp.ehlo("mail.quantx-estimation.net")
        print("Connected and EHLO")
        
        status, msg = smtp.mail("verify@mail.quantx-estimation.net")
        print(f"MAIL FROM: {status} {msg}")
        
        status, msg = smtp.rcpt("randomtestuser123213@gmail.com")
        print(f"RCPT 1 (random): {status} {msg}")
        
        # Now try to call mail() again, like the current code
        try:
            status, msg = smtp.mail("verify@mail.quantx-estimation.net")
            print(f"MAIL FROM 2: {status} {msg}")
        except Exception as e:
            print(f"MAIL FROM 2 Failed: {e}")
            
        status, msg = smtp.rcpt("anothertest123@gmail.com")
        print(f"RCPT 2: {status} {msg}")
        
        smtp.quit()
    except Exception as e:
        print(f"General failure: {e}")

if __name__ == "__main__":
    test_smtp_exchange()
