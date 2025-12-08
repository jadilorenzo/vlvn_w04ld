"""
Skin manager for Mole Hunt game
"""

import logging
from typing import List

from game_engine.rcon_client import RCONClient


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

                # Check if command succeeded (response should not contain error
                # keywords)
                if response:
                    response_lower = response.lower()
                    # Success indicators: no error keywords, might have success
                    # message
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

