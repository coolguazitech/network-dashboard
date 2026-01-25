#!/bin/bash
# Start Mock API Server for testing

cd "$(dirname "$0")/.."

echo "Starting Mock API Server on port 8001..."
echo "Press Ctrl+C to stop"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start server
uvicorn tests.mock_api_server:app --port 8001 --reload
