# ## Changes
# - Imported re, Tuple, Any, List, Dict, Set, and timezone from typing/datetime.
# - Renamed stop event to _queue_stop_event to avoid collision with scheduler.
# - Replaced datetime.utcnow() with datetime.now(timezone.utc).
# - Implemented database-atomic counter increments for crawled and matched counters using sqlalchemy.update.
# - Filtered candidate URLs with domains_filter inclusions and exclusions.
# - Filtered crawl results post-parse by languages_filter, date_range_start, and date_range_end.
# - Added unhandled worker crash safety net in queue_worker_loop to mark crashed queries as failed.

import time
import re
import threading
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set, Tuple, Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from sqlalchemy.orm import Session
from sqlalchemy import update
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.database import SessionLocal
from backend.models import SearchQuery, CrawledURL
from backend.search_engine import search_web
from backend.crawler import Crawler

# Thread-safe tracker for domain crawl times to enforce rate limits
# Format: {domain: last_request_time_float}
DOMAIN_LAST_CRAWL: Dict[str, float] = {}
domain_lock = threading.Lock()

# Worker thread variables
_worker_thread = None
_queue_stop_event = threading.Event()

def parse_sitemap_urls(xml_content: str) -> List[str]:
    """Parses URLs from an XML sitemap."""
    urls = []
    try:
        # Remove namespace prefixes for easier parsing if they exist
        xml_content_clean = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
        root = ET.fromstring(xml_content_clean.encode('utf-8'))
        for url_node in root.findall('.//url/loc'):
            if url_node.text:
                urls.append(url_node.text.strip())
    except Exception as e:
        print(f"Error parsing XML sitemap: {e}")
    return urls

def fetch_direct_urls(url_list_str: str, session: Session) -> List[str]:
    """
    Parses and sanitizes input URLs.
    If a URL is an XML sitemap, it fetches and extracts all URLs inside it.
    """
    if not url_list_str:
        return []
        
    raw_urls = [line.strip() for line in url_list_str.split("\n") if line.strip()]
    final_urls = []
    crawler = Crawler()
    
    for url in raw_urls:
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
            
        # Check if it's a sitemap
        parsed = urlparse(url)
        path = parsed.path.lower()
        if path.endswith(".xml") or "sitemap" in path:
            try:
                # Fetch XML content
                xml_text = crawler.fetch_page(url, engine="fast", ignore_robots=True)
                sitemap_urls = parse_sitemap_urls(xml_text)
                final_urls.extend(sitemap_urls)
            except Exception as e:
                print(f"Failed to fetch sitemap {url}: {e}")
                # Fallback to adding sitemap URL directly in case it's a standard page
                final_urls.append(url)
        else:
            final_urls.append(url)
            
    crawler.close()
    return list(dict.fromkeys(final_urls))  # Deduplicate

