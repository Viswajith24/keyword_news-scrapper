# ## Changes
# - Replaced Set[str] with collections.OrderedDict for deterministic URL deduplication.
# - Commented out scrape_google from default search engines list to prevent quick IP bans.

import time
import random
import urllib.parse
from collections import OrderedDict
from typing import List
import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

EXCLUDED_DOMAINS = {
    "google.com", "google.co.in", "google.co.uk", "google.ad", "google.ae",
    "youtube.com", "youtu.be", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "pinterest.com", "duckduckgo.com", "bing.com", "yahoo.com",
    "search.yahoo.com", "microsoft.com", "wikipedia.org", "w3.org", "schema.org"
}

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive"
    }

def is_valid_url(url: str) -> bool:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    
    # Exclude typical static resource extensions
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".css", ".js", ".xml"]):
        return False
        
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
        
    if domain in EXCLUDED_DOMAINS or any(domain.endswith("." + d) for d in EXCLUDED_DOMAINS):
        return False
        
    return True

def scrape_duckduckgo(query: str) -> List[str]:
    """Scrapes DuckDuckGo HTML search page."""
    urls = []
    headers = get_headers()
    # DuckDuckGo HTML search URL
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # DuckDuckGo HTML returns result links inside class "result__snippet" or "result__url"
            for link in soup.find_all("a", class_="result__url"):
                href = link.get("href")
                if href:
                    # Clean DuckDuckGo redirect link
                    # e.g., //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com
                    if "uddg=" in href:
                        parsed_href = urllib.parse.urlparse(href)
                        query_params = urllib.parse.parse_qs(parsed_href.query)
                        if "uddg" in query_params:
                            href = query_params["uddg"][0]
                    
                    if is_valid_url(href):
                        urls.append(href)
    except Exception as e:
        print(f"Error scraping DuckDuckGo: {e}")
        
    return urls

def scrape_duckduckgo_lite(query: str) -> List[str]:
    """Fallback scraping of DuckDuckGo Lite."""
    urls = []
    headers = get_headers()
    search_url = "https://lite.duckduckgo.com/lite/"
    data = {"q": query}
    try:
        response = requests.post(search_url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Links in Lite are inside anchor tags with class 'result-link' or within the search results table
            for link in soup.find_all("a"):
                href = link.get("href")
                if href and "uddg=" in href:
                    parsed_href = urllib.parse.urlparse(href)
                    query_params = urllib.parse.parse_qs(parsed_href.query)
                    if "uddg" in query_params:
                        href = query_params["uddg"][0]
                    if is_valid_url(href):
                        urls.append(href)
    except Exception as e:
        print(f"Error scraping DuckDuckGo Lite: {e}")
    return urls

def scrape_bing(query: str) -> List[str]:
    """Scrapes Bing search results."""
    urls = []
    headers = get_headers()
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Organic results inside <li class="b_algo">
            for item in soup.find_all("li", class_="b_algo"):
                h2 = item.find("h2")
                if h2:
                    link = h2.find("a")
                    if link:
                        href = link.get("href")
                        if is_valid_url(href):
                            urls.append(href)
    except Exception as e:
        print(f"Error scraping Bing: {e}")
        
    return urls

def scrape_yahoo(query: str) -> List[str]:
    """Scrapes Yahoo search results."""
    urls = []
    headers = get_headers()
    search_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Yahoo organic results are inside divs with class 'algo' or 'dd algo'
            for item in soup.find_all("div", class_="algo"):
                link = item.find("a")
                if link:
                    href = link.get("href")
                    # Clean Yahoo redirect URLs if needed (e.g. RU=https%3a%2f%2fexample.com)
                    if href:
                        if "/RU=" in href:
                            start = href.find("/RU=") + 4
                            end = href.find("/", start)
                            if end == -1:
                                end = len(href)
                            href = urllib.parse.unquote(href[start:end])
                        if is_valid_url(href):
                            urls.append(href)
    except Exception as e:
        print(f"Error scraping Yahoo: {e}")
        
    return urls

def scrape_google(query: str) -> List[str]:
    """
    [WARNING] Google blocks headless scrapers in virtually all production environments.
    This function remains here with a warning but is commented out of the default engines list.
    """
    urls = []
    headers = get_headers()
    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    
    try:
        time.sleep(random.uniform(1.0, 2.5))  # Sleep to avoid quick IP bans
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Organic results inside <div class="g">
            for item in soup.find_all("div", class_="g"):
                link = item.find("a")
                if link:
                    href = link.get("href")
                    if is_valid_url(href):
                        urls.append(href)
    except Exception as e:
        print(f"Error scraping Google: {e}")
        
    return urls

def scrape_duckduckgo_selenium(query: str) -> List[str]:
    """
    Fallback search scraper using headless Selenium Chrome to query DuckDuckGo
    in order to bypass bot challenges (202/403 blocks) on standard HTTP requests.
    """
    urls = []
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("[WARNING] Selenium not installed, skipping Selenium DDG fallback.")
        return []

    driver = None
    try:
        print(f"[INFO] Initiating Selenium DuckDuckGo scraper for query: '{query}'...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        search_url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
        driver.get(search_url)
        driver.implicitly_wait(5)
        
        # Wait 3 seconds for client-side JS rendering
        time.sleep(3.0)
        
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        for a in soup.find_all("a"):
            href = a.get("href")
            if href and is_valid_url(href):
                urls.append(href)
                
        # Deduplicate
        urls = list(dict.fromkeys(urls))
        print(f"[SUCCESS] Selenium DuckDuckGo scraper harvested {len(urls)} URLs.")
        
    except Exception as e:
        print(f"[ERROR] Selenium DuckDuckGo scraper failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
                
    return urls

def search_web(query: str, max_results: int = 50) -> List[str]:
    """
    Search the web using multiple engines in parallel and aggregate/deduplicate URLs.
    Falls back to Selenium DuckDuckGo scraper if standard HTTP requests are blocked.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Use OrderedDict for insertion-order deduplication
    aggregated_urls: OrderedDict = OrderedDict()
    
    # Sequence of engines to try. DuckDuckGo HTML is the most scraping friendly.
    # Google is excluded because it blocks headless scrapers in production.
    engines = [
        scrape_duckduckgo,
        scrape_duckduckgo_lite,
        scrape_bing,
        scrape_yahoo
    ]
    
    futures = {}
    print(f"[INFO] Launching search engine queries in parallel for: '{query}'...")
    
    with ThreadPoolExecutor(max_workers=len(engines)) as executor:
        for engine in engines:
            future = executor.submit(engine, query)
            futures[future] = engine.__name__
            
        for future in as_completed(futures):
            engine_name = futures[future]
            try:
                results = future.result()
                print(f"[INFO] Engine {engine_name} returned {len(results)} candidate URLs.")
                for url in results:
                    aggregated_urls[url] = None
            except Exception as e:
                print(f"[ERROR] Engine {engine_name} failed: {e}")
                
    # cap results
    final_urls = list(aggregated_urls.keys())[:max_results]
        
    # If standard HTTP scraping yields 0 results (due to IP blocks/challenges),
    # execute our Selenium DuckDuckGo scraper fallback
    if not final_urls:
        print("[WARNING] All HTTP search engines returned 0 results. Activating Selenium fallback scraper...")
        selenium_results = scrape_duckduckgo_selenium(query)
        for url in selenium_results:
            aggregated_urls[url] = None
        final_urls = list(aggregated_urls.keys())[:max_results]
                
    # Return as list up to max_results
    return final_urls
