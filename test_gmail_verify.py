import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import asyncio
from core.verifier import smtp_verify

async def main():
    print(await smtp_verify("test123491823123@gmail.com", ["gmail-smtp-in.l.google.com"]))

asyncio.run(main())