def crawl_url_task(
    url_id: int,
    search_id: int,
    keyword: str,
    match_type: str,
    case_sensitive: bool,
    exact_match: bool,
    engine: str,
    ignore_robots: bool = False,
    languages_filter: List[str] = None,
    date_range_start: datetime = None,
    date_range_end: datetime = None,
    domain_rate_limit: float = 0.3  # seconds delay between hits to same domain
) -> Tuple[int, Dict[str, Any]]:
    """
    Runs within a ThreadPool worker. Fetches a URL with rate limiting,
    analyzes keyword content, and returns results.
    """
    db = SessionLocal()
    crawled_url = db.query(CrawledURL).filter(CrawledURL.id == url_id).first()
    if not crawled_url:
        db.close()
        return url_id, {"status": "failed", "error_message": "URL record not found in database."}

    url = crawled_url.url
    domain = crawled_url.domain
    
    # 1. Enforce Domain Rate Limiting
    while True:
        with domain_lock:
            now = time.time()
            last_crawl = DOMAIN_LAST_CRAWL.get(domain, 0.0)
            elapsed = now - last_crawl
            remaining = domain_rate_limit - elapsed
            if remaining <= 0:
                DOMAIN_LAST_CRAWL[domain] = now
                break
        # Sleep for the exact remaining duration to avoid active spinning
        time.sleep(max(0.01, remaining))

    crawler = Crawler()
    result = {"status": "failed", "error_message": None}
    
    # 2. Fetch page with retries (up to 2 retries, exponential backoff)
    max_retries = 2
    retry_delay = 1.0
    html_content = ""
    
    for attempt in range(max_retries):
        try:
            html_content = crawler.fetch_page(url, engine=engine, ignore_robots=ignore_robots)
            break  # Success
        except PermissionError as pe:
            result = {"status": "skipped", "error_message": "Forbidden by robots.txt"}
            break
        except Exception as e:
            result["error_message"] = str(e)
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Double delay (4s, 8s)
            else:
                result["status"] = "failed"
                
    crawler.close()
    
    # 3. Analyze page content if fetch was successful
    if html_content:
        try:
            analysis = crawler.analyze_page(
                html_content=html_content,
                url=url,
                keyword=keyword,
                match_type=match_type,
                case_sensitive=case_sensitive,
                exact_match=exact_match
            )
            result.update(analysis)
            # If matched, status is "matched", else "skipped"
            result["status"] = "matched" if analysis["matched"] else "skipped"
            
            # Apply language filter
            if languages_filter and analysis.get("language"):
                if analysis["language"] not in languages_filter:
                    result["status"] = "skipped"
                    result["error_message"] = f"Language '{analysis['language']}' not in filter."
                    
            # Apply date range filters
            pub_date = analysis.get("discovered_at")
            if pub_date and isinstance(pub_date, datetime):
                # If pub_date is timezone-naive, make it timezone-aware to match date_range_start/end
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                if date_range_start:
                    start_date = date_range_start
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                    if pub_date < start_date:
                        result["status"] = "skipped"
                        result["error_message"] = "Page date before date_range_start."
                if date_range_end:
                    end_date = date_range_end
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    if pub_date > end_date:
                        result["status"] = "skipped"
                        result["error_message"] = "Page date after date_range_end."
        except Exception as e:
            result["status"] = "failed"
            result["error_message"] = f"Parsing Error: {str(e)}"
            
    db.close()
    return url_id, result

