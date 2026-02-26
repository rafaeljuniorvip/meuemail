CREATE TABLE IF NOT EXISTS app_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO app_config (key, value) VALUES
    ('openrouter_api_key', ''),
    ('openrouter_model', 'anthropic/claude-sonnet-4')
ON CONFLICT (key) DO NOTHING;
