# 📰 Keyword News Scraper & Content Analyzer

A premium, modern, glassmorphism-styled web application built with **FastAPI**, **SQLAlchemy (SQLite / PostgreSQL)**, and **Vanilla JS/CSS** that dynamically crawls websites for target keyword matches. It supports high-speed HTTP retrieval, Selenium headless browser crawling, article text expansion, multi-page pagination searching, and robust file exports (Excel, CSV, JSON, Parquet).

---

## ✨ Key Features

- **🌐 Asynchronous Scraper Engine**: Powered by a concurrent `ThreadPoolExecutor` worker queue.
- **⚡ Dual Crawling Engines**:
  - **Fast HTTP Engine (`requests`)**: Fast, lightweight scraping with standard browser headers and rate-limiting enforcement.
  - **Dynamic JS Engine (`selenium`)**: Spawns Headless Chrome to load dynamic web pages, bypass basic bot checks, progressively scroll to trigger lazy loading, and auto-click article expand buttons ("Read More", "Show More", etc.).
- **🔍 Advanced Matching Logic**:
  - **Boolean Search**: Supports logical expressions like `AND`, `OR`, `NOT`, and parenthesis grouping (e.g. `python AND (fastapi OR ruby)`) via a custom recursive descent parser.
  - **Multi-Keyword Lists**: Search for multiple comma- or newline-separated keywords. Matches are flagged in the UI as beautiful tags.
  - **Keyword-Free Archiving**: Toggle keyword filtering off to archive full pages directly.
- **📑 Multi-Page pagination**: Standalone CLI scraper searches sequentially through consecutive next-page links if keywords aren't found on the landing page.
- **🗃️ PostgreSQL Sync & Heuristics Classification**:
  - Automatically synchronizes matched scraping records to a PostgreSQL target database in the background after finishing, or manually via the "Export to PostgreSQL DB" button in the dashboard UI.
  - Features custom heuristics to classify article records automatically by **source type** (News, Journal, Think Tank, Government, Research Institute), **content type** (Article, Report, Policy Brief, Journal, Event, Book, Podcast, Video), **subject theme** (Maritime, Defence, Security, Politics, Economy, General), **country/region coverage** (with custom regex patterns), and **language**.
- **🔥 Firecrawl-Compatible Extraction Normalizer**:
  - An isolated extraction normalization layer that converts raw HTML documents into clean Markdown and structured JSON elements matching the Firecrawl response specifications.
  - Extracts page titles, descriptions, headings, paragraphs, lists, tables, nested code blocks, quotes, and lists of resolved links, image URLs (with dimension/alt metadata), and videos (HTML5 or embedded YouTube/Vimeo/Loom/etc.).
  - Features a self-healing content retention validation block that falls back to minimal cleaning if content is aggressively stripped.
  - Exposes `/api/scrape` for on-demand live scraping and `/api/results/crawled/{url_id}/firecrawl` for retrieving database records in Firecrawl schema.
- **📊 Interactive Dashboard**:
  - Live processing progress indicators and real-time log monitors.
  - Highlighting matching terms inside page titles, metadata descriptions, URLs, and article body snippets.
  - Interactive popup modal to read full scraped content, lead author info, and lead images.
- **⏱️ Scheduled Automation**: Periodic background schedules (daily, weekly, monthly) using a thread-safe cron manager.
- **📥 Advanced Data Exporters**: One-click streaming downloads for **Excel (.xlsx)**, **CSV**, **JSON**, and **Parquet** formats.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy ORM, Uvicorn, Slowapi, Beautiful Soup 4, Requests, Selenium, Psycopg2.
- **Database**: SQLite (local workspace queue and config), PostgreSQL (scraped article production synchronization).
- **Frontend**: Vanilla HTML5, CSS3 (Glassmorphism design system, CSS Grid/Flexbox, Custom variables), Vanilla ES6 JavaScript.

---

## 📂 Project Directory Structure