def process_search_query(search_id: int):
    """
    Pulls candidate URLs (from search engine or direct inputs),
    spawns a thread pool to crawl them, detects duplicates, updates progress,
    and handles final query status.
    """
    db = SessionLocal()
    query = db.query(SearchQuery).filter(SearchQuery.id == search_id).first()
    if not query:
        db.close()
        return

    # Update state to processing
    query.status = "processing"
    query.updated_at = datetime.now(timezone.utc)
    db.commit()

    try:
        # Step 1: Gather candidate URLs
        candidate_urls = []
        if query.source_type == "direct":
            candidate_urls = fetch_direct_urls(query.direct_urls, db)
        else:
            # Search web via search engine
            candidate_urls = search_web(query.keyword, max_results=100)
            
        # Parse and apply domains_filter
        domains_include = []
        domains_exclude = []
        if query.domains_filter:
            try:
                df = json.loads(query.domains_filter)
                domains_include = [d.lower() for d in df.get("include", []) if d.strip()]
                domains_exclude = [d.lower() for d in df.get("exclude", []) if d.strip()]
            except Exception as e:
                print(f"Error parsing domains_filter: {e}")

        def get_domain(url):
            d = urlparse(url).netloc.lower()
            return d[4:] if d.startswith("www.") else d

        if domains_include:
            candidate_urls = [u for u in candidate_urls if any(get_domain(u).endswith(d) for d in domains_include)]
        if domains_exclude:
            candidate_urls = [u for u in candidate_urls if not any(get_domain(u).endswith(d) for d in domains_exclude)]

        if not candidate_urls:
            query.status = "completed"
            query.error_message = "No candidate URLs discovered."
            query.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.close()
            return
            
        # Step 2: Initialize database records for candidates
        db_urls = []
        for url in candidate_urls:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
                
            db_url = CrawledURL(
                search_id=search_id,
                url=url,
                domain=domain,
                status="pending"
            )
            db.add(db_url)
            db_urls.append(db_url)
            
        db.commit()
        
        # Reload query to bind correctly
        query.total_urls_found = len(db_urls)
        db.commit()

        # Step 3: Run Crawler Pool
        # Parse languages_filter from JSON
        languages_filter = None
        if query.languages_filter:
            try:
                languages_filter = json.loads(query.languages_filter)
            except Exception as e:
                print(f"Error parsing languages_filter: {e}")

        seen_content_hashes: Set[str] = set()
        max_workers = 25 if query.engine == "fast" else 4  # Selenium is heavy, limit workers
        futures = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for db_url in db_urls:
                # Submit worker tasks
                future = executor.submit(
                    crawl_url_task,
                    url_id=db_url.id,
                    search_id=search_id,
                    keyword=query.keyword,
                    match_type=query.match_type,
                    case_sensitive=query.case_sensitive,
                    exact_match=query.exact_match,
                    engine=query.engine,
                    ignore_robots=query.ignore_robots,
                    languages_filter=languages_filter,
                    date_range_start=query.date_range_start,
                    date_range_end=query.date_range_end
                )
                futures[future] = db_url.id
                
            for future in as_completed(futures):
                if _queue_stop_event.is_set():
                    break
                    
                url_id, result = future.result()
                
                # Check for duplicates on successful matches/skips
                if result.get("content_hash") and result["status"] in ("matched", "skipped"):
                    h = result["content_hash"]
                    if h in seen_content_hashes:
                        result["status"] = "skipped"
                        result["is_duplicate"] = True
                        result["error_message"] = "Duplicate page content detected."
                    else:
                        seen_content_hashes.add(h)

                # Write results to DB for this URL
                db_item = db.query(CrawledURL).filter(CrawledURL.id == url_id).first()
                if db_item:
                    for key, val in result.items():
                        if hasattr(db_item, key):
                            setattr(db_item, key, val)
                            
                    # Update counter stats on query atomically
                    db.execute(
                        update(SearchQuery)
                        .where(SearchQuery.id == search_id)
                        .values(total_urls_crawled=SearchQuery.total_urls_crawled + 1)
                    )
                    if db_item.status == "matched":
                        db.execute(
                            update(SearchQuery)
                            .where(SearchQuery.id == search_id)
                            .values(total_urls_matched=SearchQuery.total_urls_matched + 1)
                        )
                    db.commit()

        # Complete run
        query.status = "completed"
        query.updated_at = datetime.now(timezone.utc)
        db.commit()
        
    except Exception as e:
        query.status = "failed"
        query.error_message = f"Queue Worker Error: {str(e)}"
        query.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

def queue_worker_loop():
    """Background worker loop polling for pending jobs."""
    while not _queue_stop_event.is_set():
        db = SessionLocal()
        try:
            # Query for first pending task
            pending_query = db.query(SearchQuery).filter(SearchQuery.status == "pending").first()
            if pending_query:
                db.close()  # Close session before starting heavy thread process
                try:
                    process_search_query(pending_query.id)
                except Exception as e:
                    # Safety net to recover query state in case of worker crash
                    recovery_db = SessionLocal()
                    try:
                        q = recovery_db.query(SearchQuery).filter(SearchQuery.id == pending_query.id).first()
                        if q and q.status not in ("completed", "failed"):
                            q.status = "failed"
                            q.error_message = f"Unhandled worker crash: {str(e)}"
                            q.updated_at = datetime.now(timezone.utc)
                            recovery_db.commit()
                    except Exception as commit_err:
                        print(f"Error recovering query in queue safety net: {commit_err}")
                    finally:
                        recovery_db.close()
            else:
                db.close()
                time.sleep(2.0)  # Wait 2 seconds before polling again
        except Exception as e:
            print(f"Error in queue worker loop: {e}")
            try:
                db.close()
            except Exception:
                pass
            time.sleep(5.0)

def start_queue_worker():
    """Starts the queue manager background thread."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _queue_stop_event.clear()
        _worker_thread = threading.Thread(target=queue_worker_loop, name="QueueWorkerThread", daemon=True)
        _worker_thread.start()
        print("Queue Worker Thread started successfully.")

def stop_queue_worker():
    """Stops the queue manager background thread."""
    global _worker_thread
    _queue_stop_event.set()
    if _worker_thread:
        _worker_thread.join(timeout=10)
        _worker_thread = None
        print("Queue Worker Thread stopped.")
