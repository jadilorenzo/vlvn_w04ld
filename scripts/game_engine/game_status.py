"""
Game status enumeration
"""

from enum import Enum


class GameStatus(Enum):
    """Game status enumeration"""
    NOT_STARTED = "not_started"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"

