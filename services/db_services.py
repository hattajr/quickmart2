
from sqlalchemy.orm import Session
from sqlalchemy import text
from schema.schema import SearchLog
from loguru import logger

def log_search_query(db: Session, search_log: SearchLog):
    """ Log a search query to the database."""

# class SearchLog(BaseModel):
#     session_id: str
#     query: str
#     searched_at: str
#     items_found: int = 0
    query = text("""
        INSERT INTO search_logs (session_id, query, searched_at, items_found)
        VALUES (:session_id, :query, :searched_at, :items_found)
    """)
    try:
        db.execute(query, {
            "session_id": search_log.session_id,
            "query": search_log.query,
            "searched_at": search_log.searched_at,
            "items_found": search_log.items_found
        })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error logging search query: {e}")
        return None

    return search_log
