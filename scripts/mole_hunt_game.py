#!/usr/bin/env python3
"""
Mole Hunt Game Script for Minecraft Server
Manages a mole hunt game mode with role assignment, traitor abilities, and win conditions.
"""

import json
import random
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
from pathlib import Path

try:
    from mcrcon import MCRcon
except ImportError:
    print("ERROR: mcrcon not installed. Run: pip install -r requirements.txt")
    exit(1)


class GameStatus(Enum):
    """Game status enumeration"""
    NOT_STARTED = "not_started"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"


class Role(Enum):
    """Player role enumeration"""
    TRAITOR = "traitor"
    INNOCENT = "innocent"


class RCONClient:
    """Handles RCON communication with Minecraft server"""

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.connection = None
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """Connect to RCON server"""
        try:
            self.connection = MCRcon(self.host, self.password, port=self.port)
            self.connection.connect()
            self.logger.info(f"Connected to RCON at {self.host}:{self.port}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to RCON: {e}")
            return False

    def disconnect(self):
        """Disconnect from RCON server"""
        if self.connection:
            try:
                self.connection.disconnect()
            except:
                pass
            self.connection = None

    def execute(self, command: str) -> Optional[str]:
        """Execute a command via RCON"""
        if not self.connection:
            if not self.connect():
                return None

        try:
            response = self.connection.command(command)
            self.logger.debug(f"Command: {command} -> Response: {response}")
            return response
        except Exception as e:
            self.logger.error(f"Error executing command '{command}': {e}")
            return None

    def get_online_players(self) -> List[str]:
        """Get list of online players"""
        response = self.execute("list")
        if not response:
            return []

        # Parse "There are X of a max of Y players online: player1, player2, ..."
        try:
            if ":" in response:
                players_str = response.split(":")[1].strip()
                if players_str:
                    return [p.strip() for p in players_str.split(",")]
        except:
            pass

        return []


class RoleManager:
    """Manages player role assignment"""

    def __init__(self, traitor_ratio: float):
        self.traitor_ratio = traitor_ratio
        self.roles: Dict[str, Role] = {}
        self.logger = logging.getLogger(__name__)

    def assign_roles(self, players: List[str]) -> Dict[str, Role]:
        """Randomly assign roles to players"""
        if not players:
            return {}

        num_traitors = max(1, int(len(players) * self.traitor_ratio))
        num_innocents = len(players) - num_traitors

        # Shuffle players and assign roles
        shuffled = players.copy()
        random.shuffle(shuffled)

        self.roles = {}
        for i, player in enumerate(shuffled):
            if i < num_traitors:
                self.roles[player] = Role.TRAITOR
            else:
                self.roles[player] = Role.INNOCENT

        self.logger.info(
            f"Assigned roles: {num_traitors} traitors, {num_innocents} innocents")
        return self.roles

    def get_role(self, player: str) -> Optional[Role]:
        """Get player's role"""
        return self.roles.get(player)

    def get_traitors(self) -> List[str]:
        """Get list of traitor players"""
        return [p for p, r in self.roles.items() if r == Role.TRAITOR]

    def get_innocents(self) -> List[str]:
        """Get list of innocent players"""
        return [p for p, r in self.roles.items() if r == Role.INNOCENT]

    def reset(self):
        """Reset role assignments"""
        self.roles = {}


