#!/bin/bash
# Test script to find the correct SkinChanger command format

echo "Testing SkinChanger commands..."
echo "Make sure you're logged into the server as the test player"
echo ""

read -p "Enter your Minecraft username: " USERNAME

if [ -z "$USERNAME" ]; then
    echo "ERROR: Username required"
    exit 1
fi

echo ""
echo "Testing skin restoration commands..."
echo ""

# Test different command formats
commands=(
    "skin player $USERNAME clear"
    "skin player $USERNAME reset"
    "skin $USERNAME clear"
    "skin clear $USERNAME"
    "skin reset $USERNAME"
)

for cmd in "${commands[@]}"; do
    echo "Testing: $cmd"
    python3 -c "
from mcrcon import MCRcon
import json

with open('config/mole_hunt_config.json', 'r') as f:
    config = json.load(f)

rcon_config = config.get('rcon', {})
rcon = MCRcon(rcon_config.get('host', 'localhost'), rcon_config.get('password', ''), port=rcon_config.get('port', 25575))
rcon.connect()
response = rcon.command('$cmd')
rcon.disconnect()
print(f'Response: {response}')
"
    echo ""
done

echo "Check which command worked and update the script accordingly!"

