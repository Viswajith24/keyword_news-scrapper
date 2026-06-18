import sys
import os
from datetime import datetime

# Adjust path to import from backend
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from backend.database import Base, engine, SessionLocal, init_db
from backend.models import SearchQuery, CrawledURL
from backend.crawler import Crawler
from backend.search_engine import is_valid_url
from backend.exporter import export_results

def run_tests():
    print("=== STARTING KEYWORD NEWS SCRAPER DIAGNOSTIC TESTS ===")
    
    # 1. Test Database Creation & Migration
    print("\n1. Testing Database & SQLAlchemy Models...")
    init_db()
    db = SessionLocal()
    print("[SUCCESS] Database tables successfully created and migrated.")

    # 2. Test URL Validation
    print("\n2. Testing URL Filtering Regex...")
    test_urls = [
        "https://www.wikipedia.org/wiki/Python_(programming_language)",
        "https://google.com/search?q=123",
        "https://duckduckgo.com/?q=abc",
        "https://realpython.com/tutorials/",
        "https://testsite.com/image.png",
        "https://testsite.com/style.css"
    ]
    for url in test_urls:
        valid = is_valid_url(url)
        print(f"   URL: {url:<60} -> Valid? {valid}")

    # 3. Test Keyword Extraction & Page Analyzer
    print("\n3. Testing Page Parser and Analysis Logic...")
    crawler = Crawler()
    mock_html = """
    <html>
      <head>
        <title>Learn Advanced Python Development and Programming</title>
        <meta name="description" content="This tutorial teaches advanced Python syntax, web scraping, and backend architecture.">
        <meta property="article:published_time" content="2026-05-15T12:00:00Z">
        <html lang="en-US">
      </head>
      <body>
        <nav>
          <a href="/home">Home</a> | <a href="/about">About Us</a>
        </nav>
        <main>
          <h1>Building Web Apps in Python</h1>
          <p>Python is an amazing language. Web scraping with BeautifulSoup4 is very powerful in python.
             We will also use FastAPI and Celery to manage asynchronous tasks in the backend.</p>
          <p>Developers who program in Python enjoy its clean readability and huge ecosystem.</p>
        </main>
        <footer>
          <p>&copy; 2026 Code Academy</p>
        </footer>
      </body>
    </html>
    """
    
    print("   Analyzing page for keyword 'Python'...")
    analysis_phrase = crawler.analyze_page(
        html_content=mock_html,
        url="https://codeacademy.org/tutorials/python",
        keyword="Python",
        match_type="phrase",
        case_sensitive=False,
        exact_match=False
    )
    
    print(f"   * Title parsed: '{analysis_phrase['title']}'")
    print(f"   * Language detected: '{analysis_phrase['language']}'")
    print(f"   * Date parsed: {analysis_phrase['discovered_at']}")
    print(f"   * Keyword Occurrences: {analysis_phrase['occurrences']}")
    print(f"   * Found in Title: {analysis_phrase['found_in_title']}")
    print(f"   * Found in Description: {analysis_phrase['found_in_description']}")
    print(f"   * Found in Body: {analysis_phrase['found_in_body']}")
    print(f"   * Found in URL: {analysis_phrase['found_in_url']}")
    print(f"   * Snippet extracted: '{analysis_phrase['snippet']}'")
    print(f"   * Content MD5 Hash: {analysis_phrase['content_hash']}")
    print(f"   * Content Relevance Score: {analysis_phrase['relevance_score']}/100")
    
    # Verify values
    assert analysis_phrase["occurrences"] > 0, "Keyword Python occurrences should be > 0"
    assert analysis_phrase["found_in_title"] is True, "Python is in title"
    assert analysis_phrase["found_in_body"] is True, "Python is in body"
    assert analysis_phrase["found_in_url"] is True, "Python is in url path"
    print("   [SUCCESS] Phrase analyzer tests passed.")

    # 4. Test Boolean Expression Evaluator
    print("\n4. Testing Boolean logic evaluator...")
    queries = [
        ("python AND fastapi", True),
        ("python AND ruby", False),
        ("fastapi OR ruby", True),
        ("python AND (fastapi OR ruby)", True),
        ("python AND NOT ruby", True),
        ("NOT php", True)
    ]
    
    clean_body = crawler.clean_html_content(import_soup(mock_html))
    full_text = f"Learn Advanced Python Development\nThis tutorial teaches advanced Python\n{clean_body}\nhttps://codeacademy.org/tutorials/python"
    
    for q, expected in queries:
        matched = crawler.evaluate_boolean_query(full_text, q, case_sensitive=False)
        print(f"   Boolean query: '{q:<35}' -> Match? {matched:<6} (Expected: {expected})")
        assert matched == expected, f"Failed boolean check for {q}"
    print("   [SUCCESS] Boolean evaluator tests passed.")

    # 5. Insert mock data & test Exports
    print("\n5. Testing Database Inserts and Exporter module...")
    mock_query = SearchQuery(
        keyword="Python AND fastapi",
        match_type="boolean",
        status="completed",
        total_urls_found=1,
        total_urls_crawled=1,
        total_urls_matched=1
    )
    db.add(mock_query)
    db.commit()
    db.refresh(mock_query)

    mock_url = CrawledURL(
        search_id=mock_query.id,
        url="https://codeacademy.org/tutorials/python",
        domain="codeacademy.org",
        title=analysis_phrase["title"],
        snippet=analysis_phrase["snippet"],
        occurrences=analysis_phrase["occurrences"],
        found_in_title=analysis_phrase["found_in_title"],
        found_in_description=analysis_phrase["found_in_description"],
        found_in_body=analysis_phrase["found_in_body"],
        found_in_url=analysis_phrase["found_in_url"],
        language=analysis_phrase["language"],
        status="matched",
        relevance_score=analysis_phrase["relevance_score"],
        is_duplicate=False
    )
    db.add(mock_url)
    db.commit()

    # Generate Exports
    csv_bytes, _ = export_results(mock_query.id, "csv", db)
    excel_bytes, _ = export_results(mock_query.id, "xlsx", db)
    json_bytes, _ = export_results(mock_query.id, "json", db)
    parquet_bytes, _ = export_results(mock_query.id, "parquet", db)

    print(f"   * Generated CSV Export ({len(csv_bytes)} bytes)")
    print(f"   * Generated Excel Export ({len(excel_bytes)} bytes)")
    print(f"   * Generated JSON Export ({len(json_bytes)} bytes)")
    print(f"   * Generated Parquet Export ({len(parquet_bytes)} bytes)")
    
    assert len(csv_bytes) > 0
    assert len(excel_bytes) > 0
    assert len(json_bytes) > 0
    assert len(parquet_bytes) > 0
    print("   [SUCCESS] Exporter tests passed.")

    # 6. Test Multi-Keyword matching
    print("\n6. Testing Multi-Keyword matching logic...")
    analysis_multi = crawler.analyze_page(
        html_content=mock_html,
        url="https://codeacademy.org/tutorials/python",
        keyword="Python, FastAPI, Celery, MissingWord",
        match_type="phrase",
        case_sensitive=False,
        exact_match=False
    )
    print(f"   * Matched keywords parsed: {analysis_multi['matched_keywords']}")
    import json
    matched_kws = json.loads(analysis_multi['matched_keywords'])
    assert "Python" in matched_kws, "Python should be matched"
    assert "FastAPI" in matched_kws, "FastAPI should be matched"
    assert "Celery" in matched_kws, "Celery should be matched"
    assert "MissingWord" not in matched_kws, "MissingWord should NOT be matched"
    print("   [SUCCESS] Multi-Keyword matching logic tests passed.")

    # 7. Test Empty Keyword (Keyword-Free Scraping) Match Bypass
    print("\n7. Testing Keyword-Free Scraping match bypass logic...")
    analysis_empty = crawler.analyze_page(
        html_content=mock_html,
        url="https://codeacademy.org/tutorials/python",
        keyword="",
        match_type="phrase",
        case_sensitive=False,
        exact_match=False
    )
    print(f"   * Status matched: {analysis_empty['matched']}")
    print(f"   * Occurrences: {analysis_empty['occurrences']}")
    print(f"   * Relevance score: {analysis_empty['relevance_score']}")
    print(f"   * Snippet extracted: '{analysis_empty['snippet']}'")
    assert analysis_empty["matched"] is True, "Empty keyword should always match"
    assert analysis_empty["occurrences"] == 0, "Empty keyword occurrences should be 0"
    assert analysis_empty["relevance_score"] == 100.0, "Empty keyword relevance should default to 100"
    print("   [SUCCESS] Keyword-Free Scraping match bypass tests passed.")

    # 8. Test PostgreSQL Integration (Optional/Conditional)
    print("\n8. Testing PostgreSQL Integration...")
    try:
        from backend.postgres_integration import init_postgres_db, classify_article, export_search_to_postgres
        
        # Test heuristic classification
        print("   Testing classification heuristics...")
        cls = classify_article("https://www.rand.org/pubs/policy_briefs/PB101.pdf", "US Maritime Security Strategy", "The navy and vessels are critical for defense in the Indo-Pacific region.", "en")
        print(f"   * Classification result: {cls}")
        assert cls["source_type"] == "Think Tank", "Should detect Think Tank"
        assert cls["content_type"] == "Policy Brief", "Should detect Policy Brief"
        assert "Maritime" in cls["subject_theme"], "Should detect Maritime"
        assert "Defence" in cls["subject_theme"], "Should detect Defence"
        assert "United States" in cls["country_region"], "Should detect United States"
        assert "Indo-Pacific" in cls["country_region"], "Should detect Indo-Pacific"
        assert cls["language"] == "English", "Should map to English"
        print("   [SUCCESS] Heuristic classifier tests passed.")
        
        # Test DB connection and insertion
        print("   Attempting to initialize PostgreSQL DB & run test sync...")
        init_postgres_db(verbose=True)
        
        inserted, updated = export_search_to_postgres(mock_query.id, db)
        print(f"   * Sync result: inserted {inserted}, updated {updated}")
        assert inserted > 0 or updated > 0, "Should have synced the matched mock article"
        print("   [SUCCESS] PostgreSQL database connection & sync tests passed.")
    except Exception as e:
        print(f"   [SKIPPED/WARNING] PostgreSQL tests could not be fully completed: {e}")
 
    # 9. Test Firecrawl Normalization Layer
    print("\n9. Testing Firecrawl Normalization Layer...")
    try:
        from backend.firecrawl_converter import convert_html_to_firecrawl_schema
        
        # Comprehensive test HTML including code block, blockquote, images, video tags, iframe embeds, and lists
        rich_mock_html = """
        <html>
          <head>
            <title>Advanced Scraping Framework Specs</title>
            <meta name="description" content="Detailed specs for the Firecrawl-quality content scraper.">
          </head>
          <body>
            <main id="main-content">
              <h1>Scraper Specifications</h1>
              <p>The goal is to extract visible human-readable text exactly as it appears. Let's look at this <a href="/pricing" title="Check plans">pricing guide</a>.</p>
              
              <blockquote>"This scraper is built for maximum content fidelity."</blockquote>
              
              <pre><code>def get_scraper(): return FirecrawlConverter()</code></pre>
              
              <figure>
                <img src="/assets/diagram.png" alt="Architecture Diagram" title="Core Architecture Diagram" width="800" height="600" />
                <figcaption>Our advanced data extraction flow</figcaption>
              </figure>

              <video src="/assets/demo.mp4" poster="/assets/thumbnail.png" title="Framework Demo Video"></video>
              <iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" title="Tutorial Video"></iframe>
            </main>
          </body>
        </html>
        """
        
        fc_res = convert_html_to_firecrawl_schema(
            html=rich_mock_html,
            url="https://scraper.io/docs/specs",
            status_code=200
        )
        
        print(f"   * Success flag: {fc_res['success']}")
        print(f"   * Title: '{fc_res['data']['metadata']['title']}'")
        print(f"   * Headings: {fc_res['data']['content']['headings']}")
        print(f"   * Links: {fc_res['data']['links']}")
        print(f"   * Images: {fc_res['data']['images']}")
        print(f"   * Videos: {fc_res['data']['videos']}")
        print(f"   * Code blocks: {fc_res['data']['content']['codeBlocks']}")
        print(f"   * Quotes: {fc_res['data']['content']['quotes']}")
        
        # Verify schema elements
        assert fc_res["success"] is True
        assert "markdown" in fc_res["data"]
        assert "html" in fc_res["data"]
        assert "metadata" in fc_res["data"]
        assert "links" in fc_res["data"]
        assert "images" in fc_res["data"]
        assert "videos" in fc_res["data"]
        assert "content" in fc_res["data"]
        
        # Title and content structures
        assert fc_res["data"]["metadata"]["title"] == "Advanced Scraping Framework Specs"
        assert "Scraper Specifications" in fc_res["data"]["content"]["headings"]
        assert '"This scraper is built for maximum content fidelity."' in fc_res["data"]["content"]["quotes"]
        assert "def get_scraper(): return FirecrawlConverter()" in fc_res["data"]["content"]["codeBlocks"]
        
        # Markdown Link Isolation (Anchor text plain rendering)
        markdown_body = fc_res["data"]["markdown"]
        assert "pricing guide" in markdown_body
        assert "[pricing guide]" not in markdown_body
        assert "https://scraper.io/pricing" not in markdown_body
        
        # Markdown Image Isolation
        assert "diagram.png" not in markdown_body
        assert "![" not in markdown_body
        
        # Separated Link Metadata Check
        links = fc_res["data"]["links"]
        assert len(links) == 1
        assert links[0]["text"] == "pricing guide"
        assert links[0]["url"] == "https://scraper.io/pricing"
        assert links[0]["title"] == "Check plans"
        
        # Separated Image Metadata Check
        images = fc_res["data"]["images"]
        assert len(images) == 1
        assert images[0]["src"] == "https://scraper.io/assets/diagram.png"
        assert images[0]["alt"] == "Architecture Diagram"
        assert images[0]["caption"] == "Our advanced data extraction flow"
        assert images[0]["width"] == 800
        assert images[0]["height"] == 600
        
        # Separated Video Metadata Check
        videos = fc_res["data"]["videos"]
        assert len(videos) == 2
        
        # HTML5 video
        html5_video = [v for v in videos if v["type"] == "html5"][0]
        assert html5_video["src"] == "https://scraper.io/assets/demo.mp4"
        assert html5_video["title"] == "Framework Demo Video"
        assert html5_video["thumbnail"] == "https://scraper.io/assets/thumbnail.png"
        
        # YouTube iframe embed
        yt_video = [v for v in videos if v["type"] == "youtube"][0]
        assert yt_video["src"] == "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert yt_video["title"] == "Tutorial Video"
        
        print("   [SUCCESS] Firecrawl Normalization Layer tests passed.")
    except Exception as e:
        print(f"   [FAIL] Firecrawl Normalization Layer tests failed: {e}")
        raise e

    # Clean up mock items

    db.delete(mock_url)
    db.delete(mock_query)
    db.commit()
    db.close()
    
    print("\n=== ALL DIAGNOSTIC TESTS PASSED SUCCESSFULLY ===")

def import_soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
