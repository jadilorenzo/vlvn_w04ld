#!/bin/bash
# Test script for player tracking feature

echo "=== Player Tracking Test ==="
echo ""
echo "This script will help you test the player tracking feature."
echo "Make sure you have at least 2 players online on your server."
echo ""

# Check if config file exists
CONFIG_FILE="config/mole_hunt_config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file not found: $CONFIG_FILE"
    exit 1
fi

# Check if player tracking is enabled
if grep -q '"enabled": true' "$CONFIG_FILE" | grep -A 5 "player_tracking"; then
    echo "✓ Player tracking is enabled in config"
else
    echo "⚠ WARNING: Player tracking may not be enabled in config"
    echo "  Check that 'player_tracking.enabled' is set to true"
fi

echo ""
read -p "Enter your username (traitor): " TRAITOR_USER
if [ -z "$TRAITOR_USER" ]; then
    echo "ERROR: Username required"
    exit 1
fi

echo ""
read -p "Enter another player's username (innocent): " INNOCENT_USER
if [ -z "$INNOCENT_USER" ]; then
    echo "ERROR: Innocent username required"
    exit 1
fi

echo ""
echo "Starting game in test mode..."
echo "  - $TRAITOR_USER will be assigned as TRAITOR"
echo "  - $INNOCENT_USER will be assigned as INNOCENT"
echo ""
echo "The actionbar should show:"
echo "  'Nearest: $INNOCENT_USER (XXXm) [Direction]'"
echo ""
echo "Press Ctrl+C to stop the game when done testing."
echo ""

# Start the game in test mode
python3 scripts/mole_hunt_game.py \
    --start \
    --test \
    --test-player "$TRAITOR_USER" \
    --test-role traitor

