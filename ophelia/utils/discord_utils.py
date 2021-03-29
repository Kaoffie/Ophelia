"""
Discord utilities module.

A collection of useful functions that retrieve stuff from Discord.
"""
import functools
import re
from typing import Callable, Dict, List, Optional, Union

from discord import (
    CategoryChannel, Forbidden, Guild, HTTPException, InvalidArgument, Member,
    NotFound, PermissionOverwrite, Permissions, RawReactionActionEvent, Role,
    TextChannel, VoiceChannel
)
from discord.abc import GuildChannel
from discord.ext.commands import Context

FETCH_FAIL_EXCEPTIONS = (NotFound, Forbidden, HTTPException)
ARGUMENT_FAIL_EXCEPTIONS = (NotFound, Forbidden, HTTPException, InvalidArgument)

CHANNEL_REGEX = r"<#([0-9]+)>"
ROLE_REGEX = r"<@&([0-9]+)>"
USER_REGEX = r"<@([0-9]+)>"


async def get_id(repr_str: Union[str, int], regex: str) -> Optional[int]:
    """
    Extracts an ID from either a string or integer.

    :param repr_str: ID string or integer
    :param regex: Regex matcher for ID
    :return: Integer containing required ID, or None if not found
    """
    if isinstance(repr_str, int):
        # If repr_str is just the ID itself
        return repr_str

    if isinstance(repr_str, str):
        # If repr_str is a string repr_stresentation of an integer
        id_str = repr_str.strip()
        if id_str.isnumeric():
            return int(id_str)

        # If repr contains integer matched by regex
        matches = re.search(regex, id_str)
        if matches:
            return int(matches.group(1))

    return None


async def get_channel_id(user_input: str, **_) -> Optional[int]:
    """
    Wrapper for get_id use for extracting channel IDs.

    :param user_input: User input
    :return: Extracted channel ID, or none if not found
    """
    return await get_id(user_input, CHANNEL_REGEX)


async def extract_role(
        role_repr: Union[str, int],
        guild: Guild
) -> Optional[Role]:
    """
    Extracts a role from a string or a role ID.

    :param role_repr: Integer role ID or a String of a role ID or role
        mention
    :param guild: Guild to search for the role in
    :return: Role extracted from role_repr if found, else None
    """
    role_id = await get_id(role_repr, ROLE_REGEX)
    if role_id is None:
        return None

    return guild.get_role(role_id)


async def extract_role_config(
        context: Context,
        user_input: str
) -> Optional[Role]:
    """
    Wrapper for extract_role.

    :param context: Command context
    :param user_input: User input to parse
    :return: Role extracted from user input, or None if no roles found
    """
    return await extract_role(user_input, context.guild)


async def extract_channel(
        channel_repr: Union[str, int],
        guild: Guild
) -> Optional[GuildChannel]:
    """
    Extracts a channel from a string or channel ID.

    :param channel_repr: Integer channel ID or a String of a channel ID
        or channel mention
    :param guild: Guild to search for channel in
    :return: Channel extracted from channel_repr if found, else None
    """
    channel_id = await get_id(channel_repr, CHANNEL_REGEX)
    if channel_id is None:
        return None

    return guild.get_channel(channel_id)


async def extract_channel_config(
        context: Context,
        user_input: str
) -> Optional[GuildChannel]:
    """
    Wrapper for extract_channel.

    :param context: Command context
    :param user_input: User input to parse
    :return: Channel extracted from user input, or None if no channels
        found
    """
    return await extract_channel(user_input, context.guild)


async def extract_category_config(
        context: Context,
        user_input: str
) -> Optional[CategoryChannel]:
    """
    Wrapper for extract_channel that finds a category channel.

    :param context: Command context
    :param user_input: User input to parse
    :return: Category channel extracted from user input, or None if no
        channels found
    """
    channel = await extract_channel(user_input, context.guild)
    if isinstance(channel, CategoryChannel):
        return channel

    return None


async def extract_text_config(
        context: Context,
        user_input: str
) -> Optional[TextChannel]:
    """
    Wrapper for extract_channel that finds a text channel.

    :param context: Command context
    :param user_input: User input to parse
    :return: Text channel extracted from user input, or None if no
        channels found
    """
    channel = await extract_channel(user_input, context.guild)
    if isinstance(channel, TextChannel):
        return channel

    return None


async def extract_voice_config(
        context: Context,
        user_input: str
) -> Optional[VoiceChannel]:
    """
    Wrapper for extract_channel that finds a voice channel.

    :param context: Command context
    :param user_input: User input to parse
    :return: Voice channel extracted from user input, or None if no
        channels found
    """
    channel = await extract_channel(user_input, context.guild)
    if isinstance(channel, VoiceChannel):
        return channel

    return None


