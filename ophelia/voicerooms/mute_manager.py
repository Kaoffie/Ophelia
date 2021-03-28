"""Mute manager module."""
import asyncio
from typing import Set

from discord import Member

from ophelia.utils.discord_utils import FETCH_FAIL_EXCEPTIONS


class MuteManager:
    """Mute manager; manages moderator mutes and bot mutes."""

    __slots__ = [
        "guild_id",
        "bot_muted",
        "manual_muted",
        "unmute_queue",
        "mute_lock"
    ]

    def __init__(self, guild_id: int) -> None:
        """
        Initializer for the MuteManager class.

        :param guild_id: Guild ID
        """
        self.guild_id = guild_id
        self.bot_muted: Set[int] = set()
        self.manual_muted: Set[int] = set()
        self.unmute_queue: Set[int] = set()
        self.mute_lock = asyncio.Lock()

    async def mute(self, member: Member) -> None:
        """
        Mute a member.

        :param member: Member to be muted
        """
        async with self.mute_lock:
            if member.id in self.manual_muted:
                return

            try:
                await member.edit(mute=True)
                self.bot_muted.add(member.id)
            except FETCH_FAIL_EXCEPTIONS:
                pass

    async def unmute(self, member: Member) -> None:
        """
        Unmute a member if they weren't previously unmuted by a bot.

        :param member: Member to unmute
        """
        async with self.mute_lock:
            if member.id in self.manual_muted:
                return

            self.bot_muted.discard(member.id)

            try:
                await member.edit(mute=False)
            except FETCH_FAIL_EXCEPTIONS:
                # Schedule the member for a future unmute
                self.unmute_queue.add(member.id)

    async def queue_unmute(self, member: Member) -> None:
        """
        Schedule a member for future unmuting if they left a channel
        before they could be unmuted by us.

        :param member: Member to be unmuted the next time they join a VC
        """
        async with self.mute_lock:
            self.unmute_queue.add(member.id)

    async def register_mute(self, member: Member) -> None:
        """
        Register a manually muted member.

        :param member: Member that was muted
        """
        async with self.mute_lock:
            if member.id not in self.bot_muted:
                self.manual_muted.add(member.id)

    async def register_unmute(self, member: Member) -> None:
        """
        Register a manually unmuted member.

        :param member: Member that was unmuted
        """
        async with self.mute_lock:
            # Regardless of whether the member was manually unmuted, or
            # if they were muted by the bot (which would not be possible
            # if they were in the manual muted set), we'd want to free
            # this member from any mute restrictions.
            self.manual_muted.discard(member.id)
            self.bot_muted.discard(member.id)
            self.unmute_queue.discard(member.id)

    async def handle_join(self, member: Member) -> None:
        """
        Unmutes members who are in the unmute queue (who never got the
        chance to be unmuted when they should have been)

        :param member: Member that might need unmuting
        """
        async with self.mute_lock:
            if member.id in self.unmute_queue:
                try:
                    await member.edit(mute=False)
                    self.unmute_queue.discard(member.id)
                except FETCH_FAIL_EXCEPTIONS:
                    # We'll get 'em next time
                    pass
