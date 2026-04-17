import smtplib

def test_smtp_exchange():
    try:
        # Yahoo MX: mta5.am0.yahoodns.net
        smtp = smtplib.SMTP("mta5.am0.yahoodns.net", 25, timeout=5)
        smtp.ehlo("mail.quantx-estimation.net")
        print("Connected and EHLO")
        
        status, msg = smtp.mail("verify@mail.quantx-estimation.net")
        print(f"MAIL FROM: {status} {msg}")
        
        status, msg = smtp.rcpt("test_user_super_fake_1234567@yahoo.com")
        print(f"RCPT 1 (random): {status} {msg}")
        smtp.quit()
    except Exception as e:
        print(f"General failure: {e}")

if __name__ == "__main__":
    test_smtp_exchange()
