#!/usr/bin/env python3
"""
Mole Hunt Game Script for Minecraft Server
Manages a mole hunt game mode with role assignment, traitor abilities, and win conditions.
"""

import json
import math
import os
import random
import re
import time
import threading
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
from pathlib import Path

try:
    from mcrcon import MCRcon, MCRconException
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

        # Queue for RCON commands from threads (since mcrcon uses signals that don't work in threads)
        self.command_queue = None
        self.response_queue = None
        self.worker_thread = None
        self.worker_running = False
        self._init_worker()

    def _init_worker(self):
        """Initialize worker thread for executing RCON commands from threads"""
        import queue

        # Only create worker if we're in the main thread
        if threading.current_thread() is threading.main_thread():
            self.command_queue = queue.Queue()
            self.response_queue = queue.Queue()
            self.worker_running = True

            def worker():
                """Worker thread that executes RCON commands (runs in main interpreter)"""
                worker_connection = None
                while self.worker_running:
                    try:
                        # Get command from queue (with timeout to allow checking worker_running)
                        try:
                            command, future = self.command_queue.get(
                                timeout=0.1)
                        except queue.Empty:
                            continue

                        # Execute command using main-thread connection
                        try:
                            if not worker_connection:
                                worker_connection = MCRcon(
                                    self.host, self.password, port=self.port)
                                worker_connection.connect()

                            response = worker_connection.command(command)
                            future.set_result(response)
                        except Exception:
                            # Connection might be broken, try to reconnect
                            try:
                                if worker_connection:
                                    worker_connection.disconnect()
                            except Exception:
                                pass
                            worker_connection = None

                            # Retry once with fresh connection
                            try:
                                worker_connection = MCRcon(
                                    self.host, self.password, port=self.port)
                                worker_connection.connect()
                                response = worker_connection.command(command)
                                future.set_result(response)
                            except Exception as retry_e:
                                future.set_exception(retry_e)
                    except Exception as e:
                        self.logger.error(f"Error in RCON worker thread: {e}")

            self.worker_thread = threading.Thread(target=worker, daemon=True)
            self.worker_thread.start()

    def connect(self) -> bool:
        """Connect to RCON server"""
        is_main_thread = threading.current_thread() is threading.main_thread()

        # Try to connect - even in threads, we'll attempt it
        # If it fails due to signals, we'll handle it gracefully
        try:
            # Disconnect old connection if it exists
            if self.connection:
                try:
                    self.connection.disconnect()
                except:
                    pass
                self.connection = None

            # Create new connection
            self.connection = MCRcon(self.host, self.password, port=self.port)
            self.connection.connect()
            if is_main_thread:
                self.logger.info(
                    f"Connected to RCON at {self.host}:{self.port}")
            else:
                self.logger.info(
                    f"Connected to RCON in thread at {self.host}:{self.port}")
            return True
        except Exception as e:
            if is_main_thread:
                self.logger.error(f"Failed to connect to RCON: {e}")
            else:
                self.logger.debug(f"Failed to connect to RCON in thread: {e}")
            self.connection = None
            return False

    def disconnect(self):
        """Disconnect from RCON server"""
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass
            self.connection = None

    def execute(self, command: str, retry: bool = True) -> Optional[str]:
        """Execute a command via RCON with automatic reconnection on failure"""
        is_main_thread = threading.current_thread() is threading.main_thread()

        # If we're in a thread, use subprocess to run RCON in a separate process
        # (mcrcon uses signals which don't work in threads)
        if not is_main_thread:
            try:
                # Run RCON command in a subprocess (separate Python process = can use signals)
                script = f"""
import sys
from mcrcon import MCRcon
rcon = MCRcon('{self.host}', '{self.password}', port={self.port})
rcon.connect()
response = rcon.command({repr(command)})
rcon.disconnect()
print(response, end='')
"""
                result = subprocess.run(
                    [sys.executable, '-c', script],
                    capture_output=True,
                    text=True,
                    timeout=5.0
                )
                if result.returncode == 0:
                    response = result.stdout
                    self.logger.debug(
                        f"Command (via subprocess): {command} -> Response: {repr(response)}")
                    return response
                else:
                    self.logger.error(
                        f"Subprocess RCON failed: {result.stderr}")
                    return None
            except subprocess.TimeoutExpired:
                self.logger.error(f"RCON command '{command}' timed out")
                return None
            except Exception as e:
                self.logger.error(
                    f"Error executing command '{command}' via subprocess: {e}")
                return None

        # Main thread execution (direct connection)
        max_retries = 2 if retry else 1

        for attempt in range(max_retries):
            # Ensure we have a connection
            if not self.connection:
                if not self.connect():
                    if attempt < max_retries - 1:
                        time.sleep(0.5)  # Brief delay before retry
                        continue
                    return None

            try:
                response = self.connection.command(command)
                self.logger.debug(
                    f"Command: {command} -> Response: {response}")
                return response
            except Exception as e:
                self.logger.error(
                    f"Error executing command '{command}' (attempt {attempt + 1}/{max_retries}): {e}")

                # Mark connection as broken
                try:
                    if self.connection:
                        try:
                            self.connection.disconnect()
                        except Exception:
                            pass
                    self.connection = None
                except Exception:
                    pass

                # Retry if we have attempts left
                if attempt < max_retries - 1 and retry:
                    self.logger.debug(
                        f"Retrying RCON command after connection failure...")
                    time.sleep(0.5)  # Brief delay before retry
                    continue

                return None

        return None

    def get_online_players(self) -> List[str]:
        """Get list of online players"""
        response = self.execute("list")

        if not response:
            self.logger.warning("'list' command returned no response")
            return []

        # Parse "There are X of a max of Y players online: player1, player2, ..."
        try:
            if ":" in response:
                players_str = response.split(":")[1].strip()
                if players_str:
                    # Split by comma and clean up each player name
                    # Remove newlines, extra whitespace, and any trailing text
                    players = []
                    for p in players_str.split(","):
                        # Strip whitespace and newlines
                        player_name = p.strip().replace("\n", " ").strip()
                        # Remove any trailing text that looks like part of the server message
                        # (e.g., "There are X of a max of Y players online")
                        if "There are" in player_name:
                            player_name = player_name.split("There are")[
                                0].strip()
                        if player_name:
                            players.append(player_name)

                    return players
            else:
                self.logger.warning(
                    f"Unexpected 'list' response format: {response}")
        except Exception as e:
            self.logger.error(
                f"Error parsing 'list' response: {e}, response: {repr(response)}")

        self.logger.warning(
            f"Failed to parse online players from response: {repr(response)}")
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
        # Show prominent title screen (longer display time)
        if winners.lower() == "traitors":
            title_color = "§4"
            subtitle_color = "§c"
        else:
            title_color = "§a"
            subtitle_color = "§2"

        self.title_all(
            f"{title_color}GAME OVER",
            f"{subtitle_color}{winners.upper()} WON!",
            10, 140, 20
        )
        self.tellraw_all("§6=== MOLE HUNT GAME ENDED ===", "gold")
        self.tellraw_all(f"§7Winners: §6{winners}", "yellow")
        self.tellraw_all(f"§7Reason: §6{reason}", "yellow")

    def send_time_update(self, minutes: int, seconds: int, player: Optional[str] = None):
        """Send time remaining update via actionbar to specified player or all players"""
        message = f"§7Time remaining: §6{minutes}:{seconds:02d}"
        if player:
            self.actionbar(player, message)
        else:
            # Get all online players and send actionbar to each
            online_players = self.rcon.get_online_players()
            for p in online_players:
                self.actionbar(p, message)

    def actionbar(self, player: str, message: str):
        """Send actionbar message to player (displays above hotbar)"""
        try:
            json_msg = json.dumps({"text": message})
            # Use raw JSON without quotes - Minecraft parses it directly
            cmd = f'title {player} actionbar {json_msg}'
            response = self.rcon.execute(cmd)
            self.logger.debug(
                f"Actionbar sent to {player}: {message[:50]}... (response: {response})")
        except Exception as e:
            self.logger.error(f"Failed to send actionbar to {player}: {e}")
            raise

    def send_player_location(self, traitor: str, target_player: str, distance: float, direction: str = ""):
        """Send nearest player location info to traitor via actionbar"""
        # Format: "Nearest: PlayerName (123m) [Direction]"
        if direction:
            message = f"§c§lNearest: §r§e{target_player} §7({distance:.0f}m) §6{direction}"
        else:
            message = f"§c§lNearest: §r§e{target_player} §7({distance:.0f}m)"
        self.actionbar(traitor, message)


