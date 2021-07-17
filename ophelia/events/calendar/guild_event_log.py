"""Guild Event Log Module."""

import asyncio
import copy
from typing import Any, Callable, Dict, List, Optional, Union

from discord import (
    Colour, Embed, Forbidden, Guild, HTTPException, Member, Message,
    NoMoreItems, TextChannel
)
from loguru import logger

from ophelia import settings
from ophelia.events.calendar.base_event import (
    BaseEvent, EventEdit, EventLoadError
)
from ophelia.events.calendar.member_event import MemberEvent
from ophelia.events.calendar.ongoing_event import OngoingEvent
from ophelia.events.calendar.recurring_event import RecurringEvent
from ophelia.events.events_emotes import (
    APPROVE_EMOTE, NOTIF_EMOTE, REJECT_EMOTE
)
from ophelia.output.error_handler import OpheliaCommandError
from ophelia.output.output import (
    disp_str, send_embed, send_message,
    send_simple_embed
)
from ophelia.utils.discord_utils import FETCH_FAIL_EXCEPTIONS

EVENT_TYPES = {
    MemberEvent.config_name(): MemberEvent,
    RecurringEvent.config_name(): RecurringEvent
}

DEFAULT_EVENT_TIMEOUT = 10 * 60 * 60  # 10 Hours


class GuildEventInvalidConfig(Exception):
    """When guild event log was configured wrongly."""


