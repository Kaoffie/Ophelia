"""
Role reaction module.

There's tons of reaction-based role assignment bots out there, so it's
kinda pointless to try to reinvent the wheel here again; in this case,
however, we had the problem of having way too many roles to make a role
selection menu that was easy to navigate, so traditional implementations
weren't going to work.

In this case, we've opted for a solution that sends the user a DM with
a list of all the roles that they can assign and remove.

We're disabling pylint's too many branches here. The maximum if/else
branch count (12) is used to prevent the writing of code that's too hard
to follow, and since the branches in this module can be easily broken
into commented steps and they aren't nested in each other, so it should
be readable enough to justify shutting pylint up for this.
"""

import asyncio
import re
from typing import Callable, Dict, List, Tuple, Union

import emoji
import yaml
from discord import (
    Colour, Emoji, Forbidden, Guild, HTTPException, Member, Message,
    PartialEmoji, RawBulkMessageDeleteEvent, RawMessageDeleteEvent,
    RawReactionActionEvent, RawReactionClearEmojiEvent, RawReactionClearEvent,
    Role, TextChannel
)
from discord.ext import commands
from discord.ext.commands import Context
from loguru import logger

from ophelia import settings
from ophelia.output.error_handler import OpheliaCommandError
from ophelia.output.output import (
    ConvertFailureException, ConvertNotFoundException, disp_str,
    response_convert, response_switch, response_yaml, send_embed,
    send_error_embed, send_message,
    send_simple_embed
)
from ophelia.reactrole.dm_lock import AbortQueue, DMLock
from ophelia.reactrole.reactrole_config import (
    InvalidReactConfigException, MessageConfig, ReactroleConfig, RoleMenuConfig,
    SingleRoleConfig
)
from ophelia.utils.discord_utils import (
    ARGUMENT_FAIL_EXCEPTIONS, extract_role, FETCH_FAIL_EXCEPTIONS,
    filter_self_react
)
from ophelia.utils.text_utils import (
    EMOTE_REGEX, extract_emoji, is_possibly_emoji
)

DM_TIMEOUT = settings.long_timeout
COMMAND_TIMEOUT = settings.short_timeout
YAML_TIMEOUT = settings.long_timeout


