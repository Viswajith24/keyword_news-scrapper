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
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET
from sqlalchemy.orm import Session
from sqlalchemy import update
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.database import SessionLocal
from backend.models import SearchQuery, CrawledURL, KeywordProgress
from backend.search_engine import search_web
from backend.crawler import Crawler
from bs4 import BeautifulSoup

# Thread-safe tracker for domain crawl times to enforce rate limits
# Format: {domain: last_request_time_float}
DOMAIN_LAST_CRAWL: Dict[str, float] = {}
domain_lock = threading.Lock()

# Thread-safe tracker for aborted jobs
ABORTED_JOBS: Dict[int, bool] = {}
aborted_lock = threading.Lock()

def request_job_stop(search_id: int):
    with aborted_lock:
        ABORTED_JOBS[search_id] = True

def is_job_stopped(search_id: int) -> bool:
    with aborted_lock:
        return ABORTED_JOBS.get(search_id, False)

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

    if is_job_stopped(search_id):
        db.close()
        return url_id, {"status": "skipped", "error_message": "Job aborted by user."}

    url = crawled_url.url
    domain = crawled_url.domain
    
    # 1. Enforce Domain Rate Limiting
    while True:
        if is_job_stopped(search_id):
            db.close()
            return url_id, {"status": "skipped", "error_message": "Job aborted by user."}
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
            result["error_message"] = None
            break  # Success
        except PermissionError as pe:
            result = {"status": "skipped", "error_message": "Forbidden by robots.txt"}
            break
        except Exception as e:
            result["error_message"] = str(e)
            
            # Check if it is a non-retryable HTTP status code
            is_retryable = True
            # Check if exception has response attribute (indicating an HTTPError)
            response = getattr(e, "response", None)
            if response is not None:
                status_code = getattr(response, "status_code", None)
                if status_code in (404, 410, 401, 403):
                    is_retryable = False
            
            if is_retryable and attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Double delay (4s, 8s)
            else:
                result["status"] = "failed"
                break
                
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
        # Parse list of search keywords
        keywords_list = []
        try:
            # Check if keyword is a JSON list
            parsed_json = json.loads(query.keyword)
            if isinstance(parsed_json, list):
                keywords_list = [str(k).strip() for k in parsed_json if str(k).strip()]
            else:
                keywords_list = [str(parsed_json).strip()]
        except Exception:
            # If not JSON, check if it's comma-separated or newline-separated
            if "," in query.keyword or "\n" in query.keyword:
                keywords_list = [k.strip() for k in re.split(r'[,\n]', query.keyword) if k.strip()]
            else:
                keywords_list = [query.keyword.strip()]

        # Ensure KeywordProgress records exist for all keywords in the query
        for kw in keywords_list:
            kp_record = db.query(KeywordProgress).filter(
                KeywordProgress.search_query_id == search_id,
                KeywordProgress.keyword == kw
            ).first()
            if not kp_record:
                kp_record = KeywordProgress(
                    search_query_id=search_id,
                    keyword=kw,
                    status="pending",
                    articles_found=0
                )
                db.add(kp_record)
        db.commit()

        seen_content_hashes: Set[str] = {
            c.content_hash for c in db.query(CrawledURL).filter(
                CrawledURL.search_id == search_id,
                CrawledURL.content_hash.isnot(None)
            ).all()
        }

        # Parse languages_filter from JSON once
        languages_filter = None
        if query.languages_filter:
            try:
                languages_filter = json.loads(query.languages_filter)
            except Exception as e:
                print(f"Error parsing languages_filter: {e}")

        # Sequentially process each keyword
        for kw in keywords_list:
            if _queue_stop_event.is_set() or is_job_stopped(search_id):
                break

            kp_record = db.query(KeywordProgress).filter(
                KeywordProgress.search_query_id == search_id,
                KeywordProgress.keyword == kw
            ).first()

            if kp_record and kp_record.status == "completed":
                print(f"Skipping completed keyword '{kw}' for search {search_id}")
                continue

            # Mark keyword as processing
            if kp_record:
                kp_record.status = "processing"
                kp_record.started_at = datetime.now(timezone.utc)
                kp_record.completed_at = None
                db.commit()

            # Parse domains_filter
            domains_include = []
            domains_exclude = []
            if query.domains_filter:
                try:
                    df = json.loads(query.domains_filter)
                    domains_include = [d.lower() for d in df.get("include", []) if d.strip()]
                    domains_exclude = [d.lower() for d in df.get("exclude", []) if d.strip()]
                except Exception as e:
                    print(f"Error parsing domains_filter: {e}")

            # Step 1: Gather candidate URLs
            candidate_urls = []
            if query.source_type == "direct":
                raw_direct_urls = fetch_direct_urls(query.direct_urls, db)
                candidate_urls = []
                crawler = Crawler()
                searched_domains = set()
                for d_url in raw_direct_urls:
                    candidate_urls.append(d_url)
                    try:
                        print(f"[INFO] Pre-scanning direct URL for same-domain link expansion: {d_url}")
                        html_text = crawler.fetch_page(d_url, engine="fast", ignore_robots=query.ignore_robots)
                        soup = BeautifulSoup(html_text, "html.parser")
                        parsed_origin = urlparse(d_url)
                        origin_domain = parsed_origin.netloc.lower()
                        if origin_domain.startswith("www."):
                            origin_domain = origin_domain[4:]
                        if origin_domain:
                            searched_domains.add(origin_domain)
                            
                        count = 0
                        for a in soup.find_all("a"):
                            if count >= 100:
                                break
                            href = a.get("href")
                            if href:
                                abs_url = urljoin(d_url, href.strip())
                                parsed_abs = urlparse(abs_url)
                                if parsed_abs.scheme in ("http", "https"):
                                    abs_domain = parsed_abs.netloc.lower()
                                    if abs_domain.startswith("www."):
                                        abs_domain = abs_domain[4:]
                                    if abs_domain == origin_domain:
                                        path = parsed_abs.path.lower()
                                        if not any(path.endswith(ext) for ext in [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".css", ".js", ".xml"]):
                                            candidate_urls.append(abs_url)
                                            count += 1
                    except Exception as ex:
                        print(f"[WARNING] Failed to expand links for {d_url}: {ex}")
                        try:
                            parsed_origin = urlparse(d_url)
                            origin_domain = parsed_origin.netloc.lower()
                            if origin_domain.startswith("www."):
                                origin_domain = origin_domain[4:]
                            if origin_domain:
                                searched_domains.add(origin_domain)
                        except Exception:
                            pass
                crawler.close()
                
                # Perform site-restricted search engine query for each unique domain with the current keyword
                if kw.strip():
                    for domain in searched_domains:
                        try:
                            site_query = f"{kw} site:{domain}"
                            print(f"[INFO] Performing site-restricted search query for direct URL domain: '{site_query}'")
                            search_results = search_web(site_query, max_results=50)
                            print(f"[INFO] Site-restricted search for '{domain}' returned {len(search_results)} URLs.")
                            candidate_urls.extend(search_results)
                        except Exception as search_ex:
                            print(f"[WARNING] Site-restricted search failed for domain '{domain}': {search_ex}")
                            
                candidate_urls = list(dict.fromkeys(candidate_urls))
            else:
                search_query = kw
                if domains_include:
                    if len(domains_include) == 1:
                        search_query = f"{kw} site:{domains_include[0]}"
                    else:
                        search_query = f"{kw} (" + " OR ".join(f"site:{d}" for d in domains_include) + ")"
                # Search web via search engine specifically for this keyword
                candidate_urls = search_web(search_query, max_results=100)

            def get_domain(url):
                d = urlparse(url).netloc.lower()
                return d[4:] if d.startswith("www.") else d

            if domains_include:
                candidate_urls = [u for u in candidate_urls if any(get_domain(u).endswith(d) for d in domains_include)]
            if domains_exclude:
                candidate_urls = [u for u in candidate_urls if not any(get_domain(u).endswith(d) for d in domains_exclude)]

            if not candidate_urls:
                if kp_record:
                    kp_record.status = "completed"
                    kp_record.articles_found = 0
                    kp_record.completed_at = datetime.now(timezone.utc)
                    db.commit()
                continue
                
            # Step 2: Initialize database records for candidates
            db_urls = []
            for url in candidate_urls:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                db_url = db.query(CrawledURL).filter(
                    CrawledURL.search_id == search_id,
                    CrawledURL.url == url
                ).first()
                if not db_url:
                    db_url = CrawledURL(
                        search_id=search_id,
                        url=url,
                        domain=domain,
                        status="pending"
                    )
                    db.add(db_url)
                    db.commit()
                    db_urls.append(db_url)
                else:
                    if db_url.status in ("pending", "failed"):
                        db_urls.append(db_url)
                
            db.commit()
            
            # Update overall total unique URLs found count
            unique_urls_count = db.query(CrawledURL).filter(CrawledURL.search_id == search_id).count()
            query.total_urls_found = unique_urls_count
            db.commit()

            # Step 3: Run Crawler Pool for this keyword
            if query.engine == "fast":
                max_workers = 25
            elif query.engine == "lightpanda":
                max_workers = 10  # Lightpanda is lighter than Chrome but heavier than requests
            else:
                max_workers = 4   # Selenium / dynamic stays at 4
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
                    if _queue_stop_event.is_set() or is_job_stopped(search_id):
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
                                
                        db.flush()
                        
                        # Update counter stats on query atomically based on unique rows in database
                        crawled_count = db.query(CrawledURL).filter(
                            CrawledURL.search_id == search_id,
                            CrawledURL.status != "pending"
                        ).count()
                        
                        matched_count = db.query(CrawledURL).filter(
                            CrawledURL.search_id == search_id,
                            CrawledURL.status == "matched"
                        ).count()
                        
                        db.execute(
                            update(SearchQuery)
                            .where(SearchQuery.id == search_id)
                            .values(
                                total_urls_crawled=crawled_count,
                                total_urls_matched=matched_count
                            )
                        )
                        db.commit()

            # Mark keyword as completed or failed/aborted
            if is_job_stopped(search_id):
                if kp_record:
                    kp_record.status = "failed"
                    kp_record.completed_at = datetime.now(timezone.utc)
                    db.commit()
                break

            keyword_articles_found = db.query(CrawledURL).filter(
                CrawledURL.search_id == search_id,
                CrawledURL.id.in_([u.id for u in db_urls]),
                CrawledURL.status == "matched"
            ).count()

            if kp_record:
                kp_record.status = "completed"
                kp_record.articles_found = keyword_articles_found
                kp_record.completed_at = datetime.now(timezone.utc)
                db.commit()

        # Complete run if not stopped/aborted
        if is_job_stopped(search_id):
            query.status = "aborted"
            query.updated_at = datetime.now(timezone.utc)
            db.commit()
        elif not _queue_stop_event.is_set():
            query.status = "completed"
            query.updated_at = datetime.now(timezone.utc)
            db.commit()
            
            # Automatically synchronize matched records to PostgreSQL
            try:
                from backend.postgres_integration import export_search_to_postgres
                export_search_to_postgres(search_id, db)
                print(f"[PostgreSQL Auto-Sync] Successfully synchronized search {search_id} results.")
            except Exception as pg_err:
                print(f"[PostgreSQL Auto-Sync Warning] Failed to auto-sync results for search {search_id}: {pg_err}")
            
    except Exception as e:
        query.status = "failed"
        query.error_message = f"Queue Worker Error: {str(e)}"
        query.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        with aborted_lock:
            ABORTED_JOBS.pop(search_id, None)
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
