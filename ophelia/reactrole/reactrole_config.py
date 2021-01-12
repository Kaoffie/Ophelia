"""
React configuration module.

Classes for each individual reaction, for each message, and for each
server containing reaction-based roles.

We are disabling pylint's too-few-public-methods here because we're
intentionally using classes and inheritance to modularize the whole role
reaction configuration mess.
"""
# pylint: disable=too-few-public-methods

import asyncio
import os
import re
from typing import Union, List, Optional, Dict, Tuple

import yaml
from loguru import logger

from ophelia import settings

CONFIG_PATH = settings.file_reactrole_config


class InvalidMessageConfigException(Exception):
    """Role reactions configuration exception."""


class InvalidReactConfigException(Exception):
    """Single reaction configuration exception."""


class ReactConfig:
    """Base class for reaction config."""

    __slots__ = ["custom_emote", "emote_id", "emote_name"]

    def __init__(self, emote: Union[int, str]) -> None:
        """
        Initializer for the ReactConfig class.

        :param emote: String or Int representaiton of emote
        """
        self.custom_emote = False
        self.emote_id = 0
        self.emote_name = ""

        if isinstance(emote, int):
            # Minimum Discord snowflake is 2^22
            if emote >= 4194304:
                self.emote_id = emote
                self.custom_emote = True

            # There are unicode emotes with numerical names
            # such as :100: or :1234:
            else:
                self.emote_name = str(emote)

        else:
            self.emote_name = emote


class SingleRoleConfig(ReactConfig):
    """Config for single role reaction."""

    __slots__ = ["role_id"]

    def __init__(self, emote: Union[int, str], role_id: int) -> None:
        """
        Initializer for the SingleRoleConfig class.

        :param emote: String or Int representation of emote
        :param role_id: ID of corresponding role
        """
        super().__init__(emote)
        self.role_id = role_id


class RoleMenuConfig(ReactConfig):
    """Config for role selection menu."""

    __slots__ = ["msg", "regex", "roles"]

    def __init__(
            self,
            emote: Union[int, str],
            dm_msg: str,
            dm_regex: str,
            dm_roles: List[int],
    ) -> None:
        """
        Initializer for the RoleMenuConfig class.

        :param emote: String or Int representation of emote
        :param dm_msg: Message header to send to user
        :param dm_regex: Regex string for matching role names
        :param dm_roles: List of role IDs to add to menu
        :raises re.error: Invalid regex
        """
        super().__init__(emote)
        self.msg = dm_msg
        self.regex = re.compile(dm_regex)

        if isinstance(dm_roles, list):
            self.roles = dm_roles
        else:
            logger.warning("DM roles not a list in role menu config")
            raise InvalidReactConfigException


class MessageConfig:
    """Config for reaction role message."""

    __slots__ = ["message_id", "guild_id", "channel_id", "reacts", "lock"]

    def __init__(self, message_id: str, config_dict: dict) -> None:
        """
        Initializer for the MessageConfig class.

        :param message_id: Message ID
        :param config_dict: Dictionary of config options from yaml
        :raises InvalidMessageConfigException: When role config is invalid
        """
        if not all(
                field in config_dict for field in ["guild", "channel", "reacts"]
        ):
            logger.warning(
                "Invalid react role message config: {}",
                message_id
            )

            raise InvalidMessageConfigException

        self.message_id = message_id
        self.guild_id = config_dict["guild"]
        self.channel_id = config_dict["channel"]
        self.reacts = dict()
        for emote, react_config in config_dict["reacts"].items():
            if "role" in react_config:
                self.reacts[str(emote)] = SingleRoleConfig(
                    emote,
                    react_config["role"]
                )
            elif "dm_msg" in react_config and (
                    "dm_regex" in react_config
                    or "dm_roles" in react_config
            ):
                msg = react_config["dm_msg"]
                regex = react_config.get("dm_regex", "")
                roles = react_config.get("dm_roles", [])

                try:
                    role_menu_config = RoleMenuConfig(emote, msg, regex, roles)
                    self.reacts[str(emote)] = role_menu_config
                except (re.error, InvalidReactConfigException):
                    logger.warning(
                        "Invalid react config: {}",
                        emote
                    )
                    continue

        self.lock = asyncio.Lock()

    def __getitem__(self, emote: str) -> ReactConfig:
        """
        Gets react config from emote representation.

        :param emote: String representation of emote
        :return: ReactConfig corresponding to emote
        :raises TypeError: Invalid emote
        :raises KeyError: Emote not found
        """
        return self.reacts[str(emote)]

    def __contains__(self, emote: str) -> bool:
        """
        Checks if emote is in message config.

        :param emote: String representation of emote
        :return: Boolean of whether emote is contained in message config
        :raises TypeError: Invalid emote
        """
        return str(emote) in self.reacts


