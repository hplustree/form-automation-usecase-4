#!/bin/bash

echo "=== SISO Pipeline Setup Verification ==="
echo ""

# Check if all required files exist
echo "Checking required files..."
files=(
    "app/main.py"
    "app/api/project.py"
    "app/api/status.py"
    "app/api/worker.py"
    "app/core/weaviate_client.py"
    "app/core/embedding.py"
    "app/core/llm.py"
    "app/core/validate_agents.py"
    "app/utils/file_handler.py"
    "app/utils/locks.py"
    "requirements.txt"
    "Dockerfile"
    "docker-compose.yml"
    ".env.example"
)

missing_files=0
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ $file"
    else
        echo "✗ $file (MISSING)"
        missing_files=$((missing_files + 1))
    fi
done

echo ""
if [ $missing_files -eq 0 ]; then
    echo "✓ All required files present"
else
    echo "✗ $missing_files files missing"
    exit 1
fi

# Check if .env exists
echo ""
echo "Checking configuration..."
if [ -f .env ]; then
    echo "✓ .env file exists"
    
    # Check for required variables
    if grep -q "LITELLM_MASTER_KEY" .env && ! grep -q "your_litellm_master_key" .env; then
        echo "✓ LITELLM_MASTER_KEY is configured"
    else
        echo "⚠ LITELLM_MASTER_KEY needs to be configured in .env"
    fi
else
    echo "✗ .env file not found"
    echo "  Run: cp .env.example .env"
    echo "  Then edit .env with your configuration"
fi

# Check Docker
echo ""
echo "Checking Docker..."
if command -v docker &> /dev/null; then
    echo "✓ Docker is installed"
    docker --version
else
    echo "✗ Docker is not installed"
fi

if command -v docker-compose &> /dev/null; then
    echo "✓ Docker Compose is installed"
    docker-compose --version
else
    echo "✗ Docker Compose is not installed"
fi

echo ""
echo "=== Setup Verification Complete ==="
echo ""
echo "Next steps:"
echo "1. Configure .env file with your LiteLLM credentials"
echo "2. Run: ./start.sh"
echo "3. Access API at: http://localhost:8001/docs"
