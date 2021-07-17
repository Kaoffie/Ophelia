"""Voice room generator module."""
import copy
from typing import Dict, Optional, Union

from discord import (
    CategoryChannel, HTTPException, InvalidData, Member, PermissionOverwrite,
    Role, TextChannel, VoiceChannel
)

from ophelia.output.output import disp_str, send_message
from ophelia.utils.discord_utils import (
    dict_to_multioverwrite, dict_to_overwrite, FETCH_FAIL_EXCEPTIONS,
    multioverwrite_to_dict, overwrite_to_dict
)
from ophelia.voicerooms.name_filter import (
    NameFilterManager
)
from ophelia.voicerooms.rooms.roompair import RoomPair


class GeneratorLoadError(Exception):
    """When generator fails to load from configuration."""


class RoomCreationError(Exception):
    """When bot fails to create a room."""


class Generator:
    """
    Voice room generator.

    Generators come in the form of voice channels that create new
    channel pairs when joined. These voice channels can be edited by
    users and are automatically deleted when empty; temporary text
    channels are also logged.
    """

    __slots__ = [
        "text_category",
        "voice_category",
        "generator_channel",
        "default_text_perms",
        "owner_text_perms",
        "default_voice_perms",
        "owner_voice_perms",
        "log_channel"
    ]

    def __init__(
            self,
            voice_category: CategoryChannel,
            text_category: CategoryChannel,
            generator_channel: VoiceChannel,
            default_text_perms: Dict[Union[Member, Role], PermissionOverwrite],
            owner_text_perms: Optional[PermissionOverwrite],
            default_voice_perms: Dict[Union[Member, Role], PermissionOverwrite],
            owner_voice_perms: Optional[PermissionOverwrite],
            log_channel: TextChannel
    ) -> None:
        """
        Initializer for the Generator class.

        :param voice_category: Category that new voice channels will be
            created in
        :param text_category: Category that new text channels will be
            created in
        :param generator_channel: Voice channel that generates new rooms
            using this generator
        :param default_text_perms: Default text channel permissions
        :param owner_text_perms: Default text channel permissions for
            room owner
        :param default_voice_perms: Default voice channel permissions
        :param owner_voice_perms: Default voice channel permissions for
            room owner
        :param log_channel: Channel to log all text messages to
        """
        self.voice_category = voice_category
        self.text_category = text_category
        self.generator_channel = generator_channel

        # Initialize
        self.default_text_perms = {}
        self.owner_text_perms = None
        self.default_voice_perms = {}
        self.owner_voice_perms = None

        self.update_perms(
            default_text_perms,
            owner_text_perms,
            default_voice_perms,
            owner_voice_perms
        )

        self.log_channel = log_channel

    async def update_perms(
            self,
            default_text_perms: Dict[Union[Member, Role], PermissionOverwrite],
            owner_text_perms: Optional[PermissionOverwrite],
            default_voice_perms: Dict[Union[Member, Role], PermissionOverwrite],
            owner_voice_perms: Optional[PermissionOverwrite]
    ) -> None:
        self.default_text_perms = default_text_perms
        self.default_voice_perms = default_voice_perms
        self.owner_voice_perms = owner_voice_perms

        # Owner should always have read and write permissions in the
        # text channel.
        if owner_text_perms is None:
            self.owner_text_perms = PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        else:
            owner_text_perms.update(
                read_messages=True,
                send_messages=True
            )

        self.owner_text_perms = owner_text_perms

    async def create_room(
            self,
            member: Member,
            name_filter: NameFilterManager
    ) -> Optional[RoomPair]:
        """
        Create a new room pair for a user.

        :param member: Discord member
        :param name_filter: Room name filter, in case the user has a
            username that does not pass the filter rules
        :raises RoomCreationError: When room creation fails
        """
        display_name = member.display_name

        # Run the display name through the filter first
        if await name_filter.bad_name(member.guild.id, display_name):
            # If the name is illegal, just use the member's ID
            display_name = str(member.id)

        text_overwrites = copy.copy(self.default_text_perms)
        if self.owner_text_perms is not None:
            text_overwrites[member] = self.owner_text_perms

        text_channel = await self.text_category.create_text_channel(
            name=disp_str("voicerooms_room_format").format(display_name),
            topic=disp_str("voicerooms_topic_format").format(display_name),
            overwrites=text_overwrites
        )

        voice_overwrites = copy.copy(self.default_voice_perms)
        if self.owner_voice_perms is not None:
            voice_overwrites[member] = self.owner_voice_perms

        voice_channel = await self.voice_category.create_voice_channel(
            name=disp_str("voicerooms_room_format").format(display_name),
            overwrites=voice_overwrites
        )

        room = RoomPair(
            text_channel,
            voice_channel,
            self.log_channel,
            member.id
        )

        try:
            await member.move_to(voice_channel)
            await send_message(
                channel=text_channel,
                text=disp_str("voicerooms_welcome_message").format(
                    member.mention
                )
            )
        except HTTPException as e:
            # User is not connected to voice.
            await room.destroy()
            raise RoomCreationError from e

        return room

    async def to_dict(self) -> dict:
        """
        Generate a dictionary to save in a yaml configuration file.

        :return: Dictionary to save in YAML
        """
        return {
            "voice_category": self.voice_category.id,
            "text_category": self.text_category.id,
            "generator_channel": self.generator_channel.id,
            "default_text_perms": await multioverwrite_to_dict(
                self.default_text_perms
            ),
            "owner_text_perms": await overwrite_to_dict(
                self.owner_text_perms
            ),
            "default_voice_perms": await multioverwrite_to_dict(
                self.default_voice_perms
            ),
            "owner_voice_perms": await overwrite_to_dict(
                self.owner_voice_perms
            ),
            "log_channel": self.log_channel.id
        }

    # noinspection PyUnresolvedReferences
    @classmethod
    async def from_dict(
            cls,
            bot: "OpheliaBot",
            gen_dict: dict
    ) -> "Generator":
        """
        Create a generator from a dictionary.

        :param bot: Ophelia bot instance
        :param gen_dict: Generator configuration dictionary
        :return: Voice room generator
        :raises: GeneratorLoadError: When config fails to load
        """
        try:
            voice_category = await bot.fetch_channel(gen_dict["voice_category"])
            text_category = await bot.fetch_channel(gen_dict["text_category"])
            generator_channel = await bot.fetch_channel(
                gen_dict["generator_channel"]
            )
            log_channel = await bot.fetch_channel(gen_dict["log_channel"])

            guild = voice_category.guild
            default_text_perms = await dict_to_multioverwrite(
                guild,
                gen_dict["default_text_perms"]
            )
            owner_text_perms = await dict_to_overwrite(
                gen_dict["owner_text_perms"]
            )
            default_voice_perms = await dict_to_multioverwrite(
                guild,
                gen_dict["default_voice_perms"]
            )
            owner_voice_perms = await dict_to_overwrite(
                gen_dict["owner_voice_perms"]
            )

            return Generator(
                voice_category,
                text_category,
                generator_channel,
                default_text_perms,
                owner_text_perms,
                default_voice_perms,
                owner_voice_perms,
                log_channel
            )

        except (*FETCH_FAIL_EXCEPTIONS, KeyError, InvalidData) as e:
            raise GeneratorLoadError from e
