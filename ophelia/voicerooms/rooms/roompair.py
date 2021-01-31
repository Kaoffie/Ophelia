"""Room pair module."""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from discord import Member, TextChannel, VoiceChannel

from ophelia.output import disp_str
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

    async def transfer(self, prev: Member, owner: Member) -> None:
        """
        Transfer room to new owner.

        This method doens't handle the member filtering, but assumes
        that the new member is a valid room owner.

        :param prev: Previous room owner
        :param owner: New room owner
        :raise RoomRateLimited: When topic changes are ratelimited
        """
        # Update topic
        async def change_topic() -> None:
            """Inner function."""
            await self.text_channel.edit(
                topic=disp_str("voicerooms_topic_format").format(
                    owner.display_name
                )
            )

        # This part can throw RoomRateLimits.
        await self.do_rate_limit(change_topic)

        # Get owner overwrites
        owner_voice = self.voice_channel.overwrites_for(prev)
        owner_text = self.text_channel.overwrites_for(prev)

        # Get non-owner overwrites
        member_voice = self.text_channel.overwrites_for(owner)
        member_text = self.text_channel.overwrites_for(owner)

        # Swap
        await self.voice_channel.set_permissions(prev, overwrite=member_voice)
        await self.text_channel.set_permissions(prev, overwrite=member_text)

        await self.voice_channel.set_permissions(owner, overwrite=owner_voice)
        await self.text_channel.set_permissions(owner, overwrite=owner_text)

    async def rename(self, new_name: str) -> None:
        """
        Change room name.

        This is one of the only few operations that are implemented here
        because it is ratelimited quite severely by Discord.

        :param new_name: New name
        :raises RoomRateLimited: When changes are ratelimited
        """
        async def change_name() -> None:
            """Inner function."""
            await self.text_channel.edit(name=new_name)
            await self.voice_channel.edit(name=new_name)

        await self.do_rate_limit(change_name)

    async def do_rate_limit(self, callable: Callable) -> None:
        """
        Do something if the internal ratelimit lets it happen.

        :param callable: The async thing to do
        :raise RoomRateLimited: When we're rate limited
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

        try:
            await asyncio.wait_for(callable(), 5)
        except asyncio.TimeoutError as e:
            raise RoomRateLimited from e