class TimerManager:
    """Manages game timer"""

    def __init__(self, duration_minutes: int):
        self.duration_minutes = duration_minutes
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start the timer"""
        self.start_time = datetime.now()
        self.end_time = self.start_time + \
            timedelta(minutes=self.duration_minutes)
        self.logger.info(f"Timer started: {self.duration_minutes} minutes")

    def get_remaining_seconds(self) -> int:
        """Get remaining time in seconds"""
        if not self.end_time:
            return 0
        remaining = (self.end_time - datetime.now()).total_seconds()
        return max(0, int(remaining))

    def get_remaining_minutes(self) -> int:
        """Get remaining time in minutes"""
        return self.get_remaining_seconds() // 60

    def is_expired(self) -> bool:
        """Check if timer has expired"""
        return self.get_remaining_seconds() <= 0

    def reset(self):
        """Reset the timer"""
        self.start_time = None
        self.end_time = None


class NotificationSystem:
    """Handles player notifications"""

    def __init__(self, rcon_client: RCONClient):
        self.rcon = rcon_client
        self.logger = logging.getLogger(__name__)

    def tellraw(self, player: str, message: str, color: str = "white"):
        """Send tellraw message to player"""
        json_msg = json.dumps({"text": message, "color": color})
        self.rcon.execute(f'tellraw {player} {json_msg}')

    def tellraw_all(self, message: str, color: str = "white"):
        """Send tellraw message to all players"""
        json_msg = json.dumps({"text": message, "color": color})
        self.rcon.execute(f'tellraw @a {json_msg}')

    def title(self, player: str, title: str, subtitle: str = "", fade_in: int = 10, stay: int = 70, fade_out: int = 20):
        """Send title to player"""
        self.rcon.execute(f'title {player} times {fade_in} {stay} {fade_out}')
        self.rcon.execute(
            f'title {player} title {json.dumps({"text": title})}')
        if subtitle:
            self.rcon.execute(
                f'title {player} subtitle {json.dumps({"text": subtitle})}')

    def title_all(self, title: str, subtitle: str = "", fade_in: int = 10, stay: int = 70, fade_out: int = 20):
        """Send title to all players"""
        self.rcon.execute(f'title @a times {fade_in} {stay} {fade_out}')
        self.rcon.execute(f'title @a title {json.dumps({"text": title})}')
        if subtitle:
            self.rcon.execute(
                f'title @a subtitle {json.dumps({"text": subtitle})}')

    def announce_role(self, player: str, role: Role):
        """Announce player's role"""
        if role == Role.TRAITOR:
            self.title(player, "§4YOU ARE A TRAITOR",
                       "§7Eliminate all innocents!", 10, 100, 20)
            self.tellraw(
                player, "§4[TRAITOR] §7Your goal is to eliminate all innocent players!", "red")
            self.tellraw(
                player, "§7You have special abilities. Use them wisely!", "gray")
        else:
            self.title(player, "§aYOU ARE INNOCENT",
                       "§7Survive and identify the traitors!", 10, 100, 20)
            self.tellraw(
                player, "§a[INNOCENT] §7Your goal is to survive until time runs out!", "green")
            self.tellraw(
                player, "§7Work together to identify and stop the traitors!", "gray")

    def announce_game_start(self):
        """Announce game start"""
        self.title_all("§6MOLE HUNT", "§7Game Starting!", 10, 100, 20)
        self.tellraw_all("§6=== MOLE HUNT GAME STARTED ===", "gold")
        self.tellraw_all(
            "§7Roles have been assigned. Check your title!", "gray")

    def announce_game_end(self, winners: str, reason: str):
        """Announce game end"""
        self.title_all("§6GAME OVER", f"§7{winners} won!", 10, 100, 20)
        self.tellraw_all(f"§6=== GAME ENDED ===", "gold")
        self.tellraw_all(f"§7Winners: §6{winners}", "yellow")
        self.tellraw_all(f"§7Reason: §6{reason}", "yellow")

    def send_time_update(self, minutes: int, seconds: int):
        """Send time remaining update"""
        self.tellraw_all(
            f"§7Time remaining: §6{minutes}:{seconds:02d}", "gray")


class TraitorAbilities:
    """Manages traitor abilities"""

    def __init__(self, rcon_client: RCONClient, config: dict):
        self.rcon = rcon_client
        self.config = config
        self.logger = logging.getLogger(__name__)

    def grant_abilities(self, player: str):
        """Grant traitor abilities to player"""
        abilities = self.config.get("traitor_abilities", {})

        # Grant invisibility
        if abilities.get("invisibility", False):
            self.rcon.execute(
                f"effect give {player} minecraft:invisibility 999999 1 true")
            self.logger.info(f"Granted invisibility to {player}")

        # Grant night vision
        if abilities.get("night_vision", False):
            self.rcon.execute(
                f"effect give {player} minecraft:night_vision 999999 0 true")
            self.logger.info(f"Granted night vision to {player}")

        # Give special items
        special_items = abilities.get("special_items", [])
        for item in special_items:
            self.rcon.execute(f"give {player} {item} 1")
            self.logger.info(f"Gave {item} to {player}")

    def remove_abilities(self, player: str):
        """Remove traitor abilities from player"""
        self.rcon.execute(f"effect clear {player} minecraft:invisibility")
        self.rcon.execute(f"effect clear {player} minecraft:night_vision")
        self.logger.info(f"Removed abilities from {player}")


