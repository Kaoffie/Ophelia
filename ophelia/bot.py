"""
Main bot module.

Entry point for running the bot.
"""
import asyncio
import copy
import sys
import traceback
from typing import Optional

import yaml
from discord import ext as dext, TextChannel
from discord.ext import commands
from discord.ext.commands import Context
from loguru import logger

from ophelia import settings
from ophelia.boostroles.boostroles_cog import BoostrolesCog
from ophelia.events.events_cog import EventsCog
from ophelia.output import send_message
from ophelia.output.error_handler import handle_command_error
from ophelia.reactrole.reactrole_cog import ReactroleCog
from ophelia.voicerooms.voicerooms_cog import VoiceroomsCog

# Removing and replacing the default logger output
logger.remove(0)
logger.level("DEBUG", color="<fg 251>")
logger.add(
    sys.stderr,
    format="<bg 239><fg 15> {time:YYYY-MM-DD HH:mm:ss.SSS} </fg 15></bg 239>"
           "<bg 32><lvl><b> {level} </b></lvl></bg 32>"
           "<n> {message}</n>",
    level=settings.console_log_level
)


# Monkey patching the YAML safe loader so that keys are always strings
def construct_mapping(self, node, deep=False) -> dict:
    """
    Custom function to override the YAML loader to ensure that keys are
    always strings.

    :param self: YAML safe loader
    :param node: YAML Node
    :param deep: Internal argument related to recursive construction
    :return:
    """
    data = self.construct_mapping_org(node, deep)
    return {
        (str(key) if isinstance(key, int) else key): data[key] for key in data
    }


yaml.SafeLoader.construct_mapping_org = yaml.SafeLoader.construct_mapping
yaml.SafeLoader.construct_mapping = construct_mapping


# Actual bot stuff starts here
class OpheliaBot(dext.commands.Bot):
    """Ophelia Discord bot."""

    __slots__ = [
        "master_log_id",
        "log_channel",
        "first_start"
    ]

    def __init__(self) -> None:
        """Initializer for the OpheliaBot class."""
        super().__init__(
            command_prefix=settings.command_prefix,
            help_command=None,
            description=settings.bot_description,
            owner_ids=settings.bot_owners
        )

        self.log_channel: Optional[TextChannel] = None
        self.master_log_id: int = 1
        self.first_start = True

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """
        Called when an event raises an uncaught exception.

        :param event_method: The name of the event that raised the
            exception
        :param args: Positional arguments for the event that raised the
            exception
        :param kwargs: Keyword arguments for the event that raised the
            exception
        """
        logger.error(
            "Exception raised in {}.\n\t{}",
            event_method,
            traceback.format_exc().replace("\n", "\n\t")
        )

    async def on_command_error(
            self,
            context: Context,
            exception: Exception
    ) -> None:
        """
        Called when a command triggers an error.

        :param context: Context of error-triggering command
        :param exception: Exception that the command raised
        :return:
        """
        await handle_command_error(context, exception)

    async def on_ready(self) -> None:
        """
        Called when Ophelia is done preparing the data received from
        Discord.

        This overrides the on_ready method from discord.Client.
        """
        if self.first_start:
            await self.on_first_ready()

    async def on_first_ready(self) -> None:
        """Ophelia's startup procedure."""
        logger.trace("Setting up master log channel.")
        log_channel = self.get_channel(settings.master_log_channel)
        if log_channel is not None and isinstance(log_channel, TextChannel):
            self.log_channel = log_channel
            logger.info(
                "Set up master log channel on #{} ({})",
                log_channel.name,
                log_channel.id
            )
        else:
            logger.error(
                "Bot master logging channel ID {} not found; setting ignored.",
                settings.master_log_channel
            )

        async def log_message(msg: str) -> None:
            await send_message(
                self.log_channel,
                msg,
                token_guard=True,
                path_guard=True
            )

        self.master_log_id = logger.add(
            log_message,
            colorize=False,
            backtrace=False,
            catch=False,
            format="**[{time:YYYY-MM-DD HH:mm:ss.SSS!UTC}][{level}]** "
                   "```\n{message}\n```",
            level=settings.master_log_level
        )

        logger.info(
            "Ophelia has started on {} ({}) with {} server(s).",
            self.user.name,
            self.user.id,
            len(self.guilds)
        )

        # Load Reactrole cog
        logger.info("Loading reactrole cog.")
        self.add_cog(ReactroleCog(self))

        # Load Events cog
        # Loading process is separate from initialization as many
        # configured objects are discord objects that need to be
        # retrieved from IDs
        logger.info("Loading events cog.")
        events_cog = EventsCog(self)
        self.add_cog(events_cog)
        await events_cog.load_from_database()

        # Load Voicerooms cog
        # Same thing for voicerooms
        logger.info("Loading voicerooms cog.")
        voicerooms_cog = VoiceroomsCog(self)
        self.add_cog(voicerooms_cog)
        await voicerooms_cog.load_generators()

        # Load boostroles cog
        logger.info("Loading boostroles cog.")
        boostroles_cog = BoostrolesCog(self)
        self.add_cog(boostroles_cog)
        await boostroles_cog.load_roles()

        self.first_start = False


ophelia = OpheliaBot()


@ophelia.command("botshutdown")
@commands.is_owner()
async def stop_command(context: Context) -> None:
    """
    Bot shutdown command.

    This is used for the sole purpose of stopping the bot safely and
    can only be activated by the bot owners.

    :param context: Command context
    """
    await send_message(channel=context, text="I'll be back.")
    logger.info("Bot shutting down...")

    for name in copy.copy(list(ophelia.cogs.keys())):
        cog = ophelia.cogs[name]
        logger.info("Closing cog: {}", name)
        await cog.cog_save_all()

        # Wait for the cog to close.
        await asyncio.sleep(5)

    await ophelia.close()


ophelia.run(settings.bot_token)
