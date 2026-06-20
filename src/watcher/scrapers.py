import re
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .models import ScrapeResult

logger = logging.getLogger("watcher.scrapers")


class RBIScraper:
    BASE_URL = "https://www.rbi.org.in"
    CIRCULAR_PAGE = "https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx"

    async def scrape(self, client: httpx.AsyncClient) -> list[ScrapeResult]:
        results = []
        try:
            resp = await client.get(self.CIRCULAR_PAGE, timeout=20)
            resp.raise_for_status()
            results = self._parse(resp.text)
        except Exception as e:
            logger.error(f"RBI scrape failed: {e}")
        logger.info(f"RBI: found {len(results)} items")
        return results

    def _parse(self, html: str) -> list[ScrapeResult]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for row in soup.select("table tr"):
            link = row.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if not any(x in href.lower() for x in [".pdf", "notification", "circular", "bs_"]):
                continue
            url = href if href.startswith("http") else urljoin(self.BASE_URL, href)
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            date_text = None
            for cell in row.find_all("td"):
                text = cell.get_text(strip=True)
                if re.search(r"\d{4}", text) and len(text) < 25:
                    date_text = text
                    break
            circular_no = None
            match = re.search(r"RBI/\d{4}-\d{2,4}/\d+", row.get_text(" "))
            if match:
                circular_no = match.group()
            results.append(ScrapeResult(
                regulator="RBI",
                title=title,
                url=url,
                date_issued=date_text,
                circular_no=circular_no,
            ))
        return results


class SEBIScraper:
    BASE_URL = "https://www.sebi.gov.in"
    CIRCULAR_PAGE = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=2&smid=0"

    async def scrape(self, client: httpx.AsyncClient) -> list[ScrapeResult]:
        results = []
        try:
            resp = await client.get(self.CIRCULAR_PAGE, timeout=20)
            resp.raise_for_status()
            results = self._parse(resp.text)
        except Exception as e:
            logger.error(f"SEBI scrape failed: {e}")
        logger.info(f"SEBI: found {len(results)} items")
        return results

    def _parse(self, html: str) -> list[ScrapeResult]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if ".pdf" not in href.lower():
                continue
            url = href if href.startswith("http") else urljoin(self.BASE_URL, href)
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            parent = link.find_parent("tr") or link.find_parent("li")
            date_text = None
            if parent:
                match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", parent.get_text())
                if match:
                    date_text = match.group(1)
            results.append(ScrapeResult(
                regulator="SEBI", title=title, url=url, date_issued=date_text
            ))
        return results


class IRDAIScraper:
    BASE_URL = "https://irdai.gov.in"
    CIRCULAR_PAGE = "https://irdai.gov.in/web/guest/circulars"

    async def scrape(self, client: httpx.AsyncClient) -> list[ScrapeResult]:
        results = []
        try:
            resp = await client.get(self.CIRCULAR_PAGE, timeout=20)
            resp.raise_for_status()
            results = self._parse(resp.text)
        except Exception as e:
            logger.error(f"IRDAI scrape failed: {e}")
        logger.info(f"IRDAI: found {len(results)} items")
        return results

    def _parse(self, html: str) -> list[ScrapeResult]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if ".pdf" not in href.lower():
                continue
            url = href if href.startswith("http") else urljoin(self.BASE_URL, href)
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            parent = link.find_parent("tr") or link.find_parent("div")
            date_text = None
            if parent:
                match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", parent.get_text())
                if match:
                    date_text = match.group(1)
            results.append(ScrapeResult(
                regulator="IRDAI", title=title, url=url, date_issued=date_text
            ))
        return results