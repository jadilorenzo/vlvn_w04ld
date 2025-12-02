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
- Iron sword and bow
- Red title: "YOU ARE A TRAITOR"
- Red chat messages with traitor instructions

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

## Configuration

Edit `config/mole_hunt_config.json` to customize:

- Traitor ratio (default: 25%)
- Game duration (default: 30 minutes)
- Traitor abilities
- RCON settings
