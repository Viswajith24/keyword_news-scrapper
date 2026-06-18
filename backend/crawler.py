# ## Changes
# - Implemented thread-safe LRU+TTL cache (24h TTL, 1000 entry max) for robots.txt files.
# - Replaced eval() in evaluate_boolean_query with a recursive descent parser.
# - Configured standard browser headers for requests.Session.
# - Implemented automatic requests-to-Selenium fallback on HTTP errors (e.g., 403 blocks).
# - Thread-protected Selenium driver initialization in _get_selenium_driver.
# - Replaced datetime.utcnow() with datetime.now(timezone.utc).
# - Added langdetect library fallback to detect_language if HTML tags yield None.

import re
import json
import hashlib
import urllib.parse
import urllib.robotparser
import collections
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, List, Set
import requests
from bs4 import BeautifulSoup

# Regex patterns that indicate related articles, comments, or other sections that come after the main article
STOP_PATTERNS = [
    re.compile(r'^more\s+(?:.*\s+)?(?:news|articles|stories|headlines)$', re.IGNORECASE),
    re.compile(r'^related\s+(?:.*\s+)?(?:stories|articles|posts|news|content)$', re.IGNORECASE),
    re.compile(r'^you\s+may\s+also\s+like$', re.IGNORECASE),
    re.compile(r'^recommended\s+for\s+you$', re.IGNORECASE),
    re.compile(r'^read\s+next$', re.IGNORECASE),
    re.compile(r'^sponsored\s+(?:.*\s+)?content$', re.IGNORECASE),
    re.compile(r'^latest\s+(?:.*\s+)?(?:stories|news|headlines|articles)$', re.IGNORECASE),
    re.compile(r'^popular\s+(?:.*\s+)?(?:stories|articles|posts)$', re.IGNORECASE),
    re.compile(r'^top\s+stories$', re.IGNORECASE),
    re.compile(r'^trending\s+(?:.*\s+)?(?:stories|news|topics)$', re.IGNORECASE),
    re.compile(r'^comments$', re.IGNORECASE),
    re.compile(r'^discussion$', re.IGNORECASE),
    re.compile(r'^share\s+this\s+article$', re.IGNORECASE),
    re.compile(r'^follow\s+us$', re.IGNORECASE),
    re.compile(r'^newsletter$', re.IGNORECASE),
    re.compile(r'^more\s+from\s+', re.IGNORECASE),
]

# Try importing Selenium modules; handles cases where it is not installed
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Try importing Playwright for Lightpanda integration (CDP path)
try:
    from playwright.sync_api import sync_playwright
    LIGHTPANDA_AVAILABLE = True
except ImportError:
    LIGHTPANDA_AVAILABLE = False

# Thread-safe LRU + TTL Cache for robots.txt parsers
# Format: domain: (RobotFileParser, fetched_at_float)
ROBOTS_CACHE: collections.OrderedDict = collections.OrderedDict()
ROBOTS_CACHE_LOCK = threading.Lock()

def get_chrome_user_agent_details() -> Tuple[str, str]:
    """Dynamically checks Windows registry to construct a User-Agent and its matching major version."""
    import winreg
    version = "120.0.0.0" # Default fallback
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        v, _ = winreg.QueryValueEx(key, "version")
        if v:
            version = v
    except Exception:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome")
            v, _ = winreg.QueryValueEx(key, "DisplayVersion")
            if v:
                version = v
        except Exception:
            pass
    major_version = version.split(".")[0]
    user_agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
    return user_agent, major_version

