#!/bin/bash
# Activation script for Tennis Markov Chain virtual environment

echo "Tennis Game Markov Chain - Virtual Environment Setup"
echo "=================================================="

# Check if virtual environment exists
if [ ! -d "tennis_env" ]; then
    echo "Creating virtual environment..."
    python -m venv tennis_env
fi

# Activate virtual environment
echo "Activating virtual environment..."
source tennis_env/bin/activate

# Install dependencies if not already installed
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Virtual environment activated!"
echo "You can now run:"
echo "  python example_usage.py    # Run examples"
echo "  python test_tennis_markov_chain.py  # Run tests"
echo ""
echo "To deactivate the virtual environment, run: deactivate"
