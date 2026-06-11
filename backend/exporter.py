# ## Changes
# - Added exporter documentation and changes comment block.

import io
import json
from typing import Tuple
import pandas as pd
from sqlalchemy.orm import Session
from backend.models import CrawledURL, SearchQuery

def get_export_data(search_id: int, db: Session) -> pd.DataFrame:
    """
    Queries matched URLs for a search query and returns them as a Pandas DataFrame.
    """
    query_record = db.query(SearchQuery).filter(SearchQuery.id == search_id).first()
    if not query_record:
        raise ValueError(f"Search Query ID {search_id} not found.")

    # Fetch matched records (or all crawled if there are no matched results, or just all matched)
    # The requirement is: "Display a structured list of matching URLs."
    # We will export only the rows that were crawled and marked "matched", or all crawled rows but with a "Matched" boolean column.
    # Let's export all crawled URLs and include a "Keyword Found" column for complete diagnostic export, sorted by relevance score desc.
    records = db.query(CrawledURL).filter(
        CrawledURL.search_id == search_id,
        CrawledURL.status != "pending"
    ).order_by(CrawledURL.relevance_score.desc()).all()

    data_list = []
    for r in records:
        matched_kws = ""
        if r.matched_keywords:
            try:
                kws = json.loads(r.matched_keywords)
                if isinstance(kws, list):
                    matched_kws = ", ".join(kws)
            except Exception:
                pass

        data_list.append({
            "URL": r.url,
            "Domain": r.domain,
            "Title": r.title or "N/A",
            "Keyword Found": "Yes" if r.status == "matched" else "No",
            "Matched Keywords": matched_kws,
            "Occurrences": r.occurrences,
            "Found in Title": "Yes" if r.found_in_title else "No",
            "Found in Description": "Yes" if r.found_in_description else "No",
            "Found in Body": "Yes" if r.found_in_body else "No",
            "Found in URL": "Yes" if r.found_in_url else "No",
            "Language": r.language or "Unknown",
            "Snippet": r.snippet or "",
            "Relevance Score": r.relevance_score,
            "Description": r.description or "",
            "Full Content": r.full_content or "",
            "Author": r.author or "Unknown",
            "Image URL": r.image_url or "",
            "Duplicate Content": "Yes" if r.is_duplicate else "No",
            "Error Details": r.error_message or "",
            "Discovered Date": r.discovered_at.strftime("%Y-%m-%d %H:%M:%S") if r.discovered_at else "N/A"
        })

    # Return empty dataframe if no records exist
    if not data_list:
        return pd.DataFrame(columns=[
            "URL", "Domain", "Title", "Keyword Found", "Matched Keywords", "Occurrences", 
            "Found in Title", "Found in Description", "Found in Body", 
            "Found in URL", "Language", "Snippet", "Relevance Score", 
            "Description", "Full Content", "Author", "Image URL", "Duplicate Content", "Error Details", "Discovered Date"
        ])

    return pd.DataFrame(data_list)

def export_results(search_id: int, format_type: str, db: Session) -> Tuple[bytes, str]:
    """
    Exports crawling results for a query in the specified format.
    Returns: (bytes_data, media_type)
    """
    df = get_export_data(search_id, db)
    format_type = format_type.lower()

    if format_type == "csv":
        csv_data = df.to_csv(index=False, encoding="utf-8-sig")
        return csv_data.encode("utf-8-sig"), "text/csv"

    elif format_type == "json":
        json_data = df.to_json(orient="records", force_ascii=False, indent=2)
        return json_data.encode("utf-8"), "application/json"

    elif format_type == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Keyword Crawl Results", index=False)
        output.seek(0)
        return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    elif format_type == "parquet":
        output = io.BytesIO()
        df.to_parquet(output, index=False, engine="pyarrow")
        output.seek(0)
        return output.getvalue(), "application/octet-stream"

    else:
        raise ValueError(f"Unsupported export format: {format_type}")
