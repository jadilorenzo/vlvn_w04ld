"""
Notification system for sending messages to players
"""

import json
import logging
from typing import Optional

from .rcon_client import RCONClient


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
        try:
            json_msg = json.dumps({"text": message, "color": color})
            response = self.rcon.execute(f'tellraw @a {json_msg}')
            if response:
                # Log if there's an error response
                if "error" in response.lower() or "unknown" in response.lower():
                    self.logger.warning(
                        f"tellraw_all got response: {response}")
            self.logger.debug(f"tellraw_all: {message[:50]}... -> {response}")
        except Exception as e:
            self.logger.error(f"Error in tellraw_all: {e}", exc_info=True)
            raise

    def title(
            self,
            player: str,
            title: str,
            subtitle: str = "",
            fade_in: int = 10,
            stay: int = 70,
            fade_out: int = 20):
        """Send title to player"""
        self.rcon.execute(f'title {player} times {fade_in} {stay} {fade_out}')
        self.rcon.execute(
            f'title {player} title {json.dumps({"text": title})}')
        if subtitle:
            self.rcon.execute(
                f'title {player} subtitle {json.dumps({"text": subtitle})}')

    def title_all(
            self,
            title: str,
            subtitle: str = "",
            fade_in: int = 10,
            stay: int = 70,
            fade_out: int = 20):
        """Send title to all players"""
        try:
            response1 = self.rcon.execute(
                f'title @a times {fade_in} {stay} {fade_out}')
            if response1 and ("error" in response1.lower() or "unknown" in response1.lower()):
                logging.warning(f"title_all times got response: {response1}")
            response2 = self.rcon.execute(
                f'title @a title {json.dumps({"text": title})}')
            if response2 and ("error" in response2.lower() or "unknown" in response2.lower()):
                logging.warning(f"title_all title got response: {response2}")
            if subtitle:
                response3 = self.rcon.execute(
                    f'title @a subtitle {json.dumps({"text": subtitle})}')
                if response3 and ("error" in response3.lower() or "unknown" in response3.lower()):
                    logging.warning(
                        f"title_all subtitle got response: {response3}")
        except Exception as e:
            logging.error(f"Error in title_all: {e}", exc_info=True)
            raise

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

