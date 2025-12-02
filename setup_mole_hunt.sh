#!/bin/bash
# Setup script for Mole Hunt Game Script

echo "Setting up Mole Hunt Game Script..."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed!"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "Found: $PYTHON_VERSION"
echo ""

# Install dependencies
echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed successfully!"
else
    echo "ERROR: Failed to install dependencies"
    exit 1
fi

echo ""
echo "Verifying installation..."
python3 -c "import mcrcon; print('✓ mcrcon module is available')" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Setup complete! You can now use the mole hunt script."
    echo ""
    echo "Usage:"
    echo "  python3 scripts/mole_hunt_game.py --start    # Start a game"
    echo "  python3 scripts/mole_hunt_game.py --stop     # Stop current game"
    echo "  python3 scripts/mole_hunt_game.py --status   # Check game status"
else
    echo ""
    echo "ERROR: Verification failed. Please check the error messages above."
    exit 1
fi