class SkinManager:
    """Manages player skins - resets to default Steve skin and restores originals"""

    def __init__(self, rcon_client: RCONClient, config: dict):
        self.rcon = rcon_client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.enabled = config.get("reset_skins_to_steve", False)
        # Track who had skins reset
        self.players_with_reset_skins: List[str] = []

    def reset_to_steve(self, player: str) -> bool:
        """Reset player skin to default Steve skin

        Tries multiple methods:
        1. SkinChanger mod command (/skin set <player> steve or /skin player <player> set steve)
        2. SkinRestorer mod command (/skin reset)
        3. Custom mod commands

        Returns True if command executed (may still fail if mod not installed)
        """
        if not self.enabled:
            return False

        # Try SkinChanger mod commands first (most likely for NeoForge)
        commands_to_try = [
            f"skin player {player} set steve",  # SkinChanger (admin command)
            f"skin set {player} steve",  # SkinChanger (alternative)
            f"skin {player} set steve",  # SkinChanger (alternative format)
            f"skin {player} steve",  # Generic
            f"skin reset {player}",  # SkinRestorer
            f"setskin {player} steve",  # Alternative
        ]

        for cmd in commands_to_try:
            response = self.rcon.execute(cmd)
            if response and "unknown" not in response.lower() and "error" not in response.lower():
                self.logger.info(
                    f"Reset {player}'s skin to Steve using: {cmd}")
                if player not in self.players_with_reset_skins:
                    self.players_with_reset_skins.append(player)
                return True

        # If no mod command worked, try using player data manipulation
        # Note: This requires a mod that supports it
        self.logger.warning(
            f"Could not reset {player}'s skin - no skin mod detected")
        self.logger.info(
            "Tip: Install a skin mod like 'SkinRestorer' or 'SkinChanger' for this feature")
        return False

    def reset_all_players(self, players: List[str]) -> int:
        """Reset all players' skins to Steve"""
        if not self.enabled:
            return 0

        self.players_with_reset_skins = []  # Clear previous list
        success_count = 0
        for player in players:
            if self.reset_to_steve(player):
                success_count += 1

        if success_count > 0:
            self.logger.info(
                f"Reset {success_count}/{len(players)} player skins to Steve")
        elif len(players) > 0:
            self.logger.warning(
                "No skins were reset - skin mod may not be installed")

        return success_count

    def restore_original_skins(self) -> int:
        """Restore all players' skins to their original/default skins

        Uses SkinChanger mod commands: /skin player <name> clear
        """
        if not self.enabled or not self.players_with_reset_skins:
            return 0

        success_count = 0
        # SkinChanger mod command format for clearing/resetting skins
        restore_commands = [
            # SkinChanger admin command (primary)
            "skin player {player} clear",
            "skin player {player} reset",  # Alternative reset command
            "skin {player} clear",  # Alternative format
            "skin clear {player}",  # Another alternative
            "skin reset {player}",  # SkinRestorer format
        ]

        for player in self.players_with_reset_skins.copy():
            restored = False
            for cmd_template in restore_commands:
                cmd = cmd_template.format(player=player)
                response = self.rcon.execute(cmd)

                # Check if command succeeded (response should not contain error keywords)
                if response:
                    response_lower = response.lower()
                    # Success indicators: no error keywords, might have success message
                    if ("unknown" not in response_lower and
                        "error" not in response_lower and
                        "not found" not in response_lower and
                        "cannot" not in response_lower and
                            "unable" not in response_lower):
                        self.logger.info(
                            f"Restored {player}'s skin using: {cmd}")
                        self.logger.debug(f"Response: {response}")
                        success_count += 1
                        restored = True
                        break
                    else:
                        self.logger.debug(
                            f"Command '{cmd}' failed: {response}")

            if not restored:
                self.logger.warning(
                    f"Could not restore {player}'s skin - no working command found")
                self.logger.info(
                    f"Tried commands: {[c.format(player=player) for c in restore_commands]}")

        if success_count > 0:
            self.logger.info(
                f"Restored {success_count}/{len(self.players_with_reset_skins)} player skins")
        elif len(self.players_with_reset_skins) > 0:
            self.logger.warning(
                f"Failed to restore any skins. Check SkinChanger mod is installed and commands are correct.")

        self.players_with_reset_skins = []  # Clear the list
        return success_count


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

        # Note: Mod command notification removed - using actionbar mode only

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

    def clear_all_effects(self, player: str):
        """Clear all effects from a player"""
        self.rcon.execute(f"effect clear {player}")
        self.logger.info(f"Cleared all effects from {player}")

    def remove_finder_items(self, players: List[str]):
        """Remove Modern Player Finder items from players (no-op since mod is command-based)"""
        # Modern Player Finder is command-based, not item-based, so nothing to remove
        pass


class WinConditionChecker:
    """Checks win conditions"""

    def __init__(self, role_manager: RoleManager, timer_manager: TimerManager, rcon_client: RCONClient):
        self.role_manager = role_manager
        self.timer_manager = timer_manager
        self.rcon = rcon_client
        self.logger = logging.getLogger(__name__)

    def check_win_conditions(self, alive_players: Optional[set] = None) -> Optional[Tuple[str, str]]:
        """Check if any win condition is met. Returns (winner, reason) or None

        Args:
            alive_players: Set of alive players (excluding spectators). If None, uses all online players.
        """
        if alive_players is None:
            online_players = self.rcon.get_online_players()
            alive_players = set(online_players)

        # Get alive traitors and innocents (excluding spectators)
        alive_traitors = [
            p for p in self.role_manager.get_traitors() if p in alive_players]
        alive_innocents = [
            p for p in self.role_manager.get_innocents() if p in alive_players]

        # Get all assigned traitors (not just alive ones) to check if any traitors were ever assigned
        all_traitors = self.role_manager.get_traitors()

        # Traitors win if all innocents are eliminated
        if len(alive_innocents) == 0 and len(alive_traitors) > 0:
            return ("Traitors", "All innocent players eliminated")

        # Innocents win if timer expires and at least one innocent survives
        if self.timer_manager.is_expired() and len(alive_innocents) > 0:
            return ("Innocents", "Time limit reached")

        # If all traitors are eliminated, innocents win
        # Only trigger this if traitors were actually assigned (not in test mode with single innocent)
        if len(alive_traitors) == 0 and len(alive_innocents) > 0 and len(all_traitors) > 0:
            return ("Innocents", "All traitors eliminated")

        return None


