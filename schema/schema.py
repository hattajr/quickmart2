from pydantic import BaseModel, Field

class SearchLog(BaseModel):
    session_id: str
    query: str
    searched_at: str
    items_found: int = 0



    
