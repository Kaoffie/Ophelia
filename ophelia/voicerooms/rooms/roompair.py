"""Room pair module."""
import asyncio
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Set

from discord import Member, Message, TextChannel, VoiceChannel, VoiceState

from ophelia.output import disp_str, send_simple_embed
from ophelia.utils.discord_utils import FETCH_FAIL_EXCEPTIONS

from ophelia import settings

RATELIMIT_COUNT = 2
RATELIMIT_SECONDS = 600
BACKOFF_SECONDS = 5

VOICE_UNMUTE_EMOTE = "\U0001f508"


class RoomRateLimited(Exception):
    """When room edits are ratelimited."""


class RoomMode(Enum):
    """VC room modes."""
    PUBLIC = 0
    JOINMUTE = 1
    PRIVATE = 2


class RoomPair:
    """Voice chat and text channel pair."""

    __slots__ = [
        "text_channel",
        "voice_channel",
        "log_channel",
        "owner_id",
        "ratelimit_counter",
        "ratelimit_lock",
        "ratelimit_timer",
        "current_mode",
        "joinmute_seconds",
        "muted"
    ]

    def __init__(
            self,
            text_channel: TextChannel,
            voice_channel: VoiceChannel,
            log_channel: TextChannel,
            owner_id: int
    ) -> None:
        """
        Initializer for the RoomPair class.

        :param text_channel: Room text channel
        :param voice_channel: Room voice channel
        :param log_channel: Log channel to forward text messages to
        :param owner_id: Room owner ID
        """

        self.text_channel = text_channel
        self.voice_channel = voice_channel
        self.log_channel = log_channel
        self.owner_id = owner_id

        # Hardcoded to Discord's channel name change limit
        self.ratelimit_counter = 0
        self.ratelimit_lock = asyncio.Lock()
        self.ratelimit_timer = datetime.utcfromtimestamp(0)

        # Modes
        self.current_mode: RoomMode = RoomMode.PUBLIC
        self.joinmute_seconds: int = 0

        # Mutes
        self.muted: Set[int] = set()

    def is_tempmute(self) -> bool:
        """
        Check if the current room is in tempmute mode (as opposed to
        permanent mute mode)

        :return: Whether room is in temp join mute mode.
        """
        return (
                self.current_mode == RoomMode.JOINMUTE
                and self.joinmute_seconds > 0
        )

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

        # Swap Voice
        await self.voice_channel.set_permissions(prev, overwrite=member_voice)
        await self.voice_channel.set_permissions(owner, overwrite=owner_voice)

        # Give new owner the necessary permissions
        await self.text_channel.set_permissions(owner, overwrite=owner_text)
        if owner in self.voice_channel.members:
            await owner.edit(mute=False)

        # Update internal
        self.owner_id = owner.id

        # Old owner either gets stripped of all perms or gets the new
        # owner's old perms if they're still in the voice channel
        if prev in self.voice_channel.members:
            await self.text_channel.set_permissions(prev, overwrite=member_text)
        else:
            await self.text_channel.set_permissions(prev, overwrite=None)

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

    async def do_rate_limit(self, call_func: Callable) -> None:
        """
        Do something if the internal ratelimit lets it happen.

        :param call_func: The async thing to do
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
            await asyncio.wait_for(call_func(), 5)
        except asyncio.TimeoutError as e:
            raise RoomRateLimited from e

    def should_mute(self, member: Member) -> bool:
        """
        Checks if the user should be muted upon joining the room.

        :param member: Member to check
        :return: Whether the member should be muted when joining
        """
        return member.id in self.muted or (
                member.id != self.owner_id
                and self.current_mode == RoomMode.JOINMUTE
        )

    async def mute_user(self, member: Member) -> None:
        """
        Mute a member.

        :param member: Member in channel
        """
        self.muted.add(member.id)

        if member in self.voice_channel.members:
            await member.edit(mute=True)

    async def unmute_user(self, member: Member) -> None:
        """
        Unmute a member.

        :param member: Member in channel
        """
        self.muted.remove(member.id)

        if member in self.voice_channel.members:
            await member.edit(mute=False)

    async def unmute_all(self) -> None:
        """
        Unmutes all members in room.

        Used when switching from joinmute mode to public or private
        mode.
        """
        for member in self.voice_channel.members:
            if member.id not in self.muted:
                await member.edit(mute=False)

    async def handle_join(self, member: Member) -> None:
        """
        Handle member joins; currently used for managing mutes.

        :param member: Member who just joined the channel
        """
        if (
                self.current_mode == RoomMode.JOINMUTE
                and member.id != self.owner_id
        ):
            await member.edit(mute=True)
            return

        if member.id in self.muted:
            await member.edit(mute=True)

    async def handle_leave(
            self,
            member: Member,
            to_room: Optional["RoomPair"]
    ) -> None:
        """
        Handle member exits; currently used for managing mutes.

        :param member: Member who just left the channel
        :param to_room: Room that the member is moving to
        """
        if (
                self.current_mode == RoomMode.JOINMUTE
                and member.id != self.owner_id
        ):
            if to_room is not None and to_room.should_mute(member):
                return

            await member.edit(mute=False)
            return

        if member.id in self.muted:
            voice_state: VoiceState = member.voice
            if voice_state is not None and voice_state.channel is not None:
                await member.edit(mute=False)

    async def schedule_unmute(self, member: Member) -> None:
        """
        Schedule an unmute of a user after joining a room that's in
        joinmute mode.

        :param member: Member to be unmuted
        """

        async def unmute_task(
                voice_channel: VoiceChannel,
                wait_seconds: int,
                unmute_member: Member
        ) -> None:
            """
            Internal function.

            :param voice_channel: Voice channel to unmute member in
            :param wait_seconds: Seconds to wait for before unmuting member
            :param unmute_member: Member to unmute
            """
            await asyncio.sleep(wait_seconds)
            if unmute_member not in voice_channel.members:
                return

            await unmute_member.edit(mute=False)

        asyncio.create_task(unmute_task(
            self.voice_channel,
            self.joinmute_seconds,
            member
        ))

    # noinspection PyUnresolvedReferences
    async def react_unmute(
            self,
            bot: "OpheliaBot",
            message: Message,
            owner_id: int,
            member: Member
    ) -> None:
        """
        Add an unmute reaction to a message to allow a room ownser to unmute
        a user; used for permanent joinmute.

        :param bot: Ophelia bot object
        :param message: Welcome message
        :param owner_id: Room owner ID
        :param member: Member to prepare the unmute react for
        """
        await message.add_reaction(VOICE_UNMUTE_EMOTE)

        try:
            await bot.wait_for(
                "reaction_add",
                timeout=settings.voiceroom_mute_button_timeout,
                check=(
                    lambda r, m: (
                            str(r.emoji) == VOICE_UNMUTE_EMOTE and
                            r.message.id == message.id and
                            m.id == owner_id
                    )
                )
            )

            # Unmute
            if member in self.voice_channel.members:
                await member.edit(mute=False)
                await send_simple_embed(
                    self.text_channel,
                    "voicerooms_unmute_confirm",
                    member.mention
                )

        except asyncio.exceptions.TimeoutError:
            try:
                await message.remove_reaction(VOICE_UNMUTE_EMOTE, bot.user)
            except FETCH_FAIL_EXCEPTIONS:
                return
