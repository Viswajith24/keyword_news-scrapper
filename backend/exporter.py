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

    # Fetch matched records only
    records = db.query(CrawledURL).filter(
        CrawledURL.search_id == search_id,
        CrawledURL.status == "matched"
    ).order_by(CrawledURL.relevance_score.desc()).all()

    # Get the search query keyword as fallback
    search_keyword = query_record.keyword or ""

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
            "Website Name": r.domain,
            "Keywords": matched_kws or search_keyword,
            "Fully Scraped Content": r.full_content or ""
        })

    # Return empty dataframe if no records exist
    if not data_list:
        return pd.DataFrame(columns=[
            "Website Name", "Keywords", "Fully Scraped Content"
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
