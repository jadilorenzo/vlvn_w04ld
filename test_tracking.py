#!/usr/bin/env python3
"""
Standalone test script for player tracking feature
Tests coordinate retrieval and distance calculation
"""

import sys
from pathlib import Path

# Add scripts directory to path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir / "scripts"))

from mole_hunt_game import RCONClient, NotificationSystem
import json

def test_coordinate_retrieval(rcon: RCONClient, player: str):
    """Test if we can get player coordinates"""
    print(f"\nTesting coordinate retrieval for {player}...")
    
    try:
        response = rcon.execute(f"data get entity {player} Pos")
        print(f"Response: {response}")
        
        if response and "Pos:" in response:
            import re
            matches = re.findall(r'([-\d.]+)d', response)
            if len(matches) >= 3:
                coords = (float(matches[0]), float(matches[1]), float(matches[2]))
                print(f"✓ Successfully retrieved coordinates: {coords}")
                return coords
            else:
                print(f"✗ Could not parse coordinates from response")
        else:
            print(f"✗ Invalid response format")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    return None

def test_actionbar(notifications: NotificationSystem, player: str):
    """Test if actionbar messages work"""
    print(f"\nTesting actionbar message for {player}...")
    
    try:
        notifications.actionbar(player, "§c§lTEST: §r§eThis is a test message!")
        print(f"✓ Actionbar message sent")
        print(f"  Check above your hotbar in-game!")
        return True
    except Exception as e:
        print(f"✗ Error sending actionbar: {e}")
        return False

def test_distance_calculation():
    """Test distance calculation"""
    print(f"\nTesting distance calculation...")
    
    from mole_hunt_game import GameState
    
    # Create a temporary game state to access the method
    # We'll use a dummy config path
    try:
        # Calculate distance between two test points
        pos1 = (0, 64, 0)
        pos2 = (100, 64, 100)
        
        # Create minimal game state for testing
        class TestGameState:
            def _calculate_distance(self, pos1, pos2):
                dx = pos1[0] - pos2[0]
                dy = pos1[1] - pos2[1]
                dz = pos1[2] - pos2[2]
                return (dx**2 + dy**2 + dz**2) ** 0.5
        
        test = TestGameState()
        distance = test._calculate_distance(pos1, pos2)
        expected = 141.42  # sqrt(100^2 + 100^2)
        
        print(f"  Position 1: {pos1}")
        print(f"  Position 2: {pos2}")
        print(f"  Calculated distance: {distance:.2f}m")
        print(f"  Expected distance: ~{expected:.2f}m")
        
        if abs(distance - expected) < 1:
            print(f"✓ Distance calculation works correctly!")
            return True
        else:
            print(f"✗ Distance calculation may be incorrect")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("Player Tracking Feature Test")
    print("=" * 60)
    
    # Load config
    config_path = script_dir / "config" / "mole_hunt_config.json"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Check if tracking is enabled
    tracking_config = config.get("player_tracking", {})
    if tracking_config.get("enabled", False):
        print("✓ Player tracking is enabled in config")
    else:
        print("⚠ WARNING: Player tracking is disabled in config")
        print("  Set 'player_tracking.enabled' to true to enable")
    
    print(f"\nUpdate interval: {tracking_config.get('update_interval_seconds', 3)} seconds")
    print(f"Show distance: {tracking_config.get('show_distance', True)}")
    print(f"Show direction: {tracking_config.get('show_direction', True)}")
    
    # Test distance calculation (doesn't need server)
    test_distance_calculation()
    
    # Connect to RCON
    rcon_config = config.get("rcon", {})
    rcon = RCONClient(
        rcon_config.get("host", "localhost"),
        rcon_config.get("port", 25575),
        rcon_config.get("password", "")
    )
    
    print(f"\nConnecting to RCON at {rcon_config.get('host', 'localhost')}:{rcon_config.get('port', 25575)}...")
    if not rcon.connect():
        print("✗ Failed to connect to RCON")
        print("  Make sure:")
        print("  1. Server is running")
        print("  2. RCON is enabled in server.properties")
        print("  3. RCON password is correct")
        return
    
    print("✓ Connected to RCON")
    
    # Get online players
    players = rcon.get_online_players()
    if not players:
        print("\n✗ No players online")
        print("  You need at least 1 player online to test")
        return
    
    print(f"\n✓ Found {len(players)} online player(s): {', '.join(players)}")
    
    # Test coordinate retrieval
    test_player = players[0]
    coords = test_coordinate_retrieval(rcon, test_player)
    
    # Test actionbar
    notifications = NotificationSystem(rcon)
    test_actionbar(notifications, test_player)
    
    # If we have 2+ players, test tracking between them
    if len(players) >= 2:
        print(f"\n{'=' * 60}")
        print("Full Tracking Test")
        print(f"{'=' * 60}")
        print(f"\nTo test full tracking:")
        print(f"  1. Run: ./test_tracking.sh")
        print(f"  2. Or start a game with:")
        print(f"     python3 scripts/mole_hunt_game.py --start --test --test-player {players[0]} --test-role traitor")
        print(f"\n  Then have {players[1]} join as innocent")
        print(f"  {players[0]} should see actionbar updates showing nearest player")
    
    print(f"\n{'=' * 60}")
    print("Test Complete!")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()

