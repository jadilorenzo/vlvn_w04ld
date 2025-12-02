#!/bin/bash
# Test script to test traitor vs innocent roles

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Mole Hunt Role Testing"
echo "======================"
echo ""
echo "This script will help you test what each role receives."
echo ""

# Get player username
read -p "Enter your Minecraft username: " USERNAME

if [ -z "$USERNAME" ]; then
    echo "ERROR: Username required"
    exit 1
fi

echo ""
echo "Choose a role to test:"
echo "1) Traitor (Mole)"
echo "2) Innocent"
echo ""
read -p "Enter choice (1 or 2): " CHOICE

case $CHOICE in
    1)
        ROLE="traitor"
        echo ""
        echo "Starting test as TRAITOR..."
        echo "You will receive:"
        echo "  - Invisibility effect"
        echo "  - Night vision effect"
        echo "  - Special items (iron sword, bow)"
        echo "  - Red title: 'YOU ARE A TRAITOR'"
        echo ""
        python3 scripts/mole_hunt_game.py --start --test --test-player "$USERNAME" --test-role traitor
        ;;
    2)
        ROLE="innocent"
        echo ""
        echo "Starting test as INNOCENT..."
        echo "You will receive:"
        echo "  - Green title: 'YOU ARE INNOCENT'"
        echo "  - No special abilities"
        echo ""
        python3 scripts/mole_hunt_game.py --start --test --test-player "$USERNAME" --test-role innocent
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "Test started! Check your Minecraft client to see what you received."
echo ""
echo "To stop the test, press Ctrl+C or run:"
echo "  python3 scripts/mole_hunt_game.py --stop"

