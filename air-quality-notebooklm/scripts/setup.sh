#!/bin/bash
# Quick setup script for Air Quality NotebookLM

set -e

echo "==================================="
echo "Air Quality NotebookLM Setup"
echo "==================================="
echo ""

# Check for required commands
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required but not installed. Aborting." >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js is required but not installed. Aborting." >&2; exit 1; }

echo "✓ Python 3 found: $(python3 --version)"
echo "✓ Node.js found: $(node --version)"
echo ""

# Create .env file if it doesn't exist
if [ ! -f backend/.env ]; then
    echo "Creating backend/.env file..."
    cp backend/.env.example backend/.env
    echo "⚠ Please edit backend/.env with your API keys"
else
    echo "✓ backend/.env already exists"
fi

if [ ! -f frontend/.env.local ]; then
    echo "Creating frontend/.env.local file..."
    cp frontend/.env.example frontend/.env.local
else
    echo "✓ frontend/.env.local already exists"
fi

echo ""
echo "==================================="
echo "Backend Setup"
echo "==================================="

cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✓ Backend setup complete"

cd ..

echo ""
echo "==================================="
echo "Frontend Setup"
echo "==================================="

cd frontend

# Install dependencies
echo "Installing Node.js dependencies..."
npm install

echo "✓ Frontend setup complete"

cd ..

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Edit backend/.env with your API keys"
echo "2. Start the backend:"
echo "   cd backend && source venv/bin/activate && python main.py"
echo "3. In a new terminal, start the frontend:"
echo "   cd frontend && npm run dev"
echo "4. Open http://localhost:3000 in your browser"
echo ""
echo "Or use Docker:"
echo "   docker-compose up -d"
echo ""
