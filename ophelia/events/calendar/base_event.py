"""
Base Event Module.

Contains base event class for tracking specific calendar events. Init
arguments are bundled in a separate data class to prevent excessive
code duplication in subclass init methods.
"""

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import pytz
from discord import Colour, Embed, Guild, Member, Message
from discord.abc import Messageable

from ophelia import settings
from ophelia.events.events_emotes import END_EVENT_EMOTE
from ophelia.output.output import disp_str, send_message
from ophelia.utils.discord_utils import FETCH_FAIL_EXCEPTIONS
from ophelia.utils.time_utils import (
    to_embed_timestamp, to_utc_datetime, utc_time_now
)


class EventLoadError(Exception):
    """When event fails to load from dictionary."""


@dataclass
class EventEdit:
    """
    Used for editing events.

    These have to go through staff approval as well, so they are kept
    separately until approval.

    Parameters:
    - event_message_id: Message ID of the event on the event calendar
    - new_title: New title
    - new_desc: New event description
    - new_start_time: New event time
    """
    event_message_id: int
    new_title: str
    new_desc: str
    new_image: str
    new_start_time: int

    async def get_approval_embed(
            self,
            old_event: "BaseEvent",
            colour: Colour = Colour(settings.embed_color_normal)
    ) -> Embed:
        """
        Get approval channel embed.

        :param old_event: Event before edit
        :param colour: Embed colour
        :return: Discord embed
        """
        embed = Embed(
            title=disp_str("events_edit_title"),
            colour=colour,
            description=disp_str("events_edit_desc").format(
                old_event.title,
                self.new_title if self.new_title else disp_str(
                    "events_no_change"
                ),
                to_utc_datetime(old_event.start_time).isoformat(),
                to_utc_datetime(
                    self.new_start_time
                ).isoformat() if self.new_start_time else disp_str(
                    "events_no_change"
                ),
                old_event.desc,
                self.new_desc if self.new_desc else disp_str(
                    "events_no_change"
                )
            )
        )

        embed.set_image(url=self.new_image)
        embed.set_author(
            name=old_event.organizer.display_name,
            icon_url=old_event.organizer.avatar_url
        )

        return embed


