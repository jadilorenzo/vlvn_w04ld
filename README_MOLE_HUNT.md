# Mole Hunt Game Script

A Python script that manages a mole hunt game mode for your Minecraft server, similar to Among Us or Trouble in Terrorist Town.

## Features

- **Random Role Assignment**: Players are randomly assigned as either Traitors or Innocents
- **Traitor Abilities**: Traitors receive special abilities (invisibility, night vision, special items)
- **Game Timer**: Configurable time limit for each game
- **Win Conditions**: 
  - Traitors win by eliminating all innocent players
  - Innocents win by surviving until time runs out or eliminating all traitors
- **Player Notifications**: Role announcements, time updates, and game status messages
- **Automatic Monitoring**: Script monitors game state and checks win conditions automatically

## Installation

### Quick Setup (Recommended)

Run the setup script:
```bash
./setup_mole_hunt.sh
```

This will:
- Check Python 3 installation
- Install required dependencies (mcrcon)
- Verify the installation

### Manual Setup

1. **Check Python 3**:
   ```bash
   python3 --version
   ```
   Requires Python 3.7 or higher.

2. **Install Python Dependencies**:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
   
   Or install directly:
   ```bash
   python3 -m pip install mcrcon
   ```

3. **Verify Installation**:
   ```bash
   python3 -c "import mcrcon; print('Setup complete!')"
   ```

4. **Enable RCON** (already configured):
   - RCON is enabled in `server.properties`
   - Password is set in the config file

5. **Restart Server** (required for RCON to take effect):
   ```bash
   # Stop your server, then restart it
   # RCON will be enabled on port 25575
   ```

## Configuration

Edit `config/mole_hunt_config.json` to customize:

- `traitor_ratio`: Ratio of traitors (0.25 = 25% of players)
- `game_duration_minutes`: How long games last (default: 30 minutes)
- `traitor_abilities`: What abilities traitors get
  - `invisibility`: Give traitors invisibility effect
  - `night_vision`: Give traitors night vision
  - `special_items`: List of items to give traitors
- `rcon`: RCON connection settings (host, port, password)

## Usage

### Start a Game

```bash
python3 scripts/mole_hunt_game.py --start
```

This will:
1. Connect to your server via RCON
2. Get all online players
3. Randomly assign roles
4. Notify players of their roles
5. Grant traitor abilities
6. Start the game timer
7. Begin monitoring for win conditions

**Note**: Keep the script running while the game is active. Press Ctrl+C to stop.

### Stop a Game

```bash
python3 scripts/mole_hunt_game.py --stop
```

### Check Game Status

```bash
python3 scripts/mole_hunt_game.py --status
```

## How It Works

1. **Game Start**:
   - Script connects to server via RCON
   - Collects all online players
   - Randomly assigns roles based on traitor ratio
   - Sends title and chat messages to players revealing their roles
   - Grants traitor abilities (effects and items)
   - Starts the game timer

2. **During Game**:
   - Script monitors player count every 5 seconds
   - Checks win conditions periodically
   - Sends time remaining updates every 30 seconds
   - Traitors can eliminate innocents through PvP

3. **Game End**:
   - When win condition is met, script announces winners
   - Reveals all player roles
   - Removes traitor abilities
   - Resets game state after 30 seconds

## Win Conditions

- **Traitors Win**: All innocent players are eliminated
- **Innocents Win**: 
  - Time limit is reached with at least one innocent alive, OR
  - All traitors are eliminated

## Troubleshooting

### RCON Connection Failed
- Make sure your server is running
- Verify RCON is enabled in `server.properties`
- Check that the password in config matches `server.properties`
- Restart server after enabling RCON

### Not Enough Players
- Need at least 2 players online to start a game

### Script Stops Unexpectedly
- Check `mole_hunt.log` for error messages
- Make sure server is still running
- Verify RCON connection is stable

## Logs

The script creates a log file `mole_hunt.log` in the server directory with detailed information about game events, errors, and debugging information.

## Example Game Flow

1. Admin runs: `python3 scripts/mole_hunt_game.py --start`
2. Players see title: "YOU ARE A TRAITOR" or "YOU ARE INNOCENT"
3. Traitors receive invisibility, night vision, and special items
4. Game runs for 30 minutes (or until win condition)
5. Every 30 seconds, players see time remaining
6. When game ends, roles are revealed and winners announced

## Customization

You can customize the game by editing `config/mole_hunt_config.json`:

- Change traitor ratio for different difficulty
- Adjust game duration
- Modify traitor abilities
- Add/remove special items

## Notes

- The script must remain running while a game is active
- Players can join/leave during the game (roles are only assigned at start)
- Server must have RCON enabled and accessible
- PvP should be enabled for elimination mechanics to work

