"""
Traitor abilities manager for Mole Hunt game
"""

import logging
from typing import List

from game_engine.rcon_client import RCONClient


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
        # Modern Player Finder is command-based, not item-based, so nothing to
        # remove
        pass
