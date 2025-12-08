"""
Role manager for Mole Hunt game
"""

import logging
import random
from typing import Dict, List, Optional

from .role import Role


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
