CREATE TABLE search_logs (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,  -- track anonymous users via session token
    query TEXT NOT NULL,
    searched_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Index for fast lookups by session
CREATE INDEX idx_search_logs_session_id ON search_logs (session_id);

-- Optional index for analytics or filtering by time
CREATE INDEX idx_search_logs_searched_at ON search_logs (searched_at);