class WinConditionChecker:
    """Checks win conditions"""

    def __init__(self, role_manager: RoleManager, timer_manager: TimerManager, rcon_client: RCONClient):
        self.role_manager = role_manager
        self.timer_manager = timer_manager
        self.rcon = rcon_client
        self.logger = logging.getLogger(__name__)

    def check_win_conditions(self) -> Optional[Tuple[str, str]]:
        """Check if any win condition is met. Returns (winner, reason) or None"""
        online_players = self.rcon.get_online_players()

        # Get alive traitors and innocents
        alive_traitors = [
            p for p in self.role_manager.get_traitors() if p in online_players]
        alive_innocents = [
            p for p in self.role_manager.get_innocents() if p in online_players]

        # Traitors win if all innocents are eliminated
        if len(alive_innocents) == 0 and len(alive_traitors) > 0:
            return ("Traitors", "All innocent players eliminated")

        # Innocents win if timer expires and at least one innocent survives
        if self.timer_manager.is_expired() and len(alive_innocents) > 0:
            return ("Innocents", "Time limit reached")

        # If all traitors are eliminated, innocents win
        if len(alive_traitors) == 0 and len(alive_innocents) > 0:
            return ("Innocents", "All traitors eliminated")

        return None


class GameState:
    """Manages overall game state"""

    def __init__(self, config_path: str):
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Initialize components
        rcon_config = self.config.get("rcon", {})
        self.rcon = RCONClient(
            rcon_config.get("host", "localhost"),
            rcon_config.get("port", 25575),
            rcon_config.get("password", "")
        )

        self.role_manager = RoleManager(self.config.get("traitor_ratio", 0.25))
        self.timer_manager = TimerManager(
            self.config.get("game_duration_minutes", 30))
        self.notifications = NotificationSystem(self.rcon)
        self.abilities = TraitorAbilities(self.rcon, self.config)
        self.win_checker = WinConditionChecker(
            self.role_manager, self.timer_manager, self.rcon)

        self.status = GameStatus.NOT_STARTED
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('mole_hunt.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def start_game(self, test_mode: bool = False, test_player: Optional[str] = None, test_role: Optional[Role] = None) -> bool:
        """Start a new game

        Args:
            test_mode: If True, allows starting with 1 player for testing
            test_player: If provided, assign this player the test_role
            test_role: Role to assign to test_player (TRAITOR or INNOCENT)
        """
        if self.status == GameStatus.IN_PROGRESS:
            self.logger.warning("Game already in progress")
            return False

        self.status = GameStatus.STARTING
        self.logger.info("Starting new mole hunt game...")

        # Connect to RCON
        if not self.rcon.connect():
            self.logger.error("Failed to connect to RCON")
            self.status = GameStatus.NOT_STARTED
            return False

        # Get online players
        players = self.rcon.get_online_players()

        # Test mode allows 1 player, normal mode requires 2+
        if not test_mode and len(players) < 2:
            self.logger.error("Need at least 2 players to start")
            self.status = GameStatus.NOT_STARTED
            return False

        if test_mode and len(players) < 1:
            self.logger.error("Need at least 1 player for test mode")
            self.status = GameStatus.NOT_STARTED
            return False

        # Assign roles
        if test_mode and test_player and test_role:
            # Manual role assignment for testing
            self.role_manager.roles = {}
            for player in players:
                if player == test_player:
                    self.role_manager.roles[player] = test_role
                else:
                    # Assign opposite role to other players if any
                    self.role_manager.roles[player] = Role.INNOCENT if test_role == Role.TRAITOR else Role.TRAITOR
            self.logger.info(
                f"Test mode: Assigned {test_player} as {test_role.value}")
        else:
            # Normal random assignment
            self.role_manager.assign_roles(players)

        # Announce game start
        self.notifications.announce_game_start()

        # Notify players of their roles
        for player, role in self.role_manager.roles.items():
            self.notifications.announce_role(player, role)
            if role == Role.TRAITOR:
                self.abilities.grant_abilities(player)

        # Start timer
        self.timer_manager.start()

        # Start monitoring thread (skip in test mode with 1 player)
        if not (test_mode and len(players) == 1):
            self.status = GameStatus.IN_PROGRESS
            self.monitor_running = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_game, daemon=True)
            self.monitor_thread.start()
        else:
            self.status = GameStatus.IN_PROGRESS
            self.logger.info("Test mode: Monitoring disabled (single player)")

        self.logger.info("Game started successfully")
        return True

    def stop_game(self):
        """Stop the current game"""
        if self.status != GameStatus.IN_PROGRESS:
            return

        self.logger.info("Stopping game...")
        self.monitor_running = False

        # Remove all abilities
        for player in self.role_manager.get_traitors():
            self.abilities.remove_abilities(player)

        # Reset state
        self.role_manager.reset()
        self.timer_manager.reset()
        self.status = GameStatus.ENDED

        self.notifications.tellraw_all("§7Game stopped by admin", "gray")
        self.logger.info("Game stopped")

    def _monitor_game(self):
        """Monitor game state and check win conditions"""
        last_time_update = 0

        while self.monitor_running and self.status == GameStatus.IN_PROGRESS:
            try:
                # Check win conditions every 5 seconds
                result = self.win_checker.check_win_conditions()
                if result:
                    winner, reason = result
                    self._end_game(winner, reason)
                    break

                # Send time updates every 30 seconds
                current_time = time.time()
                if current_time - last_time_update >= 30:
                    remaining = self.timer_manager.get_remaining_seconds()
                    minutes = remaining // 60
                    seconds = remaining % 60
                    self.notifications.send_time_update(minutes, seconds)
                    last_time_update = current_time

                time.sleep(5)
            except Exception as e:
                self.logger.error(f"Error in monitor thread: {e}")
                time.sleep(5)

    def _end_game(self, winner: str, reason: str):
        """End the game"""
        self.status = GameStatus.ENDED
        self.monitor_running = False

        # Remove abilities
        for player in self.role_manager.get_traitors():
            self.abilities.remove_abilities(player)

        # Announce winners
        self.notifications.announce_game_end(winner, reason)

        # Reveal roles
        self.notifications.tellraw_all("§6=== ROLE REVEAL ===", "gold")
        traitors = self.role_manager.get_traitors()
        innocents = self.role_manager.get_innocents()

        self.notifications.tellraw_all(
            f"§4Traitors: §7{', '.join(traitors)}", "red")
        self.notifications.tellraw_all(
            f"§aInnocents: §7{', '.join(innocents)}", "green")

        self.logger.info(f"Game ended: {winner} won - {reason}")

        # Reset after a delay
        threading.Timer(30.0, self._reset_game).start()

    def _reset_game(self):
        """Reset game state"""
        self.role_manager.reset()
        self.timer_manager.reset()
        self.status = GameStatus.NOT_STARTED
        self.logger.info("Game reset")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Mole Hunt Game Manager")
    parser.add_argument(
        "--config", default="config/mole_hunt_config.json", help="Path to config file")
    parser.add_argument("--start", action="store_true",
                        help="Start a new game")
    parser.add_argument("--stop", action="store_true",
                        help="Stop current game")
    parser.add_argument("--status", action="store_true",
                        help="Check game status")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: assign specific role to a player")
    parser.add_argument("--test-player", type=str,
                        help="Player username for test mode")
    parser.add_argument("--test-role", type=str, choices=["traitor", "innocent"],
                        help="Role to assign in test mode (traitor or innocent)")

    args = parser.parse_args()

    # Resolve config path relative to script directory
    script_dir = Path(__file__).parent.parent
    config_path = script_dir / args.config

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return

    game = GameState(str(config_path))

    if args.start:
        test_mode = args.test
        test_player = args.test_player
        test_role = None
        if args.test_role:
            test_role = Role.TRAITOR if args.test_role == "traitor" else Role.INNOCENT

        if test_mode and not test_player:
            print("ERROR: --test-player required when using --test mode")
            return

        if test_mode and not test_role:
            print("ERROR: --test-role required when using --test mode")
            print("Use: --test-role traitor or --test-role innocent")
            return

        if game.start_game(test_mode=test_mode, test_player=test_player, test_role=test_role):
            mode_str = f" (TEST MODE: {test_player} as {test_role.value})" if test_mode else ""
            print(f"Game started successfully!{mode_str}")
            # Keep script running to maintain monitoring
            try:
                while game.status == GameStatus.IN_PROGRESS:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping game...")
                game.stop_game()
        else:
            print("Failed to start game")
    elif args.stop:
        game.stop_game()
        print("Game stopped")
    elif args.status:
        print(f"Game status: {game.status.value}")
        if game.status == GameStatus.IN_PROGRESS:
            remaining = game.timer_manager.get_remaining_minutes()
            print(f"Time remaining: {remaining} minutes")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