def patch_chromedriver_if_needed(driver_path: str):
    """Checks if the chromedriver binary is patched; if not, replaces the cdc_ automation variables."""
    import os
    if not driver_path or not os.path.exists(driver_path):
        return
    try:
        with open(driver_path, 'rb') as f:
            data = f.read()
        
        import re
        pattern = re.compile(b"cdc_[a-zA-Z0-9_]+")
        matches = pattern.findall(data)
        
        if not matches:
            return  # Already patched or different structure
            
        # Replace cdc_ with dog_ to avoid signature detection
        new_data = data
        for match in set(matches):
            replacement = match.replace(b"cdc_", b"dog_")
            new_data = new_data.replace(match, replacement)
            
        with open(driver_path, 'wb') as f:
            f.write(new_data)
        print(f"[Stealth] Successfully patched chromedriver binary: {driver_path}")
    except Exception as e:
        print(f"[Stealth Warning] Failed to patch chromedriver: {e}")

class Crawler:
    def __init__(self, user_agent: str = None):
        dynamic_ua, major_version = get_chrome_user_agent_details()
        self.user_agent = user_agent or dynamic_ua
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": f'"Not A(Brand";v="99", "Google Chrome";v="{major_version}", "Chromium";v="{major_version}"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Cache-Control": "max-age=0"
        })
        
        # Configure Selenium driver if requested and available
        self._driver = None
        self._driver_lock = threading.Lock()

    def _get_selenium_driver(self):
        """Initializes and returns a headless Chrome Selenium driver (thread-safe)."""
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium is not installed in the current environment.")
        
        with self._driver_lock:
            if self._driver is None:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument(f"--user-agent={self.user_agent}")
                
                # Avoid bot detection by hiding automation controls
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # Use webdriver-manager to get driver path automatically
                driver_path = ChromeDriverManager().install()
                # Apply local binary patching to replace cdc_ automation signatures on the fly
                patch_chromedriver_if_needed(driver_path)
                
                service = Service(driver_path)
                self._driver = webdriver.Chrome(service=service, options=chrome_options)
                
                # Execute CDP command to remove the navigator.webdriver property completely
                self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                })
            
        return self._driver

    def _fetch_lightpanda(self, url: str) -> str:
        """
        Fetches the HTML of a page using Lightpanda's browser engine via the
        Chrome DevTools Protocol (CDP) connection with Playwright.
        
        This method connects to Lightpanda's CDP endpoint (default: ws://localhost:9222)
        using Playwright's synchronous API, navigates to the target URL, and returns
        the page content.
        """
        if not LIGHTPANDA_AVAILABLE:
            raise RuntimeError("Playwright is not installed in the current environment.")
        
        endpoint = "ws://localhost:9222"
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            try:
                page = browser.new_page()
                page.goto(url)
                return page.content()
            finally:
                browser.close()

    def _get_robots_parser(self, domain: str, robots_url: str) -> urllib.robotparser.RobotFileParser:
        """Retrieves or fetches the RobotFileParser for a domain using an LRU+TTL cache (24h TTL, 1000 entry max)."""
        import time
        now = time.time()
        
        with ROBOTS_CACHE_LOCK:
            if domain in ROBOTS_CACHE:
                rp, fetched_at = ROBOTS_CACHE[domain]
                # If cache is valid (< 24h), move to end (MRU) and return
                if now - fetched_at < 86400:
                    ROBOTS_CACHE.move_to_end(domain)
                    return rp
                else:
                    # Expired, evict
                    del ROBOTS_CACHE[domain]
            
            # Create and parse new parser
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                r = self.session.get(robots_url, timeout=5)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp.allow_all = True
            except Exception:
                rp.allow_all = True
                
            # Evict oldest if cache size >= 1000
            while len(ROBOTS_CACHE) >= 1000:
                ROBOTS_CACHE.popitem(last=False)
                
            ROBOTS_CACHE[domain] = (rp, now)
            return rp

    def close(self):
        """Safely shuts down selenium driver if open."""
        lock = getattr(self, "_driver_lock", None)
        if lock:
            with lock:
                driver = getattr(self, "_driver", None)
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    self._driver = None
        else:
            driver = getattr(self, "_driver", None)
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                self._driver = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def is_allowed_by_robots(self, url: str) -> bool:
        """Checks if the path can be crawled according to robots.txt."""
        try:
            parsed_url = urllib.parse.urlparse(url)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
            robots_url = f"{domain}/robots.txt"
            
            rp = self._get_robots_parser(domain, robots_url)
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            # Fallback to allowed in case of parsing exceptions
            return True

    def fetch_page(self, url: str, engine: str = "fast", ignore_robots: bool = False) -> str:
        """Fetches page content using HTTP requests or Selenium headless Chrome."""
        if not ignore_robots and not self.is_allowed_by_robots(url):
            raise PermissionError("Crawling forbidden by robots.txt")
            
        if engine == "dynamic" and SELENIUM_AVAILABLE:
            try:
                driver = self._get_selenium_driver()
                driver.get(url)
                # Wait up to 5 seconds for page load / body presence
                driver.implicitly_wait(5)
                return driver.page_source
            except Exception as e:
                # Fallback to HTTP requests on selenium error
                print(f"Selenium fetch failed, falling back to HTTP: {e}")
                return self._fetch_http(url)
        elif engine == "lightpanda" and LIGHTPANDA_AVAILABLE:
            try:
                return self._fetch_lightpanda(url)
            except Exception as e:
                print(f"Lightpanda fetch failed, falling back to HTTP: {e}")
                return self._fetch_http(url)
        elif engine == "lightpanda" and not LIGHTPANDA_AVAILABLE:
            print("Lightpanda not installed. Falling back to fast engine.")
            return self._fetch_http(url)
        else:
            try:
                return self._fetch_http(url)
            except requests.exceptions.HTTPError as http_err:
                status_code = http_err.response.status_code if http_err.response is not None else None
                # Only fall back to Selenium for 403 (e.g. Cloudflare / WAF block)
                if status_code == 403 and SELENIUM_AVAILABLE:
                    print(f"HTTP fetch returned 403 for {url}. Falling back to Selenium headless Chrome.")
                    try:
                        driver = self._get_selenium_driver()
                        driver.get(url)
                        driver.implicitly_wait(5)
                        return driver.page_source
                    except Exception as selenium_error:
                        print(f"Selenium fallback also failed: {selenium_error}")
                        raise http_err
                else:
                    raise http_err
            except Exception as e:
                # For connection timeouts, DNS failures, etc., fall back to Selenium if available
                if SELENIUM_AVAILABLE:
                    print(f"HTTP fetch failed for {url} ({e}). Falling back to Selenium headless Chrome.")
                    try:
                        driver = self._get_selenium_driver()
                        driver.get(url)
                        driver.implicitly_wait(5)
                        return driver.page_source
                    except Exception as selenium_error:
                        print(f"Selenium fallback also failed: {selenium_error}")
                        raise e
                else:
                    raise e

    def _fetch_http(self, url: str) -> str:
        """Fetches page content using raw requests."""
        response = self.session.get(url, timeout=7, allow_redirects=True)
        response.raise_for_status()
        return response.text

    @staticmethod
    def clean_html_content(soup: BeautifulSoup) -> str:
        """Removes script, style, footer, header, and nav tags to isolate main body text."""
        # 1. Try to find main article content container for news websites
        # <article>, [itemprop="articleBody"], or main content tags
        main_content = (
            soup.find("article") or 
            soup.find(attrs={"itemprop": "articleBody"}) or
            soup.find("main") or
            soup.find(id="main-content") or
            soup.find(class_="main-content")
        )
        
        # If a specific article or main container is found, work on a copy of that element
        if main_content:
            target_soup = BeautifulSoup(str(main_content), "html.parser")
        else:
            target_soup = BeautifulSoup(str(soup), "html.parser")
            
        # Decompose non-content boilerplate elements
        for tag in target_soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
            
        def apply_stop_patterns(t_soup):
            stop_tag = None
            for tag in t_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section"]):
                txt = tag.get_text().strip()
                if txt:
                    tag_name = tag.name.lower()
                    is_heading = tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]
                    if is_heading or len(txt) < 80:
                        is_stop = False
                        for pattern in STOP_PATTERNS:
                            if pattern.match(txt):
                                is_stop = True
                                break
                        if is_stop:
                            stop_tag = tag
                            break
            if stop_tag:
                to_decompose = list(stop_tag.next_elements)
                stop_tag.decompose()
                for el in to_decompose:
                    try:
                        el.decompose()
                    except Exception:
                        pass

        apply_stop_patterns(target_soup)
        text = target_soup.get_text(separator=" ")
        # Fallback to cleaning the full soup if article heuristic yielded extremely short text
        if main_content and len(text.strip()) < 200:
            target_soup = BeautifulSoup(str(soup), "html.parser")
            for tag in target_soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()
            apply_stop_patterns(target_soup)
            text = target_soup.get_text(separator=" ")
            
        return text

    @staticmethod
    def extract_author(soup: BeautifulSoup) -> Optional[str]:
        """Extracts the author of the page/news article from standard metadata tags or JSON-LD."""
        # 1. Try JSON-LD metadata
        for script in soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    import json
                    data = json.loads(script.string)
                    # Helper to traverse JSON for author
                    def find_author(obj):
                        if isinstance(obj, dict):
                            if obj.get("@type") == "NewsArticle" or obj.get("@type") == "Article":
                                author_obj = obj.get("author")
                                if isinstance(author_obj, dict) and author_obj.get("name"):
                                    return str(author_obj.get("name")).strip()
                                elif isinstance(author_obj, list) and len(author_obj) > 0:
                                    first = author_obj[0]
                                    if isinstance(first, dict) and first.get("name"):
                                        return str(first.get("name")).strip()
                                    elif isinstance(first, str):
                                        return first.strip()
                                elif isinstance(author_obj, str):
                                    return author_obj.strip()
                            for k, v in obj.items():
                                res = find_author(v)
                                if res:
                                    return res
                        elif isinstance(obj, list):
                            for item in obj:
                                res = find_author(item)
                                if res:
                                    return res
                        return None
                    author = find_author(data)
                    if author:
                        return author
                except Exception:
                    pass

        # 2. Try standard Meta tags
        author_selectors = [
            ("meta", {"name": "author"}),
            ("meta", {"property": "article:author"}),
            ("meta", {"name": "twitter:creator"}),
            ("meta", {"property": "og:site_name"})  # Fallback to site name if author is missing
        ]
        for tag_name, attrs in author_selectors:
            tag = soup.find(tag_name, attrs=attrs)
            if tag and tag.get("content"):
                return str(tag.get("content")).strip()
                
        # 3. Try inline author elements
        author_elements = [
            soup.find(class_=re.compile("author|byline|writer", re.I)),
            soup.find(id=re.compile("author|byline|writer", re.I))
        ]
        for element in author_elements:
            if element:
                text = element.get_text().strip()
                # Clean prefix words like "By " or "Posted by "
                text_cleaned = re.sub(r'(?i)^(?:by|posted\s+by)\s+', '', text)
                if 0 < len(text_cleaned) < 100:
                    return text_cleaned
                    
        return None

    @staticmethod
    def extract_image_url(soup: BeautifulSoup, page_url: str = "") -> Optional[str]:
        """Extracts the lead article or OG image URL from the page."""
        image_selectors = [
            ("meta", {"property": "og:image"}),
            ("meta", {"name": "twitter:image"}),
            ("link", {"rel": "image_src"})
        ]
        for tag_name, attrs in image_selectors:
            tag = soup.find(tag_name, attrs=attrs)
            val = tag.get("content") or tag.get("href") if tag else None
            if val:
                # Resolve relative URLs
                if page_url:
                    val = urllib.parse.urljoin(page_url, val.strip())
                return val.strip()
                
        # Fallback to first large image in body
        for img in soup.find_all("img"):
            src = img.get("src")
            if src and not any(ext in src.lower() for ext in [".gif", "logo", "icon", "avatar"]):
                if page_url:
                    src = urllib.parse.urljoin(page_url, src.strip())
                return src.strip()
                
        return None

    @staticmethod
    def detect_language(soup: BeautifulSoup, body_text: str = "") -> Optional[str]:
        """Detects page language from HTML lang tag, meta tags, or langdetect fallback."""
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            return html_tag.get("lang").split("-")[0].strip().lower()
            
        meta_lang = soup.find("meta", attrs={"http-equiv": "content-language"})
        if meta_lang and meta_lang.get("content"):
            return meta_lang.get("content").split(",")[0].strip().lower()
            
        if body_text:
            try:
                from langdetect import detect
                return detect(body_text[:2000])
            except Exception:
                pass
        return None

    @staticmethod
    def detect_date(soup: BeautifulSoup) -> Optional[datetime]:
        """Detects publication or last updated date from page meta tags."""
        date_selectors = [
            ("meta", {"property": "article:published_time"}),
            ("meta", {"property": "og:updated_time"}),
            ("meta", {"name": "pubdate"}),
            ("meta", {"name": "date"}),
            ("meta", {"name": "last-modified"}),
            ("time", {"datetime": True})
        ]
        
        for tag_name, attrs in date_selectors:
            tag = soup.find(tag_name, attrs=attrs)
            if tag:
                val = tag.get("datetime") or tag.get("content")
                if val:
                    try:
                        # Clean string and try to parse standard ISO format
                        val_cleaned = val.split("T")[0]  # Take YYYY-MM-DD
                        return datetime.strptime(val_cleaned, "%Y-%m-%d")
                    except Exception:
                        pass
        return None

    @staticmethod
    def calculate_content_hash(text: str) -> str:
        """Generates MD5 hash of normalized text for duplicate detection."""
        normalized = " ".join(text.lower().split())
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def generate_snippet(self, text: str, terms: Set[str], context_words: int = 20) -> str:
        """Generates a snippet highlighting the keyword."""
        # Find first term occurrence
        normalized_text = " ".join(text.split())
        lower_text = normalized_text.lower()
        
        first_idx = -1
        matched_term = ""
        for term in terms:
            idx = lower_text.find(term.lower())
            if idx != -1 and (first_idx == -1 or idx < first_idx):
                first_idx = idx
                matched_term = term
                
        if first_idx == -1:
            return normalized_text[:150] + "..." if len(normalized_text) > 150 else normalized_text
            
        # Extract surrounding context
        words = normalized_text.split()
        lower_words = [w.lower() for w in words]
        
        # Find which word index contains the match
        match_word_idx = 0
        for i, w in enumerate(lower_words):
            if matched_term.lower() in w:
                match_word_idx = i
                break
                
        start = max(0, match_word_idx - context_words // 2)
        end = min(len(words), match_word_idx + context_words // 2)
        
        snippet = " ".join(words[start:end])
        if start > 0:
            snippet = "... " + snippet
        if end < len(words):
            snippet = snippet + " ..."
            
        return snippet

    def evaluate_boolean_query(self, text: str, query: str, case_sensitive: bool = False) -> bool:
        """
        Parses and evaluates a Boolean search expression on text using a recursive descent parser.
        Supports AND, OR, NOT, and parentheses.
        """
        import re as _re
        def tokenize(q):
            q = q.replace("(", " ( ").replace(")", " ) ")
            return _re.findall(r'\(|\)|"[^"]+"|\bAND\b|\bOR\b|\bNOT\b|\S+', q, _re.IGNORECASE)
        def term_matches(term):
            t = term.strip('"')
            return t in text if case_sensitive else t.lower() in text.lower()
        tokens = tokenize(query)
        pos = [0]
        def peek(): return tokens[pos[0]] if pos[0] < len(tokens) else None
        def consume():
            tok = tokens[pos[0]]; pos[0] += 1; return tok
        def parse_expr(): return parse_or()
        def parse_or():
            left = parse_and()
            while peek() and peek().upper() == "OR": consume(); right = parse_and(); left = left or right
            return left
        def parse_and():
            left = parse_not()
            while peek() and peek().upper() == "AND": consume(); right = parse_not(); left = left and right
            return left
        def parse_not():
            if peek() and peek().upper() == "NOT": consume(); return not parse_atom()
            return parse_atom()
        def parse_atom():
            tok = peek()
            if tok == "(": consume(); val = parse_expr(); consume() if peek() == ")" else None; return val
            if tok is not None: consume(); return term_matches(tok)
            return False
        try: return parse_expr()
        except Exception: return False

    def analyze_page(
        self,
        html_content: str,
        url: str,
        keyword: str,
        match_type: str = "phrase",
        case_sensitive: bool = False,
        exact_match: bool = False
    ) -> Dict[str, Any]:
        """
        Analyzes page contents for keyword matches, generates statistics,
        snippet, metadata, and calculates relevance score.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Gather page metadata
        title = ""
        if soup.title:
            title_text = soup.title.get_text()
            if title_text:
                title = title_text.strip()
        
        meta_desc_tag = (
            soup.find("meta", attrs={"name": "description"}) or 
            soup.find("meta", attrs={"property": "og:description"})
        )
        description = ""
        if meta_desc_tag:
            desc_content = meta_desc_tag.get("content")
            if desc_content:
                if isinstance(desc_content, list):
                    desc_content = " ".join(desc_content)
                description = str(desc_content).strip()
        
        from backend.firecrawl_converter import convert_html_to_firecrawl_schema
        normalized_data = convert_html_to_firecrawl_schema(html_content, url)
        markdown_content = normalized_data["data"]["markdown"]
        
        body_text = self.clean_html_content(soup)
        language = self.detect_language(soup, body_text)
        pub_date = self.detect_date(soup)
        content_hash = self.calculate_content_hash(body_text)
        author = self.extract_author(soup)
        image_url = self.extract_image_url(soup, url)

        
        # 2. Extract domain and check URL keyword presence
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
            
        # 3. Analyze Keyword Match
        matched = False
        total_occurrences = 0
        found_in_title = False
        found_in_description = False
        found_in_body = False
        found_in_url = False
        
        # Prepare list of search terms
        is_keyword_free = not keyword or not keyword.strip()
        
        search_terms_list = []
        if not is_keyword_free:
            try:
                # Check if keyword is a JSON list
                parsed_json = json.loads(keyword)
                if isinstance(parsed_json, list):
                    search_terms_list = [str(k).strip() for k in parsed_json if str(k).strip()]
                else:
                    search_terms_list = [str(parsed_json).strip()]
            except Exception:
                # If not JSON, check if it's comma-separated or newline-separated
                if "," in keyword or "\n" in keyword:
                    search_terms_list = [k.strip() for k in re.split(r'[,\n]', keyword) if k.strip()]
                else:
                    search_terms_list = [keyword.strip()]
            search_terms_list = list(dict.fromkeys(search_terms_list))

        # Check locations and count occurrences
        if is_keyword_free:
            matched = True
            total_occurrences = 0
            found_in_title = False
            found_in_description = False
            found_in_body = False
            found_in_url = False
            matched_keywords_found = []
            search_terms = set()
        else:
            search_terms = set(search_terms_list)
            if match_type == "boolean":
                # Extract plain terms from boolean expression (words/phrases in quotes or alphanumeric)
                search_terms = set(re.findall(r'"([^"]+)"|(\b\w+\b)', keyword))
                # Flatten tuples from findall
                search_terms = {t[0] or t[1] for t in search_terms if t[0] or t[1]}
                search_terms = {t for t in search_terms if t.upper() not in ("AND", "OR", "NOT")}
                
            # Count occurrences in each location
            def count_occurrences(text_content: str, terms: Set[str]) -> int:
                count = 0
                for term in terms:
                    if exact_match:
                        # Match exact words using regex word boundaries
                        pattern = rf"\b{re.escape(term)}\b"
                        flags = 0 if case_sensitive else re.IGNORECASE
                        count += len(re.findall(pattern, text_content, flags))
                    else:
                        # Match substrings
                        if case_sensitive:
                            count += text_content.count(term)
                        else:
                            count += text_content.lower().count(term.lower())
                return count

            found_in_url = count_occurrences(url, search_terms) > 0
            
            title_count = count_occurrences(title, search_terms)
            found_in_title = title_count > 0
            
            desc_count = count_occurrences(description, search_terms)
            found_in_description = desc_count > 0
            
            body_count = count_occurrences(body_text, search_terms)
            found_in_body = body_count > 0
            
            total_occurrences = title_count + desc_count + body_count + (1 if found_in_url else 0)

            # Track which specific keywords matched
            matched_keywords_found = []
            for term in (search_terms if match_type == "boolean" else search_terms_list):
                term_set = {term}
                if (count_occurrences(url, term_set) > 0 or 
                    count_occurrences(title, term_set) > 0 or 
                    count_occurrences(description, term_set) > 0 or 
                    count_occurrences(body_text, term_set) > 0):
                    matched_keywords_found.append(term)
            
            # Evaluate boolean query matching if match_type is boolean
            if match_type == "boolean":
                # We check the entire full text combining title, description, body, url
                full_crawlable_text = f"{title}\n{description}\n{body_text}\n{url}"
                matched = self.evaluate_boolean_query(full_crawlable_text, keyword, case_sensitive)
            else:
                # Require that all searched keywords are found in the parsed content (AND logic)
                matched = len(matched_keywords_found) == len(search_terms_list)

        # 4. Snippet Generation
        snippet = ""
        if matched:
            if is_keyword_free:
                normalized_text = " ".join(body_text.split())
                snippet = normalized_text[:150] + "..." if len(normalized_text) > 150 else normalized_text
            else:
                snippet = self.generate_snippet(body_text, search_terms)
            
        # 5. Relevance Scoring (0-100)
        relevance_score = 0.0
        if matched:
            if is_keyword_free:
                relevance_score = 100.0
            else:
                # Weights: Title (35pts), Description (15pts), URL (10pts), Body density (40pts)
                if found_in_title:
                    relevance_score += 35
                if found_in_description:
                    relevance_score += 15
                if found_in_url:
                    relevance_score += 10
                    
                # Density score (up to 40pts)
                words = body_text.split()
                word_count = len(words)
                if word_count > 0 and body_count > 0:
                    density = body_count / word_count
                    # Peak density is 2% = full 40 points
                    density_score = min(40.0, density * 2000.0)
                    relevance_score += density_score
                    
                relevance_score = round(relevance_score, 1)

        # 6. Extract full images and videos list
        images_list = normalized_data.get("data", {}).get("images", [])
        videos_list = normalized_data.get("data", {}).get("videos", [])
        
        image_links_json = json.dumps([img["src"] for img in images_list if img.get("src")])
        video_links_json = json.dumps([v["src"] for v in videos_list if v.get("src")])

        return {
            "title": title[:200] if title else "Untitled",
            "snippet": snippet,
            "occurrences": total_occurrences,
            "found_in_title": found_in_title,
            "found_in_description": found_in_description,
            "found_in_body": found_in_body,
            "found_in_url": found_in_url,
            "language": language,
            "discovered_at": pub_date or datetime.now(timezone.utc),
            "domain": domain,
            "content_hash": content_hash,
            "description": description,
            "full_content": markdown_content,
            "author": author[:100] if author else "Unknown",

            "image_url": image_url,
            "image_links": image_links_json,
            "video_links": video_links_json,
            "relevance_score": relevance_score,
            "matched": matched,
            "matched_keywords": json.dumps(matched_keywords_found)
        }