```
├── backend/
│   ├── main.py                 # FastAPI server app, lifespans, API routes, and rate limits
│   ├── database.py             # SQLite/PostgreSQL engine session config and database startup checks
│   ├── models.py               # SQLAlchemy models (SearchQuery, CrawledURL, etc.)
│   ├── schemas.py              # Pydantic serialization definitions
│   ├── queue_manager.py        # Threaded worker loops, domain-rate limits, and scrape tasks
│   ├── crawler.py              # Page fetching, BS4 cleaning, language/date detection, and parser
│   ├── exporter.py             # Spreadsheet stream output generator (Excel/CSV/JSON/Parquet)
│   ├── scheduler.py            # Recurring cron scheduler loops for active automations
│   ├── firecrawl_converter.py  # Firecrawl content parser, DOM scoring, and Markdown extraction layer
│   └── postgres_integration.py # PostgreSQL scraped_articles sync engine and heuristic classifier
├── static/
│   ├── index.html              # Single Page Application HTML markup with Glassmorphic dashboard
│   ├── app.js                  # AJAX request controllers, polling state, and table renderers
│   └── styles.css              # Premium Dark-mode Glassmorphic neon-glow styling
├── requirements.txt            # Python package requirements checklist (includes psycopg2-binary)
├── run.bat                     # Automated Windows setup & launcher script
├── test_crawler.py             # Comprehensive diagnostic suite for database, search, and normalizer logic
└── selenium_scraper.py         # Standalone CLI dynamic sequential pagination scraper with PostgreSQL classifier
```

---

## 🚀 Installation & Setup

### Option A: One-Click Launcher (Windows)
Double-click the **`run.bat`** file in the root workspace. This script will automatically:
1. Verify if Python is installed.
2. Initialize a Python virtual environment (`.venv`).
3. Upgrade `pip` and install all required modules listed in `requirements.txt`.
4. Open the web interface at `http://127.0.0.1:8000` in your default browser.
5. Start the backend Uvicorn development server.

### Option B: Manual Setup (All OS)

1. **Clone or navigate** into the project directory.
2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```
3. **Activate the virtual environment**:
   - **Windows**: `.venv\Scripts\activate`
   - **macOS/Linux**: `source .venv/bin/activate`
4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
5. **Launch the FastAPI Server**:
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
6. **Open the browser**: Go to `http://127.0.0.1:8000/`.

---

## 🧪 Running Diagnostic Tests

Execute the automated test suite to verify database migrations, page parsers, boolean queries, multi-keyword extraction, exporter modules, classification heuristics, and the Firecrawl normalization layer:

```bash
python test_crawler.py
```

---

## 🖥️ Running the Standalone CLI Scraper

For standalone command-line operations (which check sequential next-page paginations dynamically):

1. Open `selenium_scraper.py` and modify the `test_urls` and `target_keywords` list at the bottom:
   ```python
   test_urls = ["https://realpython.com/tutorials/"]
   target_keywords = ["Python", "automation"]
   ```
2. Run the script:
   ```bash
   python selenium_scraper.py
   ```
3. The script will output a structured JSON containing the extracted text content, lead images, and video resource links from matching landing/paginated pages, conforming to the 19-field classification schema.

---

## 🔒 Rate Limiting & Configurations

- **Rate Limiting**: To prevent API abuse, endpoints are rate-limited via `slowapi`. The `/api/results/{search_id}` endpoint is set to a maximum of **300 requests/minute** to accommodate real-time front-end polling.
- **Database Configuration**: The application leverages SQLite for storing search configurations, schedules, and local crawled URLs.
- **PostgreSQL Configuration**: The production synchronizer connects to PostgreSQL using the connection string configured via the `DATABASE_URL` or `POSTGRES_URL` environment variable. By default, it falls back to:
  `postgresql://postgres:postgres@localhost:5432/keyword_scraper`
  On backend server startup, the system will automatically check if the target database exists on the database server and auto-create it if missing.
