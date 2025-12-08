"""
Mole Hunt Game State
Manages the overall game state for Mole Hunt game mode.
"""

import json
import math
import logging
import re
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

try:
    from mcrcon import MCRconException
except ImportError:
    print("ERROR: mcrcon not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

from game_engine.game_status import GameStatus
from game_engine.rcon_client import RCONClient
from game_engine.timer_manager import TimerManager
from .role import Role
from .role_manager import RoleManager
from .traitor_abilities import TraitorAbilities
from .skin_manager import SkinManager
from .win_condition_checker import WinConditionChecker
from .notification_system import MoleHuntNotificationSystem


class MoleHuntGameState:
    """Manages overall game state for Mole Hunt game"""

    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        rcon_config = self.config.get("rcon", {})
        self.rcon = RCONClient(
            rcon_config.get("host", "localhost"),
            rcon_config.get("port", 25575),
            rcon_config.get("password", "")
        )

        self.role_manager = RoleManager(self.config.get("traitor_ratio", 0.25))
        self.timer_manager = TimerManager(
            self.config.get("game_duration_minutes", 30))
        self.notifications = MoleHuntNotificationSystem(self.rcon)
        self.abilities = TraitorAbilities(self.rcon, self.config)
        self.skin_manager = SkinManager(self.rcon, self.config)
        self.win_checker = WinConditionChecker(
            self.role_manager, self.timer_manager, self.rcon)

        self.status = GameStatus.NOT_STARTED
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_running = False
        self.tracking_thread: Optional[threading.Thread] = None
        self.tracking_running = False
        self.cleanup_thread: Optional[threading.Thread] = None
        self._end_game_lock = threading.Lock()
        self._game_ended_announced = False

        self.alive_players: set = set()
        self.death_counts: Dict[str, int] = {}

        # player -> timestamp when first detected
        self.pending_deaths: Dict[str, float] = {}

        self.chat_disabled = False

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

    def _execute_command(self, command: str) -> bool:
        """Execute an RCON command with uniform error handling

        Args:
            command: The RCON command to execute

        Returns:
            True if command succeeded, False otherwise
        """
        try:
            self.rcon.execute(command)
            self.logger.info(f"{command}")
            return True
        except Exception as e:
            self.logger.warning(f"{command} command failed: {e}")
            self.logger.info(f"{command} command failed: {e}")
            return False

    def _validate_game_not_in_progress(self) -> bool:
        """Check if game is already in progress"""
        if self.status == GameStatus.IN_PROGRESS:
            self.logger.warning("Game already in progress")
            return False
        return True

    def _validate_rcon_connection(self) -> bool:
        """Validate RCON connection"""
        if not self.rcon.connect():
            self.logger.error("Failed to connect to RCON")
            self.status = GameStatus.NOT_STARTED
            return False
        return True

    def _validate_player_count(self, players: List[str], test_mode: bool) -> bool:
        """Validate player count for game start"""
        if not test_mode and len(players) < 2:
            self.logger.error("Need at least 2 players to start")
            self.status = GameStatus.NOT_STARTED
            return False

        if test_mode and len(players) < 1:
            self.logger.error("Need at least 1 player for test mode")
            self.status = GameStatus.NOT_STARTED
            return False

        return True

    def _spawn_simulated_player(
            self,
            near_player: str,
            distance: float = 20.0) -> bool:
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

            online_players_before = self.rcon.get_online_players()
            for player in online_players_before:
                if player.lower() == self.simulated_player_name.lower():
                    self.rcon.execute(f"player {player} kill")
                    time.sleep(0.5)

            # Use ~ for world-relative coordinates (not ^ which is rotation-relative)
            spawn_cmd = f"execute at {near_player} positioned ~{distance} ~ ~ run player {self.simulated_player_name} spawn"
            response = self.rcon.execute(spawn_cmd)

            if response and ("Unknown" not in response.lower(
            ) and "error" not in response.lower() and "does not exist" not in response.lower()):
                time.sleep(1.0)

                online_players = self.rcon.get_online_players()
                self.logger.debug(
                    f"Online players after spawn: {online_players}")

                actual_player_name = None
                for player in online_players:
                    if player.lower() == self.simulated_player_name.lower():
                        actual_player_name = player
                        break

                if actual_player_name:
                    # Carpet might use different case
                    self.simulated_player_name = actual_player_name
                    self.logger.info(
                        f"Updated simulated_player_name to match spawned player: '{self.simulated_player_name}'")

                    actual_pos = self._get_player_coordinates(
                        actual_player_name)
                    if actual_pos:
                        self.logger.info(
                            f"Spawned Carpet simulated player '{actual_player_name}' at actual position: {actual_pos}")
                        self.logger.info(
                            f"Expected position was: {spawn_pos}, player position: {player_pos}")
                        self.simulated_player_entity = None
                    else:
                        self.logger.warning(
                            f"Could not get coordinates for spawned player '{actual_player_name}'")
                        self.simulated_player_entity = None

                    if actual_player_name not in self.role_manager.roles:
                        self.role_manager.roles[actual_player_name] = Role.INNOCENT
                        self.alive_players.add(actual_player_name)
                        self.logger.info(
                            f"Added {actual_player_name} as simulated innocent")

                    if actual_pos and player_pos:
                        actual_distance = self._calculate_distance(
                            player_pos, actual_pos)
                        self.logger.info(
                            f"Actual spawn distance: {actual_distance:.1f}m (requested: {distance}m)")

                    self.notifications.tellraw(
                        near_player,
                        f"§aCarpet simulated player '{actual_player_name}' spawned!",
                        "green")
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
                still_online = any(
                    p.lower() == self.simulated_player_name.lower() for p in online_players_after)
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

    def _get_simulated_player_coordinates(
            self) -> Optional[Tuple[float, float, float]]:
        """Get coordinates of the simulated player entity (armor stand or Carpet simulated player)"""
        # First check if it's a Carpet simulated player (real player entity)
        online_players = self.rcon.get_online_players()
        self.logger.debug(
            f"_get_simulated_player_coordinates: online_players={online_players}, looking for '{self.simulated_player_name}'")
        if online_players:
            # First try exact match (should work since we update
            # simulated_player_name after spawn)
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
                    # It's a Carpet simulated player - get coordinates like a real
                    # player
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

    def start_game(
            self,
            test_mode: bool = False,
            test_player: Optional[str] = None,
            test_role: Optional[Role] = None,
            spawn_simulated_player: bool = False) -> bool:
        """Start a new game

        Args:
            test_mode: If True, allows starting with 1 player for testing
            test_player: If provided, assign this player the test_role
            test_role: Role to assign to test_player (TRAITOR or INNOCENT)
            spawn_simulated_player: If True, spawn a simulated player entity for testing
        """
        if not self._validate_game_not_in_progress():
            return False

        self.status = GameStatus.STARTING
        self.logger.info("Starting new mole hunt game...")

        if not self._validate_rcon_connection():
            return False
        players = self.rcon.get_online_players()
        if not self._validate_player_count(players, test_mode):
            return False

        self._teleport_players_to_spawn(players, spacing=10.0)

        if self.config.get("reset_skins_to_steve", False):
            self.skin_manager.reset_all_players(players)

        self._clear_all_inventories(players)
        self._heal_all_players(players)

        # Set all players to survival mode
        self._execute_command("gamemode survival @a")
        for player in players:
            self._execute_command(f"gamemode survival {player}")

        # Initialize alive players (check for spectators)
        self.alive_players = set()
        self.death_counts = {}
        for player in players:
            try:
                response = self.rcon.execute(
                    f"data get entity {player} playerGameType")
                if response and "No entity" not in response:
                    try:
                        gamemode_id = int(response.split()[-1])
                        if gamemode_id == 3:
                            pass  # Player is in spectator, don't add to alive
                        else:
                            self.alive_players.add(player)
                    except (ValueError, IndexError):
                        self.alive_players.add(player)
                else:
                    self.alive_players.add(player)
            except Exception as e:
                self.logger.debug(f"Could not get gamemode for {player}: {e}")
                self.alive_players.add(player)

            self.death_counts[player] = 0

        if test_mode:
            self._show_welcome_screen(players)
            self._execute_command("time set day")
            self._execute_command("weather clear")
            self._execute_command("gamerule doDaylightCycle true")
            self._execute_command("deathspectator setconfig enabled true")
            self.logger.info(
                "Set time to day, weather to clear, enabled daylight cycle, and enabled death spectator")
            for player in players:
                self._execute_command(f"effect clear {player}")
                self._execute_command(f"gamemode survival {player}")
        elif not self._countdown_and_start(players, countdown_seconds=10):
            self.status = GameStatus.NOT_STARTED
            return False

        if test_mode and test_player and test_role:
            self.role_manager.roles = {}
            for player in players:
                if player == test_player:
                    self.role_manager.roles[player] = test_role
                else:
                    self.role_manager.roles[player] = Role.INNOCENT if test_role == Role.TRAITOR else Role.TRAITOR
        else:
            self.role_manager.assign_roles(players)

        self.notifications.announce_game_start()

        # Inform players about PvP delay
        pvp_delay_seconds = self.config.get("pvp_delay_seconds", 60)
        self.notifications.tellraw_all(
            f"§cPvP will be enabled in {pvp_delay_seconds} seconds", "red")

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

        self._disable_chat(players)

        # Disable PvP at game start (will be re-enabled after configurable delay)
        self._disable_pvp()

        # Schedule PvP re-enable after delay
        pvp_delay_seconds = self.config.get("pvp_delay_seconds", 60)
        threading.Timer(pvp_delay_seconds, self._enable_pvp).start()

        # Set up world border (shrinking)
        self._setup_world_border()

        # Start timer
        self.timer_manager.start()

        # Always start monitoring thread to check win conditions
        # In test mode with single player, still start monitor if player is innocent (for time updates)
        # Also start if simulated player is spawned (to check win conditions)
        needs_monitoring = not (test_mode and len(players) == 1)
        if test_mode and len(players) == 1:
            if test_role == Role.INNOCENT:
                needs_monitoring = True  # Innocents need time updates
            elif spawn_simulated_player:
                needs_monitoring = True  # Need to check win conditions when simulated player dies

        # Start monitoring thread (always start if simulated player spawned, or
        # if player is innocent)
        if needs_monitoring:
            self.status = GameStatus.IN_PROGRESS
            self.monitor_running = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_game, daemon=False)
            self.monitor_thread.start()

            # Start player tracking thread (if enabled and not using mod)
            # Only start tracking if not in test mode with single innocent
            # (tracking is for traitors only)
            if not (test_mode and len(players) ==
                    1 and test_role == Role.INNOCENT):
                tracking_config = self.config.get("player_tracking", {})
                if tracking_config.get(
                        "enabled",
                        False) and not tracking_config.get(
                        "use_mod",
                        False):
                    self.tracking_running = True
                    self.tracking_thread = threading.Thread(
                        target=self._track_nearest_players, daemon=True)
                    self.tracking_thread.start()
                elif tracking_config.get("enabled", False) and tracking_config.get("use_mod", False):
                    pass  # Mod handles tracking, no thread needed
        else:
            self.status = GameStatus.IN_PROGRESS

            # In test mode, enable tracking if player is traitor
            # Use regular tracking if simulated player will be spawned (treats simulated player like real player)
            # Otherwise use test mode tracking
            tracking_config = self.config.get("player_tracking", {})
            if (test_mode and test_role == Role.TRAITOR and tracking_config.get(
                    "enabled", False) and not tracking_config.get("use_mod", False)):
                self.tracking_running = True
                # If we're spawning a simulated player, use regular tracking
                # (treats simulated player like real player)
                if spawn_simulated_player:
                    self.tracking_thread = threading.Thread(
                        target=self._track_nearest_players, daemon=True)
                else:
                    self.tracking_thread = threading.Thread(
                        target=self._track_nearest_players_test_mode, daemon=True)
                self.tracking_thread.start()
                # Give thread a moment to start
                time.sleep(0.5)
            elif (test_mode and len(players) == 1 and test_role == Role.TRAITOR and
                    tracking_config.get("enabled", False) and tracking_config.get("use_mod", False)):
                pass  # Mod handles tracking, no thread needed

        # Spawn simulated player if requested in test mode
        if test_mode and spawn_simulated_player and len(players) == 1:
            if self._spawn_simulated_player(players[0], distance=10.0):
                pass
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

        players = self.rcon.get_online_players()

        for player in players:
            self.abilities.clear_all_effects(player)

        traitors = self.role_manager.get_traitors()
        self.abilities.remove_finder_items(traitors)

        self._remove_simulated_player()

        self.skin_manager.restore_original_skins()

        # Set all players to survival mode
        self._execute_command("gamemode survival @a")
        players = self.rcon.get_online_players()
        for player in players:
            self._execute_command(f"gamemode survival {player}")

        # Set time to day and disable daylight cycle
        self._execute_command("time set day")
        self._execute_command("gamerule doDaylightCycle false")
        self._execute_command("deathspectator setconfig enabled false")

        self._enable_chat()
        self._heal_all_players(players)

        # Clean up death scoreboard if it exists
        # Scoreboard might not exist, ignore error
        self._execute_command("scoreboard objectives remove deaths")

        # Reset state
        self.role_manager.reset()
        self.timer_manager.reset()
        self.status = GameStatus.ENDED
        self.alive_players.clear()
        self.death_counts.clear()
        self.pending_deaths.clear()

        self.notifications.tellraw_all("§7Game stopped by admin", "gray")
        self.logger.info("Game stopped")

    def _get_player_coordinates(
            self, player: str, retry: bool = True) -> Optional[Tuple[float, float, float]]:
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
                # Look for the pattern: [numberd, numberd, numberd]
                # (coordinates always have 'd' suffix)
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
                    # Fallback: try to find all numbers with 'd' suffix
                    # (coordinates)
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

    def _calculate_distance(self,
                            pos1: Tuple[float,
                                        float,
                                        float],
                            pos2: Tuple[float,
                                        float,
                                        float]) -> float:
        """Calculate 3D distance between two positions"""
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        dz = pos1[2] - pos2[2]
        return (dx**2 + dy**2 + dz**2) ** 0.5

    def _calculate_direction(self,
                             traitor_pos: Tuple[float,
                                                float,
                                                float],
                             target_pos: Tuple[float,
                                               float,
                                               float]) -> str:
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

                traitors = self.role_manager.get_traitors()
                innocents = self.role_manager.get_innocents()
                self.logger.debug(
                    f"Traitors: {traitors}, Innocents: {innocents}")

                online_players = self.rcon.get_online_players()

                # If RCON failed, online_players will be empty list - skip this
                # iteration
                if not online_players:
                    self.logger.warning(
                        "No online players found (RCON may have failed), skipping tracking update")
                    time.sleep(update_interval)
                    continue

                # Get alive traitors and innocents
                # Include simulated player if it exists (check both case
                # variations)
                alive_traitors = [
                    t for t in traitors if t in self.alive_players and t in online_players]
                alive_innocents = [
                    i for i in innocents if i in self.alive_players and i in online_players]

                # Also check for simulated player - treat it exactly like a real player
                # Find the actual player name (case-insensitive match) and add
                # it to innocents
                if self.simulated_player_name:
                    simulated_found = False
                    # First check if it's already in alive_innocents (exact
                    # match)
                    for innocent in alive_innocents:
                        if innocent.lower() == self.simulated_player_name.lower():
                            simulated_found = True
                            self.logger.debug(
                                f"Simulated player '{self.simulated_player_name}' already in alive_innocents as '{innocent}'")
                            break

                    # If not found, check online players for case-insensitive
                    # match
                    if not simulated_found:
                        for player in online_players:
                            if player.lower() == self.simulated_player_name.lower():
                                # Found simulated player - add it with its
                                # actual name
                                if player in self.alive_players:
                                    alive_innocents.append(player)
                                else:
                                    # Simulated player is online but not in alive_players - add it now
                                    # This handles the case where spawn command
                                    # appeared to fail but player actually
                                    # spawned
                                    if player not in self.role_manager.roles:
                                        self.role_manager.roles[player] = Role.INNOCENT
                                    self.alive_players.add(player)
                                    alive_innocents.append(player)
                                break

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

                        if show_distance:
                            if direction:
                                message = f"{time_str}§c§lNearest: §r§e{nearest_innocent} §7({nearest_distance:.0f}m) §6{direction}"
                            else:
                                message = f"{time_str}§c§lNearest: §r§e{nearest_innocent} §7({nearest_distance:.0f}m)"
                            self.notifications.actionbar(traitor, message)
                        else:
                            message = f"{time_str}§c§lNearest: §r§e{nearest_innocent}"
                            self.notifications.actionbar(traitor, message)
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
        # Send initial test message to confirm tracking is working
        self.notifications.actionbar(traitor, "§a§lTracking Active!")
        time.sleep(1)

        loop_count = 0
        while self.tracking_running and self.status == GameStatus.IN_PROGRESS:
            try:
                loop_count += 1

                traitor_pos = self._get_player_coordinates(traitor)
                if not traitor_pos:
                    self.logger.warning(
                        f"Could not get coordinates for {traitor} - retrying...")
                    time.sleep(update_interval)
                    continue

                # Check if we have a simulated player (armor stand or Carpet
                # player)
                simulated_pos = self._get_simulated_player_coordinates()
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

    def _monitor_game(self):
        """Monitor game state and check win conditions"""
        last_time_update = 0
        last_win_check = 0
        # Get time update interval from config (default: 3 seconds)
        time_update_interval = self.config.get(
            "time_update_interval_seconds", 3)
        # Check win conditions every 1 second (frequent enough for death detection)
        win_check_interval = 1.0

        while self.monitor_running and self.status == GameStatus.IN_PROGRESS:
            try:
                current_time = time.time()

                # Check win conditions less frequently to reduce RCON overhead
                if current_time - last_win_check >= win_check_interval:
                    self._check_deaths()
                    # Pass alive players to win checker - check immediately
                    # after death processing
                    result = self.win_checker.check_win_conditions(
                        self.alive_players)
                    last_win_check = current_time
                else:
                    # Check win conditions
                    result = self.win_checker.check_win_conditions()

                # Check if win condition was detected (regardless of which branch)
                if result:
                    winner, reason = result
                    self.logger.info(
                        f"Win condition detected: {winner} wins - {reason}. Ending game...")
                    try:
                        self._end_game(winner, reason)
                    except Exception as e:
                        self.logger.error(
                            f"Error ending game: {e}", exc_info=True)
                    break

                # Send time updates via actionbar at configured interval (only
                # to innocents, traitors get it with position updates)
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
                # Use the smaller of time_update_interval or 1.0 seconds for
                # responsive checking
                sleep_time = min(time_update_interval, 1.0)
                time.sleep(sleep_time)
            except Exception as e:
                self.logger.error(f"Error in monitor thread: {e}")
                # Sleep briefly on error, but still allow frequent updates
                sleep_time = min(time_update_interval, 1.0)
                time.sleep(sleep_time)

    def _check_deaths(self):
        """Check for player deaths by checking if players are in spectator mode."""
        try:
            online_players = set(self.rcon.get_online_players())
            current_time = time.time()
            # Wait 0.5 seconds before confirming death (prevents false positives)
            verification_delay = 0.5

            # Log alive counts
            alive_traitors = [
                p for p in self.role_manager.get_traitors() if p in self.alive_players]
            alive_innocents = [
                p for p in self.role_manager.get_innocents() if p in self.alive_players]
            self.logger.info(
                f"Death check: {len(self.alive_players)} alive players ({len(alive_traitors)} traitors, {len(alive_innocents)} innocents)")

            # Remove players who disconnected from alive list
            disconnected = self.alive_players - online_players
            for player in disconnected:
                self.alive_players.discard(player)
                # Clear pending death if disconnected
                self.pending_deaths.pop(player, None)

            # Check all online players (not just those in alive_players)
            # This ensures we catch players who should be alive but aren't tracked
            for player in online_players:
                try:
                    # Check player's gamemode
                    response = self.rcon.execute(
                        f"data get entity {player} playerGameType")
                    if response and "No entity" not in response:
                        try:
                            gamemode_id = int(response.split()[-1])
                            # Check if this is a simulated player
                            is_simulated = (self.simulated_player_name and
                                            player.lower() == self.simulated_player_name.lower())

                            # 3 = spectator mode
                            if gamemode_id == 3:
                                # Player is in spectator mode
                                # For simulated players or players in alive_players, process death
                                if player in self.alive_players or is_simulated:
                                    # Check if this is a new potential death or a confirmed one
                                    if player not in self.pending_deaths:
                                        # First time detecting spectator mode - mark as pending
                                        self.pending_deaths[player] = current_time
                                        self.logger.info(
                                            f"Potential death detected for {player} (in spectator mode, verifying...)")
                                    else:
                                        # Check if enough time has passed to confirm death
                                        time_since_detection = current_time - \
                                            self.pending_deaths[player]
                                        if time_since_detection >= verification_delay:
                                            # Death confirmed - player has been in spectator for verification period
                                            self.alive_players.discard(player)
                                            self.death_counts[player] = 1
                                            self.pending_deaths.pop(
                                                player, None)

                                            self.logger.info(
                                                f"Death confirmed: {player} has been in spectator mode for {time_since_detection:.1f} seconds")

                                            # Notify player (skip for simulated players)
                                            if not is_simulated:
                                                self.notifications.tellraw(
                                                    player, f"§cYou died!", "red")
                                            # Notify all players
                                            self.notifications.tellraw_all(
                                                f"§7{player} has been eliminated!", "gray")

                                            # ALWAYS check win conditions immediately after sending death notification
                                            self.logger.info(
                                                f"Checking win conditions after {player}'s death. Alive players: {self.alive_players}")
                                            result = self.win_checker.check_win_conditions(
                                                self.alive_players)
                                            self.logger.info(
                                                f"Win condition check result: {result}")

                                            if result:
                                                winner, reason = result
                                                self.logger.info(
                                                    f"Win condition detected after {player}'s death: {winner} wins - {reason}")
                                                # End game in a separate thread to avoid blocking
                                                threading.Thread(target=lambda: self._end_game(
                                                    winner, reason), daemon=True).start()
                                                return  # Exit early since game is ending
                                            else:
                                                self.logger.debug(
                                                    f"No win condition met after {player}'s death. Game continues.")
                            else:
                                # Player is NOT in spectator mode
                                # Clear any pending death if they're no longer in spectator
                                if player in self.pending_deaths:
                                    self.pending_deaths.pop(player, None)
                                    self.logger.debug(
                                        f"Cleared pending death for {player} (no longer in spectator)")

                                # Ensure they're in alive_players (if they were part of the game OR are simulated player)
                                if (player in self.death_counts or is_simulated) and player not in self.alive_players:
                                    self.alive_players.add(player)
                                    self.logger.debug(
                                        f"Added {player} back to alive_players (not in spectator)")
                        except (ValueError, IndexError) as e:
                            self.logger.debug(
                                f"Error parsing gamemode for {player}: {response} - {e}")
                except Exception as e:
                    self.logger.debug(
                        f"Error checking gamemode for {player}: {e}")

        except Exception as e:
            self.logger.error(f"Error checking deaths: {e}")

    def _clear_all_inventories(self, players: List[str]):
        """Clear all players' inventories at game start"""
        try:
            for player in players:
                self.rcon.execute(f"clear {player}")
            self.logger.info(
                f"Cleared inventories for {len(players)} player(s)")
        except Exception as e:
            self.logger.warning(f"Error clearing inventories: {e}")

    def _heal_all_players(self, players: List[str]):
        """Heal all players to full health and saturation at game start"""
        try:
            # Try using attribute command first (more reliable)
            try:
                self.rcon.execute(
                    "attribute @a minecraft:generic.max_health base set 20")
                self.rcon.execute(
                    "attribute @a minecraft:generic.health base set 20")
            except BaseException:
                # Fallback to effect method
                pass

            # Apply instant_health multiple times with reasonable amplifier
            # Amplifier 5 = level 6 instant health, which heals 12 hearts
            for _ in range(2):  # Apply twice to ensure full healing
                self.rcon.execute(
                    "effect give @a minecraft:instant_health 1 5 true")

            # Restore hunger/saturation
            self.rcon.execute(
                "effect give @a minecraft:saturation 10 255 true")
            self.logger.info(
                f"Healed {len(players)} player(s) to full health and saturation")
        except Exception as e:
            self.logger.warning(f"Error healing players: {e}")

    def _reset_health_and_hunger(self):
        """Reset health and hunger for all players at end of game"""
        try:
            # Try using attribute command first (more reliable)
            try:
                self.rcon.execute(
                    "attribute @a minecraft:generic.max_health base set 20")
                self.rcon.execute(
                    "attribute @a minecraft:generic.health base set 20")
            except BaseException:
                # Fallback to effect method
                pass

            # Apply instant_health multiple times with reasonable amplifier
            # Amplifier 5 = level 6 instant health, which heals 12 hearts
            for _ in range(2):  # Apply twice to ensure full healing
                self.rcon.execute(
                    "effect give @a minecraft:instant_health 1 5 true")

            # Reset hunger/saturation to full for all players
            self.rcon.execute(
                "effect give @a minecraft:saturation 10 255 true")
        except Exception as e:
            self.logger.warning(f"Error resetting health and hunger: {e}")

    def _setup_world_border(self):
        """Set up a shrinking world border for the game"""
        try:
            world_border_config = self.config.get("world_border", {})
            if not world_border_config.get("enabled", False):
                return

            initial_size = world_border_config.get("initial_size", 2000)
            final_size = world_border_config.get("final_size", 100)
            center_x = world_border_config.get("center_x", 0)
            center_z = world_border_config.get("center_z", 0)
            delay_before_shrink_minutes = world_border_config.get(
                "delay_before_shrink_minutes", 10)

            # Get game duration
            game_duration_minutes = self.config.get(
                "game_duration_minutes", 30)

            # Calculate shrink duration accounting for delay and 5-minute buffer
            # Shrink should finish 5 minutes before game ends
            # Available time = game_duration - delay - 5_min_buffer
            available_shrink_time = max(
                1, game_duration_minutes - delay_before_shrink_minutes - 5)

            # Get shrink duration - ensure it finishes at least 5 minutes
            # before game ends
            shrink_duration_minutes = world_border_config.get(
                "shrink_duration_minutes")
            if shrink_duration_minutes is None:
                # Use all available time (game duration - delay - 5 min buffer)
                shrink_duration_minutes = available_shrink_time
            else:
                # If specified, ensure it doesn't exceed available time
                shrink_duration_minutes = min(
                    shrink_duration_minutes, available_shrink_time)

            # Calculate shrink speed and ensure it doesn't exceed player running speed
            # Minecraft world border "size" is diameter, so radius change is (initial - final) / 2
            # Player sprinting speed is ~5.6 blocks/second, use 5 blocks/second
            # as safe maximum
            max_shrink_speed_blocks_per_second = 5.0

            total_shrink_distance = (
                initial_size - final_size) / 2  # Radius change
            shrink_time_seconds = shrink_duration_minutes * 60
            shrink_speed = total_shrink_distance / \
                shrink_time_seconds if shrink_time_seconds > 0 else 0

            # If shrink speed is too fast, increase the duration to slow it
            # down
            if shrink_speed > max_shrink_speed_blocks_per_second:
                # Calculate minimum time needed at safe speed
                min_time_seconds = total_shrink_distance / max_shrink_speed_blocks_per_second
                min_time_minutes = min_time_seconds / 60

                # Use the longer of: configured time or minimum safe time
                shrink_duration_minutes = max(
                    shrink_duration_minutes, min_time_minutes)
                shrink_time_seconds = shrink_duration_minutes * 60

                # Recalculate actual speed
                shrink_speed = total_shrink_distance / \
                    shrink_time_seconds if shrink_time_seconds > 0 else 0

                self.logger.info(
                    f"Adjusted shrink duration to {shrink_duration_minutes:.2f} minutes "
                    f"to keep speed at {shrink_speed:.2f} blocks/second (max: {max_shrink_speed_blocks_per_second} blocks/second)")

            delay_seconds = delay_before_shrink_minutes * 60

            # Set world border center
            self.rcon.execute(f"worldborder center {center_x} {center_z}")

            # Set initial size immediately (no shrinking yet)
            self.rcon.execute(f"worldborder set {initial_size}")

            # Schedule the shrink to start after the delay
            def start_shrink():
                try:
                    # Set the world border to shrink from initial_size to
                    # final_size
                    self.rcon.execute(
                        f"worldborder set {final_size} {shrink_time_seconds}")
                    self.logger.info(
                        f"World border started shrinking: {initial_size} blocks → {final_size} blocks over {shrink_duration_minutes} minutes")

                    # Announce to all players that the border is starting to
                    # shrink
                    try:
                        players = self.rcon.get_online_players()
                        for player in players:
                            try:
                                self.rcon.execute(
                                    f"title {player} times 0 60 20")
                                self.rcon.execute(
                                    f"title {player} title {{\"text\":\"§c§lWORLD BORDER SHRINKING\",\"bold\":true}}")
                                self.rcon.execute(
                                    f"title {player} subtitle {{\"text\":\"§7The border is closing in!\",\"bold\":false}}")
                            except Exception as e:
                                self.logger.debug(
                                    f"Could not send title to {player}: {e}")

                        self.notifications.tellraw_all(
                            "§c§l⚠ WORLD BORDER SHRINKING ⚠", "red")
                        self.notifications.tellraw_all(
                            f"§7The world border is now shrinking from §e{initial_size}§7 blocks to §e{final_size}§7 blocks",
                            "yellow")
                        self.notifications.tellraw_all(
                            f"§7Shrinking over §e{shrink_duration_minutes}§7 minutes at §e{shrink_speed:.2f}§7 blocks/second",
                            "yellow")
                    except Exception as e:
                        self.logger.warning(
                            f"Could not announce world border shrink: {e}")
                except Exception as e:
                    self.logger.warning(
                        f"Error starting world border shrink: {e}")

            # Start shrinking after delay
            shrink_timer = threading.Timer(delay_seconds, start_shrink)
            shrink_timer.daemon = True
            shrink_timer.start()

            finish_time = delay_before_shrink_minutes + shrink_duration_minutes
            self.logger.info(
                f"World border set: {initial_size} blocks (initial), will start shrinking after {delay_before_shrink_minutes} minutes, then shrink to {final_size} blocks over {shrink_duration_minutes} minutes (finishes at {finish_time} minutes, {game_duration_minutes - finish_time} minutes before game end)")
        except Exception as e:
            self.logger.warning(f"Error setting up world border: {e}")

    def _reset_world_border(self):
        """Reset world border to default settings"""
        try:
            # Reset to a large size (default is 29,999,984 blocks)
            self.rcon.execute("worldborder set 29999984")
            self.rcon.execute("worldborder center 0 0")
            self.logger.info("World border reset to default")
        except Exception as e:
            self.logger.warning(f"Error resetting world border: {e}")

    def _disable_pvp(self):
        """Disable PvP at game start using high resistance effect"""
        players = self.rcon.get_online_players()
        for player in players:
            # Give resistance level 5 (100% damage reduction) for a very long duration
            self._execute_command(
                f"effect give {player} minecraft:resistance 999999 5 true")
        pvp_delay_seconds = self.config.get("pvp_delay_seconds", 60)
        self.logger.info(
            f"PvP disabled via resistance effect for {len(players)} player(s) (will be re-enabled in {pvp_delay_seconds} seconds)")

    def _enable_pvp(self):
        """Re-enable PvP after delay by removing resistance effect"""
        players = self.rcon.get_online_players()
        for player in players:
            self._execute_command(
                f"effect clear {player} minecraft:resistance")
        self.notifications.tellraw_all(
            "§c§lPvP ENABLED §7- Players can now attack each other!", "red")
        self.logger.info(
            f"PvP enabled (removed resistance effect from {len(players)} player(s))")

    def _teleport_players_to_spawn(
            self,
            players: List[str],
            spacing: float = 10.0):
        """Teleport all players to the exact spawn location"""
        try:
            # Get spawn coordinates from config, or try to get world spawn
            spawn_config = self.config.get("spawn_point", {})
            spawn_x = spawn_config.get("x")
            spawn_y = spawn_config.get("y")
            spawn_z = spawn_config.get("z")

            # If not configured, try to get world spawn point
            if spawn_x is None or spawn_y is None or spawn_z is None:
                # Default to 0, 100, 0 if can't determine
                spawn_x, spawn_y, spawn_z = 0, 100, 0

                # Try to get world spawn by checking a marker entity or using
                # world spawn
                try:
                    # Try to get spawn using a temporary marker entity
                    # First, try to get spawn from world data (not directly accessible via RCON)
                    # Instead, use the world border center if it's been set, or
                    # default
                    world_border_config = self.config.get("world_border", {})
                    if world_border_config.get("center_x") is not None and world_border_config.get(
                            "center_z") is not None:
                        # Use world border center as spawn (common pattern)
                        spawn_x = world_border_config.get("center_x", 0)
                        spawn_z = world_border_config.get("center_z", 0)
                        spawn_y = 100  # Default Y level
                        self.logger.info(
                            f"Using world border center as spawn: {spawn_x}, {spawn_y}, {spawn_z}")
                    else:
                        # Try to get spawn by checking where players respawn
                        # Use a temporary approach: get first player's spawn
                        # point
                        if players:
                            try:
                                # Get player's spawn point (where they respawn)
                                response = self.rcon.execute(
                                    f"data get entity {players[0]} SpawnPos")
                                if response and "SpawnPos:" in response:
                                    coords = re.findall(
                                        r'([-\d.]+)d', response)
                                    if len(coords) >= 3:
                                        spawn_x = float(coords[0])
                                        spawn_y = float(coords[1])
                                        spawn_z = float(coords[2])
                                        self.logger.info(
                                            f"Got spawn from player spawn point: {spawn_x}, {spawn_y}, {spawn_z}")
                            except Exception:
                                pass
                except Exception as e:
                    self.logger.debug(
                        f"Could not get spawn coordinates, using default: {e}")
            else:
                self.logger.info(
                    f"Using configured spawn point: {spawn_x}, {spawn_y}, {spawn_z}")

            # Teleport all players to the exact same spawn location
            num_players = len(players)
            for i, player in enumerate(players):
                # All players go to the exact same spawn location
                x, y, z = spawn_x, spawn_y, spawn_z

                # Teleport player
                try:
                    self.rcon.execute(f"tp {player} {x} {y} {z}")
                    self.logger.debug(f"Teleported {player} to {x}, {y}, {z}")
                except Exception as e:
                    self.logger.warning(f"Could not teleport {player}: {e}")

            self.logger.info(
                f"Teleported {num_players} player(s) to spawn")
        except Exception as e:
            self.logger.warning(f"Error teleporting players to spawn: {e}")

    def _show_welcome_screen(self, players: List[str]):
        """Show welcome screen before countdown"""
        for player in players:
            # Show welcome title with longer display time
            self._execute_command(f"title {player} times 0 80 20")
            self._execute_command(
                f"title {player} title {{\"text\":\"§6§lMOLE HUNT\",\"bold\":true}}")
            self._execute_command(
                f"title {player} subtitle {{\"text\":\"§7Prepare for the game!\",\"bold\":false}}")

        self.notifications.tellraw_all("§6=== MOLE HUNT ===", "gold")
        self.notifications.tellraw_all(
            "§7Welcome! The game will begin shortly...", "yellow")
        pvp_delay_seconds = self.config.get("pvp_delay_seconds", 60)
        self.notifications.tellraw_all(
            f"§cPvP will be enabled in {pvp_delay_seconds} seconds", "red")
        # Show welcome screen for 5 seconds to ensure it's visible
        time.sleep(5)

    def _countdown_and_start(
            self,
            players: List[str],
            countdown_seconds: int = 30):
        """Perform countdown, prevent movement/block breaking, then start the game"""
        try:
            # Show welcome screen first
            self._show_welcome_screen(players)

            # Set time to day, weather to clear, enable daylight cycle, and enable death spectator
            self._execute_command("time set day")
            self._execute_command("weather clear")
            self._execute_command("gamerule doDaylightCycle true")
            self._execute_command("deathspectator setconfig enabled true")
            self.logger.info(
                "Set time to day, weather to clear, enabled daylight cycle, and enabled death spectator")

            # Store player positions to freeze them in place
            player_positions = {}
            for player in players:
                try:
                    # Get current player position
                    pos = self._get_player_coordinates(player)
                    if pos:
                        player_positions[player] = pos
                        self.logger.debug(
                            f"Stored position for {player}: {pos}")
                except Exception as e:
                    self.logger.warning(
                        f"Could not get position for {player}: {e}")

            # Set all players to adventure mode (prevents block breaking)
            # Add effects to prevent movement and damage
            for player in players:
                try:
                    self.rcon.execute(f"gamemode adventure {player}")
                    # Add very high slowness to prevent horizontal movement
                    # (level 255 = maximum)
                    self.rcon.execute(
                        f"effect give {player} minecraft:slowness 1000000 255 true")
                    # Add resistance level 255 to make players immune to damage
                    self.rcon.execute(
                        f"effect give {player} minecraft:resistance 1000000 255 true")
                except Exception as e:
                    self.logger.warning(
                        f"Could not set {player} to adventure mode or apply effects: {e}")

            # Countdown loop
            for remaining in range(countdown_seconds, 0, -1):
                if self.status != GameStatus.STARTING:
                    # Game was cancelled
                    return False

                # Freeze players in place by teleporting them back to their
                # stored positions
                for player, pos in player_positions.items():
                    try:
                        self.rcon.execute(
                            f"tp {player} {pos[0]} {pos[1]} {pos[2]}")
                    except Exception as e:
                        self.logger.debug(
                            f"Could not freeze {player} in place: {e}")

                # Show countdown every 10 seconds, or every second in last 10
                # seconds
                if remaining % 10 == 0 or remaining <= 10:
                    minutes = remaining // 60
                    seconds = remaining % 60
                    if minutes > 0:
                        time_str = f"{minutes}:{seconds:02d}"
                    else:
                        time_str = str(seconds)

                    # Title and actionbar countdown
                    for player in players:
                        try:
                            self.rcon.execute(f"title {player} times 5 40 5")
                            self.rcon.execute(
                                f"title {player} title {{\"text\":\"§6{time_str}\",\"bold\":true}}")
                            if remaining <= 10:
                                self.rcon.execute(
                                    f"title {player} subtitle {{\"text\":\"§7Game starting soon!\",\"bold\":false}}")
                        except Exception as e:
                            self.logger.debug(
                                f"Could not send title to {player}: {e}")

                    # Chat message for longer intervals
                    if remaining % 30 == 0 or remaining <= 10:
                        self.notifications.tellraw_all(
                            f"§6Game starting in §e{time_str}§6...", "yellow")

                time.sleep(1)

            # Final "GO!" message
            for player in players:
                try:
                    self.rcon.execute(f"title {player} times 0 60 20")
                    self.rcon.execute(
                        f"title {player} title {{\"text\":\"§a§lGO!\",\"bold\":true}}")
                    self.rcon.execute(
                        f"title {player} subtitle {{\"text\":\"§7Game has begun!\",\"bold\":false}}")
                except Exception as e:
                    self.logger.debug(
                        f"Could not send GO title to {player}: {e}")

            self.notifications.tellraw_all("§a§lGAME STARTED!", "green")

            # Enable daylight cycle and death spectator at game start
            self._execute_command("gamerule doDaylightCycle true")
            self._execute_command("deathspectator setconfig enabled true")
            self.logger.info("Enabled daylight cycle and death spectator")

            # Restore survival mode and clear effects to allow movement
            for player in players:
                try:
                    # Clear all effects (removes slowness)
                    self.rcon.execute(f"effect clear {player}")
                    # Set to survival mode to allow movement and block breaking
                    self.rcon.execute(f"gamemode survival {player}")
                except Exception as e:
                    self.logger.warning(
                        f"Could not restore gamemode/clear effects for {player}: {e}")

            return True
        except Exception as e:
            self.logger.warning(f"Error during countdown: {e}")
            return False

    def _disable_chat(self, players: List[str]):
        """Disable chat for all players using FTB Essentials mute"""
        try:
            # FTB Essentials requires muting each player individually
            muted_count = 0
            for player in players:
                try:
                    response = self.rcon.execute(f"mute {player}")
                    if response and "unknown" not in response.lower() and "error" not in response.lower():
                        self.logger.debug(
                            f"Muted {player} using FTB Essentials")
                        muted_count += 1
                    else:
                        self.logger.warning(
                            f"FTB Essentials mute failed for {player}: {response}")
                except Exception as e:
                    self.logger.warning(
                        f"Error muting {player} with FTB Essentials: {e}")

            if muted_count > 0:
                self.logger.info(
                    f"Disabled chat using FTB Essentials: muted {muted_count}/{len(players)} player(s)")
                self.chat_disabled = True
            else:
                self.logger.error(
                    "Failed to mute any players with FTB Essentials")

        except Exception as e:
            self.logger.error(f"Could not disable chat: {e}")

    def _enable_chat(self):
        """Re-enable chat for all players using FTB Essentials unmute"""
        if not self.chat_disabled:
            return

        try:
            # FTB Essentials requires unmuting each player individually
            online_players = self.rcon.get_online_players()
            unmuted_count = 0
            for player in online_players:
                try:
                    response = self.rcon.execute(f"unmute {player}")
                    if response and "unknown" not in response.lower() and "error" not in response.lower():
                        self.logger.debug(
                            f"Unmuted {player} using FTB Essentials")
                        unmuted_count += 1
                    else:
                        self.logger.debug(
                            f"FTB Essentials unmute response for {player}: {response}")
                except Exception as e:
                    self.logger.warning(
                        f"Error unmuting {player} with FTB Essentials: {e}")

            if unmuted_count > 0:
                self.logger.info(
                    f"Enabled chat using FTB Essentials: unmuted {unmuted_count}/{len(online_players)} player(s)")
                self.chat_disabled = False
            else:
                self.logger.error(
                    "Failed to unmute any players with FTB Essentials")

        except Exception as e:
            self.logger.error(f"Could not enable chat: {e}")

    def _end_game(self, winner: str, reason: str):
        """End the game"""
        # Use a lock to ensure only one thread can execute end game logic
        self.logger.info(
            f"_end_game called (before lock) with winner={winner}, reason={reason}, current_status={self.status}")
        with self._end_game_lock:

            # If already announced, skip (regardless of status)
            if self._game_ended_announced:
                self.logger.warning(
                    "Game end already announced, skipping duplicate call")
                return

            # If status is already ENDED but not announced, we still need to announce
            # (this handles the case where status was set but announcement failed)
            # Only skip if status is ENDED AND already announced
            if self.status == GameStatus.ENDED and self._game_ended_announced:
                self.logger.warning(
                    "Status is ENDED and already announced, skipping")
                return

            # Mark as ended first to prevent other threads from proceeding
            was_in_progress = (self.status == GameStatus.IN_PROGRESS)
            if not was_in_progress and self.status != GameStatus.ENDED:
                self.logger.warning(
                    f"Game was not in progress (status={self.status}), but proceeding anyway")

            # Only set status if not already ENDED (to avoid overwriting)
            if self.status != GameStatus.ENDED:
                self.status = GameStatus.ENDED
                self.monitor_running = False
                self.tracking_running = False
            else:
                self.logger.info(
                    f"Game status already ENDED, continuing with announcement")

            players = self.rcon.get_online_players()
            self._teleport_players_to_spawn(players, spacing=10.0)

            self.logger.info(
                "Setting all players to survival mode after teleport")
            self._execute_command("gamemode survival @a")
            for player in players:
                self._execute_command(f"gamemode survival {player}")

            try:
                time.sleep(1.5)
            except Exception as e:
                self.logger.error(f"Error during sleep: {e}", exc_info=True)

            announcement_sent = False
            try:
                self.notifications.announce_game_end(winner, reason)
                announcement_sent = True
                self._game_ended_announced = True
            except Exception as e:
                self.logger.error(
                    f"Error sending game end announcement: {e}", exc_info=True)
                # Try to send at least a simple message if the full announcement fails
                try:
                    self.notifications.tellraw_all(
                        f"§6GAME ENDED: {winner} won - {reason}", "gold")
                    announcement_sent = True
                    self._game_ended_announced = True
                except Exception as e2:
                    self.logger.error(
                        f"Even fallback message failed: {e2}", exc_info=True)

            if not announcement_sent:
                self.logger.error(
                    "CRITICAL: Game end announcement was NOT sent! Attempting direct RCON commands...")
                try:
                    # Try direct RCON commands as last resort
                    self.rcon.execute(
                        f'tellraw @a {{"text":"§6GAME ENDED: {winner} won - {reason}","color":"gold"}}')
                    self._game_ended_announced = True
                except Exception as e3:
                    self.logger.error(
                        f"Direct RCON message also failed: {e3}", exc_info=True)

            time.sleep(2)

            self.notifications.tellraw_all("§6=== ROLE REVEAL ===", "gold")
            traitors = self.role_manager.get_traitors()
            innocents = self.role_manager.get_innocents()

            self.notifications.tellraw_all(
                f"§4Traitors: §7{', '.join(traitors)}", "red")
            self.notifications.tellraw_all(
                f"§aInnocents: §7{', '.join(innocents)}", "green")

            self.logger.info(f"Game ended: {winner} won - {reason}")

            delay_seconds = self.config.get("end_game_delay_seconds", 3)
            self.notifications.tellraw_all(
                f"§7Cleanup will begin in {delay_seconds} seconds...", "gray")
            time.sleep(delay_seconds)

        def cleanup_then_delay():
            if self._execute_command("clear @a"):
                self.logger.info("Cleared all inventories")

            current_players = self.rcon.get_online_players()

            for player in current_players:
                self._execute_command(f"effect clear {player}")

            traitors = self.role_manager.get_traitors()
            self.abilities.remove_finder_items(traitors)

            self._remove_simulated_player()
            self.skin_manager.restore_original_skins()

            # Gamemodes already set to survival after teleport, but verify here
            # (gamemodes were set immediately after teleport, so this is just a safety check)
            try:
                current_players = self.rcon.get_online_players()
                for player in current_players:
                    try:
                        response = self.rcon.execute(
                            f"data get entity {player} playerGameType")
                        if response and "No entity" not in response:
                            try:
                                gamemode_id = int(response.split()[-1])
                                if gamemode_id == 3:  # Still in spectator
                                    self.logger.warning(
                                        f"{player} still in spectator during cleanup, forcing survival")
                                    self.rcon.execute(
                                        f"gamemode survival {player}")
                            except (ValueError, IndexError):
                                pass
                    except Exception:
                        pass
            except Exception as e:
                self.logger.warning(
                    f"Error verifying gamemodes during cleanup: {e}")

            # Set time to day and disable daylight cycle
            self._execute_command("time set day")
            self._execute_command("gamerule doDaylightCycle false")
            self._execute_command("deathspectator setconfig enabled false")
            self.logger.info(
                "Set time to day and disabled daylight cycle and death spectator")

            self._enable_chat()
            self._reset_world_border()

            # Remove resistance effect from all players at game end
            current_players = self.rcon.get_online_players()
            for player in current_players:
                self._execute_command(
                    f"effect clear {player} minecraft:resistance")
            if current_players:
                self.logger.info(
                    f"Removed resistance effect from {len(current_players)} player(s) at game end")

            self._reset_health_and_hunger()

        # Run cleanup then delay in a separate thread
        cleanup_thread = threading.Thread(
            target=cleanup_then_delay, daemon=False)
        cleanup_thread.start()
        self.cleanup_thread = cleanup_thread

        # Reset after a delay (delay_seconds + 20 more seconds)
        threading.Timer(delay_seconds + 20.0, self._reset_game).start()

    def _reset_game(self):
        """Reset game state"""
        self.role_manager.reset()
        self.timer_manager.reset()
        self.status = GameStatus.NOT_STARTED
        self.logger.info("Game reset")
