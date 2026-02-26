ALTER TABLE emails ADD COLUMN IF NOT EXISTS account_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_emails_account_id ON emails(account_id);
