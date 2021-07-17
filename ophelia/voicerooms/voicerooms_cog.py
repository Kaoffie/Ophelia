"""
Voice rooms module.

Gives users the power to create and manage their own voice chat channels
instead of relying on pre-defined channels.
"""
import asyncio
import copy
import functools
import os
import re
from typing import Callable, Dict, List, Optional, Tuple, Union

import yaml
from discord import (
    Colour, Guild, HTTPException, Member, Message,
    Role, TextChannel,
    VoiceChannel, VoiceState
)
from discord.abc import GuildChannel
from discord.ext import commands
from discord.ext.commands import Context
from loguru import logger

from ophelia import settings
from ophelia.output.error_handler import OpheliaCommandError
from ophelia.output.output import (
    disp_str, get_input, response_config, response_options, response_switch,
    send_message,
    send_message_embed,
    send_simple_embed
)
from ophelia.settings import voiceroom_max_mute_time
from ophelia.utils.discord_utils import (
    ARGUMENT_FAIL_EXCEPTIONS, in_vc, vc_is_empty, vc_members
)
from ophelia.utils.text_utils import escape_formatting
from ophelia.voicerooms.config_options import VOICEROOMS_GENERATOR_CONFIG
from ophelia.voicerooms.message_buffer import MessageBuffer
from ophelia.voicerooms.mute_manager import MuteManager
from ophelia.voicerooms.name_filter import NameFilterManager
from ophelia.voicerooms.rooms.generator import (
    Generator, GeneratorLoadError,
    RoomCreationError
)
from ophelia.voicerooms.rooms.roompair import (
    RoomMode, RoomPair,
    RoomRateLimited
)

CONFIG_VOICEROOM_TIMEOUT = settings.voiceroom_empty_timeout
CONFIG_TIMEOUT_SECONDS = settings.long_timeout
CONFIG_MAX_TRIES = settings.max_tries
CONFIG_PATH = settings.file_voicerooms_config


