#!/bin/bash

# Start script for siso-pipeline

echo "Starting SISO Pipeline..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and configure it."
    exit 1
fi

# Start services
docker-compose up --build -d

echo ""
echo "Services starting..."
echo "API will be available at: http://localhost:8001"
echo "API Docs: http://localhost:8001/docs"
echo ""
echo "To view logs:"
echo "  docker logs siso-pipeline-api -f"
echo "  docker logs siso-pipeline-worker-1 -f"
echo "  docker logs siso-pipeline-worker-2 -f"
echo ""
echo "To stop services:"
echo "  docker-compose down"
