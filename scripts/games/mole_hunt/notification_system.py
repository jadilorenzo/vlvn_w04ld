"""
Mole Hunt specific notification system
Extends the base NotificationSystem with game-specific methods
"""

import json
import logging
from typing import Optional

from game_engine.notification_system import NotificationSystem
from .role import Role


class MoleHuntNotificationSystem(NotificationSystem):
    """Notification system for Mole Hunt game with game-specific methods"""

    def __init__(self, rcon_client):
        super().__init__(rcon_client)
        self.logger = logging.getLogger(__name__)

    def announce_role(self, player: str, role: Role):
        """Announce player's role"""
        if role == Role.TRAITOR:
            self.title(player, "§4YOU ARE A TRAITOR",
                       "§7Eliminate all innocents!", 10, 100, 20)
            self.tellraw(
                player,
                "§4[TRAITOR] §7Your goal is to eliminate all innocent players!",
                "red")
            self.tellraw(
                player,
                "§7You have special abilities. Use them wisely!",
                "gray")
        else:
            self.title(player, "§aYOU ARE INNOCENT",
                       "§7Survive and identify the traitors!", 10, 100, 20)
            self.tellraw(
                player,
                "§a[INNOCENT] §7Your goal is to survive until time runs out!",
                "green")
            self.tellraw(
                player,
                "§7Work together to identify and stop the traitors!",
                "gray")

    def announce_game_start(self):
        """Announce game start"""
        self.title_all("§6MOLE HUNT", "§7Game Starting!", 10, 100, 20)
        self.tellraw_all("§6=== MOLE HUNT GAME STARTED ===", "gold")
        self.tellraw_all(
            "§7Roles have been assigned. Check your title!", "gray")

    def announce_game_end(self, winners: str, reason: str):
        """Announce game end"""
        self.logger.info(
            f"announce_game_end called with winners={winners}, reason={reason}")
        try:
            # Show prominent title screen (longer display time)
            if winners.lower() == "traitors":
                title_color = "§4"
                subtitle_color = "§c"
                subtitle_text = f"{subtitle_color}{winners.upper()} WON!"
            elif winners.lower() == "draw":
                title_color = "§6"
                subtitle_color = "§e"
                subtitle_text = f"{subtitle_color}DRAW!"
            else:
                title_color = "§a"
                subtitle_color = "§2"
                subtitle_text = f"{subtitle_color}{winners.upper()} WON!"

            # Send multiple messages to ensure visibility
            self.logger.info("Sending game end tellraw messages")
            self.tellraw_all("§6" + "="*50, "gold")
            self.tellraw_all("§6=== MOLE HUNT GAME ENDED ===", "gold")
            self.tellraw_all("§6" + "="*50, "gold")
            self.tellraw_all("", "white")  # Blank line for spacing

            self.logger.info("Sending game end title")
            self.title_all(
                f"{title_color}GAME OVER",
                subtitle_text,
                10, 140, 20
            )

            # Show winner and reason prominently - ALWAYS send both
            self.logger.info("Sending winner and reason messages")
            self.tellraw_all(f"§e§lWINNERS: §r§6{winners}", "yellow")
            # Always send reason (use provided reason or default)
            reason_text = reason if reason else "Game ended"
            self.tellraw_all(f"§e§lREASON: §r§6{reason_text}", "yellow")
            self.tellraw_all("", "white")  # Blank line for spacing
            self.logger.info("announce_game_end completed successfully")
        except Exception as e:
            self.logger.error(
                f"Error in announce_game_end: {e}", exc_info=True)
            raise

    def send_time_update(
            self,
            minutes: int,
            seconds: int,
            player: Optional[str] = None):
        """Send time remaining update via actionbar to specified player or all players"""
        message = f"§7Time remaining: §6{minutes}:{seconds:02d}"
        if player:
            self.actionbar(player, message)
        else:
            # Get all online players and send actionbar to each
            online_players = self.rcon.get_online_players()
            for p in online_players:
                self.actionbar(p, message)

    def send_player_location(
            self,
            traitor: str,
            target_player: str,
            distance: float,
            direction: str = ""):
        """Send nearest player location info to traitor via actionbar"""
        # Format: "Nearest: PlayerName (123m) [Direction]"
        if direction:
            message = f"§c§lNearest: §r§e{target_player} §7({distance:.0f}m) §6{direction}"
        else:
            message = f"§c§lNearest: §r§e{target_player} §7({distance:.0f}m)"
        self.actionbar(traitor, message)

