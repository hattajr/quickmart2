-- Convert session_id from TEXT to UUID
ALTER TABLE search_logs
ALTER COLUMN session_id TYPE UUID USING session_id::uuid;

-- Recreate index due to type change
DROP INDEX IF EXISTS idx_search_logs_session_id;
CREATE INDEX idx_search_logs_session_id ON search_logs (session_id);