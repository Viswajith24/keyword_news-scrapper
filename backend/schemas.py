# ## Changes
# - Added ignore_robots parameter to SearchQueryCreate schema.
# - Added ignore_robots parameter to SearchQueryResponse schema.

from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel

class SearchQueryCreate(BaseModel):
    keyword: str
    match_type: Optional[str] = "phrase"  # "phrase" or "boolean"
    case_sensitive: Optional[bool] = False
    exact_match: Optional[bool] = False
    domains_filter: Optional[Dict[str, List[str]]] = None  # {"include": [...], "exclude": [...]}
    languages_filter: Optional[List[str]] = None  # ["en", "es", ...]
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    engine: Optional[str] = "fast"  # "fast", "dynamic", or "lightpanda"
    source_type: Optional[str] = "search"  # "search" or "direct"
    direct_urls: Optional[str] = None  # Multiline string of raw URLs
    ignore_robots: Optional[bool] = False

class SearchQueryResponse(BaseModel):
    id: int
    keyword: str
    match_type: str
    case_sensitive: bool
    exact_match: bool
    domains_filter: Optional[str] = None
    languages_filter: Optional[str] = None
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    engine: str
    source_type: str
    direct_urls: Optional[str] = None
    ignore_robots: bool
    status: str
    total_urls_found: int
    total_urls_crawled: int
    total_urls_matched: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CrawledURLResponse(BaseModel):
    id: int
    search_id: int
    url: str
    domain: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    occurrences: int
    found_in_title: bool
    found_in_description: bool
    found_in_body: bool
    found_in_url: bool
    language: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    relevance_score: float
    is_duplicate: bool
    description: Optional[str] = None
    full_content: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    discovered_at: datetime
    matched_keywords: Optional[str] = None

    class Config:
        from_attributes = True

class PaginatedCrawledURLResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[CrawledURLResponse]

class SearchScheduleCreate(BaseModel):
    keyword: str
    frequency: str  # "daily", "weekly", "monthly"
    engine: Optional[str] = "fast"
    config: SearchQueryCreate

class SearchScheduleResponse(BaseModel):
    id: int
    keyword: str
    frequency: str
    active: bool
    engine: str
    config_json: str
    last_run: Optional[datetime] = None
    next_run: datetime
    created_at: datetime

    class Config:
        from_attributes = True
