#!/usr/bin/env python3
"""
Simple test script to verify actionbar messages work
Tests the actionbar display without needing a full game
"""

import sys
from pathlib import Path

# Add scripts directory to path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir / "scripts"))

from mole_hunt_game import RCONClient, NotificationSystem
import json
import time

def main():
    print("=" * 60)
    print("Actionbar Display Test")
    print("=" * 60)
    print("\nThis will send test messages to your actionbar (above hotbar)")
    print("to verify the display works correctly.\n")
    
    # Load config
    config_path = script_dir / "config" / "mole_hunt_config.json"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Connect to RCON
    rcon_config = config.get("rcon", {})
    rcon = RCONClient(
        rcon_config.get("host", "localhost"),
        rcon_config.get("port", 25575),
        rcon_config.get("password", "")
    )
    
    print(f"Connecting to RCON...")
    if not rcon.connect():
        print("✗ Failed to connect to RCON")
        return
    
    print("✓ Connected\n")
    
    # Get player
    players = rcon.get_online_players()
    if not players:
        print("✗ No players online")
        return
    
    test_player = players[0]
    print(f"Testing with player: {test_player}\n")
    
    notifications = NotificationSystem(rcon)
    
    # Test messages
    test_messages = [
        ("§c§lTEST: §r§eThis is a test message!", "Basic test"),
        ("§c§lNearest: §r§eTestPlayer §7(123m) §6→ E", "Tracking format"),
        ("§c§lNearest: §r§ePlayerName §7(456m) §6↑ N", "With direction"),
        ("§c§lNearest: §r§eTarget §7(789m)", "Distance only"),
    ]
    
    print("Sending test messages to actionbar...")
    print("Look above your hotbar in-game!\n")
    
    for i, (message, description) in enumerate(test_messages, 1):
        print(f"  {i}. {description}")
        notifications.actionbar(test_player, message)
        time.sleep(2)
    
    print("\n✓ Test complete!")
    print("\nIf you saw the messages above your hotbar, actionbar is working!")
    print("If not, check:")
    print("  - You're logged into the server")
    print("  - RCON is enabled and working")
    print("  - Server version supports actionbar (1.8+)")

if __name__ == "__main__":
    main()

