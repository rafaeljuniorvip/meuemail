-- Migration 012: Per-user AI configuration
-- Add ai_enabled to users, create user_ai_config table

ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE;

-- Super admin gets AI enabled by default
UPDATE users SET ai_enabled = TRUE WHERE id = 1;

CREATE TABLE IF NOT EXISTS user_ai_config (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    openrouter_api_key TEXT,
    openrouter_model VARCHAR(200) DEFAULT 'anthropic/claude-sonnet-4',
    system_prompt TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Migrate existing global config to super admin (user_id=1)
INSERT INTO user_ai_config (user_id, openrouter_api_key, openrouter_model, system_prompt)
SELECT 1,
    (SELECT value FROM app_config WHERE key = 'openrouter_api_key'),
    COALESCE((SELECT value FROM app_config WHERE key = 'openrouter_model'), 'anthropic/claude-sonnet-4'),
    (SELECT value FROM app_config WHERE key = 'openrouter_system_prompt')
WHERE EXISTS (SELECT 1 FROM app_config WHERE key = 'openrouter_api_key' AND value IS NOT NULL AND value != '')
ON CONFLICT (user_id) DO NOTHING;