class VoiceroomsCog(commands.Cog, name="voicerooms"):
    """
    Custom Voice Rooms.

    Manage user-initiated voice rooms and accompanying text rooms.
    """

    __slots__ = [
        "bot",
        "generators",
        "rooms",
        "vc_room_map",
        "text_room_map",
        "message_buffer",
        "name_filter",
        "generator_lock",
        "mute_managers"
    ]

    # Using forward references to avoid cyclic imports
    # noinspection PyUnresolvedReferences
    def __init__(self, bot: "OpheliaBot") -> None:
        """
        Initializer for the VoiceroomsCog class.

        :param bot: Ophelia bot object
        """
        self.bot = bot
        self.generators: Dict[int, Generator] = {}
        self.rooms: Dict[int, RoomPair] = {}
        self.vc_room_map: Dict[int, int] = {}
        self.text_room_map: Dict[int, int] = {}
        self.message_buffer = MessageBuffer()
        self.name_filter = NameFilterManager.load_filters()
        self.generator_lock = asyncio.Lock()

        # We have to keep track of users who will be unmuted on their
        # next VC join because we are unable to unmute them if they
        # leave a VC in a muted state. This is a limitation set by
        # Discord and we can't really circumvent it because the other
        # kind of muting (using permissions) doesn't allow instant
        # muting.
        self.mute_managers: Dict[int, MuteManager] = {}

    def get_mute(self, guild_id: int) -> MuteManager:
        """
        Get guild mute manager from guild ID.

        :param guild_id: Guild ID
        :return: Mute manager corresponding to guild ID
        """
        return self.mute_managers.setdefault(guild_id, MuteManager(guild_id))

    # pylint: disable=too-few-public-methods
    class VoiceroomsDecorators:
        """
        Voiceroom decorators for checking relevant voicerooms before
        going to command logic.
        """

        @classmethod
        def pass_voiceroom(cls, func: Callable) -> Callable:
            """
            Decorator to pass voiceroom pair under a given owner
            directly to the command.

            :param func: Async function to be wrapped
            :return: Wrapped function
            """

            @functools.wraps(func)
            async def wrapped(
                    self: "VoiceroomsCog",
                    context: Context,
                    *args,
                    **kwargs
            ) -> None:
                """
                Inner function.

                :param self: VoiceroomsCog instance
                :param context: Command context
                """
                author = context.author
                if author.id not in self.rooms:
                    raise OpheliaCommandError("voicerooms_no_room")

                await func(
                    self,
                    context=context,
                    room=self.rooms[author.id],
                    *args,
                    **kwargs
                )

            return wrapped

    # pylint: enable=too-few-public-methods

    async def cog_save_all(self) -> None:
        """Save all generator configurations before bot shutdown."""
        # Dump all logs
        await self.message_buffer.dump()

        # Delete all channels
        for room_key in copy.copy(list(self.rooms.keys())):
            await self.rooms[room_key].destroy()

        # Saves all generators
        await self.save_generators()

        # Saves all room name filters
        await self.name_filter.save_filters()

    async def save_generators(self) -> None:
        """Save all generator configurations for future use."""
        generators_dict = {}
        for channel_id, generator in self.generators.items():
            generators_dict[str(channel_id)] = await generator.to_dict()

        with open(CONFIG_PATH, "w", encoding="utf-8") as save_target:
            yaml.dump(
                generators_dict,
                save_target,
                default_flow_style=False
            )

    async def load_generators(self) -> None:
        """Load all generator configurations for use."""
        if not os.path.exists(CONFIG_PATH):
            return

        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            generators_dict = yaml.safe_load(file)
            if generators_dict is None:
                return

            for channel_id_str, gen_dict in generators_dict.items():
                try:
                    channel_id = int(channel_id_str)
                    generator = await Generator.from_dict(self.bot, gen_dict)
                    self.generators[channel_id] = generator

                    # Create new guild mute manager
                    guild_id: int = generator.generator_channel.guild.id
                    if guild_id not in self.mute_managers:
                        self.mute_managers[guild_id] = MuteManager(guild_id)

                except GeneratorLoadError:
                    logger.warning(
                        "Failed to load generator with ID {}",
                        channel_id_str
                    )

    @commands.Cog.listener()
    async def on_message(self, message: Message) -> None:
        """
        Checks incoming messages for any that require logging in
        temporary text channels.

        :param message: Message
        """
        channel_id = message.channel.id
        if channel_id in self.text_room_map:
            if message.author.bot:
                return

            owner_id = self.text_room_map[channel_id]

            try:
                log_channel = self.rooms[owner_id].log_channel

                await self.message_buffer.log_message(log_channel, message)
            except KeyError:
                # Zombie room, delete channel.
                await message.channel.delete()
                self.text_room_map.pop(channel_id, None)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel) -> None:
        """
        Cleans up any generators or rooms associated with deleted
        channels.

        :param channel: Deleted channel
        """
        # noinspection PyUnresolvedReferences
        channel_id = channel.id

        if channel_id in self.vc_room_map:
            await self.delete_room(self.vc_room_map[channel_id])
        elif channel_id in self.text_room_map:
            await self.delete_room(self.text_room_map[channel_id])
        elif channel_id in self.rooms:
            await self.delete_room(channel_id)
        elif channel_id in self.generators:
            self.generators.pop(channel_id, None)
            await self.save_generators()

    @commands.Cog.listener()
    async def on_voice_state_update(
            self,
            member: Member,
            before: VoiceState,
            after: VoiceState
    ) -> None:
        """
        Detects when a user joins or leaves a voice channel.

        :param member: Guild member
        :param before: Previous voice state
        :param after: New voice state
        """
        if before.channel == after.channel:
            if before.mute and not after.mute:
                await self.get_mute(member.guild.id).register_unmute(member)
            elif not before.mute and after.mute:
                await self.get_mute(member.guild.id).register_mute(member)

            return

        if after.channel is not None:
            await self.on_voice_join(member, after.channel)

        if before.channel is not None:
            await self.on_voice_leave(member, before.channel, after.channel)

    async def on_voice_join(
            self,
            member: Member,
            channel: VoiceChannel
    ) -> None:
        """
        Handles members joining voice channels.

        :param member: Guild member
        :param channel: Voice channel joined
        """
        channel_id = channel.id
        guild_id = channel.guild.id

        # Unmute first, even if the user is gonna be muted again
        # later by another VC room
        await self.get_mute(guild_id).handle_join(member)

        if channel_id in self.generators:
            await self.on_generator_join(member, self.generators[channel_id])

        if channel_id in self.vc_room_map:
            owner_id = self.vc_room_map[channel_id]
            if member.id == owner_id:
                return

            try:
                room: RoomPair = self.rooms[owner_id]
                text_channel = room.text_channel
                voice_channel = room.voice_channel

                # Grant read and write permissions:
                overwrite = text_channel.overwrites_for(member)
                overwrite.update(send_messages=True, read_messages=True)
                await text_channel.set_permissions(member, overwrite=overwrite)

                # Let room object do its thing
                await room.handle_join(member, self.get_mute(guild_id))

                # If on joinmute, mute user and set a timer for unmuting:
                # This won't apply to the owner due to the filter
                # a few lines back (intentional)
                if room.current_mode == RoomMode.JOINMUTE:
                    # Welcome user
                    if room.is_tempmute():
                        await send_message(
                            channel=text_channel,
                            text=disp_str("voicerooms_joinmute_welcome").format(
                                mention=member.mention,
                                name=voice_channel.name,
                                time=room.joinmute_seconds
                            ),
                            mass_ping_guard=True
                        )

                        # Schedule unmute
                        await room.schedule_unmute(
                            member,
                            self.get_mute(guild_id)
                        )

                    else:
                        message = await send_message(
                            channel=text_channel,
                            text=disp_str("voicerooms_permmute_welcome").format(
                                mention=member.mention,
                                name=voice_channel.name
                            ),
                            mass_ping_guard=True
                        )

                        # Prepare unmute reaction
                        asyncio.create_task(room.react_unmute(
                            bot=self.bot,
                            message=message,
                            owner_id=owner_id,
                            member=member,
                            mute_manager=self.get_mute(guild_id)
                        ))

            except KeyError:
                # Invalid zombie room; delete VC.
                await channel.delete()
                self.vc_room_map.pop(channel_id, None)

    async def on_generator_join(
            self,
            member: Member,
            generator: Generator
    ) -> None:
        """
        handles members joining generator channels.

        :param member: Guild member
        :param generator: Room generator
        """
        async with self.generator_lock:
            if member.id in self.rooms:
                return

            try:
                room: RoomPair = await generator.create_room(
                    member,
                    self.name_filter
                )

                await self.message_buffer.log_system_msg(
                    log_channel=room.log_channel,
                    text_channel=room.text_channel,
                    text=disp_str("voicerooms_log_create_room").format(
                        name=member.display_name,
                        id=member.id
                    )
                )
            except RoomCreationError:
                # Room has already been destroyed; fail silently.
                return

            self.rooms[member.id] = room
            self.vc_room_map[room.voice_channel.id] = member.id
            self.text_room_map[room.text_channel.id] = member.id

            # Check if room is occupied, or if the user has left the
            # room during channel creation.
            if vc_is_empty(room.voice_channel):
                await self.delete_room(member.id)
                return

    async def on_voice_leave(
            self,
            member: Member,
            channel: VoiceChannel,
            to_channel: Optional[VoiceChannel]
    ) -> None:
        """
        Handles members leaving voice channels.

        :param member: Guild member
        :param channel: Voice channel left
        :param to_channel: Voice channel that the member moved to
        """
        channel_id = channel.id
        guild_id = channel.guild.id

        if channel_id in self.vc_room_map:
            owner_id = self.vc_room_map[channel_id]

            try:
                room: RoomPair = self.rooms[owner_id]
                text_channel = room.text_channel
                voice_channel = room.voice_channel

                # Let room object do its thing
                to_room: Optional[RoomPair] = None
                if to_channel is not None and to_channel.id in self.vc_room_map:
                    to_owner_id = self.vc_room_map[to_channel.id]
                    to_room = self.rooms[to_owner_id]

                await room.handle_leave(
                    member,
                    to_room,
                    self.get_mute(guild_id)
                )

                # Before we remove permissions, we check that the user is
                # not an owner.
                if member.id != owner_id:
                    await text_channel.set_permissions(member, overwrite=None)

                # In case of a misclick, give the user a chance to rejoin:
                await asyncio.sleep(CONFIG_VOICEROOM_TIMEOUT)

                # While waiting, the channel might have been deleted.
                if channel_id not in self.vc_room_map:
                    return

                # Check if channel is empty:
                if vc_is_empty(voice_channel):
                    await self.message_buffer.log_system_msg(
                        log_channel=room.log_channel,
                        text_channel=room.text_channel,
                        text=disp_str("voicerooms_log_delete_room").format(
                            room=room.voice_channel.name,
                            name=member.display_name,
                            id=member.id
                        )
                    )
                    await self.delete_room(owner_id)
                    return

            except KeyError:
                # Zombie room.
                await channel.delete()
                self.vc_room_map.pop(channel_id, None)

    @commands.group(
        "voiceroom",
        invoke_without_command=True,
        aliases=["voicechat", "voice", "vr", "vc"]
    )
    @commands.bot_has_permissions(administrator=True)
    @commands.guild_only()
    async def voiceroom(self, context: Context, *_) -> None:
        """
        Main voice room command, displays list of subcommands.

        :param context: Command context
        """
        await send_simple_embed(context, "voicerooms_commands")

    @staticmethod
    async def update_room_membership(
            room: RoomPair,
            member_or_role: Union[Member, Role],
            new_value: Optional[bool] = True,
    ) -> None:
        """
        Update a member or a role's permissions in a room.

        Used for adding or removing roles from a private room, including
        the default @everyone role which is used to set a room public
        or private.

        :param room: Room pair
        :param member_or_role: Member or role to be added or removed
        :param new_value: New permissions value
        """
        voice_channel = room.voice_channel

        voice_overwrite = voice_channel.overwrites_for(member_or_role)
        if new_value is not None:
            voice_overwrite.update(connect=new_value)
            await voice_channel.set_permissions(
                member_or_role,
                overwrite=voice_overwrite
            )
        else:
            await voice_channel.set_permissions(member_or_role, overwrite=None)

    @voiceroom.command(name="public")
    @VoiceroomsDecorators.pass_voiceroom
    async def set_public(self, context: Context, *_, **kwargs) -> None:
        """
        Set current voice room to public.

        This sets the default connection permissions to None instead of
        True since what we want is to default to the server base perms
        which would allow the server to control which roles get to join
        using role perms.

        :param context: Command context
        """
        room: RoomPair = kwargs["room"]
        everyone = context.guild.default_role
        await self.update_room_membership(room, everyone, None)
        await send_simple_embed(context, "voicerooms_public")
        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_public").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id
            )
        )

        room.current_mode = RoomMode.PUBLIC
        await room.unmute_all(self.get_mute(context.guild.id))

    @voiceroom.command(name="joinmute")
    @VoiceroomsDecorators.pass_voiceroom
    async def set_joinmute(
            self,
            context: Context,
            *,
            mute_time: Optional[int],
            **kwargs
    ) -> None:
        """
        Set the current voice room to joinmute mode.

        This will temporarily mute every new member who joins the room
        for a configured amount of time

        :param context: Command context
        :param mute_time: Amount of time new joins are muted for
        """
        room: RoomPair = kwargs["room"]

        # Check if mute_time is valid
        if mute_time is None:
            room.joinmute_seconds = 0
            await send_simple_embed(context, "voicerooms_permmute")
        elif 0 < mute_time <= voiceroom_max_mute_time:
            room.joinmute_seconds = mute_time
            await send_simple_embed(context, "voicerooms_joinmute", mute_time)
        else:
            raise OpheliaCommandError(
                "voicerooms_mute_too_long",
                voiceroom_max_mute_time
            )

        # Underlying permissions are the same as public rooms
        everyone = context.guild.default_role
        await self.update_room_membership(room, everyone, None)

        # Update room mode
        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_joinmute").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                time=mute_time
            )
        )
        room.current_mode = RoomMode.JOINMUTE

    @voiceroom.command(name="private")
    @VoiceroomsDecorators.pass_voiceroom
    async def set_private(self, context: Context, *_, **kwargs) -> None:
        """
        Set current voice room to private.

        :param context: Command context
        """
        room: RoomPair = kwargs["room"]
        everyone = context.guild.default_role
        await self.update_room_membership(room, everyone, False)
        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_private").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id
            )
        )
        await send_simple_embed(context, "voicerooms_private")
        room.current_mode = RoomMode.PRIVATE
        await room.unmute_all(self.get_mute(context.guild.id))

        for member in vc_members(room.voice_channel):
            await self.update_room_membership(room, member, True)

    @voiceroom.command(name="end")
    @VoiceroomsDecorators.pass_voiceroom
    async def room_end(self, context: Context, *_, **kwargs) -> None:
        """
        Delete current room.

        :param context: Command context
        """
        room: RoomPair = kwargs["room"]
        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_delete_room").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id
            )
        )

        await self.delete_room(context.author.id)

    @voiceroom.command(name="add")
    @VoiceroomsDecorators.pass_voiceroom
    async def room_add(
            self,
            context: Context,
            *,
            added: Union[Member, Role],
            **kwargs
    ) -> None:
        """
        Add a role or user to a voice room.

        :param context: Command context
        :param added: Discord member or role
        """
        room: RoomPair = kwargs["room"]
        await self.update_room_membership(room, added, True)
        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_add").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                target=escape_formatting(added.name),
                target_id=added.id
            )
        )
        await send_simple_embed(context, "voicerooms_add", added.mention)

    @voiceroom.command(name="remove", aliases=["kick"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_remove(
            self,
            context: Context,
            *,
            removed: Union[Member, Role],
            **kwargs
    ) -> None:
        """
        Remove a role or user from a voice room.

        :param context: Command context
        :param removed: Discord member or role
        """
        room: RoomPair = kwargs["room"]

        if isinstance(removed, Role) and "mod" in removed.name.lower():
            raise OpheliaCommandError("voicerooms_remove_mod")

        if context.author == removed:
            raise OpheliaCommandError("voicerooms_remove_self")

        await self.update_room_membership(room, removed, None)
        await send_simple_embed(context, "voicerooms_remove", removed.mention)

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_remove").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                target=escape_formatting(removed.name),
                target_id=removed.id
            )
        )

        if isinstance(removed, Member):
            if in_vc(removed, room.voice_channel):
                await removed.move_to(None)
        else:
            for member in vc_members(room.voice_channel):
                if removed in member.roles:
                    await member.move_to(None)

    @voiceroom.command(name="blacklist", aliases=["ban"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_blacklist(
            self,
            context: Context,
            *,
            removed: Member,
            **kwargs
    ) -> None:
        """
        Blacklist a member from a voiceroom.

        :param context: Command context
        :param removed: Discord member or role
        """
        room: RoomPair = kwargs["room"]

        if context.author == removed:
            raise OpheliaCommandError("voicerooms_remove_self")

        await self.update_room_membership(room, removed, False)
        await send_simple_embed(
            context,
            "voicerooms_blacklist",
            removed.mention
        )

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_blacklist").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                target=escape_formatting(removed.name),
                target_id=removed.id
            )
        )

        if in_vc(removed, room.voice_channel):
            await removed.move_to(None)

    @voiceroom.command(name="unblacklist", aliases=["unban"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_unblacklist(
            self,
            context: Context,
            *,
            removed: Member,
            **kwargs
    ) -> None:
        """
        Remove a member from a room blacklist.

        :param context: Command context
        :param removed: Discord member to remove from blacklist
        """
        room: RoomPair = kwargs["room"]

        await self.update_room_membership(room, removed, None)
        await send_simple_embed(
            context,
            "voicerooms_unblacklist",
            removed.mention
        )

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_unblacklist").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                target=escape_formatting(removed.name),
                target_id=removed.id
            )
        )

    @voiceroom.command(name="mute", aliases=["silence"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_mute(
            self,
            context: Context,
            *,
            member: Member,
            **kwargs
    ) -> None:
        """
        Mute a member.

        :param context: Command context
        :param member: Member to mute
        """
        room: RoomPair = kwargs["room"]

        if context.author == member:
            raise OpheliaCommandError("voicerooms_mute_self")

        if not in_vc(member, room.voice_channel):
            raise OpheliaCommandError("voicerooms_mute_not_present")

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_mute").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                target=escape_formatting(member.name),
                target_id=member.id
            )
        )

        await room.mute_user(member, self.get_mute(context.guild.id))
        await send_simple_embed(context, "voicerooms_mute", member.mention)

    @voiceroom.command(name="unmute", aliases=["unsilence"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_unmute(
            self,
            context: Context,
            *,
            member: Member,
            **kwargs
    ) -> None:
        """
        Unmte a member.

        :param context: Command context
        :param member: Member to mute
        """
        room: RoomPair = kwargs["room"]

        if context.author == member:
            raise OpheliaCommandError("voicerooms_unmute_self")

        if not in_vc(member, room.voice_channel):
            raise OpheliaCommandError("voicerooms_unmute_not_present")

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_unmute").format(
                room=room.voice_channel.name,
                name=escape_formatting(context.author.name),
                id=context.author.id,
                target=escape_formatting(member.name),
                target_id=member.id
            )
        )

        await room.unmute_user(member, self.get_mute(context.guild.id))
        await send_simple_embed(context, "voicerooms_unmute", member.mention)

    @voiceroom.command(name="name", aliases=["rename"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_name(
            self,
            context: Context,
            *,
            new_name: str,
            **kwargs
    ) -> None:
        """
        Set the name of the voice room.

        :param context: Command context
        :param new_name: New room name
        """
        if await self.name_filter.bad_name(context.guild.id, new_name):
            raise OpheliaCommandError("voicerooms_name_invalid")

        room: RoomPair = kwargs["room"]
        prev: str = room.voice_channel.name

        try:
            await room.rename(new_name)
        except RoomRateLimited as e:
            raise OpheliaCommandError("voicerooms_ratelimited") from e
        except HTTPException as e:
            raise OpheliaCommandError("voicerooms_name_invalid") from e

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_rename").format(
                name=escape_formatting(context.author.name),
                id=context.author.id,
                prev=escape_formatting(prev),
                curr=escape_formatting(new_name)
            )
        )

        await send_simple_embed(context, "voicerooms_name", new_name)

    @voiceroom.command(name="size", aliases=["resize"])
    @VoiceroomsDecorators.pass_voiceroom
    async def room_size(
            self,
            context: Context,
            *,
            size: int,
            **kwargs
    ) -> None:
        """
        Set the size of the voice room.

        :param context: Command context
        :param size: New room size
        """
        room: RoomPair = kwargs["room"]
        prev: int = room.voice_channel.user_limit

        try:
            await room.voice_channel.edit(user_limit=size)
            await self.message_buffer.log_system_msg(
                log_channel=room.log_channel,
                text_channel=room.text_channel,
                text=disp_str("voicerooms_log_resize").format(
                    name=escape_formatting(context.author.name),
                    id=context.author.id,
                    prev=prev,
                    curr=size
                )
            )

            await send_simple_embed(context, "voicerooms_size")
        except (*ARGUMENT_FAIL_EXCEPTIONS, KeyError, ValueError) as e:
            raise OpheliaCommandError("voicerooms_size_invalid") from e

    @voiceroom.command(name="bitrate")
    @VoiceroomsDecorators.pass_voiceroom
    async def room_bitrate(
            self,
            context: Context,
            *,
            bitrate: int,
            **kwargs
    ) -> None:
        """
        Set the bitrate of the voice room.

        :param context: Command context
        :param bitrate: New bitrate
        """
        room: RoomPair = kwargs["room"]
        prev: int = room.voice_channel.bitrate

        try:
            await room.voice_channel.edit(bitrate=bitrate * 1000)
            await self.message_buffer.log_system_msg(
                log_channel=room.log_channel,
                text_channel=room.text_channel,
                text=disp_str("voicerooms_log_bitrate").format(
                    name=escape_formatting(context.author.name),
                    id=context.author.id,
                    prev=prev / 1000,
                    curr=bitrate
                )
            )

            await send_simple_embed(context, "voicerooms_bitrate", bitrate)
        except ARGUMENT_FAIL_EXCEPTIONS as e:
            raise OpheliaCommandError("voicerooms_bitrate_invalid") from e

    async def transfer_room(
            self,
            room: RoomPair,
            old_owner: Member,
            new_owner: Member
    ) -> None:
        """
        Transfer ownership of a room from one user to another user.

        :param room: Pair of rooms
        :param old_owner: Previous owner
        :param new_owner: New Owner
        """
        # Check if new owner is a bot
        if new_owner.bot:
            raise OpheliaCommandError("voicerooms_transfer_bot")

        # Check if member already owns a room
        if new_owner.id in self.rooms:
            raise OpheliaCommandError("voicerooms_transfer_already_owner")

        try:
            await room.transfer(
                old_owner,
                new_owner,
                self.get_mute(new_owner.guild.id)
            )
        except RoomRateLimited as e:
            raise OpheliaCommandError("voicerooms_ratelimited") from e

        old_id = old_owner.id
        new_id = new_owner.id

        self.text_room_map[room.text_channel.id] = new_id
        self.vc_room_map[room.voice_channel.id] = new_id
        self.rooms[new_id] = self.rooms.pop(old_id)

        await self.message_buffer.log_system_msg(
            log_channel=room.log_channel,
            text_channel=room.text_channel,
            text=disp_str("voicerooms_log_transfer").format(
                name=escape_formatting(old_owner.name),
                id=old_id,
                new_name=escape_formatting(new_owner.name),
                new_id=new_id
            )
        )

        await room.text_channel.edit(
            topic=disp_str(
                "voicerooms_topic_format"
            ).format(new_owner.display_name)
        )

    @voiceroom.command(name="transfer")
    @VoiceroomsDecorators.pass_voiceroom
    async def ownership_transfer(
            self,
            context: Context,
            *,
            new_owner: Member,
            **kwargs
    ) -> None:
        """
        Command to transfer ownership of a room to another user.

        :param context: Command context
        :param new_owner: New owner
        """
        room: RoomPair = kwargs["room"]

        # Check if member is in the voice room
        if not in_vc(new_owner, room.voice_channel):
            raise OpheliaCommandError("voicerooms_transfer_bad_owner")

        await self.transfer_room(room, context.author, new_owner)
        await send_simple_embed(
            context,
            "voicerooms_transfer",
            new_owner.mention
        )

    @voiceroom.command(name="list", aliases=["rooms", "knock"])
    async def list_rooms(self, context: Context) -> None:
        """
        Command to list all voicerooms and to allow users to knock on
        them to request for access.

        :param context: Command context
        """
        non_private_rooms: List[Tuple[int, RoomPair]] = []
        private_rooms: List[Tuple[int, RoomPair]] = []

        for owner_id, room in self.rooms.items():
            if room.voice_channel.guild.id == context.guild.id:
                if room.current_mode == RoomMode.PRIVATE:
                    private_rooms.append((owner_id, room))
                else:
                    non_private_rooms.append((owner_id, room))

        if not non_private_rooms and not private_rooms:
            await send_simple_embed(context, "voicerooms_list_no_rooms")
            return

        rooms_desc: str = ""

        pub_rooms_descs: List[str] = []
        if non_private_rooms:
            for (owner_id, room) in non_private_rooms:
                pub_rooms_descs.append(
                    disp_str("voicerooms_public_room").format(
                        name=room.voice_channel.name,
                        owner_id=owner_id
                    )
                )

            rooms_desc += disp_str("voicerooms_public_list").format(
                pub="\n".join(pub_rooms_descs)
            )

        priv_rooms_descs: List[str] = []
        if private_rooms:
            owner_id: int
            room: RoomPair
            for num, (owner_id, room) in enumerate(private_rooms):
                priv_rooms_descs.append(
                    disp_str("voicerooms_private_room").format(
                        num=num + 1,  # So that it starts from 1
                        name=room.voice_channel.name,
                        owner_id=owner_id
                    )
                )

            rooms_desc += disp_str("voicerooms_private_list").format(
                priv="\n".join(priv_rooms_descs)
            )

        await send_simple_embed(context, "voicerooms_list_rooms", rooms_desc)

        # Wait for knocking
        if private_rooms:
            try:
                message = await get_input(
                    self.bot,
                    context,
                    settings.short_timeout,
                    check=lambda txt: (
                            txt.isnumeric()
                            and 0 < int(txt) <= len(private_rooms)
                    )
                )

                owner_id, room = private_rooms[int(message.content) - 1]

                # Knock confirm
                await send_simple_embed(
                    context,
                    "voicerooms_knock_confirm",
                    owner_id
                )

                # Sending the knocking message
                await send_message(
                    channel=room.text_channel,
                    text=disp_str("voicerooms_knock").format(
                        owner_id=owner_id,
                        mention=context.author.mention
                    )
                )

            except asyncio.exceptions.TimeoutError:
                return

    @voiceroom.command(name="forcetransfer", aliases=["ftransfer"])
    @commands.has_guild_permissions(administrator=True)
    async def force_transfer(
            self,
            context: Context,
            old_owner: Member,
            new_owner: Member
    ) -> None:
        """
        Command to force a transfer form a member to another member.

        :param context: Command context
        :param old_owner: Old owner
        :param new_owner: New owner
        """
        if old_owner.id not in self.rooms:
            raise OpheliaCommandError("voicerooms_transfer_bad_old_owner")

        room: RoomPair = self.rooms[old_owner.id]
        await self.transfer_room(room, old_owner, new_owner)
        await send_simple_embed(
            context,
            "voicerooms_transfer",
            new_owner.mention
        )

    @voiceroom.command(name="setup", aliases=["generator", "gen"])
    @commands.has_guild_permissions(administrator=True)
    async def create_generator(self, context: Context) -> None:
        """
        Configure voice room generator.

        :param context: Command context
        """
        message = await send_simple_embed(
            context,
            "voicerooms_generator",
            colour=Colour(settings.embed_color_important)
        )

        await response_config(
            bot=self.bot,
            context=context,
            message=message,
            config_items=VOICEROOMS_GENERATOR_CONFIG,
            response_call=self.confirm_create_generator,
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            timeout_exception=OpheliaCommandError("voicerooms_timeout"),
            response_tries=CONFIG_MAX_TRIES
        )

    async def confirm_create_generator(
            self,
            context: Context,
            config_vars: dict
    ) -> None:
        """
        Confirm creation of generator.

        :param context: Command context
        :param config_vars: Configuration variables
        """
        author = context.author

        text_category = config_vars["text_category"]
        voice_category = config_vars["voice_category"]
        generator_channel: VoiceChannel = config_vars["generator_channel"]
        log_channel = config_vars["log_channel"]

        sample_voice_channel: VoiceChannel = config_vars["sample_voice_channel"]
        sample_text_channel: TextChannel = config_vars["sample_text_channel"]

        default_voice_perms = sample_voice_channel.overwrites
        owner_voice_perms = sample_voice_channel.overwrites_for(author)
        default_voice_perms.pop(author, None)

        default_text_perms = sample_text_channel.overwrites
        owner_text_perms = sample_voice_channel.overwrites_for(author)
        default_text_perms.pop(author, None)

        generator = Generator(
            voice_category=voice_category,
            text_category=text_category,
            generator_channel=generator_channel,
            default_voice_perms=default_voice_perms,
            owner_voice_perms=owner_voice_perms,
            default_text_perms=default_text_perms,
            owner_text_perms=owner_text_perms,
            log_channel=log_channel
        )

        self.generators[generator_channel.id] = generator
        await send_simple_embed(
            context,
            "voicerooms_generator_success",
            generator_channel.name
        )

    @voiceroom.command(name="updategen", aliases=["updategenerator", "ug"])
    @VoiceroomsDecorators.pass_voiceroom
    @commands.has_guild_permissions(administrator=True)
    async def generator_update(
            self,
            context: Context,
            *,
            channel_id_str: str,
            **kwargs
    ) -> None:
        """
        Update generator permission settings.

        :param context: Command context
        :param channel_id_str: Generator ID as a string
        """
        guild: Guild = context.guild
        if not channel_id_str.isnumeric():
            raise OpheliaCommandError("voicerooms_error_not_channel_id")

        channel_id = int(channel_id_str)
        channel = guild.get_channel(channel_id)
        if channel_id not in self.generators or channel is None:
            raise OpheliaCommandError("voicerooms_error_invalid_channel")

        room: RoomPair = kwargs["room"]
        author = context.author

        prompt = await send_simple_embed(context.channel, "voicerooms_update")

        await response_switch(
            bot=self.bot,
            context=context,
            message=prompt,
            options={
                "y": self.confirm_update_generator(room, author, channel),
                "n": self.cancel_update_generator
            },
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            timeout_exception=OpheliaCommandError("voicerooms_timeout")
        )

    def confirm_update_generator(
            self,
            room: RoomPair,
            author: Member,
            generator_channel: VoiceChannel
    ) -> Callable:
        """
        Confirm generator update.

        :param room: Room pair used as a template
        :param author: Room owner
        :param generator_channel: Generator to be updated
        """

        async def func(context: Context) -> None:
            """Internal function."""
            default_voice_perms = room.voice_channel.overwrites
            owner_voice_perms = room.voice_channel.overwrites_for(author)
            default_voice_perms.pop(author, None)

            default_text_perms = room.text_channel.overwrites
            owner_text_perms = room.text_channel.overwrites_for(author)
            default_text_perms.pop(author, None)

            self.generators[generator_channel.id].update_perms(
                default_voice_perms=default_voice_perms,
                owner_voice_perms=owner_voice_perms,
                default_text_perms=default_text_perms,
                owner_text_perms=owner_text_perms
            )

            await send_simple_embed(context, "voicerooms_update_confirm")

        return func

    @staticmethod
    async def cancel_update_generator(context: Context) -> None:
        """
        Cancel generator update.

        :param context: Command context
        :param config_vars: Ignored
        """
        await send_simple_embed(context, "voicerooms_update_cancel")

    @voiceroom.command(name="listgen", aliases=["listgenerators", "lg"])
    @commands.has_guild_permissions(administrator=True)
    async def generator_list(self, context: Context) -> None:
        """
        List all generators in a server.

        :param context: Command context
        """
        guild: Guild = context.guild
        string_builder = []
        for channel_id in self.generators:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                string_builder.append(
                    disp_str("voicerooms_list_item").format(
                        channel.id,
                        channel.name
                    )
                )

        await send_message_embed(
            channel=context,
            title=disp_str("voicerooms_list_title"),
            desc="\n".join(string_builder)
        )

    @voiceroom.command(name="listall", aliases=["la"])
    @commands.is_owner()
    async def generator_listall(self, context: Context) -> None:
        """
        List all generators.

        :param context: Command context
        """
        string_builder = []
        for channel_id in self.generators:
            channel = self.bot.get_channel(channel_id)
            name = (
                disp_str("voicerooms_list_none")
                if channel is None else channel.name
            )

            string_builder.append(
                disp_str("voicerooms_list_item").format(channel_id, name)
            )

        await send_message_embed(
            channel=context,
            title=disp_str("voicerooms_listall_title"),
            desc="\n".join(string_builder)
        )

    @voiceroom.command(name="admindelete", aliases=["admindel", "ad"])
    @commands.has_guild_permissions(administrator=True)
    async def generator_admindelete(
            self,
            context: Context,
            *,
            channel_id_str: str
    ) -> None:
        """
        Delete a generator from a server.

        :param context: Command context
        :param channel_id_str: String of generator voice channel ID
        """
        guild: Guild = context.guild
        if not channel_id_str.isnumeric():
            raise OpheliaCommandError("voicerooms_error_not_channel_id")

        channel_id = int(channel_id_str)
        channel = guild.get_channel(channel_id)
        if channel_id not in self.generators or channel is None:
            raise OpheliaCommandError("voicerooms_error_invalid_channel")

        self.generators.pop(channel_id, None)
        await self.save_generators()
        await send_simple_embed(context, "voicerooms_delete_success")

    @voiceroom.command(name="filter", aliases=["f"])
    @commands.has_guild_permissions(administrator=True)
    async def list_filters(
            self,
            context: Context,
            *,
            regex_str: Optional[str]
    ) -> None:
        """
        Adds or removes a room name filter from a guild, or lists all
        filters if no arguments are provided.

        :param context: Command context
        :param regex_str: Regex filter to add or remove
        """
        if regex_str is None:
            await send_simple_embed(
                context,
                "voicerooms_filter_list",
                "\n".join(
                    f"`{filt}`" for filt
                    in await self.name_filter.list_filters(context.guild.id)
                )
            )
            return

        try:
            added = await self.name_filter.add_filter(
                context.guild.id,
                regex_str
            )

            if added:
                await send_simple_embed(
                    context,
                    "voicerooms_filter_added",
                    regex_str
                )
            else:
                await send_simple_embed(
                    context,
                    "voicerooms_filter_deleted",
                    regex_str
                )
        except re.error as e:
            raise OpheliaCommandError("voicerooms_filter_regex_error") from e

    @voiceroom.command(name="forcedelete", aliases=["forcedel", "fd"])
    @commands.is_owner()
    async def generator_forcedelete(
            self,
            context: Context,
            *,
            channel_id_str: str
    ) -> None:
        """
        Force delete a generator.

        :param context: Command context
        :param channel_id_str: String of generator voice channel ID
        """
        channel_id = int(channel_id_str)
        if channel_id not in self.generators:
            raise OpheliaCommandError("voicerooms_error_invalid_channel")

        self.generators.pop(channel_id, None)
        await self.save_generators()
        await send_simple_embed(context, "voicerooms_delete_success")

    async def delete_room(self, owner_id: int) -> None:
        """
        Delete room.

        This method need not be used on bot shutdown since it would do
        the necessary steps of cleaning up the dictionary mappings.

        :param owner_id: Room owner
        """
        room = self.rooms.pop(owner_id, None)
        if room is None:
            return

        self.vc_room_map.pop(room.voice_channel.id, None)
        self.text_room_map.pop(room.text_channel.id, None)
        await room.destroy()
