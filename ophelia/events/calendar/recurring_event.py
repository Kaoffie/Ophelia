"""
Recurring Event Module.

Contains the Recurring event tracking class as well as relevant
constants for time conversion.
"""
import json

from discord import TextChannel, Guild, Colour, Embed, Message
from loguru import logger

from ophelia import settings
from ophelia.events.calendar.base_event import BaseEvent, EventLoadError
from ophelia.output import disp_str
from ophelia.utils.text_utils import escape_json_formatting

DAY_SECONDS = 60 * 60 * 24


class RecurringEvent(BaseEvent):
    """Recurring events that post messages from a queue channel"""

    __slots__ = [
        "queue_channel",
        "target_channel",
        "post_template",
        "post_embed",
        "repeat_interval"
    ]

    @staticmethod
    def config_name() -> str:
        """Type Name used in configuration."""
        return "recurring_event"

    def __init__(
            self,
            queue_channel: TextChannel,
            target_channel: TextChannel,
            post_template: str,
            post_embed: str,
            repeat_interval: int,
            **kwargs
    ) -> None:
        """
        Initializer for the RecurringEvent class.

        :param init_bundle: Base class init argument bundle
        :param queue_channel: Recurring message queue channel
        :param target_channel: Recurring message target channel
        :param post_template: Event post template
        :param post_embed: Event post embed in dictionary format as a
            string; empty string if no embed configured.
        :param repeat_interval: Event interval (in days)
        """
        super().__init__(**kwargs)
        self.queue_channel = queue_channel
        self.target_channel = target_channel
        self.post_template = post_template
        self.post_embed = post_embed
        self.repeat_interval = repeat_interval

    def update_time(self) -> None:
        """
        Update event with next event time and make the appropriate
        message edits.

        Note that this DOES NOT account for any discrepencies in time-
        keeping, including timezone changes or Daylight Savings Time.
        All this does is add the interval time to the UTC timestamp.
        Users will have to reschedule themselves if they'd like to keep
        the time consistent with DST.
        """
        while self.time_to_start():
            self.start_time = (
                    self.start_time + self.repeat_interval * DAY_SECONDS
            )

        self.notif_time = self.start_time - self.notif_min_before * 60

    async def get_calendar_embed(
            self,
            colour: Colour = Colour(settings.embed_color_important)
    ) -> Embed:
        """
        Get the recurrent event embed to be posted to the calendar
        channel.

        :param colour: Embed colour
        :return: Calendar event embed
        """
        return await self.get_event_embed(
            disp_str("events_recurring_embed_text").format(
                self.desc,
                self.repeat_interval
            ),
            colour
        )

    async def get_approval_embed(
            self,
            colour: Colour = Colour(settings.embed_color_important)
    ) -> Embed:
        """
        Get the recurrent event embed to be posted to the approval
        channel.

        :param colour: Embed colour
        :return: Approval embed
        """
        return await self.get_event_embed(
            disp_str("events_recurring_approval").format(
                self.organizer.mention,
                self.desc,
                self.queue_channel.mention,
                self.target_channel.mention,
                self.dm_msg,
                self.notif_min_before,
                self.repeat_interval
            ),
            colour
        )

    @staticmethod
    async def load_from_dict(
            config_dict: dict,
            guild: Guild
    ) -> "RecurringEvent":
        """
        Loads recurring event object from configuration parameters.

        :param config_dict: Dictionary containing configuration
            parameters
        :param guild: Event guild
        :return: Recurring event object
        :raises EventLoadError: Invalid arguments passed
        """
        try:
            base_dict = await BaseEvent.base_event_params(config_dict, guild)

            queue_channel = guild.get_channel(int(config_dict["queue_channel"]))
            if queue_channel is None:
                raise EventLoadError

            target_channel = guild.get_channel(
                int(config_dict["target_channel"])
            )
            if queue_channel is None:
                raise EventLoadError

            post_template = str(config_dict["post_template"])
            post_embed = str(config_dict["post_embed"])
            repeat_interval = int(config_dict["repeat_interval"])

            base_dict.update({
                "queue_channel": queue_channel,
                "target_channel": target_channel,
                "post_template": post_template,
                "post_embed": post_embed,
                "repeat_interval": repeat_interval
            })

            return RecurringEvent(**base_dict)
        except KeyError as e:
            raise EventLoadError from e

    async def save_to_dict(self) -> dict:
        """
        Saves recurrent event object into dictionary containing
        configuration parameters so that it may be loaded again.

        :return: Dictionary of configuration parameters
        """
        save_dict = await super().save_to_dict()
        save_dict.update({
            "type": "recurring_event",
            "queue_channel": self.queue_channel.id,
            "target_channel": self.target_channel.id,
            "post_template": self.post_template,
            "post_embed": self.post_embed,
            "repeat_interval": self.repeat_interval
        })

        return save_dict

    async def send_event_post(self) -> None:
        """
        Send an event post.

        Takes the oldest post in the queue channel and inserts that as
        the content using the %CONTENT% flag into a new message on the
        target channel.

        :raises Forbidden: Could not send event post or delete old
            message
        """
        dequeued_message: Message = await self.queue_channel.history(
            limit=1,
            oldest_first=True
        ).next()

        message_content = dequeued_message.content
        escaped_content = escape_json_formatting(message_content)
        content_flag = "%CONTENT%"

        text = None
        embed = None

        if self.post_template:
            text = self.post_template.replace(content_flag, message_content)
        if self.post_embed:
            embed_json = self.post_embed.replace(content_flag, escaped_content)
            embed = Embed.from_dict(json.loads(embed_json))

        if text is None and embed is None:
            logger.warning("Recurring event {} scheduled an empty message")
            return

        # Delete old message
        await dequeued_message.delete()

        # Post new message
        await self.target_channel.send(content=text, embed=embed)
