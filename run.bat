@echo off
title Keyword News Scraper Launcher
echo ===================================================
echo      KEYWORD NEWS SCRAPER LAUNCHER
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.9+ from python.org and try again.
    pause
    exit /b 1
)

:: Create Virtual Environment if it does not exist
if not exist .venv (
    echo [INFO] Creating Python virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
      )
)

:: Check if .env file exists; if not, create it from template
if not exist .env (
    if exist .env.example (
        echo [INFO] Creating .env file from .env.example template...
        copy .env.example .env >nul
        echo [SUCCESS] Default .env created. Please configure your PostgreSQL connection in .env.
    ) else (
        echo [WARNING] .env and .env.example not found. Creating a default .env file...
        echo DATABASE_URL=postgresql://postgres:postgres@localhost:5432/keyword_scraper > .env
        echo API_TOKEN=changeme >> .env
        echo [SUCCESS] Default .env created.
    )
)


:: Activate Virtual Environment & Check dependencies
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate

echo [INFO] Checking / Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Dependency installation failed or warnings occurred.
)

echo.
echo [INFO] Starting Keyword News Scraper Backend Server...
echo [INFO] The server will run on http://127.0.0.1:8000
echo [INFO] Press Ctrl+C in this terminal window to stop the server.
echo.

:: Wait 2 seconds and launch browser in parallel
start "" http://127.0.0.1:8000

:: Start Uvicorn Server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

pause
