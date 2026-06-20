import asyncio
import httpx

async def check():
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        resp = await client.get("https://www.rbi.org.in/scripts/rss.aspx")
        print("Status:", resp.status_code)
        print("Content-Type:", resp.headers.get("content-type"))
        print()
        print("First 2000 chars of response:")
        print(resp.text[:2000])

asyncio.run(check())