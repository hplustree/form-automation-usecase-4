#!/bin/bash
# Entrypoint script for the application

echo "Starting application initialization..."

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! nc -z ${POSTGRES_HOST:-postgres} ${POSTGRES_PORT:-5432}; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done
echo "PostgreSQL is up and running!"

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
  echo "Redis is unavailable - sleeping"
  sleep 2
done
echo "Redis is up and running!"

# Wait for Weaviate to be ready
echo "Waiting for Weaviate..."
WEAVIATE_HOST=$(echo ${WEAVIATE_URL:-http://weaviate:8080} | sed -E 's|https?://([^:/]+).*|\1|')
while ! nc -z ${WEAVIATE_HOST} 8080; do
  echo "Weaviate is unavailable - sleeping"
  sleep 2
done
echo "Weaviate is up and running!"

# Run database initialization
echo "Initializing database..."
python init_db.py

# Execute the main command
echo "Starting application..."
exec "$@"
