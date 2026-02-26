-- Migration 008: Add user_id foreign key to emails, accounts, chat_sessions

-- Add user_id to emails
ALTER TABLE emails ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_emails_user_id ON emails(user_id);

-- Add user_id to accounts
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);

-- Add user_id to chat_sessions
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
