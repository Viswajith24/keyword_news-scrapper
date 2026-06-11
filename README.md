# 📰 Keyword News Scraper & Content Analyzer

A premium, modern, glassmorphism-styled web application built with **FastAPI**, **SQLAlchemy (SQLite)**, and **Vanilla JS/CSS** that dynamically crawls websites for target keyword matches. It supports high-speed HTTP retrieval, Selenium headless browser crawling, article text expansion, multi-page pagination searching, and robust file exports (Excel, CSV, JSON, Parquet).

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
- **📊 Interactive Dashboard**:
  - Live processing progress indicators and real-time log monitors.
  - Highlighting matching terms inside page titles, metadata descriptions, URLs, and article body snippets.
  - Interactive popup modal to read full scraped content, lead author info, and lead images.
- **⏱️ Scheduled Automation**: Periodic background schedules (daily, weekly, monthly) using a thread-safe cron manager.
- **📥 Advanced Data Exporters**: One-click streaming downloads for **Excel (.xlsx)**, **CSV**, **JSON**, and **Parquet** formats.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy ORM, Uvicorn, Slowapi, Beautiful Soup 4, Requests, Selenium.
- **Database**: SQLite (Write-Ahead Logging (WAL) enabled for high concurrency).
- **Frontend**: Vanilla HTML5, CSS3 (Glassmorphism design system, CSS Grid/Flexbox, Custom variables), Vanilla ES6 JavaScript.

---

## 📂 Project Directory Structure

```
├── backend/
│   ├── main.py          # FastAPI server app, lifespans, API routes, and rate limits
│   ├── database.py      # SQLite engine session config and startup schemas migration
│   ├── models.py        # SQLAlchemy models (SearchQuery, CrawledURL, etc.)
│   ├── schemas.py       # Pydantic serialization definitions
│   ├── queue_manager.py # Threaded worker loops, domain-rate limits, and scrape tasks
│   ├── crawler.py       # Page fetching, BS4 cleaning, language/date detection, and parser
│   ├── exporter.py      # Spreadsheet stream output generator (Excel/CSV/JSON/Parquet)
│   └── scheduler.py     # Recurring cron scheduler loops for active automations
├── static/
│   ├── index.html       # Single Page Application HTML markup
│   ├── app.js           # AJAX request controllers, polling state, and table renderers
│   └── styles.css       # Premium Dark-mode Glassmorphic neon-glow styling
├── requirements.txt     # Python package requirements checklist
├── run.bat              # Automated Windows setup & launcher script
├── test_crawler.py      # Comprehensive local diagnostic unit tests
└── selenium_scraper.py  # Standalone CLI dynamic sequential pagination scraper
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

Execute the automated test suite to verify database migrations, page parsers, boolean queries, multi-keyword extraction, and exporter modules:

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
3. The script will output a structured JSON containing the extracted text content, lead images, and video resource links from matching landing/paginated pages.

---

## 🔒 Rate Limiting & Performance Configurations

- **Rate Limiting**: To prevent API abuse, endpoints are rate-limited via `slowapi`. The `/api/results/{search_id}` endpoint is set to a maximum of **300 requests/minute** to accommodate real-time front-end polling.
- **SQLite Optimization**: The app runs SQLite in **WAL (Write-Ahead Logging)** mode with a synchronous setting of `NORMAL` and a busy timeout of `30 seconds`. This enables concurrent database reads/writes without table-locking issues.
