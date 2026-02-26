CREATE TABLE IF NOT EXISTS saved_queries (
    id VARCHAR(12) PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    description TEXT,
    query_type VARCHAR(20) NOT NULL DEFAULT 'sql',
    query_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
