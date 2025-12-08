"""
Win condition checker for Mole Hunt game
"""

import logging
from typing import Optional, Tuple

from game_engine.rcon_client import RCONClient
from game_engine.timer_manager import TimerManager
from .role_manager import RoleManager


class WinConditionChecker:
    """Checks win conditions"""

    def __init__(
            self,
            role_manager: RoleManager,
            timer_manager: TimerManager,
            rcon_client: RCONClient):
        self.role_manager = role_manager
        self.timer_manager = timer_manager
        self.rcon = rcon_client
        self.logger = logging.getLogger(__name__)

    def check_win_conditions(
            self, alive_players: Optional[set] = None) -> Optional[Tuple[str, str]]:
        """Check if any win condition is met. Returns (winner, reason) or None

        Args:
            alive_players: Set of alive players. If None, uses all online players.
        """
        if alive_players is None:
            online_players = self.rcon.get_online_players()
            alive_players = set(online_players)

        # Get alive traitors and innocents
        alive_traitors = [
            p for p in self.role_manager.get_traitors() if p in alive_players]
        alive_innocents = [
            p for p in self.role_manager.get_innocents() if p in alive_players]

        # Get all assigned traitors (not just alive ones) to check if any
        # traitors were ever assigned
        all_traitors = self.role_manager.get_traitors()
        all_innocents = self.role_manager.get_innocents()

        # Debug logging for win condition checks
        self.logger.debug(
            f"Win condition check: alive_traitors={alive_traitors}, alive_innocents={alive_innocents}, "
            f"all_traitors={all_traitors}, all_innocents={all_innocents}, alive_players={alive_players}")

        # End game if there are neither traitors nor innocents alive
        # This handles the case where all players have died or edge cases
        # BUT only if there are still players online (don't end if everyone disconnected)
        if len(alive_traitors) == 0 and len(alive_innocents) == 0:
            # Only end if roles were actually assigned (game was started) AND there are players online
            if (len(all_traitors) > 0 or len(all_innocents) > 0) and len(alive_players) > 0:
                self.logger.info(
                    f"Win condition: Game ended - No traitors or innocents alive "
                    f"(alive traitors: {len(alive_traitors)}, alive innocents: {len(alive_innocents)}, "
                    f"total traitors assigned: {len(all_traitors)}, total innocents assigned: {len(all_innocents)}, "
                    f"online players: {len(alive_players)})")
                return ("Draw", "No players remaining")
            elif len(alive_players) == 0:
                self.logger.debug(
                    f"No players online - not ending game (alive traitors: {len(alive_traitors)}, "
                    f"alive innocents: {len(alive_innocents)}, online players: {len(alive_players)})")
                return None

        # Traitors win if all innocents are eliminated
        # Check: no alive innocents AND there were innocents assigned at game start AND there were traitors assigned
        # Also ensure we're not in a degenerate case (e.g., only 1 innocent
        # total)
        if (len(alive_innocents) == 0 and
            len(all_innocents) > 0 and
            len(all_traitors) > 0 and
                len(alive_traitors) > 0):  # At least one traitor must still be alive
            self.logger.info(
                f"Win condition: Traitors win - No innocents alive (alive innocents: {len(alive_innocents)}, "
                f"total innocents assigned: {len(all_innocents)}, alive traitors: {len(alive_traitors)}, "
                f"total traitors assigned: {len(all_traitors)})")
            return ("Traitors", "All innocent players eliminated")

        # Innocents win if timer expires and at least one innocent survives
        if self.timer_manager.is_expired() and len(alive_innocents) > 0:
            return ("Innocents", "Time limit reached")

        # If all traitors are eliminated, innocents win
        # Only trigger this if traitors were actually assigned
        if (len(alive_traitors) == 0 and len(alive_innocents) > 0 and len(all_traitors) > 0):
            self.logger.info(
                f"Win condition: Innocents win - All traitors eliminated (alive traitors: {len(alive_traitors)}, "
                f"total traitors assigned: {len(all_traitors)}, alive innocents: {len(alive_innocents)}, "
                f"total innocents assigned: {len(all_innocents)})")
            return ("Innocents", "All traitors eliminated")

        return None

