#!/bin/bash

# This script will create all remaining files for siso-pipeline project
# Run this script from /home/akash/Documents/siso/siso-pipeline directory

echo "Setting up siso-pipeline project..."

# Create project structure
mkdir -p app/api app/core app/utils temp_files temp_image_summaries

# Copy core modules from siso-daex (embedding, llm, validate_agents)
echo "Copying core modules from siso-daex..."
cp ../siso-daex/app/core/embedding.py app/core/
cp ../siso-daex/app/core/llm.py app/core/
cp ../siso-daex/app/core/validate_agents.py app/core/

echo "Project structure created successfully!"
echo ""
echo "Next steps:"
echo "1. Create API endpoints (project.py, status.py, worker.py)"
echo "2. Create requirements.txt"
echo "3. Create .env file"
echo "4. Create docker-compose.yml"
echo "5. Create README.md"
echo ""
echo "Files already created:"
echo "- app/main.py"
echo "- app/logging_config.py"
echo "- app/core/weaviate_client.py"
echo "- app/utils/file_handler.py"
echo "- app/utils/locks.py"
