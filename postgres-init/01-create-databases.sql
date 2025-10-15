-- Create siso_pipeline database if it doesn't exist
SELECT 'CREATE DATABASE siso_pipeline'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'siso_pipeline')\gexec

-- Grant all privileges to postgres user
GRANT ALL PRIVILEGES ON DATABASE siso_pipeline TO postgres;