class GuildEventLog:
    """
    Event calendar manager for guilds.

    Note that guild events are indexed by their correpsonding message
    IDs in either the actual calendar channel or the approval channel -
    this is to make sure that the event lists on those channels are the
    true copies of the actual behind-the-scenes events and any deletions
    of those messages will lead to the rejection or deletion of the
    corresponding events.

    Parameters:
    - approval_channel: Event approval queue channel
    - calendar_channel: Event calendar channel
    - staff_role: Role required to approve or reject events
    - accept_template: Event approval DM template
    - reject_template: Event rejection DM template
    - accept_edit_template: Event edit approval DM template
    - reject_edit_template: Event edit rejection DM template
    - dm_template: Event notification DM template
    - organizer_dm_template: Event organizer notification DM template
    - ongoing_template: Ongoing event announcement template
    - approval_events: Event approval queue
    - upcoming_events: Event calendar
    - ongoing_events: Ongoing events
    - approval_edits: Event edits pending approval
    - event_timeout: Seconds for an ongoing event to timeout
    """

    __slots__ = [
        "lock",
        "approval_channel",
        "calendar_channel",
        "staff_role",
        "accept_template",
        "reject_template",
        "accept_edit_template",
        "reject_edit_template",
        "dm_template",
        "organizer_dm_template",
        "new_event_template",
        "ongoing_template",
        "approval_events",
        "upcoming_events",
        "ongoing_events",
        "approval_edits",
        "event_timeout"
    ]

    def __init__(self, guild_config_dict: dict) -> None:
        """
        Initializer for the GuildEventLog class.

        This only initializes with the basic variables that don't
        require fetching anything from a guild using async methods.

        :param guild_config_dict: Dictionary of config options
        """
        self.lock = asyncio.Lock()
        try:
            # Get template strings
            self.accept_template = guild_config_dict["accept_template"]
            self.reject_template = guild_config_dict["reject_template"]
            self.accept_edit_template = guild_config_dict[
                "accept_edit_template"
            ]
            self.reject_edit_template = guild_config_dict[
                "reject_edit_template"
            ]
            self.dm_template = guild_config_dict["dm_template"]
            self.organizer_dm_template = guild_config_dict[
                "organizer_dm_template"
            ]
            self.new_event_template = guild_config_dict["new_event_template"]
            self.ongoing_template = guild_config_dict["ongoing_template"]

            # Parse event timeout
            self.event_timeout = guild_config_dict.get(
                "event_timeout",
                DEFAULT_EVENT_TIMEOUT
            )

            # Initialize everything else as None
            self.approval_channel = None
            self.calendar_channel = None
            self.staff_role = None
            self.approval_events = None
            self.upcoming_events = None
            self.ongoing_events = None
            self.approval_edits = None

        except (EventLoadError, KeyError, ValueError) as e:
            raise GuildEventInvalidConfig from e

    @staticmethod
    async def approval_message_edit(
            message: Message,
            approve_text: str,
            rejection: bool = False
    ) -> None:
        """
        Edit a message to indicate that something has been approved or
        rejected.

        :param message: Original message to edit
        :param approve_text: Approval text to insert into message text
        :param rejection: Whether to use the rejection colour or the
            approval colour
        """
        if message.embeds:
            embed = message.embeds[0]
            if rejection:
                embed.colour = Colour(settings.embed_color_severe)
            else:
                embed.colour = Colour(settings.embed_color_success)

            await message.edit(content=approve_text, embed=embed)

    @staticmethod
    async def parse_guild_config(
            guild: Guild,
            guild_config_dict: dict
    ) -> "GuildEventLog":
        """
        Initializes a new GuildEventLog from a dictionary loaded from
        a file.

        All configuration options are named after their respective
        variable names; for the events, there's an extra "type" config
        that indicates whether an event is a member event or a
        recurring event.

        This method retrieves all the channels and roles from their
        respective IDs, used for loading event logs from the database.

        :param guild: Discord guild
        :param guild_config_dict: Dictionary of config options
        :raises GuildEventInvalidConfig: Invalid config
        :return: Fully initialized guild log
        """
        try:
            guild_log = GuildEventLog(guild_config_dict)

            # Retrieve server channels
            guild_log.approval_channel = guild.get_channel(
                guild_config_dict["approval_channel"]
            )
            guild_log.calendar_channel = guild.get_channel(
                guild_config_dict["calendar_channel"]
            )

            # Get staff role
            guild_log.staff_role = guild.get_role(
                guild_config_dict["staff_role"]
            )

            # Parse events and edits
            guild_log.approval_events = await guild_log.load_events(
                guild_config_dict["approval_events"],
                guild
            )
            guild_log.upcoming_events = await guild_log.load_events(
                guild_config_dict["upcoming_events"],
                guild
            )
            guild_log.ongoing_events = await guild_log.load_ongoing_events(
                guild_config_dict["ongoing_events"]
            )
            guild_log.approval_edits = await guild_log.load_edits(
                guild_config_dict["approval_edits"]
            )

            return guild_log

        except (
                GuildEventInvalidConfig, EventLoadError, KeyError, ValueError
        ) as e:
            raise GuildEventInvalidConfig from e

    @staticmethod
    async def new_guild_log(guild_config_dict: dict) -> "GuildEventLog":
        """
        Initializes a new GuildEventLog.

        This method assumes that all channels and roles have already
        been retrieved from the guild and just dumps them into the log
        object without attempting to parse anything.

        :param guild_config_dict: Dictionary of config options
        :raises GuildEventInvalidConfig: Invalid config
        :return: Fully initialized guild log
        """
        try:
            guild_log = GuildEventLog(guild_config_dict)

            # Retrieve server channels
            guild_log.approval_channel = guild_config_dict["approval_channel"]
            guild_log.calendar_channel = guild_config_dict["calendar_channel"]

            # Get staff role
            guild_log.staff_role = guild_config_dict["staff_role"]

            # Parse events and edits
            guild_log.approval_events = guild_config_dict["approval_events"]
            guild_log.upcoming_events = guild_config_dict["upcoming_events"]
            guild_log.ongoing_events = guild_config_dict["ongoing_events"]
            guild_log.approval_edits = guild_config_dict["approval_edits"]

            return guild_log

        except (
                GuildEventInvalidConfig, EventLoadError, KeyError, ValueError
        ) as e:
            raise GuildEventInvalidConfig from e

    @staticmethod
    async def load_event(event_dict: dict, guild: Guild) -> BaseEvent:
        """
        Load a single event from a config dictionary.

        :param event_dict: Event parameters
        :param guild: Discord guild
        :return: Parsed event
        :raises KeyError: Invalid arguments in config
        :raises EventLoadError: Failed to configure event
        :raises ValueError: Conversion error (probably from message ID)
        """
        try:
            event_type = EVENT_TYPES[event_dict["type"]]
            return await event_type.load_from_dict(
                event_dict,
                guild
            )
        except (KeyError, EventLoadError, ValueError) as e:
            raise EventLoadError from e

    async def load_events(
            self,
            event_config: dict,
            guild: Guild
    ) -> Dict[int, BaseEvent]:
        """
        Load events from a config dictionary.

        :param event_config: Dictionary of event parameters indexed by
            message IDs
        :param guild: Discord guild
        :return: Dictionary of events indexed by message IDs
        :raises EventLoadError: Failed to configure event
        """
        events = {}
        for message_id_str, event_dict in event_config.items():
            events[int(message_id_str)] = await self.load_event(
                event_dict,
                guild
            )

        return events

    @staticmethod
    async def load_ongoing_events(
            event_config: dict
    ) -> Dict[int, OngoingEvent]:
        """
        Load ongoing events from a config dictionary.

        :param event_config: Dictionary of ongoing event parameters
            indexed by message IDs
        :return: Dictionary of ongoing events indexed by message IDs
        :raises KeyError: Invalid arguments passed
        :raises ValueError: Conversion error (probably from message ID)
        """
        events = {}
        for message_id_str, event_dict in event_config.items():
            event_dict["message_embed"] = Embed.from_dict(
                event_dict["message_embed"]
            )
            events[int(message_id_str)] = OngoingEvent(**event_dict)

        return events

    @staticmethod
    async def load_edits(edit_config: dict) -> Dict[int, EventEdit]:
        """
        Load event edits from a config dictionary.

        :param edit_config: Dictionary of event edit parameters indexed
            by mesage IDs
        :return: Dictionary of event edits indexed by message IDs
        :raises KeyError: Invalid arguments passed
        :raises ValueError: Conversion error (probably from message ID)
        """
        edits = {}
        for message_id_str, edit_dict in edit_config.items():
            edits[int(message_id_str)] = EventEdit(**edit_dict)

        return edits

    @staticmethod
    async def save_events(
            event_dict: Union[Dict[int, BaseEvent], Dict[int, OngoingEvent]]
    ) -> dict:
        """
        Save events to a config dictionary.

        :param event_dict: Events indexed by message ID
        :return: Dictionary of event parameters indexed by message IDs
            as strings
        """
        events = {}
        for message_id, event in event_dict.items():
            events[str(message_id)] = await event.save_to_dict()

        return events

    @staticmethod
    async def save_dataclasses(dataclasses_dict: Dict[int, Any]) -> dict:
        """
        Save dataclasses (such as event edits) to a dictionary.

        :param dataclasses_dict: Dictionary of dataclasses indexed by
            message ID
        :return: Dictionary of dataclass parameters indexed by message
            IDs as strings
        """
        objs = {}
        for message_id, obj in dataclasses_dict.items():
            # Message ID stored as string
            objs[str(message_id)] = vars(obj)

        return objs

    async def retrieve_user_events(self, user_id: int) -> Dict[int, BaseEvent]:
        """
        Retrieve all upcoming events initiated by a user.

        :param user_id: User ID
        :return: Dictionary of events by user, indexed by calendar
            message ID
        """
        user_events: Dict[int, BaseEvent] = {}
        event: BaseEvent
        for event_id, event in self.upcoming_events.items():
            if event.organizer.id == user_id:
                user_events[event_id] = event

        return user_events

    async def save_config(self) -> dict:
        """
        Save config to dictionary.

        :return: Dictionary containing guild event log parameters
        """
        save_dict = {
            "approval_channel": self.approval_channel.id,
            "calendar_channel": self.calendar_channel.id,
            "staff_role": self.staff_role.id,
            "accept_template": self.accept_template,
            "reject_template": self.reject_template,
            "accept_edit_template": self.accept_edit_template,
            "reject_edit_template": self.reject_edit_template,
            "dm_template": self.dm_template,
            "organizer_dm_template": self.organizer_dm_template,
            "new_event_template": self.new_event_template,
            "ongoing_template": self.ongoing_template,
            "approval_events": await self.save_events(self.approval_events),
            "upcoming_events": await self.save_events(self.upcoming_events),
            "ongoing_events": await self.save_events(self.ongoing_events),
            "approval_edits": await self.save_dataclasses(self.approval_edits),
            "event_timeout": self.event_timeout
        }

        return save_dict

    async def update_new_event(
            self,
            event: BaseEvent
    ) -> None:
        """
        Update event log and calendar channel with new event.

        :param event: Event to add to log
        """
        message = await send_message(
            channel=self.calendar_channel,
            text=event.format_vars(self.new_event_template),
            embed=await event.get_calendar_embed()
        )

        await message.add_reaction(NOTIF_EMOTE)
        self.upcoming_events[message.id] = event

    async def update_ongoing_event(
            self,
            ongoing_event: OngoingEvent
    ) -> None:
        """
        Update event log and calendar channel with ongoing event.

        :param ongoing_event: Ongoing event to add to log
        """
        message = await send_message(
            channel=self.calendar_channel,
            text=ongoing_event.message_text,
            embed=ongoing_event.message_embed
        )

        self.ongoing_events[message.id] = ongoing_event

    async def update_new_approval_event(
            self,
            event: BaseEvent
    ) -> None:
        """
        Update approval log with new approval event.

        :param event: Event to add to approval log
        """
        message = await send_message(
            channel=self.approval_channel,
            text=None,
            embed=await event.get_approval_embed()
        )

        await message.add_reaction(APPROVE_EMOTE)
        await message.add_reaction(REJECT_EMOTE)
        self.approval_events[message.id] = event

    async def submit_event(self, args_dict: dict, guild: Guild) -> BaseEvent:
        """
        Submit a new event for approval.

        :param args_dict: Dictionary of arguments to initialize event
            (including type)
        :param guild: Discord guild
        :return Submitted event
        :raises EventLoadError: Failed to configure event
        """
        event = await self.load_event(args_dict, guild)
        await self.update_new_approval_event(event)
        return event

    async def approve_event(self, message_id: int) -> None:
        """
        Approve an event and send the event to the event calendar.

        Approving an event kicks the event to the bottom of the event
        calendar channel, which might be below the ongoing event
        announcements. This is intentional; resending the announcement
        message will mean resending any pings contained in the message,
        which is not exactly desireable. The only way around this is by
        editing the messages.

        Approval DM template variables:
        %NAME%         Name of organizer
        %TITLE%        Title of event
        %DESC%         Description of event

        :param message_id: Approval message ID
        """
        if message_id not in self.approval_events:
            return

        async with self.lock:
            approved_event: BaseEvent = self.approval_events[message_id]
            event_embed = await approved_event.get_calendar_embed()
            try:
                await self.update_new_event(approved_event)
                del self.approval_events[message_id]
            except (HTTPException, Forbidden) as e:
                raise OpheliaCommandError(
                    "events_approval_error",
                    approved_event.title,
                    self.calendar_channel.mention
                ) from e

        try:
            # Edit approval message
            approved_message: Message = (
                await self.approval_channel.fetch_message(message_id)
            )
            await self.approval_message_edit(
                approved_message,
                disp_str("events_add_approved")
            )

            await send_message(
                channel=approved_event.organizer,
                text=approved_event.format_vars(self.accept_template),
                embed=event_embed
            )
        except (HTTPException, Forbidden):
            await send_simple_embed(
                self.approval_channel,
                "events_approval_dm_error",
                approved_event.title,
                approved_event.organizer.mention,
                colour=Colour(settings.embed_color_warning)
            )

    async def reject_event(self, message_id: int) -> None:
        """
        Reject an event.

        :param message_id: Approval message ID
        """
        if message_id not in self.approval_events:
            return

        async with self.lock:
            rejected_event: BaseEvent = self.approval_events[message_id]
            event_embed = await rejected_event.get_calendar_embed()

            try:
                del self.approval_events[message_id]

                # Edit approval message
                rejected_message: Message = (
                    await self.approval_channel.fetch_message(message_id)
                )
                await self.approval_message_edit(
                    rejected_message,
                    disp_str("events_add_rejected"),
                    rejection=True
                )

                await send_message(
                    channel=rejected_event.organizer,
                    text=rejected_event.format_vars(self.reject_template),
                    embed=event_embed
                )
            except (HTTPException, Forbidden):
                await send_embed(
                    channel=self.approval_channel,
                    embed_text=disp_str(
                        "events_rejection_dm_error_desc"
                    ).format(
                        rejected_event.title,
                        rejected_event.organizer.mention
                    ),
                    title=disp_str("events_rejection_dm_error_title"),
                    colour=Colour(settings.embed_color_warning),
                    timestamp=None
                )

    async def update_new_edit(self, edit: EventEdit) -> None:
        """
        Update approval log with new event edit.

        :param edit: Edit to send to approval log
        """
        event = self.upcoming_events[edit.event_message_id]
        message = await send_message(
            channel=self.approval_channel,
            text=None,
            embed=await edit.get_approval_embed(event)
        )

        await message.add_reaction(APPROVE_EMOTE)
        await message.add_reaction(REJECT_EMOTE)
        self.approval_edits[message.id] = edit

    async def submit_edit(self, args_dict: dict) -> EventEdit:
        """
        Submit a new edit for approval.

        :param args_dict: Edit parameters
        """
        edit = EventEdit(**args_dict)
        await self.update_new_edit(edit)
        return edit

    async def approve_edit(self, message_id: int) -> None:
        """
        Approve an event edit.

        :param message_id: Message ID of the event edit approval message
        """
        if message_id not in self.approval_edits:
            return

        async with self.lock:
            approved_edit: EventEdit = self.approval_edits[message_id]
            target_id = approved_edit.event_message_id
            if target_id not in self.upcoming_events:
                return

            target_event = self.upcoming_events[target_id]
            target_event.merge_edit(approved_edit)

            try:
                # Edit approval message
                approved_message: Message = (
                    await self.approval_channel.fetch_message(message_id)
                )
                await self.approval_message_edit(
                    approved_message,
                    disp_str("events_edit_approved")
                )

                # Edit old event message
                target_message: Message = (
                    await self.calendar_channel.fetch_message(target_id)
                )
                await target_message.edit(
                    content=target_event.format_vars(self.new_event_template),
                    embed=await target_event.get_calendar_embed()
                )

                # Inform the organizer that the edit was approved
                await send_message(
                    channel=target_event.organizer,
                    text=target_event.format_vars(self.accept_edit_template),
                    embed=await target_event.get_calendar_embed()
                )

            except FETCH_FAIL_EXCEPTIONS:
                # The event would have been edited before this try clause
                # so the only issue here is updating it.
                await send_embed(
                    channel=self.approval_channel,
                    embed_text=disp_str(
                        "events_edit_approval_dm_error_desc"
                    ).format(
                        target_event.title,
                        target_event.organizer.mention
                    ),
                    title=disp_str("events_edit_approval_dm_error_title"),
                    colour=Colour(settings.embed_color_warning),
                    timestamp=None
                )

    async def reject_edit(self, message_id: int) -> None:
        """
        Reject an event edit.

        :param message_id: Message ID of the event edit approval message
        """
        if message_id not in self.approval_events:
            return

        async with self.lock:
            rejected_edit: EventEdit = self.approval_edits[message_id]
            target_id = rejected_edit.event_message_id
            if target_id not in self.upcoming_events:
                return

            target_event = self.upcoming_events[target_id]

            try:
                # Edit approval message
                rejected_message: Message = (
                    await self.approval_channel.fetch_message(message_id)
                )
                await self.approval_message_edit(
                    rejected_message,
                    disp_str("events_edit_rejected"),
                    rejection=True
                )

                await send_message(
                    channel=target_event.organizer,
                    text=target_event.format_vars(self.reject_edit_template),
                    embed=await target_event.get_calendar_embed()
                )

            except (HTTPException, Forbidden):
                await send_embed(
                    channel=self.approval_channel,
                    embed_text=disp_str(
                        "events_edit_rejection_dm_error_desc"
                    ).format(
                        target_event.title,
                        target_event.organizer.mention
                    ),
                    title=disp_str("events_edit_rejection_dm_error_title"),
                    colour=Colour(settings.embed_color_warning),
                    timestamp=None
                )

    async def subscribe_event(
            self,
            message_id: int,
            member: Member,
            unsubscribe: bool = False
    ) -> None:
        """
        Subscribes a user to notifications for a given event.

        :param message_id: Calendar message of the event
        :param member: Subscribing member
        :param unsubscribe: Unsubscription mode
        """
        if message_id not in self.upcoming_events:
            return

        event = self.upcoming_events[message_id]
        if unsubscribe:
            try:
                event.notif_list.remove(member)
                await send_message(
                    channel=member,
                    text=disp_str("events_unsubscribe").format(
                        event.title
                    )
                )
            except ValueError:
                # This is fine.
                pass
        else:
            event.notif_list.append(member)
            await send_message(
                channel=member,
                text=disp_str("events_subscribe").format(
                    event.title
                )
            )

    async def force_update(
            self,
            item_dict: dict,
            old_channel: Optional[TextChannel],
            sender: Callable
    ) -> None:
        """
        Deletes all existing messages in an event or edit dictionary
        and sends all of them again to be re-indexed.

        :param item_dict: Dictionary of events or edits indexed by
            message IDs
        :param old_channel: Channel to delete old messages from; if
            there is no need to delete anything from an older channel,
            then this can be None
        :param sender: Async callable to send each new item message
        """
        async with self.lock:
            items: List[Union[BaseEvent, OngoingEvent, EventEdit]] = []
            item_messages = []

            # Sorted based on message ID, which are based on UNIX
            # timestamps
            for message_id, event in sorted(item_dict.items()):
                item_message = None
                if old_channel is not None:
                    item_message = await old_channel.fetch_message(
                        message_id
                    )

                items.append(event)
                if item_message is not None:
                    item_messages.append(item_message)

            if item_messages:
                await self.calendar_channel.delete_messages(item_message)

            # Empty the list and fill the new one
            item_dict.clear()
            for item in items:
                await sender(item)

    async def force_update_calendar(
            self,
            old_channel: Optional[TextChannel],
            new_channel: TextChannel
    ) -> None:
        """
        Delete all existing calendar messages in the calendar channel
        and sends them all to the new calendar channel.

        This method will not do anything if the old and the new channels
        are the same channel, assuming that the old channel is formatted
        correctly. If there are any ongoing events,

        :param old_channel: Old calendar channel
        :param new_channel: New calendar channel
        """
        if old_channel == new_channel:
            return

        self.calendar_channel = new_channel
        await self.force_update(
            self.upcoming_events,
            old_channel,
            self.update_new_event
        )

        await self.force_update(
            self.ongoing_events,
            old_channel,
            self.update_ongoing_event
        )

    async def force_update_approvals(
            self,
            old_channel: Optional[TextChannel],
            new_channel: TextChannel
    ) -> None:
        """
        Deletes all existing approval messages in the approval channel
        and sends the new approval list to the given channel.

        :param old_channel: Old approval channel
        :param new_channel: New approval channel
        """
        if old_channel == new_channel:
            return

        self.approval_channel = new_channel
        await self.force_update(
            self.approval_events,
            old_channel,
            self.update_new_approval_event
        )

        await self.force_update(
            self.approval_edits,
            old_channel,
            self.update_new_edit
        )

    async def delete_upcoming_event(self, message_id: int) -> None:
        """
        Delete an upcoming event.

        This may be triggered by the deletion of the actual calendar
        event message, so it's okay if we can't fetch the message ID;
        what's important is that the event is deleted behind-the-scenes.

        :param message_id: Message ID of the calendar entry message
        """
        if message_id not in self.upcoming_events:
            return

        deleted_event = self.upcoming_events[message_id]
        try:
            await send_message(
                channel=self.approval_channel,
                text=disp_str("events_delete"),
                embed=await deleted_event.get_calendar_embed()
            )

            event_message = await self.calendar_channel.fetch_message(
                message_id
            )

            await event_message.delete()

        except FETCH_FAIL_EXCEPTIONS:
            pass

        finally:
            # By deleting the event message, the event would have
            # been deleted, but we delete it here just to be sure.
            self.upcoming_events.pop(message_id, None)

    async def end_ongoing_event(self, message_id: int) -> None:
        """
        End an ongoing event.

        :param message_id: Message ID of the event announcement
        """
        if message_id not in self.ongoing_events:
            return

        del self.ongoing_events[message_id]

        try:
            message = await self.calendar_channel.fetch_message(message_id)
            await message.delete()
        except FETCH_FAIL_EXCEPTIONS:
            pass

    async def check_retrieve(self) -> None:
        """Check if any recurring events should retrieve post content."""
        async with self.lock:
            for upcoming_event in self.upcoming_events.values():
                if not isinstance(upcoming_event, RecurringEvent):
                    continue

                if not upcoming_event.time_to_notify():
                    continue

                if isinstance(upcoming_event, RecurringEvent):
                    try:
                        await upcoming_event.retrieve_content()
                    except NoMoreItems:
                        continue

    async def check_notify(self) -> None:
        """
        Check if any of the upcoming events should be started and send
        all respective DMs.
        """
        async with self.lock:
            # We loop through a list of keys because we are going to
            # mutate the dictionary as we loop through it.
            for message_id in copy.copy(list(self.upcoming_events.keys())):
                upcoming_event = self.upcoming_events[message_id]
                if not upcoming_event.time_to_notify():
                    continue

                # Delete upcoming event if it's a member event
                if isinstance(upcoming_event, MemberEvent):
                    # Delete upcoming if it's a member event
                    await self.delete_upcoming_event(message_id)

                # Prepare message from the queue if it's recurring
                stop_notifying = False
                if isinstance(upcoming_event, RecurringEvent):
                    stop_notifying = (
                            upcoming_event.event_cancelled
                            or upcoming_event.notified
                    )

                if not stop_notifying:
                    # Send ongoing event message
                    ongoing_message = await upcoming_event.send_ongoing_message(
                        notif_message=self.ongoing_template,
                        channel=self.calendar_channel
                    )

                    # Distribute DM
                    await upcoming_event.distribute_dm(
                        self.dm_template,
                        self.organizer_dm_template
                    )

                    # Create new ongoing event
                    ongoing_event = OngoingEvent(
                        countdown_time=upcoming_event.start_time,
                        timeout_length=self.event_timeout,
                        organizer_id=upcoming_event.organizer.id,
                        message_text=ongoing_message.content,
                        message_embed=ongoing_message.embeds[0]
                    )

                    self.ongoing_events[ongoing_message.id] = ongoing_event

    async def check_start(self) -> None:
        """
        Check if any of the recurring events has started and send any
        respective event messages.

        This check only applies to recurring events since they are the
        only events that are not deleted after the notifications are
        sent out. Events that pass this check will have their event
        messages sent out in the respective channels, with the content
        field taken from the oldest message in the queue channel.
        """
        async with self.lock:
            for upcoming_event in self.upcoming_events.values():
                if not isinstance(upcoming_event, RecurringEvent):
                    continue

                # Check if the event has started
                if not upcoming_event.time_to_start():
                    continue

                try:
                    await upcoming_event.send_event_post()
                except Forbidden as e:
                    raise OpheliaCommandError(
                        "events_recurring_error",
                        upcoming_event.title
                    ) from e

    async def check_update(self) -> None:
        """Check if any recurring events should be updated."""
        async with self.lock:
            # We loop through a list of keys because we are going to
            # mutate the dictionary as we loop through it.
            for message_id in copy.copy(list(self.upcoming_events.keys())):
                upcoming_event = self.upcoming_events[message_id]
                # Update time if it's a recurring event
                if isinstance(upcoming_event, RecurringEvent):
                    if not upcoming_event.time_to_update():
                        continue

                    upcoming_event.update_time()
                    try:
                        message = await self.calendar_channel.fetch_message(
                            message_id
                        )
                        await message.edit(
                            content=message.content,
                            embed=await upcoming_event.get_calendar_embed()
                        )
                    except FETCH_FAIL_EXCEPTIONS:
                        logger.warning(
                            "Tried to update recurring event that doesn't have "
                            "a calendar entry."
                        )

    async def check_timeout(self) -> None:
        """Check if any of the ongoing events should be timed out."""
        async with self.lock:
            # Looping through the keys because we are mutating the dict
            for message_id in copy.copy(list(self.ongoing_events.keys())):
                ongoing_event = self.ongoing_events[message_id]
                if ongoing_event.timed_out():
                    await self.end_ongoing_event(message_id)