class ReactroleCog(commands.Cog, name="reactrole"):
    """
    Reaction roles.

    Assign roles to members using reactions. Designed for servers with
    a large number of roles providing a reaction option that DMs users
    role lists for further selection.
    """

    __slots__ = ["bot", "config", "dm_lock"]

    # Using forward references (See PEP 484) to avoid cyclic imports
    # noinspection PyUnresolvedReferences
    def __init__(self, bot: "OpheliaBot") -> None:
        """
        Initializer for the ReactroleCog class.

        :param bot: Ophelia bot object
        """
        logger.debug("Initializing the Reactrole Cog.")
        self.bot = bot
        self.config = ReactroleConfig()
        self.dm_lock = DMLock()

    async def cog_save_all(self) -> None:
        """Save all cog configurations before shutdown."""
        await self.config.save_file()

    @commands.Cog.listener()
    async def on_raw_reaction_add(
            self,
            reaction_payload: RawReactionActionEvent
    ) -> None:
        """
        Listener for adding reactions.

        :param reaction_payload: Raw reaction payload
        """
        # Role assign will filter out any bot inputs
        await self.role_assign(reaction_payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
            self,
            reaction_payload: RawReactionActionEvent
    ) -> None:
        """
        Listener for removing reactions.

        :param reaction_payload: Raw reaction payload
        """
        # Role assign will filter out any bot inputs
        await self.role_assign(reaction_payload, True)
        await self.delete_reaction(reaction_payload)

    @commands.Cog.listener()
    async def on_raw_reaction_clear_emoji(
            self,
            reaction_payload: RawReactionClearEmojiEvent
    ) -> None:
        """
        Listener for emoji clears on a message.

        :param reaction_payload: Raw emoji clear payload
        """
        await self.delete_reaction(reaction_payload)

    @commands.Cog.listener()
    async def on_raw_message_delete(
            self,
            raw_message_delete: RawMessageDeleteEvent
    ) -> None:
        """
        Listener for deleting messages.

        :param raw_message_delete: Raw deletion event
        """
        await self.delete_message(raw_message_delete.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(
            self,
            raw_reaction_clear: RawReactionClearEvent
    ) -> None:
        """
        Listener for reaction clears.

        :param raw_reaction_clear: Raw reaction clear event
        """
        await self.delete_message(raw_reaction_clear.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(
            self,
            raw_bulk_message_delete: RawBulkMessageDeleteEvent
    ) -> None:
        """
        Listener for bulk deleting messages.

        :param raw_bulk_message_delete: Raw deletion event
        """
        for message_id in raw_bulk_message_delete.message_ids:
            await self.delete_message(message_id)

    @staticmethod
    async def command_cancel(context: Context) -> None:
        """
        Command response when user cancels an operation.

        :param context: Command context
        """
        await send_simple_embed(context, "reactrole_cmd_exit")

    @commands.command("reactrole")
    @commands.has_guild_permissions(administrator=True)
    async def reactrole(self, context: Context) -> None:
        """
        Main reactrole configuration command.

        :param context: Command context
        """
        message = await send_embed(
            channel=context,
            embed_text=disp_str("reactrole_cmd_menu_options"),
            title=disp_str("reactrole_cmd_menu_title"),
            timestamp=None,
            embed_fallback=True
        )

        await response_switch(
            bot=self.bot,
            context=context,
            message=message,
            options={
                "1": self.command_add_reaction,
                "2": self.command_delete_reaction,
                "3": self.command_view_reaction
            },
            timeout_seconds=COMMAND_TIMEOUT,
            timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
        )

    @staticmethod
    async def retrieve_message(
            context: Context,
            user_input: str
    ) -> Message:
        """
        Converts message ID as a string into a Message object.

        :param context: Context to search for message
        :param user_input: String sent by user
        :return: Message object retrieved from message ID contained in
            user string, or None if message could not be found
        :raises ConvertNotFoundException: When the message corresponding
            to the input message ID cannot be retrieved
        :raises ConvertFailureException: When user input is not a valid
            message ID
        """
        if not user_input.isnumeric():
            raise ConvertFailureException

        try:
            message_id = int(user_input)
            channel: TextChannel = context.channel

            try:
                message = await channel.fetch_message(message_id)
                return message
            except FETCH_FAIL_EXCEPTIONS:
                raise ConvertNotFoundException

        except ValueError as e:
            raise ConvertFailureException from e

    async def retrieve_emoji(
            self,
            _: Context,
            user_input: str
    ) -> Union[str, Emoji]:
        """
        Async wrapper for extract_emoji.

        :param _: Command context
        :param user_input: String sent by user
        :return: Unicode emoji string or Discord Emoji
        :raises ConvertFailureException: When the user input does not
            contain a valid emote or emoji
        """
        emote = extract_emoji(user_input, self.bot)
        if emote is None:
            raise ConvertFailureException

        return emote

    async def retrieve_messages_in_guild(
            self,
            guild: Guild
    ) -> Tuple[
        Dict[str, MessageConfig],
        Dict[str, MessageConfig],
        Dict[str, Message]
    ]:
        """
        Retrieves all message configs for a given guild and splits them
        into two dictionaries, one of message configs of messages that
        are still retrievable by the bot, and one of message configs
        that are no longer retrievable, either because they have been
        deleted or the bot no longer has the necessary permissions to
        view them.

        :param guild: Guild to retrieve message configs from
        :return: Tuple of three dictionaries; the first is of message
            configs of messages that are fetchable by the bot, the
            second is of those that are not; the third is of the Discord
            message objects corresponding to the configs of the first
            dictionary; all three are indexed by message ID
        """
        message_configs = await self.config.list_guild_message_configs(guild.id)

        # Filter fetchable channels
        fetchable_channels: Dict[int, TextChannel] = {
            channel.id: channel
            for channel in await guild.fetch_channels()
            if isinstance(channel, TextChannel)
        }

        fetchable_message_configs: Dict[str, MessageConfig] = {}
        unfetchable_message_configs: Dict[str, MessageConfig] = {}
        fetchable_messages: Dict[str, Message] = {}

        message_config: MessageConfig
        for message_id_str, message_config in message_configs.items():
            if message_config.channel_id not in fetchable_channels:
                unfetchable_message_configs[message_id_str] = message_config
                continue

            channel = fetchable_channels[message_config.channel_id]
            try:
                message = await channel.fetch_message(int(message_id_str))
                fetchable_message_configs[message_id_str] = message_config
                fetchable_messages[message_id_str] = message
            except FETCH_FAIL_EXCEPTIONS:
                unfetchable_message_configs[message_id_str] = message_config

        return (
            fetchable_message_configs,
            unfetchable_message_configs,
            fetchable_messages
        )

    @staticmethod
    async def print_message_configs(configs: Dict[str, MessageConfig]) -> str:
        """
        Get a user-friendly list of message configs.

        :param configs: Dictionary of message configs indexed by message
            ID
        :return: String representation of message configs
        """
        if not configs:
            return disp_str("reactrole_cmd_no_messages_found")

        return "\n".join(
            f"> **{message_id_str}** "
            f"| {len(config.reacts)} Reaction{'s' * (len(config.reacts) != 1)}"
            for message_id_str, config in configs.items()
        )

    async def command_add_reaction(self, context: Context) -> None:
        """
        Ask user for message ID to add reaction roles to.

        :param context: Command context
        """
        message = await send_embed(
            channel=context,
            embed_text=disp_str("reactrole_cmd_add_reaction_desc"),
            title=disp_str("reactrole_cmd_add_reaction_title"),
            timestamp=None,
            embed_fallback=True
        )

        await response_convert(
            bot=self.bot,
            context=context,
            message=message,
            conversion_call=self.retrieve_message,
            success_call=self.command_add_type,
            notfound_exception=OpheliaCommandError("reactrole_cmd_invalid_arg"),
            failure_exception=OpheliaCommandError("reactrole_cmd_invalid_arg"),
            timeout_seconds=COMMAND_TIMEOUT,
            timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
        )

    async def command_delete_reaction(self, context: Context) -> None:
        """
        Ask user for message ID to delete from reaction roles config.

        :param context: Command context
        """
        (
            fetchable, unfetchable, messages
        ) = await self.retrieve_messages_in_guild(context.guild)

        message = await send_embed(
            channel=context,
            embed_text=disp_str("reactrole_cmd_delete_reaction_desc").format(
                await self.print_message_configs(fetchable),
                await self.print_message_configs(unfetchable)
            ),
            title=disp_str("reactrole_cmd_delete_reaction_title"),
            timestamp=None,
            embed_fallback=True
        )

        options = {}
        for message_id_str in fetchable:
            options[message_id_str] = await self.gen_command_delete_message(
                messages[message_id_str]
            )

        for message_id_str in unfetchable:
            options[
                message_id_str
            ] = await self.gen_command_delete_invalid_message(
                message_id_str
            )

        await response_switch(
            bot=self.bot,
            context=context,
            message=message,
            options=options,
            timeout_seconds=COMMAND_TIMEOUT,
            timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
        )

    async def command_view_reaction(self, context: Context) -> None:
        """
        Ask user for message ID to edit the reaction roles for.

        :param context: Command context
        """
        (
            fetchable, unfetchable, messages
        ) = await self.retrieve_messages_in_guild(context.guild)

        sent_message = await send_embed(
            channel=context,
            embed_text=disp_str("reactrole_cmd_view_reaction_desc").format(
                await self.print_message_configs(fetchable),
                await self.print_message_configs(unfetchable)
            ),
            title=disp_str("reactrole_cmd_view_reaction_title"),
            timestamp=None,
            embed_fallback=True
        )

        options = {}
        for message_id_str in fetchable:
            options[message_id_str] = await self.gen_command_view_yaml(
                messages[message_id_str]
            )
        for message_id_str in unfetchable:
            options[
                message_id_str
            ] = await self.gen_command_delete_invalid_message(
                message_id_str
            )

        await response_switch(
            bot=self.bot,
            context=context,
            message=sent_message,
            options=options,
            timeout_seconds=COMMAND_TIMEOUT,
            timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
        )

    async def command_add_type(
            self,
            context: Context,
            message: Message
    ) -> None:
        """
        Prompts the user to select a reaction type to add to the config
        based on the given message.

        :param context: Command context
        :param message: Message to add reaction to
        """
        sent_message = await send_embed(
            channel=context,
            embed_text=disp_str("reactrole_cmd_add_type_desc").format(
                message.id
            ),
            title=disp_str("reactrole_cmd_add_type_title"),
            timestamp=None,
            embed_fallback=True
        )

        await response_switch(
            bot=self.bot,
            context=context,
            message=sent_message,
            options={
                "1": await self.gen_command_add_simple_reaction(message),
                "2": await self.gen_command_add_dm_emote(message)
            },
            timeout_seconds=COMMAND_TIMEOUT,
            timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
        )

    async def gen_command_add_simple_reaction(
            self,
            message: Message
    ) -> Callable:
        """
        First order function for adding new simple reaction role.

        :param message: Message to add reaction to
        :return: Command callable to request for a list of emotes
            and corresponding roles
        """

        async def func(context: Context) -> None:
            """
            Generic command response to ask for reaction emotes and
            roles.

            :param context: Command context
            """
            sent_message = await send_embed(
                channel=context,
                embed_text=disp_str("reactrole_cmd_add_simple_reaction_desc"),
                title=disp_str("reactrole_cmd_add_simple_reaction_title"),
                timestamp=None,
                embed_fallback=True
            )

            await response_yaml(
                bot=self.bot,
                context=context,
                message=sent_message,
                key_set=None,
                response_call=await self.gen_command_add_simple_confirm(
                    message
                ),
                timeout_seconds=YAML_TIMEOUT,
                timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
            )

        return func

    # pylint: disable=too-many-branches
    async def gen_command_add_simple_confirm(
            self,
            message: Message
    ) -> Callable:
        """
        First order function for confirming the addition of a new
        simple reaction role.

        :param message: Message to add reaction to
        :return: Command callable to add simple reaction role config
            and confirm the addition with the user
        """

        async def func(yaml_output: dict, context: Context) -> None:
            """
            Generic command response to confirm simple reaction role
            addition.

            :param yaml_output: YAML parser output for initializing
                reaction role configuration
            :param context: Command context
            """
            add_pile: List[Tuple[Union[str, Emoji], Role]] = []
            discard_pile = []
            for emote_repr, role_repr in yaml_output.items():
                if not isinstance(emote_repr, str):
                    discard_pile.append((emote_repr, role_repr))
                    continue

                # Check if role is real
                role = await extract_role(role_repr, context.guild)
                if role is None:
                    discard_pile.append((emote_repr, role_repr))
                    continue

                # Check if emote is real
                # We don't use the emote functions from text utils b/c
                # that'd be inefficient, but the algorithm for getting
                # the emotes is basically the same here.
                if emote_repr in emoji.EMOJI_UNICODE_ENGLISH:
                    add_pile.append((emote_repr, role))
                    continue

                # Check if emote matches the Discord Emote format
                matches = re.search(EMOTE_REGEX, emote_repr)
                if matches:
                    emote_id = int(matches.group(1))
                elif emote_repr.isnumeric():
                    emote_id = int(emote_repr)
                else:
                    discard_pile.append((emote_repr, role_repr))
                    continue

                # Retrieve discord emote object
                emote = self.bot.get_emoji(emote_id)
                if emote is None:
                    discard_pile.append((emote_repr, role_repr))
                else:
                    add_pile.append((emote, role))

            # Try adding the reactions first
            try:
                for emote, _ in add_pile:
                    await message.add_reaction(emote)
            except ARGUMENT_FAIL_EXCEPTIONS as e:
                raise OpheliaCommandError("reactrole_cmd_react_failed") from e

            # Add the config later
            add_message_list = []
            for emote, role in add_pile:
                if isinstance(emote, Emoji):
                    emote_repr = str(emote.id)
                    emote_name = emote.name
                else:
                    emote_repr = str(emote)
                    emote_name = emote_repr

                add_message_list.append(f"{emote_name}: {role.name}")

                await self.config.add_simple_reaction(
                    message_id=message.id,
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    emote=emote_repr,
                    role_id=role.id
                )

            # Print add result
            await send_embed(
                channel=context,
                embed_text=disp_str(
                    "reactrole_cmd_add_simple_confirm_desc"
                ).format(
                    ", ".join(add_message_list),
                    ", ".join(
                        f"{emote_repr}: {role_id}"
                        for emote_repr, role_id in discard_pile
                    )
                ),
                title=disp_str("reactrole_cmd_add_simple_confirm_title"),
                colour=Colour(settings.embed_color_success),
                timestamp=None,
                embed_fallback=True
            )

        return func

    # pylint: enable=too-many-branches

    async def gen_command_add_dm_emote(self, message: Message) -> Callable:
        """
        First order function for adding a DM reaction to a message.

        :param message: Message to add reaction to
        :return: Command callable to request for emote name or emote ID
        """

        async def func(context: Context) -> None:
            """
            Generic command response to ask for emote ID or name.

            :param context: Command context
            """
            sent_message = await send_embed(
                channel=context,
                embed_text=disp_str("reactrole_cmd_add_dm_emote_desc"),
                title=disp_str("reactrole_cmd_add_dm_emote_title"),
                timestamp=None,
                embed_fallback=True
            )

            await response_convert(
                bot=self.bot,
                context=context,
                message=sent_message,
                check_call=is_possibly_emoji,
                conversion_call=self.retrieve_emoji,
                success_call=await self.gen_command_add_dm_config(message),
                notfound_exception=OpheliaCommandError(
                    "reactrole_cmd_invalid_arg"
                ),
                failure_exception=OpheliaCommandError(
                    "reactrole_cmd_invalid_arg"
                ),
                timeout_seconds=COMMAND_TIMEOUT,
                timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
            )

        return func

    async def gen_command_add_dm_config(
            self,
            message: Message,
    ) -> Callable:
        """
        First order function for configuring a DM reaction to a message.

        :param message: Message to add reaction to
        :return: Command callable to request for DM reaction parameters
        """

        async def func(context: Context, emote: Union[str, Emoji]) -> None:
            """
            Generic command response to ask for DM reaction config
            parameters

            :param context: Command context
            :param emote: Unicode emoji or custom Discord emote
            """
            sent_message = await send_embed(
                channel=context,
                embed_text=disp_str("reactrole_cmd_add_dm_config_desc"),
                title=disp_str("reactrole_cmd_add_dm_config_title"),
                timestamp=None,
                embed_fallback=False
            )

            await response_yaml(
                bot=self.bot,
                context=context,
                message=sent_message,
                key_set={"dm_msg", "dm_regex", "dm_roles"},
                response_call=await self.gen_command_add_dm_confirm(
                    message=message,
                    emote=emote
                ),
                timeout_seconds=YAML_TIMEOUT,
                timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
            )

        return func

    async def gen_command_add_dm_confirm(
            self,
            message: Message,
            emote: Union[str, Emoji]
    ) -> Callable:
        """
        First order function for confirming the addition of a new
        DM reaction config.

        :param message: Message to add reaction to
        :param emote: Unicode emoji or custom Discord emote
        :return: Command callable to confirm the addition of a new
            DM reaction based on input parameters
        """

        async def func(yaml_output: dict, context: Context) -> None:
            """
            Generic command response to confirm DM role config.

            :param yaml_output: YAML parser output for initializing
                reaction role configuration
            :param context: Command context
            """
            # Checks on user input
            if "dm_msg" not in yaml_output:
                raise OpheliaCommandError("reactrole_cmd_invalid_arg")

            if "dm_regex" not in yaml_output and "dm_roles" not in yaml_output:
                raise OpheliaCommandError("reactrole_cmd_invalid_arg")

            if isinstance(emote, Emoji):
                emote_repr = emote.id
            else:
                emote_repr = str(emote)

            try:
                # Add reaction
                await message.add_reaction(emote)

                # Add to config
                await self.config.add_dm_reaction(
                    message_id=message.id,
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    emote=emote_repr,
                    dm_msg=yaml_output["dm_msg"],
                    dm_regex=yaml_output.get("dm_regex", None),
                    dm_roles=yaml_output.get("dm_roles", None)
                )

                # Send confirmation message
                await send_embed(
                    channel=context,
                    embed_text=disp_str(
                        "reactrole_cmd_add_dm_config_confirm_desc"
                    ).format(str(yaml_output)),
                    title=disp_str("reactrole_cmd_add_dm_config_confirm_title"),
                    colour=Colour(settings.embed_color_success),
                    timestamp=None,
                    embed_fallback=True
                )

            except re.error as e:
                raise OpheliaCommandError("reactrole_cmd_invalid_regex") from e
            except InvalidReactConfigException as e:
                raise OpheliaCommandError("reactrole_cmd_invalid_arg") from e
            except ARGUMENT_FAIL_EXCEPTIONS as e:
                raise OpheliaCommandError("reactrole_cmd_react_failed") from e

        return func

    async def gen_command_delete_message(self, message: Message) -> Callable:
        """
        First order function to prompt the user to confirm the deletion
        of all reaction roles from a message.

        :param message: Message to remove reaction roles from
        """

        async def func(context: Context) -> None:
            """
            Generic command response to confirm deletion of reaction
            roles from a message.

            :param context: Command context
            """
            message_id = message.id
            num_reacts = len(
                self.config.message_configs[str(message_id)].reacts
            )

            sent_message = await send_embed(
                channel=context,
                embed_text=disp_str("reactrole_cmd_delete_message_desc").format(
                    message_id,
                    num_reacts,
                    (num_reacts != 1) * "s"
                ),
                title=disp_str("reactrole_cmd_delete_message_title"),
                timestamp=None,
                embed_fallback=False
            )

            await response_switch(
                bot=self.bot,
                context=context,
                message=sent_message,
                options={
                    "y": await self.gen_command_delete_confirm(message),
                    "n": self.command_cancel
                },
                timeout_seconds=COMMAND_TIMEOUT,
                timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
            )

        return func

    async def gen_command_delete_confirm(self, message: Message) -> Callable:
        """
        First order function for performing deletion of message config

        :param message: Message to remove from the reaction config
        :return: Command callable to confirm deletion of message from
            reaction config
        """

        async def func(context: Context) -> None:
            """
            Generic command response to confirm deletion.

            :param context: Command context
            """
            # Delete from config
            await self.config.delete_message(message.id)

            # Delete reactions
            # Intentionally not surrounding this with a try/except block
            # because the only error that can happen here would be an
            # internal error that's out of the user's control, and that
            # is already handled by the bot's internal error message
            for reaction in message.reactions:
                users = await reaction.users().flatten()
                if self.bot.user in users:
                    await reaction.remove(self.bot.user)

            # Confirmation message
            await send_embed(
                channel=context,
                embed_text=disp_str(
                    "reactrole_cmd_delete_confirm_desc"
                ),
                title=disp_str("reactrole_cmd_delete_confirm_title"),
                colour=Colour(settings.embed_color_success),
                timestamp=None,
                embed_fallback=True
            )

        return func

    async def gen_command_view_yaml(self, message: Message) -> Callable:
        """
        First order function for displaying the current message role
        reaction config (raw YAML) for the given message.

        :param message: Message corresponding to reaction message
            config that's being viewed
        """

        async def func(context: Context) -> None:
            """
            Generic command response to display role reaction config

            :param context: Command context
            """
            conf_dict = self.config.config_dict[str(message.id)]
            yaml_print = yaml.safe_dump(conf_dict, default_flow_style=False)

            # Print current config
            await send_embed(
                channel=context,
                embed_text=disp_str("reactrole_cmd_view_yaml_desc").format(
                    yaml_print
                ),
                title=disp_str("reactrole_cmd_view_yaml_title"),
                timestamp=None,
                embed_fallback=True
            )

        return func

    async def gen_command_delete_invalid_message(
            self,
            message_id_str: str
    ) -> Callable:
        """
        First order function for deleting messages unreachable by the
        bot, either because they're in an unaccesible channel,
        misconfigured or deleted.

        :param message_id_str: Message ID of the unreachable message
        :return: Command callable to request for new message config
            parameters
        """

        async def func(context: Context) -> None:
            """
            Generic command response to request for a yes/no response
            from user on whether to delete invalid message ID config.

            :param context: Command context
            """
            num_reacts = len(self.config.message_configs[message_id_str].reacts)

            sent_message = await send_embed(
                channel=context,
                embed_text=disp_str(
                    "reactrole_cmd_delete_invalid_message_desc"
                ).format(
                    message_id_str,
                    num_reacts,
                    (num_reacts != 1) * "s"
                ),
                title=disp_str("reactrole_cmd_delete_invalid_message_title"),
                timestamp=None,
                embed_fallback=False
            )

            await response_switch(
                bot=self.bot,
                context=context,
                message=sent_message,
                options={
                    "y": await self.gen_command_delete_invalid_confirm(
                        message_id_str
                    ),
                    "n": self.command_cancel
                },
                timeout_seconds=COMMAND_TIMEOUT,
                timeout_exception=OpheliaCommandError("reactrole_cmd_exit")
            )

        return func

    async def gen_command_delete_invalid_confirm(
            self,
            message_id_str: str
    ) -> Callable:
        """
        First order function for confirming the deletion of a message ID
        from the role reaction config.

        :param message_id_str: Message ID of message to be deleted
        :return: Command callable to delete message ID from reaction
            config and inform the user of the deletion
        """

        async def func(context: Context) -> None:
            """
            Generic command response to confirm message ID deletion.

            :param context: Command context
            """
            # Delete from config
            await self.config.delete_message(int(message_id_str))

            # Confirmation message
            await send_embed(
                channel=context,
                embed_text=disp_str(
                    "reactrole_cmd_delete_invalid_confirm_desc"
                ),
                title=disp_str("reactrole_cmd_delete_invalid_confirm_title"),
                colour=Colour(settings.embed_color_success),
                timestamp=None,
                embed_fallback=True
            )

        return func

    async def delete_reaction(
            self,
            reaction_payload: Union[
                RawReactionActionEvent,
                RawReactionClearEmojiEvent
            ]
    ) -> None:
        """
        Deletes a reaction config when the bot's reaction is removed.

        :param reaction_payload: Reaction payload from raw reaction
        """
        # Find message config
        message_id_str = str(reaction_payload.message_id)
        if message_id_str not in self.config.message_configs:
            return

        partial_emoji: PartialEmoji = reaction_payload.emoji

        # Check if this is the bot itself
        if isinstance(reaction_payload, RawReactionActionEvent):
            user_id = reaction_payload.user_id
            if user_id != self.bot.user.id:
                return

        # Find reaction emote config
        if partial_emoji.is_unicode_emoji():
            emote_repr = partial_emoji.name
        else:
            emote_repr = partial_emoji.id

        logger.trace(
            "Deleting reaction config {} for message {}",
            emote_repr,
            message_id_str
        )
        await self.config.delete_reaction(message_id_str, emote_repr)

    async def delete_message(self, message_id: int) -> None:
        """
        Deletes a message role reaction config when a message is
        deleted or cleared.

        :param message_id: ID of deleted message
        """
        message_id_str = str(message_id)
        if message_id_str not in self.config.message_configs:
            return

        logger.trace("Deleting message config for message {}", message_id_str)
        await self.config.delete_message(message_id_str)

    # pylint: disable=too-many-branches
    @filter_self_react
    async def role_assign(
            self,
            reaction_payload: RawReactionActionEvent,
            remove: bool = False
    ) -> None:
        """
        Assign or remove a role from a member.

        :param reaction_payload: Reaction payload from raw reaction
        :param remove: Whether to remove roles instead of assigning them
        """
        # Find message config
        message_id_str = str(reaction_payload.message_id)
        if message_id_str not in self.config.message_configs:
            return

        message_config = self.config.message_configs[message_id_str]

        user_id = reaction_payload.user_id
        guild_id = reaction_payload.guild_id
        partial_emoji: PartialEmoji = reaction_payload.emoji

        # Find reaction emote config
        if partial_emoji.is_unicode_emoji():
            emote_repr = partial_emoji.name
        else:
            emote_repr = partial_emoji.id

        # Check if the emote is configured for this specific message
        if emote_repr not in message_config:
            return

        # Retrieve the react config for this emote on this message
        react_config = message_config[emote_repr]

        # Find reaction guild
        guild: Guild = self.bot.get_guild(guild_id)
        if guild is None:
            logger.trace("Reactrole could not find guild {}", guild_id)
            return

        # Find member who reacted
        try:
            member: Member = await guild.fetch_member(user_id)
            if member.bot:
                return
        except (Forbidden, HTTPException):
            logger.trace(
                "Reactrole failed to retrieve member {} from guild {}",
                user_id,
                guild_id
            )
            return

        # Assign or remove roles
        try:
            if isinstance(react_config, SingleRoleConfig):
                role_id = react_config.role_id
                role = guild.get_role(role_id)
                if role is None:
                    logger.warning(
                        "Reactrole tried to assign a non-existent "
                        "role {} in guild {}; removing react config.",
                        role_id,
                        guild_id
                    )

                    await self.config.delete_reaction(
                        message_id_str,
                        emote_repr
                    )
                    return

                if remove:
                    await member.remove_roles(role)
                else:
                    await member.add_roles(role)

            elif isinstance(react_config, RoleMenuConfig):
                await self.dm_lock.queue_call(
                    self.role_dm,
                    member.id,
                    member_id=member.id,
                    guild=guild,
                    react_config=react_config
                )

        except Forbidden:
            logger.trace(
                "Reactrole could not assign role to user in guild {} "
                "with emote {}",
                guild_id,
                emote_repr
            )
        except HTTPException:
            logger.trace(
                "Reactrole failed to assign/remove role in guild {} "
                "with emote {}",
                guild_id,
                emote_repr
            )

    # pylint: enable=too-many-branches

    @staticmethod
    def role_list(roles: Dict[int, Role]) -> str:
        """
        Generates a string containing a list of roles.

        :param roles: Dictionary of roles indexed by option number
        :return: String containing formatted list
        """
        role_entries = [
            f"> **{num}** | {role}" for num, role in sorted(roles.items())
        ]
        return "\n".join(role_entries)

    async def role_dm(
            self,
            member_id: int,
            guild: Guild,
            react_config: RoleMenuConfig
    ) -> None:
        """
        Send a role list selection menu to member.

        We take the member ID instead of the member because we want to
        retrieve roles in the function.

        :param member_id: Target member ID
        :param guild: Guild that the member came from
        :param react_config: Role menu configuration
        """
        try:
            member = await guild.fetch_member(member_id)
        except FETCH_FAIL_EXCEPTIONS:
            return

        message_text = react_config.msg

        guild_roles = guild.roles
        role_options = [
            role for role in guild_roles
            if role.name in react_config.roles
               or role.id in react_config.roles
               or str(role.id) in react_config.roles
               or react_config.regex.fullmatch(role.name)
        ]

        add_role_options: Dict[int, Role] = {}
        remove_role_options: Dict[int, Role] = {}
        add_counter = 1
        remove_counter = len(role_options)
        for role in role_options:
            if role not in member.roles:
                add_role_options[add_counter] = role
                add_counter += 1
            else:
                remove_role_options[remove_counter] = role
                remove_counter -= 1

        add_role_str = self.role_list(add_role_options)
        remove_role_str = self.role_list(remove_role_options)

        if add_role_str:
            message_text += disp_str("reactrole_add_role_header").format(
                add_role_str
            )
        if remove_role_str:
            message_text += disp_str("reactrole_remove_role_header").format(
                remove_role_str
            )

        await send_message(
            channel=member,
            text=message_text
        )

        try:
            user_input = await self.bot.wait_for(
                "message",
                timeout=DM_TIMEOUT,
                check=lambda msg: (
                        msg.channel == member.dm_channel
                        and msg.author == member
                )
            )

            await self.confirm_role_dm(
                member,
                add_role_options,
                remove_role_options,
                user_input.content
            )
        except asyncio.TimeoutError as e:
            # We can't just raise an OpheliaCommandError here because
            # this wasn't triggered by a command.
            await send_error_embed(
                channel=member,
                title=disp_str("reactrole_dm_timeout_title"),
                desc=disp_str("reactrole_dm_timeout_desc")
            )
            raise AbortQueue from e
        except (Forbidden, HTTPException):
            logger.warning(
                "Reactrole could not perform DM role assignment for "
                "member {} in guild {}",
                member.id,
                member.guild.id
            )

    @staticmethod
    async def confirm_role_dm(
            member: Member,
            add_role_options: Dict[int, Role],
            remove_role_options: Dict[int, Role],
            user_input: str
    ) -> None:
        """
        Assign or remove selected roles based on user input.

        :param member: Member to assign roles to or remove roles from
        :param add_role_options: All addable roles
        :param remove_role_options: All removeable roles
        :param user_input: User input
        :raises Forbidden: Insufficient permissions to modify user roles
        :raises HTTPException: Unable to modify user roles or send DMs
        """
        # Splitting input using commas and spaces
        args = re.split("[, ]", user_input)

        add_roles: List[Role] = []
        remove_roles: List[Role] = []
        for arg in args:
            if arg.isnumeric():
                int_arg = int(arg)
                if int_arg in add_role_options:
                    add_roles.append(add_role_options[int_arg])
                elif int_arg in remove_role_options:
                    remove_roles.append(remove_role_options[int_arg])

        confirm_messages = []
        if add_roles:
            await member.add_roles(*add_roles)
            confirm_messages.append(
                disp_str("reactrole_add_role_confirm").format(
                    ", ".join(role.name for role in add_roles)
                )
            )
        if remove_roles:
            await member.remove_roles(*remove_roles)
            confirm_messages.append(
                disp_str("reactrole_remove_role_confirm").format(
                    ", ".join(role.name for role in remove_roles)
                )
            )

        if confirm_messages:
            await send_embed(
                channel=member.dm_channel,
                embed_text="\n".join(confirm_messages),
                colour=Colour(settings.embed_color_success),
                timestamp=None,
                embed_fallback=True
            )
