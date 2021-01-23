"""
Voice rooms module.

Gives users the power to create and manage their own voice chat channels
instead of relying on pre-defined channels.
"""
import copy
import functools
import os
import re
from typing import Callable, Dict, Optional, Union

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
from ophelia.output import (
    disp_str, response_config, send_message_embed, send_simple_embed
)
from ophelia.output.error_handler import OpheliaCommandError
from ophelia.utils.discord_utils import (
    ARGUMENT_FAIL_EXCEPTIONS
)
from ophelia.voicerooms.rooms.generator import Generator, GeneratorLoadError
from ophelia.voicerooms.message_buffer import MessageBuffer
from ophelia.voicerooms.rooms.roompair import RoomPair, RoomRateLimited
from ophelia.voicerooms.config_options import VOICEROOMS_GENERATOR_CONFIG
from ophelia.voicerooms.name_filter import NameFilterManager

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
        "name_filter"
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
                    self.generators[int(channel_id_str)] = (
                        await Generator.from_dict(self.bot, gen_dict)
                    )
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
            log_channel = self.rooms[owner_id].log_channel

            await self.message_buffer.log_message(log_channel, message)

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
            return

        if after.channel is not None:
            await self.on_voice_join(member, after.channel)

        if before.channel is not None:
            await self.on_voice_leave(member, before.channel)

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
        if channel_id in self.generators:
            await self.on_generator_join(member, self.generators[channel_id])

        if channel_id in self.vc_room_map:
            owner_id = self.vc_room_map[channel_id]
            if member.id == owner_id:
                return

            room: RoomPair = self.rooms[owner_id]
            text_channel = room.text_channel

            # Grant read and write permissions:
            overwrite = text_channel.overwrites_for(member)
            overwrite.update(send_messages=True, read_messages=True)
            await text_channel.set_permissions(member, overwrite=overwrite)

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
        if member.id in self.rooms:
            return

        room: RoomPair = await generator.create_room(member)
        self.rooms[member.id] = room
        self.vc_room_map[room.voice_channel.id] = member.id
        self.text_room_map[room.text_channel.id] = member.id

    async def on_voice_leave(
            self,
            member: Member,
            channel: VoiceChannel
    ) -> None:
        """
        Handles members leaving voice channels.

        :param member: Guild member
        :param channel: Voice channel left
        """
        channel_id = channel.id

        if channel_id in self.vc_room_map:
            owner_id = self.vc_room_map[channel_id]
            room: RoomPair = self.rooms[owner_id]
            text_channel = room.text_channel
            voice_channel = room.voice_channel

            # Check if channel is empty:
            if not voice_channel.members:
                await self.delete_room(owner_id)
                return

            # Before we remove permissions, we check that the user is
            # not an owner.
            if member.id == owner_id:
                return

            # Remove permissions:
            overwrite = text_channel.overwrites_for(member)
            await text_channel.set_permissions(member, overwrite=None)

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
            voice_overwrite.update(view_channel=new_value, connect=new_value)
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

        :param context: Command context
        """
        room: RoomPair = kwargs["room"]
        everyone = context.guild.default_role
        await self.update_room_membership(room, everyone, True)
        await send_simple_embed(context, "voicerooms_public")

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
        await send_simple_embed(context, "voicerooms_private")
        await room.kick_unauthorized()

    @voiceroom.command(name="end")
    @VoiceroomsDecorators.pass_voiceroom
    async def room_end(self, context: Context, *_, **__) -> None:
        """
        Delete current room.

        :param context: Command context
        """
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
        await self.update_room_membership(room, removed, None)
        await send_simple_embed(context, "voicerooms_remove", removed.mention)
        await room.kick_unauthorized()

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

        try:
            await room.rename(new_name)
        except RoomRateLimited as e:
            raise OpheliaCommandError("voicerooms_ratelimited") from e
        except HTTPException as e:
            raise OpheliaCommandError("voicerooms_name_invalid") from e

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
        try:
            await room.voice_channel.edit(user_limit=size)
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
        try:
            await room.voice_channel.edit(bitrate=bitrate * 1000)
            await send_simple_embed(context, "voicerooms_bitrate", bitrate)
        except ARGUMENT_FAIL_EXCEPTIONS as e:
            raise OpheliaCommandError("voicerooms_bitrate_invalid") from e

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
        Transfer ownership of a room to another user.

        :param context: Command context
        :param new_owner: New owner
        """
        room: RoomPair = kwargs["room"]

        # Check if member is a bot
        if new_owner.bot:
            raise OpheliaCommandError("voicerooms_transfer_bot")

        # Check if member already owns a room
        if new_owner.id in self.rooms:
            raise OpheliaCommandError("voicerooms_transfer_already_owner")

        # Check if member is in the voice room
        if new_owner not in room.voice_channel.members:
            raise OpheliaCommandError("voicerooms_transfer_bad_owner")

        try:
            await room.transfer(context.author, new_owner)
        except RoomRateLimited:
            raise OpheliaCommandError("voicerooms_ratelimited")

        old_id = context.author.id
        new_id = new_owner.id

        self.text_room_map[room.text_channel.id] = new_id
        self.vc_room_map[room.voice_channel.id] = new_id
        self.rooms[new_id] = self.rooms.pop(old_id)

        await room.text_channel.edit(
            topic=disp_str(
                "voicerooms_topic_format"
            ).format(new_owner.display_name)
        )

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

    @voiceroom.command(name="list", aliases=["l"])
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
        self.vc_room_map.pop(room.voice_channel.id, None)
        self.text_room_map.pop(room.text_channel.id, None)
        await room.destroy()
