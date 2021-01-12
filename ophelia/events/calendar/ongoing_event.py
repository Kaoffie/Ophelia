"""Ongoing Event Module."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from discord import Embed

from ophelia.utils.time_utils import to_utc_datetime, utc_time_now


@dataclass
class OngoingEvent:
    """
    Class for tracking ongoing events.

    This class does not inherit from BaseEvents since it does not track
    event submissions - objects from this class are created separately
    to track events that have already had their notifications sent out,
    and they are kept there for the sole purpose of making sure that
    the event announcement message is deleted when the event ends.

    Parameters:
    - countdown_time: Time to start counting down to timeout
    - timeout_length: Seconds it takes for event to time out
    - organizer_id: User ID of organizer
    - message_text: Content of event announcement message
    - message_embed: Embed of event announcement message
    """
    countdown_time: int
    timeout_length: int
    organizer_id: int
    message_text: str
    message_embed: Embed

    def timed_out(self, time: Optional[datetime] = None) -> bool:
        """
        Check if the event announcement has timed out.

        :param time: Time to check against
        :return: Boolean indicating if the announcement has timed out
            and should be deleted
        """
        if time is None:
            time = utc_time_now()

        return time >= to_utc_datetime(
            self.countdown_time + self.timeout_length
        )

    async def save_to_dict(self) -> dict:
        """
        Saves ongoing event object into dictionary containing
        configuration parameters so that it may be loaded again.

        :return: Dictionary of configuration parameters
        """
        save_dict = {
            "countdown_time": self.countdown_time,
            "timeout_length": self.timeout_length,
            "organizer_id": self.organizer_id,
            "message_text": self.message_text,
            "message_embed": self.message_embed.to_dict()
        }

        return save_dict
