"""
Timer manager for game duration tracking
"""

import logging
from datetime import datetime, timedelta
from typing import Optional


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

