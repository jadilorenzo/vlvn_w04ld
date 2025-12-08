"""
Dragon detection helper for checking if the Ender Dragon has been killed.

This module provides a simple way to poll whether the Ender Dragon has been
defeated during the current game, using Minecraft advancements.
"""

import logging
from typing import Callable, List

# Constants
ADVANCEMENT_ID = "minecraft:end/kill_dragon"
DRAGON_KILLED_MARKER = "DRAGON_KILLED"

logger = logging.getLogger(__name__)


def clear_dragon_advancement_for_all_players(send_cmd: Callable[[str], str]) -> None:
    """Revoke the Ender Dragon kill advancement for all players in the world.

    This ensures that any future detection only reflects what happens during
    this game session. Clears for all players (online and offline) using @a selector.

    Args:
        send_cmd: Function that sends an RCON command and returns the output
    """
    logger.info("Clearing dragon advancement for all players")
    try:
        send_cmd(f"advancement revoke @a only {ADVANCEMENT_ID}")
        logger.info("Revoked dragon kill advancement for all players")
    except Exception as e:
        logger.warning(f"Error revoking advancement for all players: {e}")


def clear_dragon_advancement_for_players(send_cmd: Callable[[str], str], players: List[str]) -> None:
    """For each player name in `players`, revoke the Ender Dragon kill advancement.

    This ensures that any future detection only reflects what happens during
    this game session.

    Args:
        send_cmd: Function that sends an RCON command and returns the output
        players: List of player names to clear the advancement for
    """
    logger.info(f"Clearing dragon advancement for {len(players)} player(s)")
    for player in players:
        try:
            send_cmd(f"advancement revoke {player} only {ADVANCEMENT_ID}")
            logger.info(f"Revoked dragon kill advancement for {player}")
        except Exception as e:
            # Ignore errors if a player doesn't have the advancement yet
            logger.warning(
                f"Error revoking advancement for {player} (may not have it): {e}")


def has_any_player_killed_dragon(send_cmd: Callable[[str], str]) -> bool:
    """Check if any currently-online player has killed the dragon.

    Uses execute if entity with a command that returns data, which RCON can capture.
    If any player has the advancement, the command runs and returns player data.
    If no player has it, the command doesn't run and returns an error or empty.

    Args:
        send_cmd: Function that sends an RCON command and returns the output

    Returns:
        True if any player has the advancement, False otherwise
    """
    try:
        # Use execute if entity with a command that returns data
        # If any player has the advancement, this will return player data
        # If no player has it, the execute won't run and we'll get an error/empty
        command = f"execute if entity @a[advancements={{minecraft:end/kill_dragon=true}}] run data get entity @p"
        logger.debug(f"Checking dragon kill status with command: {command}")
        result = send_cmd(command)
        logger.debug(f"Dragon check result: {result}")

        # If we get a result with player data (not an error), the condition matched
        # Player data will contain things like "Pos", "Rotation", etc.
        if result and "No entity" not in result and "error" not in result.lower() and len(result.strip()) > 0:
            # Check if it looks like player data (contains common NBT keys)
            if "Pos" in result or "Rotation" in result or "Health" in result or "data" in result.lower():
                logger.info(
                    "Dragon has been killed - advancement detected (player data found)")
                return True

        logger.debug("Dragon not killed - no advancement detected")
        return False
    except Exception as e:
        logger.warning(f"Error checking if any player killed dragon: {e}")
        return False