class ReactroleConfig:
    """
    Config builder and editor for reaction roles.

    Config format:
    <message_id>:
      guild: <guild_id>
      channel: <channel_id>
      reacts:
        <emote_id/unicode_emoji>:
          role: <role_id>
          OR
          dm_msg: <Message to DM user>
          dm_regex: <Regex to match role list>
          dm_roles:
            - <role_id>
            - <role_id>
    """

    __slots__ = ["message_configs", "config_dict", "lock"]

    def __init__(self) -> None:
        """Initializer for the ReactroleConfig class."""
        logger.debug("Initializing reaction role config.")
        self.message_configs, self.config_dict = self.parse_config()
        self.lock = asyncio.Lock()

    @staticmethod
    def parse_config() -> Tuple[dict, dict]:
        """Parses reactrole configs."""
        if not os.path.exists(CONFIG_PATH):
            return {}, {}

        filtered_settings_dict = {}
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            settings_dict = yaml.safe_load(file)

            message_configs = {}
            for message_id_str, message_dict in settings_dict.items():
                try:
                    message_config = MessageConfig(message_id_str, message_dict)
                    message_configs[message_id_str] = message_config
                    filtered_settings_dict[message_id_str] = message_dict
                except InvalidMessageConfigException:
                    logger.warning(
                        "Invalid message config parsed for message ID: {}",
                        message_id_str
                    )

        return message_configs, filtered_settings_dict

    @staticmethod
    def get_empty_config(guild_id: int, channel_id: int) -> dict:
        """
        Build empty configuration dictionary for new message.

        :param guild_id: ID of guild
        :param channel_id: ID of channel
        :return: Dictionary of empty config
        """
        return {
            "guild": guild_id,
            "channel": channel_id,
            "reacts": {}
        }

    async def save_file(self) -> None:
        """Save config yaml file."""
        with open(CONFIG_PATH, "w", encoding="utf-8") as save_target:
            yaml.dump(
                self.config_dict,
                save_target,
                default_flow_style=False
            )

    async def add_message(
            self,
            message_id: int,
            guild_id: int,
            channel_id: int
    ) -> None:
        """
        Add message to reaction config.

        :param message_id: ID of message
        :param guild_id: ID of guild containing message
        :param channel_id: ID of channel containing message
        """
        message_id_str = str(message_id)
        self.message_configs[message_id_str] = MessageConfig(
            message_id_str,
            self.get_empty_config(guild_id, channel_id)
        )

        self.config_dict[message_id_str] = dict()
        self.config_dict[message_id_str]["guild"] = guild_id
        self.config_dict[message_id_str]["channel"] = channel_id
        self.config_dict[message_id_str]["reacts"] = dict()

    async def add_simple_reaction(
            self,
            message_id: int,
            guild_id: int,
            channel_id: int,
            emote: str,
            role_id: int
    ) -> None:
        """
        Add simple role reaction to message.

        :param message_id: ID of message
        :param guild_id: ID of guild containing message
        :param channel_id: ID of channel containing message
        :param emote: String representation of emote
        :param role_id: ID of role to assign
        """
        async with self.lock:
            message_id_str = str(message_id)
            if message_id_str not in self.message_configs:
                await self.add_message(message_id, guild_id, channel_id)

            message_config = self.message_configs[message_id_str]
            async with message_config.lock:
                message_config.reacts[str(emote)] = SingleRoleConfig(emote,
                                                                     role_id)

            message_id_str = str(message_id)
            self.config_dict[message_id_str]["reacts"][emote] = {}
            react_config = self.config_dict[message_id_str]["reacts"][emote]
            react_config["role"] = role_id

            await self.save_file()

    async def add_dm_reaction(
            self,
            message_id: int,
            guild_id: int,
            channel_id: int,
            emote: Union[int, str],
            dm_msg: str,
            dm_regex: Optional[str],
            dm_roles: Optional[List[int]]
    ) -> None:
        """
        Add DM role menu reaction to message.

        :param message_id: ID of message
        :param guild_id: ID of guild containing message
        :param channel_id: ID of channel containing message
        :param emote: String or integer representation of emote
        :param dm_msg: DM header to send to user
        :param dm_regex: Regex string to match roles
        :param dm_roles: List of roles to add
        :raises re.error: Invalid regex
        :raises InvalidReactConfigException: Invalid role list
        """
        async with self.lock:
            if dm_regex is not None and not isinstance(dm_regex, str):
                raise InvalidReactConfigException

            if dm_roles is not None:
                if isinstance(dm_roles, list):
                    if any(not isinstance(role, int) for role in dm_roles):
                        raise InvalidReactConfigException
                else:
                    raise InvalidReactConfigException

            message_id_str = str(message_id)
            if message_id_str not in self.message_configs:
                await self.add_message(message_id, guild_id, channel_id)

            message_config = self.message_configs[message_id_str]
            async with message_config.lock:
                message_config.reacts[str(emote)] = RoleMenuConfig(
                    emote,
                    dm_msg,
                    dm_regex if dm_regex is not None else "",
                    dm_roles if dm_roles is not None else []
                )

            self.config_dict[message_id_str]["reacts"][emote] = {}
            react_config = self.config_dict[message_id_str]["reacts"][emote]
            react_config["dm_msg"] = dm_msg

            if dm_regex is not None:
                react_config["dm_regex"] = dm_regex
            if dm_roles is not None:
                react_config["dm_roles"] = dm_roles

            await self.save_file()

    async def delete_message(self, message_id: Union[int, str]) -> None:
        """
        Delete message config.

        :param message_id: ID of message
        """
        async with self.lock:
            message_id_str = str(message_id)
            del self.message_configs[message_id_str]
            del self.config_dict[message_id_str]

            await self.save_file()

    async def delete_reaction(
            self,
            message_id: Union[int, str],
            emote: Union[int, str]
    ) -> None:
        """
        Delete emote reaction from message.

        :param message_id: ID of message
        :param emote: String or representation of emote
        """
        async with self.lock:
            message_id_str = str(message_id)
            if message_id_str not in self.message_configs:
                return

            message_config = self.message_configs[message_id_str]
            del_message = False
            async with message_config.lock:
                emote_str = str(emote)
                if emote_str in message_config.reacts:
                    del message_config.reacts[emote_str]

                if not message_config.reacts:
                    del_message = True

            if del_message:
                del self.config_dict[message_id_str]
            else:
                del self.config_dict[message_id_str]["reacts"][emote]

            await self.save_file()

    async def list_guild_message_configs(
            self,
            guild_id
    ) -> Dict[str, MessageConfig]:
        """
        Retrieve a dictionary of message configs with the corresponding
        guild ID.

        :param guild_id: Guild ID
        :return: Dictionary of message configs indexed by message ID
        """
        return {
            message_id_str: message_config
            for message_id_str, message_config
            in self.message_configs.items()
            if message_config.guild_id == guild_id
        }
