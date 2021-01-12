"""Guild room name filter module."""

import os
import re
from typing import Dict, List, Pattern

import yaml
from loguru import logger

from ophelia import settings

FILTER_CONFIG_PATH = settings.file_voicerooms_filter_config


class GuildRoomNameFilter:
    """Voiceroom name filters."""

    __slots__ = ["regex_filters"]

    def __init__(self, regex_list: List[str]) -> None:
        """
        Initializer for the GuildRoomNameFilter class.

        :param regex_list: List of regex filters
        """
        self.regex_filters: List[Pattern[str]] = []
        for regex_str in regex_list:
            try:
                self.regex_filters.append(re.compile(regex_str, re.IGNORECASE))
            except re.error:
                logger.warning("Failed to parse regex: {}", regex_str)

    async def add_filter(self, regex_str: str) -> bool:
        """
        Add a regex filter to the list of filters.

        :param regex_str: New regex string
        :return If the filter was added (True) or removed (False)
        :raises re.error: When regex fails to compile
        """
        if regex_str in await self.list_filters():
            self.regex_filters = [
                filt for filt in self.regex_filters if filt.pattern != regex_str
            ]
            return False

        self.regex_filters.append(re.compile(regex_str, re.IGNORECASE))
        return True

    async def list_filters(self) -> List[str]:
        """
        Gets a list of regex filter strings.

        :return: List of regex filter strings
        """
        return [filt.pattern for filt in self.regex_filters]

    async def bad_name(self, name: str) -> bool:
        """
        Check if a room name matches any of the regex strings.

        This checks for partial matches and will return true even if not
        the entire input string is matched by any of the regex filters;
        it is also case-insensitive.

        :param name: New voice room name
        :return: If name is bad
        """
        for regex_filter in self.regex_filters:
            if regex_filter.search(name):
                return True

        return False


class NameFilterManager:
    """Manages name filters across different guilds."""

    __slots__ = ["guild_filters"]

    def __init__(self, filters_dict: Dict[str, List[str]]) -> None:
        """
        Initializer for the NameFilterManager class.

        :param filters_dict: Dictionary of lists of filters indexed by
            guild ID strings
        """
        self.guild_filters: Dict[int, GuildRoomNameFilter] = {}
        for guild_id_str, filter_strs in filters_dict.items():
            if not guild_id_str.isnumeric():
                logger.warning(
                    "Non guild ID found in a name filter config: {}",
                    guild_id_str
                )
                continue

            guild_id = int(guild_id_str)
            self.guild_filters[guild_id] = GuildRoomNameFilter(filter_strs)

    async def save_filters(self) -> None:
        """Save room name filters to configuration file."""
        filters_dict = {
            str(guild_id_str): await filt.list_filters()
            for guild_id_str, filt in self.guild_filters.items()
        }

        with open(FILTER_CONFIG_PATH, "w", encoding="utf-8") as save_target:
            yaml.dump(
                filters_dict,
                save_target,
                default_flow_style=False
            )

    @classmethod
    def load_filters(cls) -> "NameFilterManager":
        """
        Loads filters from config file.

        :return: Name filter manager object with all guild filters
        """
        if not os.path.exists(FILTER_CONFIG_PATH):
            return cls({})

        with open(FILTER_CONFIG_PATH, "r", encoding="utf-8") as file:
            filters_dict = yaml.safe_load(file)
            return cls(filters_dict)

    async def add_filter(self, guild_id: int, regex_str: str) -> bool:
        """
        Add a regex filter to a guild filter.

        :param guild_id: Discord guild ID
        :param regex_str: New regex string
        :return Whetner the filter was added (True) or removed (False)
        :raises re.error: When regex fails to compile
        """
        return await self.guild_filters.setdefault(
            guild_id, GuildRoomNameFilter([])
        ).add_filter(regex_str)

    async def list_filters(self, guild_id: int) -> List[str]:
        """
        Gets a list of regex filter strings from a guild filter.

        :param guild_id: Discord guild ID
        :return: List of regex filter strings
        """
        if guild_id in self.guild_filters:
            return await self.guild_filters[guild_id].list_filters()

        return []

    async def bad_name(self, guild_id: int, name: str) -> bool:
        """
        Check if a room name matches any guild regex filters.

        :param guild_id: Discord guild ID
        :param name: New voice room name
        :return: If name is bad
        """
        if guild_id in self.guild_filters:
            return await self.guild_filters[guild_id].bad_name(name)

        return False
