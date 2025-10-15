#!/bin/bash
# Script to run database migrations

echo "Waiting for PostgreSQL to be ready..."
while ! nc -z postgres 5432; do
  sleep 1
done

echo "PostgreSQL is ready. Running migrations..."

# Initialize database and run migrations
python init_db.py

echo "Migrations completed."