def filter_self_react(func: Callable) -> Callable:
    """
    Decorator for checking if reaction event was sent by someone who is
    not the bot itself.

    :param func: Async function to be wrapped
    :return: Wrapper function
    """

    @functools.wraps(func)
    async def wrapped(
            self,
            payload: RawReactionActionEvent,
            *args,
            **kwargs
    ) -> None:
        """
        Inner function.

        :param self: Cog instance
        :param payload: Raw discord action payload to extract guild
            ID from
        :param args: arguments
        :param kwargs: Keyword arguments
        """
        user_id = payload.user_id
        if user_id == self.bot.user.id:
            return

        return await func(self, payload, *args, **kwargs)

    return wrapped


async def overwrite_to_dict(overwrite: PermissionOverwrite) -> dict:
    """
    Save permission overwrites to dictionaries.

    :param overwrite: Permission overwrite to save
    :return: Dictionary representing permission overwrite
    """
    allow, deny = overwrite.pair()
    return {
        "allow": allow.value,
        "deny": deny.value
    }


async def multioverwrite_to_dict(
        overwrites: Dict[Union[Member, Role], PermissionOverwrite]
) -> dict:
    """
    Save a dictionary of permission overwrites to dictionaries.

    :param overwrites: Dictionary of permission overwrites
    :return: Dictionary representing permission overwrites to save in
        YAML
    """
    repr_dict = {}
    for index, overwrite in overwrites.items():
        is_member = bool(isinstance(index, Member))

        repr_dict[str(index.id)] = {
            "is_member": is_member,
            "overwrite": await overwrite_to_dict(overwrite)
        }

    return repr_dict


async def dict_to_overwrite(overwrite_dict: dict) -> PermissionOverwrite:
    """
    Load permission overwrite from dictionary.

    :param overwrite_dict: Dictionary representing permission overwrite
    :return: Discord permission overwrite object
    """
    allow = Permissions(overwrite_dict.get("allow", 0))
    deny = Permissions(overwrite_dict.get("deny", 0))
    return PermissionOverwrite.from_pair(allow, deny)


async def dict_to_multioverwrite(
        guild: Guild,
        overwrites_dict: dict
) -> Dict[Union[Member, Role], PermissionOverwrite]:
    """
    Generates a dictionary of members/roles to overwrites from a config
    dictionary.

    :param guild: Discord guild
    :param overwrites_dict: Source dictionary
    :return: Dictionary of permission overwrites indexed by member or
        role
    """
    overwrites = {}
    for index_id_str, fields in overwrites_dict.items():
        try:
            index_id = int(index_id_str)
            is_member = fields["is_member"]
            overwrite = await dict_to_overwrite(fields["overwrite"])

            if is_member:
                member = await guild.fetch_member(index_id)
                overwrites[member] = overwrite
            else:
                role = guild.get_role(index_id)
                if role is None:
                    continue

                overwrites[role] = overwrite
        except (*FETCH_FAIL_EXCEPTIONS, KeyError, ValueError):
            continue

    return overwrites


def in_vc(member: Member, channel: VoiceChannel) -> bool:
    """
    Check if a member is in VC without using channel.members.

    :param member: Member to check
    :param channel: Channel to check
    :return: Whether member is connected to channel
    """
    voice_state = member.voice
    if voice_state is not None:
        member_channel = voice_state.channel
        if channel is not None:
            return member_channel.id == channel.id

    return False


# pylint: disable=protected-access
def vc_is_empty(channel: VoiceChannel) -> bool:
    """
    Check if a VC is empty without using channel.members.

    This is an emergency patch for servers that have stage channels that
    return as NoneTypes in voice states. We are thus forced to use a
    protected member because there is no other alternative.

    :param channel: Channel to check
    :return: Whether channel is empty
    """
    # noinspection PyProtectedMember
    for _, state in channel.guild._voice_states.items():
        if state.channel is not None and state.channel.id == channel.id:
            return False

    return True


def vc_members(channel: VoiceChannel) -> List[Member]:
    """
    Get a list of members connected to a VC.

    This is an emergency patch for servers that have stage channels that
    return as NoneTypes in voice states. This implementation is nearly
    identical to the original implementation except for an extra check
    if state.channel is not None.

    :param channel: Voice channel
    :return: Members connected to voice channel
    """
    members: List[Member] = []

    # noinspection PyProtectedMember
    for user_id, state, in channel.guild._voice_states.items():
        if state.channel is not None and state.channel.id == channel.id:
            member = channel.guild.get_member(user_id)
            if member is not None:
                members.append(member)

    return members
# pylint: enable=protected-access
