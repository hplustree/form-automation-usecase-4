#!/bin/bash

# This script will set up the siso-pipeline project including database initialization
# Run this script from /home/akash/Documents/siso/siso-pipeline directory

echo "Setting up siso-pipeline project..."
# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "Please do not run this script as root"
    exit 1
fi

# Create project structure
echo "Creating project directories..."
mkdir -p app/api app/core app/utils temp_files temp_image_summaries logs

# Set proper permissions
echo "Setting up permissions..."
chmod -R 755 .
chmod +x run_migrations.sh
chmod +x init_db.py

# Check for required commands
echo "Checking for required tools..."
for cmd in python3 pip3 docker docker-compose; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd is not installed. Please install it first."
        exit 1
    fi
done

# Install Python dependencies
echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

# Set up environment variables
if [ ! -f .env ]; then
    echo "Creating .env file from example..."
    cp .env.example .env
    echo "Please edit the .env file with your configuration"
else
    echo ".env file already exists, skipping..."
fi

# Start Docker services
echo "Starting Docker services..."
docker-compose up -d postgres redis

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until docker-compose exec -T postgres pg_isready -U postgres -d siso_pipeline; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done

# Run database migrations
echo "Running database migrations..."
./run_migrations.sh

# Build and start the application
echo "Building and starting the application..."
docker-compose build
docker-compose up -d

echo ""
echo "Setup completed successfully!"
echo ""
echo "Application is now running at http://localhost:8000"
echo ""
echo "Useful commands:"
echo "  docker-compose logs -f     # View application logs"
echo "  docker-compose down        # Stop all services"
echo "  ./run_migrations.sh        # Run database migrations"
echo ""
