import asyncio, sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from src.watcher.auto_scraper import fetch_rss_items, RBI_CIRCULAR_INDEX

async def check():
    print("Fetching RBI circular index via Playwright...")
    items = await fetch_rss_items(RBI_CIRCULAR_INDEX)
    print(f"Total circulars found: {len(items)}")
    for item in items[:5]:
        print(f"  - {item['title'][:70]}")
        print(f"    {item['link'][:70]}")

asyncio.run(check())