class GameState:
    """Manages overall game state"""

    def __init__(self, config_path: str):
        # Load configuration
        with open(config_path, 'r', encoding='utf-8') as f:
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
        self.skin_manager = SkinManager(self.rcon, self.config)
        self.win_checker = WinConditionChecker(
            self.role_manager, self.timer_manager, self.rcon)

        self.status = GameStatus.NOT_STARTED
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False
        self.tracking_thread: Optional[threading.Thread] = None
        self.tracking_running = False

        # Track alive players and death counts for spectator mode
        self.alive_players: set = set()
        self.death_counts: Dict[str, int] = {}
        self.original_gamemodes: Dict[str, str] = {}
        self.original_ops: List[str] = []  # Store ops to restore after game

        # Track chat state
        self.chat_disabled = False

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
        self.simulated_player_name = "TestInnocent"
        self.simulated_player_entity = None

    def _spawn_simulated_player(self, near_player: str, distance: float = 20.0) -> bool:
        """Spawn a Carpet simulated player for testing

        Args:
            near_player: Player to spawn near
            distance: Distance from player to spawn (default 20 blocks)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get player position
            player_pos = self._get_player_coordinates(near_player)
            if not player_pos:
                self.logger.error(f"Could not get position for {near_player}")
                return False

            # Calculate spawn position (offset in X direction)
            spawn_pos = (player_pos[0] + distance,
                         player_pos[1], player_pos[2])

            # Check if simulated player already exists and remove it first
            online_players_before = self.rcon.get_online_players()
            for player in online_players_before:
                if player.lower() == self.simulated_player_name.lower():
                    self.logger.info(
                        f"Simulated player '{player}' already exists, removing first...")
                    self.rcon.execute(f"player {player} kill")
                    time.sleep(0.5)

            # Spawn Carpet simulated player at the calculated position
            # Use execute positioned to spawn at the offset location
            # Use ~ for world-relative coordinates (not ^ which is rotation-relative)
            spawn_cmd = f"execute at {near_player} positioned ~{distance} ~ ~ run player {self.simulated_player_name} spawn"
            self.logger.info(f"Executing Carpet spawn command: {spawn_cmd}")
            response = self.rcon.execute(spawn_cmd)
            self.logger.info(f"Spawn command response: {repr(response)}")

            # Check if spawn was successful
            if response and ("Unknown" not in response.lower() and "error" not in response.lower() and "does not exist" not in response.lower()):
                # Wait a moment for the player to spawn
                # Increased wait time to ensure spawn completes
                time.sleep(1.0)

                # Verify the player exists and get actual coordinates
                online_players = self.rcon.get_online_players()
                self.logger.debug(
                    f"Online players after spawn: {online_players}")

                # Check case-insensitive match
                actual_player_name = None
                for player in online_players:
                    if player.lower() == self.simulated_player_name.lower():
                        actual_player_name = player
                        break

                if actual_player_name:
                    # Update simulated_player_name to match the actual spawned player name
                    # (Carpet might use different case)
                    self.simulated_player_name = actual_player_name
                    self.logger.info(
                        f"Updated simulated_player_name to match spawned player: '{self.simulated_player_name}'")

                    # Get the ACTUAL coordinates from the game, not the calculated position
                    actual_pos = self._get_player_coordinates(
                        actual_player_name)
                    if actual_pos:
                        self.logger.info(
                            f"Spawned Carpet simulated player '{actual_player_name}' at actual position: {actual_pos}")
                        self.logger.info(
                            f"Expected position was: {spawn_pos}, player position: {player_pos}")
                        # Store None - we'll always get coordinates from the game
                        self.simulated_player_entity = None
                    else:
                        self.logger.warning(
                            f"Could not get coordinates for spawned player '{actual_player_name}'")
                        self.simulated_player_entity = None

                    # Add to innocents list for tracking
                    if actual_player_name not in self.role_manager.roles:
                        self.role_manager.roles[actual_player_name] = Role.INNOCENT
                        self.alive_players.add(actual_player_name)
                        self.logger.info(
                            f"Added {actual_player_name} as simulated innocent")

                    # Calculate actual distance
                    if actual_pos and player_pos:
                        actual_distance = self._calculate_distance(
                            player_pos, actual_pos)
                        self.logger.info(
                            f"Actual spawn distance: {actual_distance:.1f}m (requested: {distance}m)")

                    # Notify the test player
                    self.notifications.tellraw(
                        near_player,
                        f"§aCarpet simulated player '{actual_player_name}' spawned!",
                        "green"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"Carpet simulated player '{self.simulated_player_name}' not found in online players after spawn")
                    return False
            else:
                self.logger.warning(
                    f"Failed to spawn Carpet simulated player: {response}")
                self.logger.info(
                    "Note: Make sure Carpet mod is installed and enabled")
                return False

        except Exception as e:
            self.logger.error(
                f"Error spawning Carpet simulated player: {e}", exc_info=True)
            return False

    def _remove_simulated_player(self):
        """Remove the Carpet simulated player"""
        try:
            # Check if player is online (Carpet simulated player)
            online_players = self.rcon.get_online_players()

            # Check for case-insensitive match
            player_to_remove = None
            for player in online_players:
                if player.lower() == self.simulated_player_name.lower():
                    player_to_remove = player
                    break

            if player_to_remove:
                # Kill the Carpet simulated player
                kill_cmd = f"player {player_to_remove} kill"
                self.logger.info(
                    f"Removing Carpet simulated player: {player_to_remove}")
                self.rcon.execute(kill_cmd)

                # Wait a moment for the player to be removed
                time.sleep(0.5)

                # Verify removal
                online_players_after = self.rcon.get_online_players()
                still_online = any(p.lower() == self.simulated_player_name.lower()
                                   for p in online_players_after)
                if not still_online:
                    self.logger.info(
                        f"Successfully removed Carpet simulated player '{player_to_remove}'")
                else:
                    self.logger.warning(
                        f"Carpet simulated player '{player_to_remove}' still online after kill command")

            # Remove from game state
            if self.simulated_player_name in self.role_manager.roles:
                del self.role_manager.roles[self.simulated_player_name]
            if self.simulated_player_name in self.alive_players:
                self.alive_players.remove(self.simulated_player_name)

            self.simulated_player_entity = None

        except Exception as e:
            self.logger.error(f"Error removing Carpet simulated player: {e}")

    def _get_simulated_player_coordinates(self) -> Optional[Tuple[float, float, float]]:
        """Get coordinates of the simulated player entity (armor stand or Carpet simulated player)"""
        # First check if it's a Carpet simulated player (real player entity)
        online_players = self.rcon.get_online_players()
        self.logger.debug(
            f"_get_simulated_player_coordinates: online_players={online_players}, looking for '{self.simulated_player_name}'")
        if online_players:
            # First try exact match (should work since we update simulated_player_name after spawn)
            if self.simulated_player_name in online_players:
                self.logger.debug(
                    f"Found exact match for simulated player: '{self.simulated_player_name}'")
                coords = self._get_player_coordinates(
                    self.simulated_player_name)
                if coords:
                    self.logger.info(
                        f"Got simulated player '{self.simulated_player_name}' coordinates (exact match): {coords}")
                    return coords

            # Fallback to case-insensitive match
            for player in online_players:
                self.logger.debug(
                    f"Checking player '{player}' (lower: '{player.lower()}') against '{self.simulated_player_name.lower()}'")
                if player.lower() == self.simulated_player_name.lower():
                    # It's a Carpet simulated player - get coordinates like a real player
                    self.logger.info(
                        f"Found simulated player match (case-insensitive): '{player}' (expected '{self.simulated_player_name}')")
                    coords = self._get_player_coordinates(player)
                    if coords:
                        self.logger.info(
                            f"Got simulated player '{player}' coordinates from game: {coords}")
                        return coords
                    else:
                        self.logger.warning(
                            f"Could not get coordinates for simulated player '{player}'")

        # Try armor stand fallback (for older spawn method)
        if self.simulated_player_entity:
            try:
                cmd = f"execute as @e[type=minecraft:armor_stand,name={self.simulated_player_name},limit=1] run data get entity @s Pos"
                response = self.rcon.execute(cmd)

                if response:
                    coord_pattern = r'\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]'
                    coord_match = re.search(coord_pattern, response)
                    if coord_match:
                        coords = (float(coord_match.group(1)),
                                  float(coord_match.group(2)),
                                  float(coord_match.group(3)))
                        self.logger.debug(
                            f"Got simulated player coordinates from armor stand: {coords}")
                        return coords
            except Exception as e:
                self.logger.debug(
                    f"Error getting armor stand coordinates: {e}")

        # Never fallback to stored position - it's unreliable
        self.logger.warning(
            f"Could not get coordinates for simulated player '{self.simulated_player_name}'")
        return None

    def start_game(self, test_mode: bool = False, test_player: Optional[str] = None, test_role: Optional[Role] = None, spawn_simulated_player: bool = False) -> bool:
        """Start a new game

        Args:
            test_mode: If True, allows starting with 1 player for testing
            test_player: If provided, assign this player the test_role
            test_role: Role to assign to test_player (TRAITOR or INNOCENT)
            spawn_simulated_player: If True, spawn a simulated player entity for testing
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

        # Reset all players to Steve skin (if enabled)
        if self.config.get("reset_skins_to_steve", False):
            self.skin_manager.reset_all_players(players)

        # Initialize death tracking and gamemode storage
        if self.config.get("set_dead_to_spectator", False):
            self.alive_players = set(players)
            self.death_counts = {}
            self.original_gamemodes = {}
            # Store original gamemodes and initialize death tracking
            for player in players:
                # Try to get current gamemode (default to survival if can't determine)
                self.original_gamemodes[player] = "survival"
                self.death_counts[player] = 0
            # Initialize death scoreboard (create if doesn't exist)
            try:
                self.rcon.execute(
                    "scoreboard objectives add deaths deathCount")
            except Exception:
                # Scoreboard might already exist, try to remove and recreate
                try:
                    self.rcon.execute("scoreboard objectives remove deaths")
                    self.rcon.execute(
                        "scoreboard objectives add deaths deathCount")
                except:
                    pass  # Ignore errors, scoreboard might be managed elsewhere

            # Reset all players' death counts to 0 for a clean start
            for player in players:
                try:
                    self.rcon.execute(
                        f"scoreboard players set {player} deaths 0")
                except Exception as e:
                    self.logger.warning(
                        f"Could not reset death count for {player}: {e}")

            self.logger.info(
                "Initialized death tracking for spectator mode (reset all death counts to 0)")

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

        # Inform traitors of other traitors' identities
        traitors = self.role_manager.get_traitors()
        if len(traitors) > 1:
            # There are multiple traitors - inform each traitor of the others
            for traitor in traitors:
                other_traitors = [t for t in traitors if t != traitor]
                if other_traitors:
                    traitor_list = ', '.join(other_traitors)
                    self.notifications.tellraw(
                        traitor, f"§4[TRAITOR] §7Your fellow traitors: §c{traitor_list}", "red")
                    self.logger.info(
                        f"Informed traitor {traitor} of other traitors: {traitor_list}")

        # Remove operator status from all players to prevent console messages from revealing traitors
        self._deop_all_players(players)

        # Disable chat
        self._disable_chat(players)

        # Start timer
        self.timer_manager.start()

        # Check if we need monitoring thread (for innocents to get time updates)
        # In test mode with single player, still start monitor if player is innocent
        needs_monitoring = not (test_mode and len(players) == 1)
        if test_mode and len(players) == 1 and test_role == Role.INNOCENT:
            needs_monitoring = True  # Innocents need time updates

        # Start monitoring thread (skip in test mode with 1 player, unless player is innocent)
        if needs_monitoring:
            self.status = GameStatus.IN_PROGRESS
            self.monitor_running = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_game, daemon=True)
            self.monitor_thread.start()

            # Start player tracking thread (if enabled and not using mod)
            # Only start tracking if not in test mode with single innocent (tracking is for traitors only)
            if not (test_mode and len(players) == 1 and test_role == Role.INNOCENT):
                tracking_config = self.config.get("player_tracking", {})
                if tracking_config.get("enabled", False) and not tracking_config.get("use_mod", False):
                    self.tracking_running = True
                    self.tracking_thread = threading.Thread(
                        target=self._track_nearest_players, daemon=True)
                    self.tracking_thread.start()
                    self.logger.info(
                        "Player tracking enabled (actionbar mode)")
                elif tracking_config.get("enabled", False) and tracking_config.get("use_mod", False):
                    self.logger.info(
                        "Player tracking enabled (Modern Player Finder mod)")
        else:
            self.status = GameStatus.IN_PROGRESS
            self.logger.info("Test mode: Monitoring disabled (single player)")

            # In test mode, enable tracking if player is traitor
            # Use regular tracking if simulated player will be spawned (treats simulated player like real player)
            # Otherwise use test mode tracking
            tracking_config = self.config.get("player_tracking", {})
            if (test_mode and test_role == Role.TRAITOR and
                    tracking_config.get("enabled", False) and not tracking_config.get("use_mod", False)):
                self.tracking_running = True
                # If we're spawning a simulated player, use regular tracking (treats simulated player like real player)
                if spawn_simulated_player:
                    self.logger.info(
                        f"Using regular tracking - simulated player will be treated as real player")
                    self.tracking_thread = threading.Thread(
                        target=self._track_nearest_players, daemon=True)
                else:
                    self.logger.info(
                        f"Using test mode tracking (no simulated player)")
                    self.tracking_thread = threading.Thread(
                        target=self._track_nearest_players_test_mode, daemon=True)
                self.tracking_thread.start()
                self.logger.info("Player tracking enabled (actionbar mode)")
                # Give thread a moment to start
                time.sleep(0.5)
                self.logger.info(
                    f"Tracking thread started: {self.tracking_thread.is_alive()}")
            elif (test_mode and len(players) == 1 and test_role == Role.TRAITOR and
                    tracking_config.get("enabled", False) and tracking_config.get("use_mod", False)):
                self.logger.info(
                    "Modern Player Finder mod enabled - traitors received finder items")

        # Spawn simulated player if requested in test mode
        if test_mode and spawn_simulated_player and len(players) == 1:
            self.logger.info(
                f"Attempting to spawn simulated player for {players[0]}...")
            if self._spawn_simulated_player(players[0], distance=10.0):
                self.logger.info("Simulated player spawned for testing")
            else:
                self.logger.warning(
                    "Failed to spawn simulated player - check logs for details")

        self.logger.info("Game started successfully")
        return True

    def stop_game(self):
        """Stop the current game"""
        if self.status != GameStatus.IN_PROGRESS:
            return

        self.logger.info("Stopping game...")
        self.monitor_running = False
        self.tracking_running = False

        # Get all online players
        players = self.rcon.get_online_players()

        # Clear all effects from all players
        for player in players:
            self.abilities.clear_all_effects(player)

        # Remove Modern Player Finder items from traitors
        traitors = self.role_manager.get_traitors()
        self.abilities.remove_finder_items(traitors)

        # Remove simulated player if it exists
        self._remove_simulated_player()

        # Restore original skins
        self.skin_manager.restore_original_skins()

        # Restore gamemodes for all players (including spectators)
        self._restore_gamemodes()

        # Re-enable chat
        self._enable_chat()

        # Restore operator status to players who had it before the game
        self._restore_ops()

        # Clean up death scoreboard if it exists
        if self.config.get("set_dead_to_spectator", False):
            try:
                self.rcon.execute("scoreboard objectives remove deaths")
            except Exception:
                pass  # Scoreboard might not exist, ignore error

        # Reset state
        self.role_manager.reset()
        self.timer_manager.reset()
        self.status = GameStatus.ENDED
        self.alive_players.clear()
        self.death_counts.clear()
        self.original_gamemodes.clear()

        self.notifications.tellraw_all("§7Game stopped by admin", "gray")
        self.logger.info("Game stopped")

    def _get_player_coordinates(self, player: str, retry: bool = True) -> Optional[Tuple[float, float, float]]:
        """Get player's current coordinates with retry logic for RCON failures"""
        max_retries = 2
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                # Use data command to get player position
                response = self.rcon.execute(f"data get entity {player} Pos")

                if not response:
                    if attempt < max_retries - 1 and retry:
                        self.logger.debug(
                            f"No response for coordinate command for {player} (attempt {attempt + 1}/{max_retries}), retrying...")
                        time.sleep(retry_delay)
                        continue
                    self.logger.debug(
                        f"No response for coordinate command for {player}")
                    return None

                self.logger.debug(
                    f"Coordinate response for {player}: {response}")

                # Parse response format: "PlayerName has the following entity data: [123.5d, 64.0d, -456.7d]"
                # Or: "Pos: [123.5d, 64.0d, -456.7d]"
                # Extract the array of coordinates: [x, y, z]
                # Look for the pattern: [numberd, numberd, numberd] (coordinates always have 'd' suffix)
                array_match = re.search(
                    r'\[([-\d.]+)d,\s*([-\d.]+)d,\s*([-\d.]+)d\]', response)

                if array_match:
                    # Extract the three coordinates from the array
                    coords = [
                        float(array_match.group(1)),
                        float(array_match.group(2)),
                        float(array_match.group(3))
                    ]
                    self.logger.debug(
                        f"Matched array pattern for {player}: {coords}")
                else:
                    # Fallback: try to find all numbers with 'd' suffix (coordinates)
                    matches = re.findall(r'([-\d.]+)d', response)
                    coords = []
                    for match in matches:
                        try:
                            val = float(match)
                            coords.append(val)
                            if len(coords) >= 3:
                                break
                        except ValueError:
                            continue
                    if coords:
                        self.logger.debug(
                            f"Used fallback pattern matching for {player}: {coords}")

                if len(coords) >= 3:
                    result = (coords[0], coords[1], coords[2])
                    return result
                else:
                    self.logger.warning(
                        f"Could not parse coordinates from response: {response} (found {len(coords)} coords, expected 3)")
                    return None

            except Exception as e:
                if attempt < max_retries - 1 and retry:
                    self.logger.debug(
                        f"Error getting coordinates for {player} (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                    time.sleep(retry_delay)
                    continue
                self.logger.error(
                    f"Error getting coordinates for {player}: {e}")
                return None

        return None

    def _calculate_distance(self, pos1: Tuple[float, float, float], pos2: Tuple[float, float, float]) -> float:
        """Calculate 3D distance between two positions"""
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        dz = pos1[2] - pos2[2]
        return (dx**2 + dy**2 + dz**2) ** 0.5

    def _calculate_direction(self, traitor_pos: Tuple[float, float, float], target_pos: Tuple[float, float, float]) -> str:
        """Calculate cardinal direction from traitor to target

        Minecraft coordinate system:
        - +X = East, -X = West
        - +Z = South, -Z = North
        atan2(dz, dx): 0°=East, 90°=South, 180°=West, 270°=North
        """
        dx = target_pos[0] - traitor_pos[0]  # East-West difference (+ = East)
        # North-South difference (+ = South)
        dz = target_pos[2] - traitor_pos[2]

        # Calculate angle in degrees
        angle = math.degrees(math.atan2(dz, dx))
        # Normalize to 0-360
        angle = (angle + 360) % 360

        # Map to cardinal directions (Minecraft: +X=East, +Z=South)
        if 337.5 <= angle or angle < 22.5:
            return "→ E"  # East (dx > 0, dz ≈ 0)
        elif 22.5 <= angle < 67.5:
            return "↗ SE"  # South-East (dx > 0, dz > 0)
        elif 67.5 <= angle < 112.5:
            return "↓ S"  # South (dx ≈ 0, dz > 0)
        elif 112.5 <= angle < 157.5:
            return "↙ SW"  # South-West (dx < 0, dz > 0)
        elif 157.5 <= angle < 202.5:
            return "← W"  # West (dx < 0, dz ≈ 0)
        elif 202.5 <= angle < 247.5:
            return "↖ NW"  # North-West (dx < 0, dz < 0)
        elif 247.5 <= angle < 292.5:
            return "↑ N"  # North (dx ≈ 0, dz < 0)
        else:  # 292.5 <= angle < 337.5
            return "↗ NE"  # North-East (dx > 0, dz < 0)

    def _track_nearest_players(self):
        """Track nearest innocent player for each traitor and update actionbar"""
        tracking_config = self.config.get("player_tracking", {})
        update_interval = tracking_config.get("update_interval_seconds", 3)
        show_distance = tracking_config.get("show_distance", True)
        show_direction = tracking_config.get("show_direction", True)

        self.logger.info(
            f"Tracking thread started - update_interval={update_interval}s")
        loop_count = 0

        while self.tracking_running and self.status == GameStatus.IN_PROGRESS:
            try:
                loop_count += 1
                self.logger.info(f"Tracking loop iteration {loop_count}")

                traitors = self.role_manager.get_traitors()
                innocents = self.role_manager.get_innocents()
                self.logger.debug(
                    f"Traitors: {traitors}, Innocents: {innocents}")

                online_players = self.rcon.get_online_players()
                self.logger.info(f"Online players: {online_players}")

                # If RCON failed, online_players will be empty list - skip this iteration
                if not online_players:
                    self.logger.warning(
                        "No online players found (RCON may have failed), skipping tracking update")
                    time.sleep(update_interval)
                    continue

                # Get alive traitors and innocents
                # Include simulated player if it exists (check both case variations)
                alive_traitors = [
                    t for t in traitors if t in self.alive_players and t in online_players]
                alive_innocents = [
                    i for i in innocents if i in self.alive_players and i in online_players]

                self.logger.info(
                    f"Alive traitors: {alive_traitors}, Alive innocents (before simulated check): {alive_innocents}")

                # Also check for simulated player - treat it exactly like a real player
                # Find the actual player name (case-insensitive match) and add it to innocents
                if self.simulated_player_name:
                    simulated_found = False
                    # First check if it's already in alive_innocents (exact match)
                    for innocent in alive_innocents:
                        if innocent.lower() == self.simulated_player_name.lower():
                            simulated_found = True
                            self.logger.debug(
                                f"Simulated player '{self.simulated_player_name}' already in alive_innocents as '{innocent}'")
                            break

                    # If not found, check online players for case-insensitive match
                    if not simulated_found:
                        for player in online_players:
                            if player.lower() == self.simulated_player_name.lower():
                                # Found simulated player - add it with its actual name
                                if player in self.alive_players:
                                    alive_innocents.append(player)
                                    self.logger.info(
                                        f"Added simulated player '{player}' to alive_innocents (treating as real player)")
                                else:
                                    # Simulated player is online but not in alive_players - add it now
                                    # This handles the case where spawn command appeared to fail but player actually spawned
                                    self.logger.info(
                                        f"Simulated player '{player}' found online but not in alive_players - adding now")
                                    if player not in self.role_manager.roles:
                                        self.role_manager.roles[player] = Role.INNOCENT
                                    self.alive_players.add(player)
                                    alive_innocents.append(player)
                                    self.logger.info(
                                        f"Added simulated player '{player}' to alive_players and alive_innocents")
                                break

                self.logger.info(
                    f"Alive traitors: {alive_traitors}, Alive innocents (final): {alive_innocents}")

                if not alive_traitors:
                    self.logger.warning(
                        "No alive traitors found, skipping tracking update")
                    time.sleep(update_interval)
                    continue

                if not alive_innocents:
                    self.logger.warning(
                        "No alive innocents found, skipping tracking update")
                    time.sleep(update_interval)
                    continue

                # For each traitor, find nearest innocent
                for traitor in alive_traitors:
                    traitor_pos = self._get_player_coordinates(traitor)
                    if not traitor_pos:
                        self.logger.warning(
                            f"Could not get coordinates for traitor {traitor}, skipping")
                        continue

                    nearest_innocent = None
                    nearest_distance = float('inf')

                    # Find nearest innocent
                    for innocent in alive_innocents:
                        innocent_pos = self._get_player_coordinates(innocent)
                        if not innocent_pos:
                            self.logger.warning(
                                f"Could not get coordinates for innocent {innocent}, skipping")
                            continue

                        distance = self._calculate_distance(
                            traitor_pos, innocent_pos)
                        if distance < nearest_distance:
                            nearest_distance = distance
                            nearest_innocent = innocent

                    # Update actionbar for traitor (include time remaining)
                    if nearest_innocent:
                        # Get time remaining
                        remaining = self.timer_manager.get_remaining_seconds()
                        time_minutes = remaining // 60
                        time_seconds = remaining % 60
                        time_str = f"§7Time: §6{time_minutes}:{time_seconds:02d} §7| "

                        direction = ""
                        if show_direction and nearest_distance > 0:
                            innocent_pos = self._get_player_coordinates(
                                nearest_innocent)
                            if innocent_pos:
                                direction = self._calculate_direction(
                                    traitor_pos, innocent_pos)
                                self.logger.info(
                                    f"Direction from {traitor} to {nearest_innocent}: {direction}")

                        if show_distance:
                            if direction:
                                message = f"{time_str}§c§lNearest: §r§e{nearest_innocent} §7({nearest_distance:.0f}m) §6{direction}"
                            else:
                                message = f"{time_str}§c§lNearest: §r§e{nearest_innocent} §7({nearest_distance:.0f}m)"
                            self.notifications.actionbar(traitor, message)
                            self.logger.info(
                                f"Sent actionbar to {traitor}: {message}")
                        else:
                            message = f"{time_str}§c§lNearest: §r§e{nearest_innocent}"
                            self.notifications.actionbar(traitor, message)
                            self.logger.info(
                                f"Sent actionbar to {traitor}: {message}")
                    else:
                        self.logger.warning(
                            f"No nearest innocent found for {traitor}")

                time.sleep(update_interval)
            except MCRconException as e:
                # RCON connection errors - just skip this iteration
                # Connection will be re-established when possible
                self.logger.debug(f"RCON error in tracking (will retry): {e}")
                time.sleep(update_interval)
            except Exception as e:
                self.logger.error(f"Error in player tracking thread: {e}")
                time.sleep(update_interval)

    def _track_nearest_players_test_mode(self):
        """Test mode tracking - tracks simulated players or real players (including Carpet simulated players)"""
        tracking_config = self.config.get("player_tracking", {})
        update_interval = tracking_config.get("update_interval_seconds", 3)
        show_distance = tracking_config.get("show_distance", True)
        show_direction = tracking_config.get("show_direction", True)

        # Get the traitor player (should be the only one)
        traitors = self.role_manager.get_traitors()
        if not traitors:
            self.logger.warning("No traitors found in test mode tracking")
            return

        traitor = traitors[0]
        self.logger.info(f"Starting test mode tracking for {traitor}")
        self.logger.info(
            f"Tracking config: interval={update_interval}s, distance={show_distance}, direction={show_direction}")

        # Send initial test message to confirm tracking is working
        self.logger.info(f"Sending initial test message to {traitor}")
        self.notifications.actionbar(traitor, "§a§lTracking Active!")
        time.sleep(1)

        loop_count = 0
        while self.tracking_running and self.status == GameStatus.IN_PROGRESS:
            try:
                loop_count += 1
                self.logger.info(
                    f"Tracking loop iteration {loop_count} for {traitor}")

                traitor_pos = self._get_player_coordinates(traitor)
                if not traitor_pos:
                    self.logger.warning(
                        f"Could not get coordinates for {traitor} - retrying...")
                    time.sleep(update_interval)
                    continue

                self.logger.info(
                    f"Traitor '{traitor}' position: {traitor_pos}")

                # Check if we have a simulated player (armor stand or Carpet player)
                simulated_pos = self._get_simulated_player_coordinates()
                self.logger.info(
                    f"Simulated player check: name='{self.simulated_player_name}', simulated_pos={simulated_pos}")
                if not simulated_pos:
                    self.logger.warning(
                        f"Could not get simulated player coordinates - skipping this iteration")
                    time.sleep(update_interval)
                    continue

                # Both coordinates are valid - calculate distance
                distance = self._calculate_distance(
                    traitor_pos, simulated_pos)

                # Validate distance is reasonable (not more than 1000 blocks)
                if distance > 1000:
                    self.logger.error(
                        f"Calculated distance is suspiciously large: {distance:.1f}m. "
                        f"Traitor: {traitor_pos}, Simulated: {simulated_pos}. Skipping this update.")
                    time.sleep(update_interval)
                    continue

                # Calculate direction
                direction = ""
                if show_direction:
                    direction = self._calculate_direction(
                        traitor_pos, simulated_pos)

                # Build and send message (include time remaining)
                remaining = self.timer_manager.get_remaining_seconds()
                time_minutes = remaining // 60
                time_seconds = remaining % 60
                time_str = f"§7Time: §6{time_minutes}:{time_seconds:02d} §7| "

                if show_distance:
                    if direction:
                        message = f"{time_str}§c§lNearest: §r§e{self.simulated_player_name} §7({distance:.0f}m) §6{direction}"
                    else:
                        message = f"{time_str}§c§lNearest: §r§e{self.simulated_player_name} §7({distance:.0f}m)"
                else:
                    message = f"{time_str}§c§lNearest: §r§e{self.simulated_player_name}"

                self.logger.info(
                    f"Sending actionbar to {traitor}: {message}")
                try:
                    self.notifications.actionbar(traitor, message)
                    self.logger.debug(
                        f"Actionbar sent successfully to {traitor}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to send actionbar to {traitor}: {e}")

                time.sleep(update_interval)
            except MCRconException as e:
                # RCON connection errors - just skip this iteration
                # Connection will be re-established when possible
                self.logger.debug(
                    f"RCON error in test tracking (will retry): {e}")
                time.sleep(update_interval)
            except Exception as e:
                self.logger.error(
                    f"Error in test mode tracking thread: {e}", exc_info=True)
                time.sleep(update_interval)

        self.logger.info(f"Tracking thread ended for {traitor}")

    def _monitor_game(self):
        """Monitor game state and check win conditions"""
        last_time_update = 0
        last_win_check = 0
        # Get time update interval from config (default: 3 seconds)
        time_update_interval = self.config.get(
            "time_update_interval_seconds", 3)
        # Check win conditions every 2 seconds (less frequent to reduce RCON calls)
        win_check_interval = 2.0

        while self.monitor_running and self.status == GameStatus.IN_PROGRESS:
            try:
                current_time = time.time()

                # Check win conditions less frequently to reduce RCON overhead
                if current_time - last_win_check >= win_check_interval:
                    if self.config.get("set_dead_to_spectator", False):
                        self._check_deaths_and_set_spectator()
                        # Pass alive players to win checker
                        result = self.win_checker.check_win_conditions(
                            self.alive_players)
                    else:
                        # Check win conditions
                        result = self.win_checker.check_win_conditions()
                    if result:
                        winner, reason = result
                        self._end_game(winner, reason)
                        break
                    last_win_check = current_time

                # Send time updates via actionbar at configured interval (only to innocents, traitors get it with position updates)
                if current_time - last_time_update >= time_update_interval:
                    remaining = self.timer_manager.get_remaining_seconds()
                    minutes = remaining // 60
                    seconds = remaining % 60
                    # Only send to innocents (traitors get time with their position updates)
                    # Cache online players to avoid multiple RCON calls
                    online_players = self.rcon.get_online_players()
                    traitors = self.role_manager.get_traitors()
                    innocents = [
                        p for p in online_players if p not in traitors]
                    for innocent in innocents:
                        self.notifications.send_time_update(
                            minutes, seconds, innocent)
                    last_time_update = current_time

                # Sleep for a short interval to allow frequent time updates
                # Use the smaller of time_update_interval or 0.5 seconds for responsive checking
                sleep_time = min(time_update_interval, 0.5)
                time.sleep(sleep_time)
            except Exception as e:
                self.logger.error(f"Error in monitor thread: {e}")
                # Sleep briefly on error, but still allow frequent updates
                sleep_time = min(time_update_interval, 0.5)
                time.sleep(sleep_time)

    def _check_deaths_and_set_spectator(self):
        """Check for player deaths and set dead players to spectator mode.
        Also ensures dead players stay in spectator mode even after respawn."""
        try:
            online_players = self.rcon.get_online_players()

            # Get all players who were in the game (alive + dead)
            all_game_players = set(self.alive_players) | set(
                self.death_counts.keys())

            for player in list(all_game_players):
                if player not in online_players:
                    # Player disconnected, remove from alive list but keep in death_counts
                    self.alive_players.discard(player)
                    continue

                # Check death count from scoreboard
                response = self.rcon.execute(
                    f"scoreboard players get {player} deaths")
                if response:
                    try:
                        # Parse response like "player has 1 [deaths]"
                        # Or "player has 1"
                        parts = response.split()
                        if len(parts) >= 3:
                            death_count = int(parts[2])
                        elif len(parts) >= 2:
                            death_count = int(parts[1])
                        else:
                            death_count = 0
                    except (ValueError, IndexError):
                        death_count = 0
                else:
                    death_count = 0

                # If death count increased, player died
                if death_count > self.death_counts.get(player, 0):
                    self.death_counts[player] = death_count
                    if player in self.alive_players:
                        self.alive_players.discard(player)
                        # Set to spectator mode
                        self.rcon.execute(f"gamemode spectator {player}")
                        self.logger.info(
                            f"{player} died and was set to spectator mode")
                        # Notify player
                        self.notifications.tellraw(
                            player, f"§cYou died! You are now in spectator mode.", "red")
                        # Notify all players
                        self.notifications.tellraw_all(
                            f"§7{player} has been eliminated!", "gray")

                # If player is dead (not in alive_players) but has died before,
                # ensure they stay in spectator mode (handles respawn)
                # Continuously set them to spectator to prevent respawn bypass
                if player not in self.alive_players and self.death_counts.get(player, 0) > 0:
                    # Force spectator mode (handles immediate respawn)
                    self.rcon.execute(f"gamemode spectator {player}")
        except Exception as e:
            self.logger.error(f"Error checking deaths: {e}")

    def _restore_gamemodes(self):
        """Restore all players to their original gamemodes"""
        if not self.config.get("set_dead_to_spectator", False):
            return

        try:
            online_players = self.rcon.get_online_players()
            for player in online_players:
                original_gamemode = self.original_gamemodes.get(
                    player, "survival")
                self.rcon.execute(f"gamemode {original_gamemode} {player}")
                self.logger.debug(
                    f"Restored {player} to {original_gamemode} mode")
        except Exception as e:
            self.logger.error(f"Error restoring gamemodes: {e}")

    def _deop_all_players(self, players: List[str]):
        """Remove operator status from all players to prevent console messages from revealing traitors"""
        try:
            # Get list of current ops from ops.json (if accessible) or by checking each player
            # We'll store the list and restore it later
            self.original_ops = []

            # Try to read ops.json to get the list of ops
            try:
                ops_file = "ops.json"
                if os.path.exists(ops_file):
                    with open(ops_file, 'r', encoding='utf-8') as f:
                        ops_data = json.load(f)
                        if isinstance(ops_data, list):
                            self.original_ops = [
                                op.get('name', '') for op in ops_data if isinstance(op, dict) and 'name' in op]
                        elif isinstance(ops_data, dict) and 'ops' in ops_data:
                            self.original_ops = [op.get('name', '') for op in ops_data['ops'] if isinstance(
                                op, dict) and 'name' in op]
            except Exception as e:
                self.logger.debug(f"Could not read ops.json: {e}")

            # Deop all players (even if we couldn't read ops.json, deop them anyway)
            for player in players:
                try:
                    self.rcon.execute(f"deop {player}")
                    self.logger.debug(f"Deopped {player}")
                except Exception as e:
                    self.logger.debug(f"Could not deop {player}: {e}")

            self.logger.info(
                f"Removed operator status from all players (stored {len(self.original_ops)} original ops)")
        except Exception as e:
            self.logger.warning(f"Error deopping players: {e}")

    def _restore_ops(self):
        """Restore operator status to players who had it before the game"""
        try:
            if not self.original_ops:
                self.logger.debug("No original ops to restore")
                return

            online_players = self.rcon.get_online_players()
            restored_count = 0

            for op_name in self.original_ops:
                # Only restore if player is online
                if op_name in online_players:
                    try:
                        self.rcon.execute(f"op {op_name}")
                        restored_count += 1
                        self.logger.debug(f"Restored op status to {op_name}")
                    except Exception as e:
                        self.logger.debug(
                            f"Could not restore op status to {op_name}: {e}")

            self.logger.info(
                f"Restored operator status to {restored_count} player(s)")
            self.original_ops = []  # Clear the list
        except Exception as e:
            self.logger.warning(f"Error restoring ops: {e}")

    def _disable_chat(self, players: List[str]):
        """Disable chat for all players using teams (vanilla method)"""
        try:
            # Try mod commands first (if mods are installed)
            # Common chat disable mods:
            # - "Disable Chat" mod: /chat disable
            # - "AntiChat" mod: /antichat enable
            # - "Chat Control" mod: /chatcontrol disable
            # - Generic: /chat disable, disablechat
            text_chat_commands = [
                "chat disable",  # Disable Chat mod
                "/chat disable",  # Disable Chat mod (with slash)
                "antichat enable",  # AntiChat mod
                "/antichat enable",  # AntiChat mod (with slash)
                "chatcontrol disable",  # Chat Control mod
                "/chatcontrol disable",  # Chat Control mod (with slash)
                "disablechat",  # Generic alternative
                "/disablechat",  # Generic alternative (with slash)
            ]

            for cmd in text_chat_commands:
                try:
                    response = self.rcon.execute(cmd)
                    if response and "unknown" not in response.lower() and "error" not in response.lower():
                        self.logger.info(
                            f"Disabled chat using mod command: {cmd}")
                        self.chat_disabled = True
                        return
                except:
                    pass

            # Vanilla method: Put each player in their own team to prevent cross-player chat
            # Players in different teams cannot see each other's chat messages
            base_team_name = "molehunt_"

            for player in players:
                team_name = f"{base_team_name}{player}"
                try:
                    # Create a unique team for each player
                    self.rcon.execute(f"team add {team_name}")
                    # Set team to not see friendly invisibles (prevents some interactions)
                    self.rcon.execute(
                        f"team modify {team_name} seeFriendlyInvisibles false")
                    # Hide nametags for anonymity
                    self.rcon.execute(
                        f"team modify {team_name} nametagVisibility never")
                    # Add player to their own isolated team
                    self.rcon.execute(f"team join {team_name} {player}")
                except Exception as e:
                    self.logger.debug(
                        f"Could not create team for {player}: {e}")

            self.logger.info(
                "Chat disabled using teams (each player in separate team - prevents cross-player chat)")
            self.chat_disabled = True

        except Exception as e:
            self.logger.warning(f"Could not disable chat: {e}")
            self.logger.info(
                "Note: For full chat disable, consider installing a mod like 'Disable Chat' or 'Chat Control'")

    def _enable_chat(self):
        """Re-enable chat for all players"""
        if not self.chat_disabled:
            return

        try:
            # Try mod commands first (if mods were used)
            # Common chat enable mods:
            # - "Disable Chat" mod: /chat enable
            # - "AntiChat" mod: /antichat disable
            # - "Chat Control" mod: /chatcontrol enable
            text_chat_commands = [
                "chat enable",  # Disable Chat mod
                "/chat enable",  # Disable Chat mod (with slash)
                "antichat disable",  # AntiChat mod
                "/antichat disable",  # AntiChat mod (with slash)
                "chatcontrol enable",  # Chat Control mod
                "/chatcontrol enable",  # Chat Control mod (with slash)
                "enablechat",  # Generic alternative
                "/enablechat",  # Generic alternative (with slash)
            ]

            for cmd in text_chat_commands:
                try:
                    response = self.rcon.execute(cmd)
                    if response and "unknown" not in response.lower() and "error" not in response.lower():
                        self.logger.info(
                            f"Enabled chat using mod command: {cmd}")
                        self.chat_disabled = False
                        return
                except:
                    pass

            # Remove players from their isolated teams
            online_players = self.rcon.get_online_players()
            base_team_name = "molehunt_"

            for player in online_players:
                try:
                    # Remove player from their team
                    self.rcon.execute(f"team leave {player}")
                    # Remove the team
                    team_name = f"{base_team_name}{player}"
                    self.rcon.execute(f"team remove {team_name}")
                except:
                    pass  # Team might not exist, ignore

            self.logger.info("Chat re-enabled (teams removed)")
            self.chat_disabled = False

        except Exception as e:
            self.logger.warning(f"Could not enable chat: {e}")

    def _end_game(self, winner: str, reason: str):
        """End the game"""
        self.status = GameStatus.ENDED
        self.monitor_running = False
        self.tracking_running = False

        # Get all online players
        players = self.rcon.get_online_players()

        # Announce winners FIRST so players can see the message
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

        # Delay before cleanup so players can see the win message (10 seconds)
        def cleanup_after_delay():
            time.sleep(10)

            # Get fresh player list
            current_players = self.rcon.get_online_players()

            # Clear all effects from all players
            for player in current_players:
                try:
                    self.abilities.clear_all_effects(player)
                except Exception as e:
                    self.logger.warning(
                        f"Could not clear effects for {player}: {e}")

            # Remove Modern Player Finder items from traitors
            traitors = self.role_manager.get_traitors()
            self.abilities.remove_finder_items(traitors)

            # Remove simulated player if it exists
            self._remove_simulated_player()

            # Restore original skins
            self.skin_manager.restore_original_skins()

            # Restore gamemodes for all players (including spectators)
            self._restore_gamemodes()

            # Re-enable chat
            self._enable_chat()

            # Clean up death scoreboard if it exists
            if self.config.get("set_dead_to_spectator", False):
                try:
                    self.rcon.execute("scoreboard objectives remove deaths")
                except Exception:
                    pass  # Scoreboard might not exist, ignore error

        # Run cleanup in a separate thread after delay
        cleanup_thread = threading.Thread(
            target=cleanup_after_delay, daemon=True)
        cleanup_thread.start()

        # Reset after a delay (30 seconds total: 10 for cleanup delay + 20 more)
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
    parser.add_argument("--spawn-simulated-player", action="store_true",
                        help="Spawn a simulated player entity for testing (test mode only)")

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

        spawn_simulated = args.spawn_simulated_player if test_mode else False
        if game.start_game(test_mode=test_mode, test_player=test_player, test_role=test_role, spawn_simulated_player=spawn_simulated):
            mode_str = f" (TEST MODE: {test_player} as {test_role.value})" if test_mode else ""
            if spawn_simulated:
                mode_str += " [Simulated Player Spawned]"
            print(f"Game started successfully!{mode_str}")
            # Keep script running to maintain monitoring
            try:
                while game.status == GameStatus.IN_PROGRESS:
                    try:
                        time.sleep(1)
                    except MCRconException:
                        # Ignore timeout errors during sleep - connection will be re-established when needed
                        pass
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
