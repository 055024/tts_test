#!/bin/bash

# TTS Remote Controller Startup Script

echo "🎤 Starting TTS Remote Controller Server"
echo "========================================"

# Check if we're in the right directory
if [ ! -f "remote_api.py" ]; then
    echo "❌ Error: remote_api.py not found. Please run this script from the project directory."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Error: Virtual environment not found. Please create it first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt fastapi uvicorn python-multipart"
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Check if required packages are installed
echo "🔍 Checking dependencies..."
python -c "import fastapi, uvicorn, app" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Error: Missing dependencies. Installing..."
    pip install fastapi uvicorn python-multipart
fi

# Set environment variables (optional)
export API_TOKEN=""  # Set this if you want authentication
export CORS_ORIGINS="*"  # Allow all origins

echo "🚀 Starting server on http://0.0.0.0:8000"
echo "📱 Open index.html in your browser to access the web interface"
echo "🛑 Press Ctrl+C to stop the server"
echo ""

# Start the server
python remote_api.py