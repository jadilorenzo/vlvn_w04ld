# Mole Hunt Game - Quick Start Guide

## Prerequisites

- Python 3.7 or higher installed
- Minecraft server running with RCON enabled
- At least 2 players online to start a game

## Setup (One-Time)

1. **Run the setup script**:

   ```bash
   ./setup_mole_hunt.sh
   ```

   This installs all required dependencies.

2. **Restart your Minecraft server** (if you just enabled RCON)

## Starting a Game

1. **Make sure your server is running** and has players online

2. **Start the game script**:

   ```bash
   python3 scripts/mole_hunt_game.py --start
   ```

3. **Keep the script running** - it will monitor the game and check win conditions

4. **Press Ctrl+C** to stop the game manually (or wait for win condition)

## Commands

- **Start game**: `python3 scripts/mole_hunt_game.py --start`
- **Stop game**: `python3 scripts/mole_hunt_game.py --stop`
- **Check status**: `python3 scripts/mole_hunt_game.py --status`

## Testing Roles

To test what each role receives (useful for testing with just yourself):

### Easy Method (Interactive Script):

```bash
./test_roles.sh
```

### Manual Method:

**Test as Traitor:**

```bash
python3 scripts/mole_hunt_game.py --start --test --test-player YourUsername --test-role traitor
```

**Test as Innocent:**

```bash
python3 scripts/mole_hunt_game.py --start --test --test-player YourUsername --test-role innocent
```

**What Traitors Receive:**

- Invisibility effect (level 2)
- Night vision effect
- Compass (points to spawn for navigation)
- Special items (configured in config file)
- Red title: "YOU ARE A TRAITOR"
- Red chat messages with traitor instructions

**Note**: Compass is automatically removed when the game ends.

**What Innocents Receive:**

- Green title: "YOU ARE INNOCENT"
- Green chat messages with innocent instructions
- No special abilities or items

## Troubleshooting

### "ModuleNotFoundError: No module named 'mcrcon'"

Run: `python3 -m pip install mcrcon`

### "Failed to connect to RCON"

- Make sure server is running
- Verify RCON is enabled in `server.properties`
- Check password matches in config file
- Restart server after enabling RCON

### "Need at least 2 players to start"

Make sure you have at least 2 players online before starting

## Testing Player Tracking

To test the player tracking feature:

### Quick Test (Standalone)
```bash
python3 test_tracking.py
```
This will:
- Check if tracking is enabled
- Test coordinate retrieval
- Test actionbar messages
- Verify distance calculations

### Full Game Test
```bash
./test_tracking.sh
```
Or manually:
```bash
python3 scripts/mole_hunt_game.py --start --test --test-player YourName --test-role traitor
```

**What to look for:**
- Actionbar above hotbar showing: `Nearest: PlayerName (XXXm) [Direction]`
- Updates every 3 seconds (configurable)
- Only traitors see the tracking info
- Distance and direction update as players move

## Configuration

Edit `config/mole_hunt_config.json` to customize:

- Traitor ratio (default: 20%)
- Game duration (default: 30 minutes)
- Traitor abilities
- Player tracking settings:
  - `player_tracking.enabled` - Enable/disable tracking
  - `player_tracking.update_interval_seconds` - How often to update (default: 3)
  - `player_tracking.show_distance` - Show distance in meters
  - `player_tracking.show_direction` - Show cardinal direction
- RCON settings
