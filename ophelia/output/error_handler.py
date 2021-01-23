"""
Error handler module.

Command errors are all handled here. There is a send_error_embed
function that is in __init__ since it isn't tied to the command error
system though.
"""

from discord import Forbidden
from discord.ext.commands import (
    BotMissingAnyRole, BotMissingPermissions, BotMissingRole, CommandError,
    CommandNotFound,
    Context, MissingAnyRole, MissingPermissions, MissingRole
)
from loguru import logger

from ophelia.output import disp_str, send_error_embed

COMMAND_ERRORS = {
    "UserInputError": "command_error_user_input_error",
    "ConversionError": "command_error_conversion_error",
    "BadArgument": "command_error_bad_argument",
    "BadUnionArgument": "command_error_bad_argument",
    "MissingRequiredArgument": "command_error_missing_required_arugment",
    "UnexpectedQuoteError": "command_error_unexpected_quote_error",
    "InvalidEndOfQuotedStringError": (
        "command_error_invalid_end_of_quoted_string_error"
    ),
    "ExpectedClosingQuoteError": "command_error_expected_closing_quote_error",
    "PrivateMessageOnly": "command_error_private_message_only",
    "NoPrivateMessage": "command_error_no_private_message",
    "CommandInvokeError": "command_error_invoke_error",
    "TooManyArguments": "command_error_too_many_arguments",
    "CommandOnCooldown": "command_error_command_on_cooldown",
    "NotOwner": "command_error_not_owner",
    "MessageNotFound": "command_error_message_not_found",
    "MemberNotFound": "command_error_member_not_found",
    "UserNotFound": "command_error_user_not_found",
    "ChannelNotFound": "command_error_channel_not_found",
    "ChannelNotReadable": "command_error_channel_not_readable",
    "RoleNotFound": "command_error_role_not_found",
    "EmojiNotFound": "command_error_emoji_not_found",
    "PartialEmojiConversionFailure": (
        "command_error_partial_emoji_conversion_failure"
    ),
    "BadBoolArgument": "command_error_bad_bool_argument",
    "NSFWChannelRequired": "command_error_nsfw_channel_required"
}


class OpheliaCommandError(CommandError):
    """
    Ophelia command error.

    Directs error outputs to disp_str to control
    """

    __slots__ = ["error_header", "error_message"]

    def __init__(self, disp_type: str, *args):
        """
        Initializer for the OpheliaCommandError class.

        :param disp_type: Display type taken from disp_str
        """
        self.error_header = disp_str(f"{disp_type}_title")
        self.error_message = disp_str(f"{disp_type}_desc")

        if args:
            self.error_message = self.error_message.format(*args)

        super().__init__(self.error_message)


async def handle_command_error(
        context: Context,
        exception: Exception
) -> None:
    """
    Handles retrieval and sending of command error messages.

    :param context: Context in which error-causing message was sent
    :param exception: Exception raised by command
    """
    if isinstance(exception, CommandNotFound):
        logger.trace("Command not found: {}", context.command)
        return

    error_header = disp_str("command_error_header")

    try:
        # This is ugly. I don't know why I'm doing this. I'm sorry.
        error_message = (
                disp_str(COMMAND_ERRORS[type(exception).__name__])
                + "\n" + str(exception)
        )
    except KeyError:
        if isinstance(exception, OpheliaCommandError):
            error_header = exception.error_header
            error_message = exception.error_message
        elif isinstance(exception, MissingPermissions):
            error_message = disp_str(
                "command_error_missing_permissions"
            ).format(", ".join(exception.missing_perms))
        elif isinstance(exception, BotMissingPermissions):
            error_message = disp_str(
                "command_error_bot_missing_permissions"
            ).format(", ".join(exception.missing_perms))
        elif isinstance(exception, MissingRole):
            error_message = disp_str(
                "command_error_missing_role"
            ).format(exception.missing_role)
        elif isinstance(exception, BotMissingRole):
            error_message = disp_str(
                "command_error_bot_missing_role"
            ).format(exception.missing_role)
        elif isinstance(exception, MissingAnyRole):
            error_message = disp_str(
                "command_error_missing_any_role"
            ).format(", ".join(role.name for role in exception.missing_roles))
        elif isinstance(exception, BotMissingAnyRole):
            error_message = disp_str(
                "command_error_bot_missing_any_role"
            ).format(", ".join(role.name for role in exception.missing_roles))
        else:
            logger.error(
                "Ignored command error {} "
                "triggered by command {} in channel {}",
                type(exception).__name__,
                context.command,
                context.channel.name
            )
            return

    if error_message is not None and error_message:
        # Trace, because we don't need the bot to report to us whenever
        # a user enters a command wrongly.
        logger.trace(
            disp_str("command_error_logger_header"),
            error_message,
            context.command
        )

        try:
            await send_error_embed(
                channel=context,
                title=error_header,
                desc=error_message
            )
        except Forbidden:
            logger.warning(
                disp_str("command_error_failed_to_send"),
                context.channel.id,
                error_message
            )