class BaseEvent:
    """Base class for events."""

    __slots__ = [
        "lock",
        "organizer",
        "title",
        "desc",
        "image",
        "dm_msg",
        "start_time",
        "notif_min_before",
        "notif_time",
        "notif_list"
    ]

    def __init__(
            self,
            organizer: Member,
            title: str,
            desc: str,
            image: str,
            dm_msg: str,
            start_time: int,
            notif_min_before: int,
            notif_list: Optional[List[Member]] = None
    ) -> None:
        """
        Initializer for the BaseEvent class.

        :param organizer: Organizer of event
        :param title: Title of event
        :param desc: Description of event
        :param image: Image URL
        :param dm_msg: DM notification message
        :param start_time: Event timestamp (UNIX, seconds accuracy)
        :param notif_min_before: When to send the event notification
            in terms of minutes before event start
        :param notif_list: List of event subscribers
        :raises KeyError: Missing keyword arguments
        """
        self.organizer = organizer
        self.title = title
        self.desc = desc
        self.image = image
        self.dm_msg = dm_msg
        self.start_time = start_time
        self.notif_min_before = notif_min_before
        self.notif_time = (
                start_time - notif_min_before * 60
        )

        if notif_list is not None:
            self.notif_list = notif_list
        else:
            self.notif_list: List[Member] = []

    def time_to_start(self, time: Optional[datetime] = None) -> bool:
        """
        Check if the event has started.

        :param time: Time to check against
        :return: Boolean representing if the event has started
        """
        if time is None:
            time = utc_time_now()

        return time >= to_utc_datetime(self.start_time)

    def time_to_notify(self, time: Optional[datetime] = None) -> bool:
        """
        Check if it's time to send out event notifications.

        :param time: Time to check against
        :return: Boolean representing if the notification time has
            passed
        """
        if time is None:
            time = utc_time_now()

        return time >= to_utc_datetime(self.notif_time)

    def merge_edit(self, edit: EventEdit) -> None:
        """
        Update event with new start time.

        This method is not responsible for deleting the old event
        message and replacing it with a new message in the event
        calendar. That is managed by the guild event log, which manages
        all the actual message deletion.

        :param edit: Edit parameters
        """
        if edit.new_title:
            self.title = edit.new_title
        if edit.new_desc:
            self.desc = edit.new_desc
        if edit.new_start_time:
            self.start_time = edit.new_start_time

    def format_vars(
            self,
            string: str,
            dm_target: Optional[Member] = None
    ) -> str:
        """
        Format an input string with variables.

        Variables:
        %NAME%         Organizer display name
        %TITLE%        Title of event
        %DESC%         Description of event
        %PING%         Organizer ping
        %DM_MSG%       DM Message

        Optional Variables:
        %NOTIF_NAME%   Notification target name

        :param string: Input string
        :param dm_target: DM receiver
        :return: String with variable placeholders replaced with their
            actual values.
        """
        formatted_str = (
            string
                .replace("%NAME%", self.organizer.display_name)
                .replace("%TITLE%", self.title)
                .replace("%DESC%", self.desc)
                .replace("%PING%", self.organizer.mention)
                .replace("%DM_MSG%", self.dm_msg)
        )

        if dm_target is not None:
            formatted_str = formatted_str.replace(
                "%NOTIF_NAME%", dm_target.display_name
            )

        return formatted_str

    @staticmethod
    def get_world_time(time: datetime) -> str:
        """
        Get a list of world times from a given datetime.

        List of timezones displayed (hardcoded):
        - New York
        - London
        - Beijing

        :param time: Given UTC time to convert
        :return: String representing the time in various timezones
        """
        timezones = [
            "America/New_York",
            "Europe/London",
            "Asia/Shanghai"
        ]

        fmt = "%b %d, %H:%M"
        world_clock_list = []
        time = pytz.utc.localize(time)
        for timezone_str in timezones:
            location = timezone_str.split("/")[-1].replace("_", " ")
            timezone = pytz.timezone(timezone_str)
            world_clock_list.append(
                f"{location} | {time.astimezone(timezone).strftime(fmt)}"
            )

        return "\n".join(world_clock_list)

    async def get_event_embed(
            self,
            desc: str,
            colour: Colour = Colour(settings.embed_color_normal),
    ) -> Embed:
        """
        Get a basic event embed.

        The %TIME% flag is replaced by a list of times in different
        timezones. They are hardcoded because I'm lazy.

        :param desc: Embed description
        :param colour: Embed colour
        :return: Event embed
        """
        event_start_time = to_embed_timestamp(self.start_time)
        embed = Embed(
            title=self.title,
            colour=colour,
            description=desc.replace(
                "%TIME%",
                self.get_world_time(event_start_time)
            ),
            timestamp=event_start_time
        )

        embed.set_image(url=self.image)
        embed.set_footer(text=disp_str("events_time_footer"))
        embed.set_author(
            name=self.organizer.display_name,
            icon_url=self.organizer.avatar_url
        )

        return embed

    async def get_calendar_embed(
            self,
            colour: Colour = Colour(settings.embed_color_normal)
    ) -> Embed:
        """
        Get the event embed to be posted in the calendar channel.

        :param colour: Embed Colour
        :return: Calendar event embed
        """
        return await self.get_event_embed(
            disp_str("events_embed_text").format(self.desc),
            colour
        )

    async def get_ongoing_embed(
            self,
            colour: Colour = Colour(settings.embed_color_severe)
    ) -> Embed:
        """
        Get the ongoing event embed for when the event is about to
        start.

        :param colour: Embed Colour
        :return: Ongoing event embed
        """
        return await self.get_event_embed(
            disp_str("events_embed_ongoing").format(self.desc),
            colour
        )

    async def get_approval_embed(
            self,
            colour: Colour = Colour(settings.embed_color_normal)
    ) -> Embed:
        """
        Get the event embed to be posted on the approval channel.

        :param colour: Embed colour
        :return: Approval embed
        """
        return await self.get_event_embed(
            disp_str("events_approval").format(
                self.organizer.mention,
                self.desc,
                self.dm_msg,
                self.notif_min_before
            ),
            colour
        )

    async def send_ongoing_message(
            self,
            notif_message: str,
            channel: Messageable
    ) -> Message:
        """
        Send a message to the calendar channel to inform members that
        the event is ongoing or about to start.

        :param notif_message: Notification message (typically contains
            the events ping)
        :param channel: Channel to send message to
        """
        message_preamble = self.format_vars(
            disp_str("events_ongoing_message").format(notif_message)
        )

        embed = await self.get_ongoing_embed()

        message = await send_message(
            channel=channel,
            text=message_preamble,
            embed=embed
        )

        await message.add_reaction(END_EVENT_EMOTE)
        return message

    async def distribute_dm(self, notif_msg: str, organizer_msg: str) -> None:
        """
        Send notification DMs to all members subscribed to the event.

        :param notif_msg: Notification message format
        :param organizer_msg: Organizer notification message format
        """
        message_preamble = disp_str("events_dm_notif").format(notif_msg)
        embed = await self.get_calendar_embed()

        for member in self.notif_list:
            member_preamble = self.format_vars(message_preamble, member)
            await send_message(
                channel=member,
                text=member_preamble,
                embed=embed
            )

        await send_message(
            channel=self.organizer,
            text=self.format_vars(
                disp_str("events_dm_notif").format(organizer_msg)
            ),
            embed=embed
        )

    @staticmethod
    @abc.abstractmethod
    async def load_from_dict(config_dict: dict, guild: Guild) -> "BaseEvent":
        """
        Loads event object from configuration parameters.

        :param config_dict: Dictionary containing configuration
            parameter
        :param guild: Event guild
        :return: Event object
        """
        raise NotImplementedError("Loading function should be overridden")

    @staticmethod
    async def base_event_params(config_dict: dict, guild: Guild) -> dict:
        """
        Parse event keyword parameters from configuration parameters.

        :param config_dict: Dictionary containing configuration
            parameters
        :param guild: Event guild
        :return: Dictionary containing basic event parameters
        """
        try:
            organizer = await guild.fetch_member(int(config_dict["organizer"]))
            title = str(config_dict["title"])
            desc = str(config_dict["desc"])
            image = str(config_dict["image"])
            dm_msg = str(config_dict["dm_msg"])
            start_time = int(config_dict["start_time"])
            notif_min_before = int(config_dict["notif_min_before"])

            notif_list: List[Member] = []
            for subscriber in config_dict.get("notif_list", []):
                try:
                    subber = await guild.fetch_member(subscriber)
                    notif_list.append(subber)
                except FETCH_FAIL_EXCEPTIONS:
                    # This is normal; people can leave the server.
                    continue

            return {
                "organizer": organizer,
                "title": title,
                "desc": desc,
                "image": image,
                "dm_msg": dm_msg,
                "start_time": start_time,
                "notif_min_before": notif_min_before,
                "notif_list": notif_list
            }

        except (*FETCH_FAIL_EXCEPTIONS, KeyError, ValueError) as e:
            raise EventLoadError from e

    async def save_to_dict(self) -> dict:
        """
        Saves event object into dictionary containing configuration
        parameters so that it may be loaded again.

        :return: Dictionary of configuration parameters
        """
        save_dict = {
            "organizer": self.organizer.id,
            "title": self.title,
            "desc": self.desc,
            "image": self.image,
            "dm_msg": self.dm_msg,
            "start_time": self.start_time,
            "notif_min_before": self.notif_min_before,
            "notif_list": [m.id for m in self.notif_list]
        }

        return save_dict
