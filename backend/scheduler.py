# ## Changes
# - Renamed stop event to _scheduler_stop_event to prevent collision with queue manager.
# - Replaced datetime.utcnow() with datetime.now(timezone.utc).
# - Configured triggered SearchQuery to inherit ignore_robots setting from schedule configuration.

import time
import json
import threading
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models import SearchSchedule, SearchQuery

_scheduler_thread = None
_scheduler_stop_event = threading.Event()

def trigger_scheduled_search(db: Session, schedule: SearchSchedule):
    """
    Creates a new pending SearchQuery based on schedule parameters.
    """
    try:
        config = json.loads(schedule.config_json)
    except Exception as e:
        print(f"Error reading configuration for schedule {schedule.id}: {e}")
        return

    # Create new search query in pending state
    new_query = SearchQuery(
        keyword=schedule.keyword,
        match_type=config.get("match_type", "phrase"),
        case_sensitive=config.get("case_sensitive", False),
        exact_match=config.get("exact_match", False),
        domains_filter=json.dumps(config.get("domains_filter")) if config.get("domains_filter") else None,
        languages_filter=json.dumps(config.get("languages_filter")) if config.get("languages_filter") else None,
        engine=schedule.engine,
        source_type=config.get("source_type", "search"),
        direct_urls=config.get("direct_urls"),
        ignore_robots=config.get("ignore_robots", False),
        status="pending"
    )
    
    db.add(new_query)
    
    # Calculate next execution time
    now = datetime.now(timezone.utc)
    schedule.last_run = now
    if schedule.frequency == "daily":
        schedule.next_run = now + timedelta(days=1)
    elif schedule.frequency == "weekly":
        schedule.next_run = now + timedelta(weeks=1)
    elif schedule.frequency == "monthly":
        schedule.next_run = now + timedelta(days=30)
    else:
        schedule.next_run = now + timedelta(days=1) # Default fallback
        
    db.commit()
    print(f"Triggered scheduled search query for keyword: '{schedule.keyword}' (Schedule ID: {schedule.id})")

def scheduler_loop():
    """Background loop checking and triggering active schedules."""
    while not _scheduler_stop_event.is_set():
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            # Find active schedules that are past due
            due_schedules = db.query(SearchSchedule).filter(
                SearchSchedule.active == True,
                SearchSchedule.next_run <= now
            ).all()
            
            for schedule in due_schedules:
                trigger_scheduled_search(db, schedule)
                
        except Exception as e:
            print(f"Error in scheduler loop: {e}")
        finally:
            db.close()
            
        time.sleep(10.0)  # Check schedules every 10 seconds

def start_scheduler():
    """Starts the scheduler background thread."""
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_stop_event.clear()
        _scheduler_thread = threading.Thread(target=scheduler_loop, name="SchedulerThread", daemon=True)
        _scheduler_thread.start()
        print("Scheduler Thread started successfully.")

def stop_scheduler():
    """Stops the scheduler background thread."""
    global _scheduler_thread
    _scheduler_stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=10)
        _scheduler_thread = None
        print("Scheduler Thread stopped.")
