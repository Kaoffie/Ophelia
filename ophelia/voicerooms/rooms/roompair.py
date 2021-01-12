"""Room pair module."""
import asyncio
from dataclasses import dataclass
from datetime import datetime

from discord import TextChannel, VoiceChannel

from ophelia.utils.discord_utils import FETCH_FAIL_EXCEPTIONS


RATELIMIT_COUNT = 2
RATELIMIT_SECONDS = 600
BACKOFF_SECONDS = 5


class RoomRateLimited(Exception):
    """When room edits are ratelimited."""


@dataclass
class RoomPair:
    """Voice chat and text channel pair."""
    text_channel: TextChannel
    voice_channel: VoiceChannel
    log_channel: TextChannel

    # Hardcoded to Discord's channel name change limit
    ratelimit_counter = 0
    ratelimit_lock = asyncio.Lock()
    ratelimit_timer = datetime.utcfromtimestamp(0)

    async def destroy(self) -> None:
        """
        Delete room.

        The two rooms are deleted separately in case one of them fails,
        which is expected in cases where one of the channels was deleted
        manually, triggering the delete of the other.
        """
        try:
            await self.text_channel.delete()
        except FETCH_FAIL_EXCEPTIONS:
            pass

        try:
            await self.voice_channel.delete()
        except FETCH_FAIL_EXCEPTIONS:
            pass

    async def rename(self, new_name: str) -> None:
        """
        Change room name.

        This is one of the only few operations that are implemented here
        because it is ratelimited quite severely by Discord.

        :param new_name: New name
        :raises RoomRateLimited: When changes are ratelimited
        """
        async with self.ratelimit_lock:
            time_now = datetime.utcnow()
            time_delta = time_now - self.ratelimit_timer
            if time_delta.seconds > RATELIMIT_SECONDS:
                self.ratelimit_timer = time_now
                self.ratelimit_counter = 1

            elif self.ratelimit_counter >= RATELIMIT_COUNT:
                raise RoomRateLimited

            elif 0 < self.ratelimit_counter < RATELIMIT_COUNT:
                self.ratelimit_counter += 1

        async def change_name() -> None:
            """Inner function."""
            await self.text_channel.edit(name=new_name)
            await self.voice_channel.edit(name=new_name)

        try:
            print("Doing the change...")
            await asyncio.wait_for(change_name(), 5)
        except asyncio.TimeoutError as e:
            raise RoomRateLimited from e
