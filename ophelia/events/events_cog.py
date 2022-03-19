"""Events Cog Module."""
import functools
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import yaml
from discord import (
    Colour, Guild, Member, RawBulkMessageDeleteEvent, RawMessageDeleteEvent,
    RawReactionActionEvent, Role
)
from discord.ext import commands, tasks
from discord.ext.commands import Context
from loguru import logger

from ophelia import settings
from ophelia.events.calendar.base_event import BaseEvent, EventLoadError
from ophelia.events.calendar.guild_event_log import (
    GuildEventInvalidConfig, GuildEventLog
)
from ophelia.events.calendar.member_event import MemberEvent
from ophelia.events.calendar.ongoing_event import OngoingEvent
from ophelia.events.calendar.recurring_event import RecurringEvent
from ophelia.events.config_options import (
    add_edit_time_params, add_event_time_params, BASE_ADD_CONFIG_ITEMS,
    BASE_EDIT_CONFIG_ITEMS, BASE_RECURRING_CONFIG_ITEMS, SETUP_CONFIG_ITEMS
)
from ophelia.events.events_emotes import (
    APPROVE_EMOTE, END_EVENT_EMOTE, NOTIF_EMOTE, REJECT_EMOTE
)
from ophelia.output.error_handler import OpheliaCommandError
from ophelia.output.output import (
    disp_str, response_config, response_options, send_message,
    send_message_embed,
    send_simple_embed
)
from ophelia.utils.discord_utils import (
    FETCH_FAIL_EXCEPTIONS,
    filter_self_react
)

CONFIG_TIMEOUT_SECONDS = settings.long_timeout
CONFIG_MAX_TRIES = settings.max_tries
CHECK_INTERVAL_MINUTES = settings.events_check_interval_minutes
SAVE_INTERVAL_MINUTES = settings.config_save_interval_minutes


