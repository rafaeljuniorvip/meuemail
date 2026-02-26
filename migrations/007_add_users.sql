-- Migration 007: Create users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    picture TEXT,
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE
);

-- Insert super admin
INSERT INTO users (email, name, role, is_active)
VALUES ('rafaeljrssg@gmail.com', 'Rafael', 'admin', true)
ON CONFLICT (email) DO NOTHING;
