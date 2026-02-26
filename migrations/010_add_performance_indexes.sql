-- Migration 010: Performance indexes for 133k+ emails table
-- Composite indexes for common query patterns filtered by user_id

-- 1. User + date (most common: listing emails, date range, stats)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_user_date
    ON emails(user_id, date DESC NULLS LAST);

-- 2. User + account (multi-account filtering)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_user_account
    ON emails(user_id, account_id);

-- 3. User + sender_email (top senders, sender aggregations)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_user_sender_email
    ON emails(user_id, sender_email);

-- 4. Labels array (label filtering: WHERE :label = ANY(labels))
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_labels_gin
    ON emails USING GIN(labels);

-- 5. Attachments + date (attachment search)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_attachments_date
    ON emails(has_attachments, date DESC NULLS LAST)
    WHERE has_attachments = true;

-- 6. Run ANALYZE to update statistics for query planner
ANALYZE emails;
