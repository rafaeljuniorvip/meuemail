CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(300) NOT NULL,
    provider VARCHAR(20) NOT NULL CHECK (provider IN ('gmail', 'imap')),
    oauth_token TEXT,
    imap_host VARCHAR(300),
    imap_port INTEGER DEFAULT 993,
    imap_username VARCHAR(300),
    imap_password_encrypted TEXT,
    imap_use_ssl BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50) DEFAULT 'idle',
    sync_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_email_provider ON accounts(email, provider);
