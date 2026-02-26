-- iRedMail integration config
CREATE TABLE IF NOT EXISTS iredmail_config (
    id SERIAL PRIMARY KEY,
    mariadb_host VARCHAR(300) NOT NULL,
    mariadb_port INTEGER DEFAULT 3306,
    mariadb_user VARCHAR(100) NOT NULL,
    mariadb_password_encrypted TEXT NOT NULL,
    mariadb_database VARCHAR(100) DEFAULT 'vmail',
    imap_host VARCHAR(300) DEFAULT 'email2.viptecnologia.com.br',
    imap_port INTEGER DEFAULT 993,
    master_user VARCHAR(100) DEFAULT 'dovecotadmin',
    master_password_encrypted TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_discovery_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Track which accounts were imported from iRedMail
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS iredmail_source_email VARCHAR(300);
