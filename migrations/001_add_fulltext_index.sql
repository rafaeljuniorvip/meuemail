-- Habilitar extensão pg_trgm para busca fuzzy
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Coluna tsvector + índice GIN para full-text search no body
ALTER TABLE emails ADD COLUMN IF NOT EXISTS body_tsv tsvector;
UPDATE emails SET body_tsv = to_tsvector('portuguese', COALESCE(body, ''));
CREATE INDEX IF NOT EXISTS idx_emails_body_tsv ON emails USING GIN(body_tsv);

-- Trigger para manter body_tsv atualizado automaticamente
CREATE OR REPLACE FUNCTION emails_body_tsv_trigger() RETURNS trigger AS $$
BEGIN
    NEW.body_tsv := to_tsvector('portuguese', COALESCE(NEW.body, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_emails_body_tsv ON emails;
CREATE TRIGGER trg_emails_body_tsv BEFORE INSERT OR UPDATE OF body ON emails
    FOR EACH ROW EXECUTE FUNCTION emails_body_tsv_trigger();

-- Índices trigram para busca fuzzy em subject e sender
CREATE INDEX IF NOT EXISTS idx_emails_subject_trgm ON emails USING GIN(subject gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_emails_sender_trgm ON emails USING GIN(sender gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_emails_sender_email_trgm ON emails USING GIN(sender_email gin_trgm_ops);
