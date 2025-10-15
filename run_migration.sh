#!/bin/bash

echo "Running database migrations..."
docker compose exec -T api alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully!"
else
    echo "❌ Migration failed. Please check the logs."
    exit 1
fi

echo ""
echo "Checking migration status..."
docker compose exec -T api alembic current
