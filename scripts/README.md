# Game Engine Architecture

This directory contains a refactored game engine architecture that separates reusable game round functionality from game-specific implementations.

## Directory Structure

```
scripts/
├── game_engine/          # Core reusable game engine components
│   ├── __init__.py
│   ├── game_status.py   # GameStatus enum
│   ├── rcon_client.py   # RCON communication with Minecraft server
│   ├── timer_manager.py # Game timer management
│   └── notification_system.py  # Base notification system
│
├── games/               # Game implementations
│   └── mole_hunt/       # Mole Hunt game implementation
│       ├── __init__.py
│       ├── role.py      # Role enum (TRAITOR, INNOCENT)
│       ├── role_manager.py
│       ├── traitor_abilities.py
│       ├── skin_manager.py
│       ├── win_condition_checker.py
│       ├── notification_system.py  # Extends base NotificationSystem
│       ├── game_state.py  # MoleHuntGameState - main game class
│       └── main.py       # Entry point for Mole Hunt game
│
└── mole_hunt_game.py     # Original file (kept for reference)
```

## Core Engine Components

The `game_engine/` folder contains reusable components that can be used by any game:

- **GameStatus**: Enum for game states (NOT_STARTED, STARTING, IN_PROGRESS, ENDED)
- **RCONClient**: Handles all RCON communication with the Minecraft server
- **TimerManager**: Manages game duration and time tracking
- **NotificationSystem**: Base class for sending messages, titles, and actionbars to players

## Creating a New Game

To create a new game using the same game round functionality:

1. **Create a new game folder** under `games/`:
   ```bash
   mkdir -p games/my_new_game
   ```

2. **Create game-specific components**:
   - Define your game's roles, rules, and mechanics
   - Create a game state class that uses the core engine components
   - Implement win condition checking
   - Create a notification system that extends `NotificationSystem` if needed

3. **Example structure**:
   ```
   games/my_new_game/
   ├── __init__.py
   ├── game_state.py      # YourGameState class
   ├── win_condition_checker.py
   ├── notification_system.py  # Optional: extends base NotificationSystem
   └── main.py            # Entry point
   ```

4. **Use core engine components**:
   ```python
   from game_engine.game_status import GameStatus
   from game_engine.rcon_client import RCONClient
   from game_engine.timer_manager import TimerManager
   from game_engine.notification_system import NotificationSystem
   
   class MyGameState:
       def __init__(self, config_path: str):
           # Load config
           # Initialize core components
           self.rcon = RCONClient(...)
           self.timer_manager = TimerManager(...)
           self.notifications = NotificationSystem(self.rcon)
           self.status = GameStatus.NOT_STARTED
   ```

## Running Mole Hunt Game

The Mole Hunt game can be run using:

```bash
python3 -m games.mole_hunt.main --start --config config/mole_hunt_config.json
```

Or use the original entry point (which now imports from the new structure):

```bash
python3 scripts/mole_hunt_game.py --start
```

## Benefits of This Architecture

1. **Reusability**: Core game round functionality (timers, RCON, notifications) can be reused across different games
2. **Modularity**: Each game is self-contained in its own folder
3. **Maintainability**: Changes to core engine don't affect game-specific code
4. **Extensibility**: Easy to add new games without modifying existing code