class EventsCog(commands.Cog, name="events"):
    """
    Event Calendar.

    Manage server event calendar boards, including recurring events,
    member-initiated events, staff vetting of event submissions and
    edits, notification subscriptions to events, and event tracking.
    Settings are configured per server and stored separately for each
    server.
    """

    __slots__ = ["guild_event_logs", "bot", "events_db"]

    # Using forward references to avoid cyclic imports
    # noinspection PyUnresolvedReferences
    def __init__(self, bot: "OpheliaBot") -> None:
        """
        Initializer for the EventsCog class.

        :param bot: Ophelia bot object
        """
        self.bot = bot
        self.guild_event_logs: Dict[str, Any] = {}
        self.events_db: dict = {}

        self.save_database.start()  # pylint: disable=no-member
        self.check_update.start()  # pylint: disable=no-member

    async def cog_save_all(self) -> None:
        """Save all events and server config options to database."""
        for guild_id_str in self.guild_event_logs:
            await self.save_guild_to_database(guild_id_str)

    @staticmethod
    async def list_events(
            event_dict: Dict[int, BaseEvent]
    ) -> Tuple[List[str], Dict[str, Dict[str, int]]]:
        """
        Get an event list string and a dictionary of callables for each
        event option.

        :param event_dict: Dictionary of events indexed by calendar
            message ID
        :return: Tuple of string list of events and a dictionary of
            event selection options with corresponding command response
            callables
        """
        str_list = []
        options_dict = {}
        for num, (event_id, event) in enumerate(event_dict.items()):
            counter = num + 1
            str_list.append(f"**{counter}** | {event.title} ({event_id})")
            options_dict[str(counter)] = {"event_id": event_id}

        return str_list, options_dict

    class EventDecorators:
        """
        Event decorators for checking relevant guild configs and staff
        roles before each listener or command.
        """

        @classmethod
        def guild_context_check(cls, func: Callable) -> Callable:
            """
            Decorator for checking if guild has been set up from command
            context.

            :param func: Async function to be wrapped
            :return: Wrapped function
            """

            @functools.wraps(func)
            async def wrapped(
                    self: "EventsCog",
                    context: Context,
                    *args,
                    **kwargs
            ) -> None:
                """
                Inner function.

                :param self: EventsCog instance
                :param context: Command context
                :param args: Arguments
                :param kwargs: Keyword arguments
                """
                if str(context.guild.id) not in self.guild_event_logs:
                    raise OpheliaCommandError("events_no_guild")

                return await func(self, context, *args, **kwargs)

            return wrapped

        @classmethod
        def pass_user_events(cls, func: Callable) -> Callable:
            """
            Decorator to pass the list of events initiated by the user
            directly to the command.

            :param func: Async function to be wrapped
            :return: Wrapped function
            """

            @functools.wraps(func)
            async def wrapped(
                    self: "EventsCog",
                    context: Context,
                    *args,
                    **kwargs
            ) -> None:
                """
                Inner function.

                :param self: EventsCog instance
                :param context: Command context
                """
                event_log: GuildEventLog = self.guild_event_logs[
                    str(context.guild.id)
                ]
                event_dict = await event_log.retrieve_user_events(
                    context.author.id
                )

                if not event_dict:
                    raise OpheliaCommandError("events_no_events")

                await func(
                    self,
                    context=context,
                    event_dict=event_dict,
                    *args,
                    **kwargs
                )

            return wrapped

        @classmethod
        def guild_payload_check(cls, func: Callable) -> Callable:
            """
            Decorator for checking if guild has been set up from discord
            raw action payload.

            :param func: Async function to be wrapped
            :return: Wrapped function
            """

            @functools.wraps(func)
            async def wrapped(
                    self: "EventsCog",
                    payload: Union[
                        RawReactionActionEvent,
                        RawMessageDeleteEvent,
                        RawBulkMessageDeleteEvent
                    ],
                    *args,
                    **kwargs
            ) -> None:
                """
                Inner function.

                :param self: EventsCog instance
                :param payload: Raw discord action payload to extract
                    guild ID from
                :param args: arguments
                :param kwargs: Keyword arguments
                """
                guild_id = payload.guild_id
                if (
                        guild_id is None
                        or str(guild_id) not in self.guild_event_logs
                ):
                    return

                return await func(self, payload, *args, **kwargs)

            return wrapped

        @classmethod
        def guild_staff_check(cls, func: Callable) -> Callable:
            """
            Decorator for checking if command caller has the staff role.

            Since this decorator also checks if the guild has been set
            up yet, commands that use this decorator can skip the
            context check decorator.

            :param func: Async function to be wrapped
            :return: Wrapped function
            """

            @functools.wraps(func)
            async def wrapped(
                    self: "EventsCog",
                    context: Context,
                    *args,
                    **kwargs
            ) -> None:
                """
                Inner function.

                :param self: EventsCog instance
                :param context: Command context
                :param args: arguments
                :param kwargs: Keyword arguments
                """
                guild_id = context.guild.id
                if str(guild_id) not in self.guild_event_logs:
                    return

                # We can assume that the author is a member since the
                # command group is guild only.
                author: Member = context.author
                guild_event_log: GuildEventLog = self.guild_event_logs[
                    str(guild_id)
                ]
                staff_role: Role = guild_event_log.staff_role

                if staff_role not in author.roles:
                    raise OpheliaCommandError("events_not_staff")

                return await func(self, context, *args, **kwargs)

            return wrapped

    async def load_from_database(self) -> None:
        """Load all events and server config options from database."""
        with open(settings.file_events_db, "r", encoding="utf-8") as file:
            self.events_db = yaml.safe_load(file)

        for guild_id_str, config_dict in self.events_db.items():
            guild = self.bot.get_guild(int(guild_id_str))
            if guild is None:
                logger.warning(
                    "Events failed to fetch guild config for guild {}",
                    guild_id_str
                )
                continue

            self.guild_event_logs[guild_id_str] = (
                await GuildEventLog.parse_guild_config(guild, config_dict)
            )

    async def save_guild_to_database(self, guild_id_str: str) -> None:
        """
        Save the events log of a single guild to database.

        :param guild_id_str: Discord Guild ID as a string
        :raises KeyError: Guild ID event log could not be found
        """
        if guild_id_str not in self.guild_event_logs:
            raise KeyError

        guild_event_log: GuildEventLog = self.guild_event_logs[guild_id_str]
        guild_saved_config = await guild_event_log.save_config()
        self.events_db[guild_id_str] = guild_saved_config

        with open(settings.file_events_db, "w", encoding="utf-8") as file:
            yaml.dump(
                self.events_db,
                file,
                default_flow_style=False,
                allow_unicode=True
            )

    @tasks.loop(minutes=SAVE_INTERVAL_MINUTES)
    async def save_database(self) -> None:
        """Save backup to database."""
        await self.cog_save_all()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_update(self) -> None:
        """Check for event notification and timeout updates."""
        event_log: GuildEventLog
        for event_log in self.guild_event_logs.values():
            await event_log.check_retrieve()
            await event_log.check_start()
            await event_log.check_notify()
            await event_log.check_update()
            await event_log.check_timeout()

    @commands.Cog.listener()
    @EventDecorators.guild_payload_check
    @filter_self_react
    async def on_raw_reaction_add(
            self,
            reaction_payload: RawReactionActionEvent
    ) -> None:
        """
        Listener for adding reactions.

        Used for staff approval reactions and event notification
        subscription reactions.

        :param reaction_payload: Raw reaction payload
        """
        emote = reaction_payload.emoji.name
        guild_event_log = self.guild_event_logs[str(reaction_payload.guild_id)]
        if emote == APPROVE_EMOTE:
            await self.approve(guild_event_log, reaction_payload.message_id)
        elif emote == REJECT_EMOTE:
            await self.reject(guild_event_log, reaction_payload.message_id)
        elif emote == NOTIF_EMOTE:
            await self.subscribe_event(
                guild_event_log,
                reaction_payload.message_id,
                reaction_payload.user_id,
                reaction_payload.guild_id
            )
        elif emote == END_EVENT_EMOTE:
            await self.end_ongoing_event(
                guild_event_log,
                reaction_payload.guild_id,
                reaction_payload.message_id,
                reaction_payload.user_id
            )

    @commands.Cog.listener()
    @EventDecorators.guild_payload_check
    @filter_self_react
    async def on_raw_reaction_remove(
            self,
            reaction_payload: RawReactionActionEvent
    ) -> None:
        """
        Listener for removing reactions.

        Used for event notification unsubscription reactions.

        :param reaction_payload: Raw reaction payload
        """
        emote = reaction_payload.emoji.name
        if emote == NOTIF_EMOTE:
            guild_event_log = self.guild_event_logs[
                str(reaction_payload.guild_id)
            ]
            await self.subscribe_event(
                guild_event_log,
                reaction_payload.message_id,
                reaction_payload.user_id,
                reaction_payload.guild_id,
                unsubscribe=True
            )

    @commands.Cog.listener()
    @EventDecorators.guild_payload_check
    async def on_raw_message_delete(
            self,
            raw_message_delete: RawMessageDeleteEvent
    ) -> None:
        """
        Listener for messages being deleted.

        Used for when event calendar entries are deleted so that the
        backend is synced with the actual channel.

        :param raw_message_delete: Raw deletion event
        """
        await self.delete_event(
            raw_message_delete.guild_id,
            raw_message_delete.message_id
        )

    @commands.Cog.listener()
    @EventDecorators.guild_payload_check
    async def on_raw_bulk_message_delete(
            self,
            raw_bulk_message_delete: RawBulkMessageDeleteEvent
    ) -> None:
        """
        Listener for message bulk deletions.

        Used for when event calendar entries are deleted in bulk so that
        the backend is synced with the actual channel.

        :param raw_bulk_message_delete: Raw bulk deletion event
        """
        for event_id in raw_bulk_message_delete.message_ids:
            await self.delete_event(
                raw_bulk_message_delete.guild_id,
                event_id
            )

    @commands.group("event", invoke_without_command=True)
    @commands.bot_has_guild_permissions(send_messages=True, embed_links=True)
    @commands.guild_only()
    async def event(self, context: Context, *_) -> None:
        """
        Main event command, displays list of subcommands.

        :param context: Command context
        """
        await send_simple_embed(context, "events")

    @staticmethod
    async def command_event_add_success(
            context: Context,
            event: BaseEvent
    ) -> None:
        """
        Command response after successful event submission.

        :param context: Command context
        :param event: Event submitted
        """
        await send_message(
            channel=context,
            text=disp_str("events_add_success"),
            embed=await event.get_approval_embed()
        )

    @event.command(name="setup")
    @commands.has_guild_permissions(administrator=True)
    async def event_setup(self, context: Context) -> None:
        """
        Set up the event calendar module.

        :param context: Command context
        """
        message = await send_simple_embed(
            context,
            "events_setup",
            colour=Colour(settings.embed_color_important)
        )

        await response_config(
            bot=self.bot,
            context=context,
            message=message,
            config_items=SETUP_CONFIG_ITEMS,
            response_call=self.confirm_setup,
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            response_tries=CONFIG_MAX_TRIES,
            timeout_exception=OpheliaCommandError("events_cmd_exit"),
            delete_message=True,
            delete_response=True
        )

    async def confirm_setup(self, context: Context, config_vars: dict) -> None:
        """
        Confirm event module server setup.

        :param context: Command context
        :param config_vars: Configuration variables
        """
        approval_events, upcoming_events, ongoing_events, approval_edits = (
            {}, {}, {}, {}
        )

        # Check if the server already has events
        guild_id = context.guild.id
        old_log: Optional[GuildEventLog] = None
        if str(guild_id) in self.guild_event_logs:
            old_log = self.guild_event_logs[str(guild_id)]
            approval_events = old_log.approval_events
            upcoming_events = old_log.upcoming_events
            ongoing_events = old_log.ongoing_events
            approval_edits = old_log.approval_edits

        config_vars.update({
            "approval_events": approval_events,
            "upcoming_events": upcoming_events,
            "ongoing_events": ongoing_events,
            "approval_edits": approval_edits
        })

        # Initialize new event log with event and edit lists
        try:
            new_log = await GuildEventLog.new_guild_log(config_vars)
            self.guild_event_logs[str(guild_id)] = new_log

            if old_log is not None:
                await new_log.force_update_calendar(
                    old_log.calendar_channel,
                    new_log.calendar_channel
                )
                await new_log.force_update_approvals(
                    old_log.approval_channel,
                    new_log.approval_channel
                )

            await send_simple_embed(
                context,
                "events_setup_success",
                colour=Colour(settings.embed_color_success)
            )

            await self.save_guild_to_database(str(guild_id))

        except GuildEventInvalidConfig as e:
            raise OpheliaCommandError("events_guild_event_invalid") from e

    @event.command(name="add", aliases=["a", "submit"])
    @EventDecorators.guild_context_check
    async def event_add(self, context: Context) -> None:
        """
        Submit member event for staff approval.

        :param context: Command context
        """
        message = await send_simple_embed(
            context,
            "events_add",
            colour=Colour(settings.embed_color_important)
        )

        await response_config(
            bot=self.bot,
            context=context,
            message=message,
            config_items=await add_event_time_params(BASE_ADD_CONFIG_ITEMS),
            response_call=await self.gen_confirm_add(MemberEvent.config_name()),
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            response_tries=CONFIG_MAX_TRIES,
            timeout_exception=OpheliaCommandError("events_cmd_exit")
        )

    @event.command(name="addr", aliases=["ar"])
    @EventDecorators.guild_staff_check
    async def event_add_recurring(self, context: Context) -> None:
        """
        Submit recurring event for staff approval.

        This command checks if the user has the staff role configured
        for the guild as recurring events are not designed to be used
        by regular members.

        :param context: Command context
        """
        message = await send_simple_embed(
            context,
            "events_add_recurring",
            colour=Colour(settings.embed_color_important)
        )

        await response_config(
            bot=self.bot,
            context=context,
            message=message,
            config_items=await add_event_time_params(
                BASE_RECURRING_CONFIG_ITEMS
            ),
            response_call=await self.gen_confirm_add(
                RecurringEvent.config_name()
            ),
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            response_tries=CONFIG_MAX_TRIES,
            timeout_exception=OpheliaCommandError("events_cmd_exit")
        )

    async def gen_confirm_add(self, type_str: str) -> Callable:
        """
        Confirm event addition.

        :param type_str: Type of event to be added
        :return Add event confirmation response async callable
        """

        async def func(context: Context, config_vars: dict) -> None:
            """
            Internal function.

            :param context: Command context
            :param config_vars: Event config variables
            """
            config_vars["organizer"] = context.author.id
            config_vars["type"] = type_str
            try:
                guild = context.guild
                guild_log: GuildEventLog = self.guild_event_logs[str(guild.id)]
                event = await guild_log.submit_event(config_vars, guild)

                await self.command_event_add_success(context, event)
            except EventLoadError as e:
                raise OpheliaCommandError("events_add_fail") from e

        return func

    @event.command(name="edit", aliases=["e"])
    @EventDecorators.guild_context_check
    @EventDecorators.pass_user_events
    async def event_edit(self, context: Context, *_, **kwargs) -> None:
        """
        Submit event edit for staff approval.

        All members can edit their own events.

        There's an additional param, event_dict, that's passed through
        kwargs - it's a dictionary of events initiated by the user,
        indexed by message ID.

        :param context: Command context
        """
        event_dict = kwargs["event_dict"]

        # Ask user to pick an event
        str_list, options_dict = await self.list_events(event_dict)
        event_str = "\n".join(str_list)
        message = await send_simple_embed(context, "events_add_edit", event_str)

        await response_options(
            bot=self.bot,
            context=context,
            message=message,
            response_call=self.edit_menu,
            options=options_dict,
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            timeout_exception=OpheliaCommandError("events_cmd_exit")
        )

    async def edit_menu(self, context: Context, event_id: int) -> None:
        """
        Confirm submission of event edit.

        :param context: Command context
        :param event_id: Event ID to edit
        :return Async callable that takes user through a step-by-step
            menu for entering event edit details
        """
        message = await send_simple_embed(
            context,
            "events_edit_menu",
            colour=Colour(settings.embed_color_important)
        )

        await response_config(
            bot=self.bot,
            context=context,
            message=message,
            config_items=await add_edit_time_params(
                BASE_EDIT_CONFIG_ITEMS
            ),
            response_call=await self.gen_confirm_edit(event_id),
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            response_tries=CONFIG_MAX_TRIES,
            timeout_exception=OpheliaCommandError("events_cmd_exit")
        )

    async def gen_confirm_edit(self, event_id: int) -> Callable:
        """
        Confirm event edit submission.

        :param event_id: Event message ID
        :return Edit confirmation repsonse async callable
        """

        async def func(context: Context, config_vars: dict) -> None:
            """
            Interval function.

            :param context: Command context
            :param config_vars: Event edit config variables
            """
            config_vars["event_message_id"] = event_id
            guild = context.guild
            guild_log: GuildEventLog = self.guild_event_logs[str(guild.id)]
            edit = await guild_log.submit_edit(config_vars)

            await send_message(
                channel=context,
                text=disp_str("events_edit_success"),
                embed=await edit.get_approval_embed(
                    guild_log.upcoming_events[event_id]
                )
            )

        return func

    @event.command(name="delete", aliases=["d"])
    @EventDecorators.guild_context_check
    @EventDecorators.pass_user_events
    async def event_delete(self, context: Context, *_, **kwargs) -> None:
        """
        Delete upcoming event.

        All members can delete their own events.

        There's an additional param, event_dict, that's passed through
        kwargs - it's a dictionary of events initiated by the user,
        indexed by message ID.

        :param context: Command context
        """
        event_dict = kwargs["event_dict"]

        # Ask user to pick an event
        str_list, options_dict = await self.list_events(event_dict)
        event_str = "\n".join(str_list)
        message = await send_simple_embed(context, "events_delete", event_str)

        await response_options(
            bot=self.bot,
            context=context,
            message=message,
            response_call=self.delete_menu,
            options=options_dict,
            timeout_seconds=CONFIG_TIMEOUT_SECONDS,
            timeout_exception=OpheliaCommandError("events_cmd_exit")
        )

    async def delete_menu(self, context: Context, event_id: int) -> None:
        """
        Confirm deletion of event.

        :param context: Command context
        :param event_id: Event ID to delete
        :return: Async callable that deletes event
        """
        guild_log: GuildEventLog = self.guild_event_logs[str(context.guild.id)]
        await guild_log.delete_upcoming_event(event_id)
        await send_simple_embed(
            context,
            "events_delete_confirm",
            colour=Colour(settings.embed_color_severe)
        )

    @event.command(name="listall", aliases=["la"])
    @EventDecorators.guild_staff_check
    async def event_listall(self, context: Context) -> None:
        """
        Lists all background events in the current server.

        :param context: Command context
        """
        event_log: GuildEventLog = self.guild_event_logs[str(context.guild.id)]
        approval_list = "\n".join(
            f"> {k}: {v.title}" for k, v in event_log.approval_events.items()
        )
        upcoming_list = "\n".join(
            f"> {k}: {v.title}" for k, v in event_log.upcoming_events.items()
        )
        ongoing_list = "\n".join(
            f"> {k}: {v.message_embed.title}"
            for k, v in event_log.ongoing_events.items()
        )

        await send_message_embed(
            channel=context,
            title=disp_str("events_listall_title"),
            desc=disp_str("events_listall_desc").format(
                approval_list,
                upcoming_list,
                ongoing_list
            )
        )

    @event.command(name="forcedelete", aliases=["forcedel", "fd"])
    @EventDecorators.guild_staff_check
    async def event_force_delete(
            self,
            context: Context,
            *,
            event_id_str: str
    ) -> None:
        """
        Force deletes or rejects an event by ID.

        :param context: Command context
        :param event_id_str: Event ID string
        """
        try:
            event_id = int(event_id_str)
        except ValueError as e:
            raise OpheliaCommandError("events_forcedelete_not_int") from e

        await self.delete_event(context.guild.id, event_id)
        await send_simple_embed(context, "events_forcedelete")

    async def delete_event(
            self,
            guild_id: int,
            event_id: int
    ) -> None:
        """
        Delete an event by event message ID.

        :param guild_id: ID of Discord Guild
        :param event_id: Event ID
        """
        event_log: GuildEventLog = self.guild_event_logs[str(guild_id)]

        await event_log.reject_event(event_id)
        await event_log.delete_upcoming_event(event_id)
        await event_log.end_ongoing_event(event_id)

    @event.command(name="save", aliases=["s"])
    @EventDecorators.guild_staff_check
    async def event_save(self, context: Context) -> None:
        """
        Saves current event configuration to file.

        The bot runs a check first to ensure that the user has the staff
        role configured in the guild. It saves the event configuration
        only for the guild that the command is being run in.

        :param context: Command context
        """
        await self.save_guild_to_database(str(context.guild.id))
        await send_simple_embed(
            context,
            "events_save",
            colour=Colour(settings.embed_color_success)
        )

    @staticmethod
    async def approve(guild_event_log: GuildEventLog, message_id: int) -> None:
        """
        Approve a submitted event or edit.

        :param guild_event_log: Guild event log
        :param message_id: Reaction message ID
        """
        await guild_event_log.approve_event(message_id)
        await guild_event_log.approve_edit(message_id)

    @staticmethod
    async def reject(guild_event_log: GuildEventLog, message_id: int) -> None:
        """
        Reject a submitted event or edit.

        :param guild_event_log: Guild Event log
        :param message_id: Reaction message ID
        """
        await guild_event_log.reject_event(message_id)
        await guild_event_log.reject_edit(message_id)

    async def subscribe_event(
            self,
            guild_event_log: GuildEventLog,
            message_id: int,
            member_id: int,
            guild_id: int,
            unsubscribe: bool = False
    ) -> None:
        """
        Subscribe to an upcoming event.

        :param guild_event_log: Guild event log
        :param message_id: Reaction message ID
        :param member_id: ID of member subscribing
        :param guild_id: ID of Discord Guild
        :param unsubscribe: Whether the member is unsubscribing
        """
        guild: Guild = self.bot.get_guild(guild_id)
        try:
            member: Member = await guild.fetch_member(member_id)
        except FETCH_FAIL_EXCEPTIONS:
            return

        await guild_event_log.subscribe_event(
            message_id=message_id,
            member=member,
            unsubscribe=unsubscribe
        )

    async def end_ongoing_event(
            self,
            guild_event_log: GuildEventLog,
            guild_id: int,
            message_id: int,
            member_id: int
    ) -> None:
        """
        End an ongoing event.

        :param guild_event_log: Guild event log
        :param guild_id: Discord Guild ID
        :param message_id: Message ID of event to end
        :param member_id: Member ID of member who tried to end it
        """
        guild: Guild = self.bot.get_guild(guild_id)
        try:
            ongoing_event: OngoingEvent = guild_event_log.ongoing_events[
                message_id
            ]
        except KeyError:
            return

        delete_event = False
        if member_id == ongoing_event.organizer_id:
            delete_event = True
        else:
            try:
                member: Member = await guild.fetch_member(member_id)
            except FETCH_FAIL_EXCEPTIONS:
                return

            if guild_event_log.staff_role in member.roles:
                delete_event = True

        if delete_event:
            await guild_event_log.end_ongoing_event(message_id)
