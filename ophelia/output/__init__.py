"""
Output tools module.

Everything that the bot sends through discord is managed by this module;
this includes all the functions that manage the sending of Discord
messages and embeds, Discord error messages, as well as all the
"response switch" type functions that react to user input.
"""

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import yaml
from discord import Colour, Embed, Forbidden, HTTPException, Message
from discord.abc import Messageable
from discord.ext.commands import (
    Context
)
from loguru import logger

from ophelia import settings
from ophelia.output import eng_strings
from ophelia.utils.discord_utils import FETCH_FAIL_EXCEPTIONS

PARENT_DIRECTORY = os.getcwd().split("ophelia")[0]
DEFAULT_LANG = "eng"
TOKEN_REGEX = r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}"

# Turned into a dict at runtime, so that we don't have to use getattr.
ENG_STRINGS = {
    name: value for name, value in vars(eng_strings).items()
    if not name.startswith("__")
}


def disp_str(str_name: str, lang: str = DEFAULT_LANG) -> str:
    """
    Retrieves display string based on string name.

    :param str_name: Name of string
    :param lang: Language of string
    :return: Pre-formatted string
    """
    if lang == "eng" and str_name in ENG_STRINGS:
        return ENG_STRINGS[str_name].replace(
            "%PREFIX%", settings.command_prefix
        )

    return ""


async def send_message(
        channel: Messageable,
        text: Optional[str],
        embed: Embed = None,
        token_guard: bool = False,
        path_guard: bool = False
) -> Message:
    """
    Sends a message to a given context or channel.

    :param channel: Context or channel of message
    :param text: Text content of message
    :param embed: Embed of message
    :param token_guard: Censor discord bot tokens
    :param path_guard: Censor full project directory
    :return: Discord Message object
    """
    if token_guard:
        text = re.sub(TOKEN_REGEX, "[REDACTED TOKEN]", text)

    if path_guard:
        text = text.replace(PARENT_DIRECTORY, "../")

    try:
        message = await channel.send(text, embed=embed)
        return message
    except Forbidden:
        logger.warning(
            "Failed to send message to channel ID {}",
            str(channel)
        )
    except HTTPException:
        # Possibly an invalid image from the embed.
        # This is the only place we can catch this sort of error,
        # so there really isn't a way around this that I know of.
        if embed is not None and embed.image != Embed.Empty:
            embed.set_image(url=Embed.Empty)

            try:
                message = await channel.send(text, embed=embed)
                return message
            except HTTPException:
                # Give up.
                logger.error(
                    "Failed to send message to channel {} "
                    "due to invalid argument.",
                    channel
                )


async def send_embed(
        channel: Messageable,
        embed_text: str,
        title: str = "",
        url: Optional[str] = None,
        colour: Colour = Colour(settings.embed_color_normal),
        footer_text: Optional[str] = None,
        footer_icon: Optional[str] = None,
        timestamp: Optional[datetime] = datetime.now(),
        fields: Optional[List[Tuple[str, str, bool]]] = None,
        embed_fallback: bool = False,
        token_guard: bool = False,
        path_guard: bool = False
) -> Message:
    """
    Sends an embeded message to a given context or channel.

    :param channel: Context or channel of message
    :param embed_text: Text content of embed
    :param title: Title of embed
    :param url: URL of embed
    :param colour: Colour of embed
    :param footer_text: Footer text of embed
    :param footer_icon: Footer icon URL of embed
    :param timestamp: Timestamp of embed
    :param fields: List of fields represented by a tuple of their title,
        text, and inline mode
    :param embed_fallback: Whether embed will be sent as a regular
        message if the bot doesn't have the send embeds permission
    :param token_guard: Censor Discord bot tokens
    :param path_guard: Censor full project directory
    :return: Discord Message object
    """
    if token_guard:
        title = re.sub(TOKEN_REGEX, "[REDACTED TOKEN]", title)
        embed_text = re.sub(TOKEN_REGEX, "[REDACTED TOKEN]", embed_text)

    if path_guard:
        title = title.replace(PARENT_DIRECTORY, ".")
        embed_text = embed_text.replace(PARENT_DIRECTORY, ".")

    embed = Embed(
        title=title,
        url=url if url is not None else Embed.Empty,
        colour=colour,
        description=embed_text,
        timestamp=timestamp if timestamp is not None else Embed.Empty
    )

    if footer_text is not None or footer_icon is not None:
        embed = embed.set_footer(
            text=footer_text if footer_text is not None else embed.Empty,
            icon_url=footer_icon if footer_icon is not None else embed.Empty
        )

    try:
        if fields is not None:
            for name, text, inline in fields:
                embed = embed.add_field(name=name, value=text, inline=inline)
    except ValueError:
        logger.warning("Failed to add fields to embed: {}", str(fields))

    try:
        # noinspection PyTypeChecker
        message = await channel.send(None, embed=embed)
        return message
    except Forbidden:
        logger.warning(
            "Failed to send embed to channel ID {}; "
            "falling back on plain message: {}",
            str(channel),
            embed_fallback
        )

        if embed_fallback:
            field_text = "\n\n".join(
                f"**{title}**\n{text}" for title, text, inline in fields
            )

            try:
                message = await send_message(
                    channel,
                    f"**{title}**\n\n{embed_text}\n\n"
                    f"{field_text}\n\n{footer_text}"
                )

                return message
            except Forbidden:
                logger.warning(
                    "Failed to send message to channel ID {}",
                    str(channel)
                )


async def send_message_embed(
        channel: Messageable,
        title: str,
        desc: str,
        colour: Colour = Colour(settings.embed_color_normal)
) -> Message:
    """
    Send a single embed with just a title, description and colour.

    :param channel: Channel to send embed to
    :param title: Embed title
    :param desc: Embed description
    :param colour: Embed colour
    """
    return await send_embed(
        channel=channel,
        title=title,
        embed_text=desc,
        colour=colour,
        timestamp=None,
        embed_fallback=True,
        path_guard=True
    )


async def send_simple_embed(
        channel: Messageable,
        disp_type: str,
        *args,
        colour: Colour = Colour(settings.embed_color_normal)
) -> Message:
    """
    Send a simple default coloured embed with its title and description
    taken from disp_str.

    :param channel: Channel to send embed to
    :param disp_type: Display string descriptor, reflects the
        corresponding string in the list of strings that end with
        `_title` and `_desc` for the title and description respectively
    :param args: Arguments to be formatted into the description
    :param colour: Embed colour, defaults to normal colour defined in
        settings
    :return: Sent message
    """
    desc = disp_str(f"{disp_type}_desc")
    if args:
        desc = desc.format(*args)

    return await send_message_embed(
        channel=channel,
        title=disp_str(f"{disp_type}_title"),
        desc=desc,
        colour=colour
    )


async def send_error_embed(
        channel: Messageable,
        title: str,
        desc: str
) -> Message:
    """
    Send an error embed.

    :param channel: Channel to send error to
    :param title: Embed title
    :param desc: Embed desc
    :return: Sent message
    """
    return await send_message_embed(
        channel,
        title,
        desc,
        Colour(settings.embed_color_severe)
    )


async def try_del(
        delete_message: bool,
        delete_response: bool,
        message: Message,
        user_input: Optional[Message] = None
) -> None:
    """
    Delete bot message and user response according ton configured vars.

    :param delete_message: Whether to delete bot message
    :param delete_response: Whether to delete user response
    :param message: Bot message
    :param user_input: User input message
    """
    try:
        if delete_message:
            await message.delete()
        if delete_response and user_input is not None:
            await user_input.delete()
    except FETCH_FAIL_EXCEPTIONS:
        logger.warning(
            "Failed to delete message from channel {}",
            message.channel.id
        )


# noinspection PyUnresolvedReferences
async def get_input(
        bot: "OpheliaBot",
        context: Context,
        timeout_seconds: float,
        check=lambda c: True
) -> Message:
    """
    Wait for user input:

    :param bot: Ophelia bot instance
    :param context: Command context
    :param timeout_seconds: Seconds to timeout
    :param check: Message content validity check
    :return: User input message
    """
    return await bot.wait_for(
        "message",
        timeout=timeout_seconds,
        check=lambda msg: (
                msg.channel == context.channel
                and msg.author == context.author
                and check(msg.content)
        )
    )


# noinspection PyUnresolvedReferences
async def response_switch(
        bot: "OpheliaBot",
        context: Context,
        message: Message,
        options: Dict[str, Callable],
        timeout_seconds: float,
        timeout_exception: Exception,
        delete_message: bool = True,
        delete_response: bool = True
) -> None:
    """
    Waits for user response and calls corresponding function.

    This function is kinda weird in that every option branches out to a
    separate function to be called - in most cases, response_options is
    much better, especially if all the options can be evaluated with
    the same function call with different arguments.

    This is better suited for situations where we're branching out to
    multiple options that do very different things, which justify
    passing entire functions.

    :param bot: Ophelia bot instance
    :param context: Command context
    :param message: Message that triggered this switch
    :param options: Dictionary of lowercase user response strings and
        corresponding async callables that accept context as a keyword
        argument
    :param timeout_seconds: Timeout in seconds to wait for user response
    :param timeout_exception: Exception to throw when command times out
    :param delete_message: Whether to delete the original bot message
    :param delete_response: Whether to delete user response
    """
    try:
        user_input = await get_input(
            bot,
            context,
            timeout_seconds,
            lambda c: c.casefold() in options
        )

        await try_del(delete_message, delete_response, message, user_input)
        await options[user_input.content.casefold()](context=context)

    except asyncio.TimeoutError as e:
        raise timeout_exception from e


# noinspection PyUnresolvedReferences
async def response_options(
        bot: "OpheliaBot",
        context: Context,
        message: Message,
        response_call: Callable,
        options: Dict[str, Dict[str, Any]],
        timeout_seconds: float,
        timeout_exception: Exception,
        delete_message: bool = True,
        delete_response: bool = True
) -> None:
    """
    Waits for a user to select one of many options.

    :param bot: Ophelia bot instance
    :param context: Command context
    :param message: Message that triggered this switch
    :param response_call: Response async callable to pass context and
        keyword arguments to
    :param options: Dictionary of lowercase user response strings and
        corresponding dictionaries of keyword arguments
    :param timeout_seconds: Timeout in seconds to wait for user response
    :param timeout_exception: Exception to raise when command times out
    :param delete_message: Whether to delete the original bot message
    :param delete_response: Whether to delete user response
    """
    try:
        user_input = await get_input(
            bot,
            context,
            timeout_seconds,
            lambda c: c.casefold() in options
        )

        await try_del(delete_message, delete_response, message, user_input)
        await response_call(
            context=context,
            **options[user_input.content.casefold()]
        )

    except asyncio.TimeoutError as e:
        raise timeout_exception from e


class ConvertNotFoundException(Exception):
    """Raised when conversion result not found."""


class ConvertFailureException(Exception):
    """Raised when user input conversion fails."""


# noinspection PyUnresolvedReferences
async def response_convert(
        bot: "OpheliaBot",
        context: Context,
        message: Message,
        conversion_call: Callable,
        success_call: Callable,
        notfound_exception: Exception,
        failure_exception: Exception,
        timeout_seconds: float,
        timeout_exception: Exception,
        check_call: Callable = lambda c: True,
        delete_message: bool = True,
        delete_response: bool = True
) -> None:
    """
    Waits for user response and calls corresponding function with the
    user response converted using the conversion call.

    :param bot: Ophelia bot instance
    :param context: Command context
    :param message: Message that triggered this switch
    :param conversion_call: Async callable used for converting user
        input; accepts context and input string and returns either the
        converted object or None if conversion fails
    :param success_call: Async allable to call with the converted input;
        accepts the command context and converted input as arguments
    :param notfound_exception: Exception to raise if converted input is
        not invalid but not found (used for retrieving objects such as
        messages or guilds from IDs)
    :param failure_exception: Exception to raise when input conversion
        fails
    :param timeout_seconds: Timeout in seconds to wait for user response
    :param timeout_exception: Exception to raise when command times out
    :param check_call: Non-async callable used for filtering messages
    :param delete_message: Whether to delete the original bot message
    :param delete_response: Whether to delete user response
    """
    try:
        user_input = await get_input(bot, context, timeout_seconds, check_call)
        await try_del(delete_message, delete_response, message, user_input)

        try:
            converted = await conversion_call(context, user_input.content)
            await success_call(context, converted)
        except ConvertNotFoundException as e:
            raise notfound_exception from e
        except ConvertFailureException as e:
            raise failure_exception from e

    except asyncio.TimeoutError as e:
        raise timeout_exception from e


# noinspection PyUnresolvedReferences
async def response_yaml(
        bot: "OpheliaBot",
        context: Context,
        message: Message,
        key_set: Optional[Set[str]],
        response_call: Callable,
        timeout_seconds: float,
        timeout_exception: Exception,
        delete_message: bool = False,
        delete_response: bool = False
) -> None:
    """
    Waits for YAML response from user and calls corresponding function.

    :param bot: Ophelia bot instance
    :param context: Command context
    :param message: Message that triggered this yaml parsing
    :param key_set: Set of keyword param names
    :param response_call: Async callable to call when valid yaml is
        detected
    :param timeout_seconds: Timeout in seconds to wait for user response
    :param timeout_exception: Exception raised when command times out
    :param delete_message: Whether to delete the original bot message
    :param delete_response: Whether to delete the user response
    """
    yaml_output: dict = {}

    def valid_yaml(yaml_text: str) -> bool:
        """
        Evaluates if text input is valid yaml.

        :param yaml_text: YAML input
        :return: Whether input text is valid yaml
        """
        try:
            yaml_output.clear()
            yaml_output.update(yaml.safe_load(yaml_text))

            if key_set is None or set(yaml_output.keys()).issubset(key_set):
                return True

            return False
        except yaml.YAMLError:
            return False

    try:
        user_input = await get_input(bot, context, timeout_seconds, valid_yaml)
        await try_del(delete_message, delete_response, message, user_input)
        await response_call(yaml_output=yaml_output, context=context)
    except asyncio.TimeoutError as e:
        raise timeout_exception from e


class ResponseConfigException(Exception):
    """
    When a user input string for a single response config variable
    could not be parsed.
    """


@dataclass
class ConfigItem:
    """
    Configurable item, to be used in response_config.

    Parameters:
    - key: Variable name
    - desc: Variable description or config instructions
    - converter: Async callable that parses the input string into the
        target variable type, taking the context and the input string
        as input and raising ResponseConfigException if the input string
        is invalid.
    """
    key: str
    desc: str
    converter: Callable


# noinspection PyUnresolvedReferences
async def response_config(
        bot: "OpheliaBot",
        context: Context,
        message: Message,
        config_items: List[ConfigItem],
        response_call: Callable,
        timeout_seconds: float,
        timeout_exception: Exception,
        response_tries: int = 3,
        delete_message: bool = True,
        delete_response: bool = True
) -> None:
    """
    Guilds a user through a step-by-step configuration menu and calls
    a function with the configured variables in a dictionary.

    :param bot: Ophelia bot instance
    :param context: Command context
    :param message: Message that triggered this config menu
    :param config_items: List of configuration items
    :param response_call: Async callable to call when valid config
        variables have all been gathered into a dictionary
    :param timeout_seconds: Timeout in seconds to wait for user repsonse
    :param timeout_exception: Exception to raise when command times out
    :param response_tries: Number of tries a member gets per variable
    :param delete_message: Whether to delete the original bot message
        and any subsequent messages
    :param delete_response: Whether to delete user responses
    """
    # Even though the first message has already started the config
    # process, we are going to send a new message at the start of every
    # loop to make implementation slightly easier.
    item_len = len(config_items)
    config_vars = {}
    for num, config_item in enumerate(config_items):
        key = config_item.key
        desc = config_item.desc
        converter = config_item.converter

        # Send prompt
        prompt = await send_embed(
            channel=context,
            embed_text=disp_str("config_var_desc").format(desc),
            title=disp_str("config_var_title").format(key),
            footer_text=disp_str("config_var_footer").format(num + 1, item_len),
            timestamp=None
        )

        for try_num in range(response_tries):
            try:
                # If this is not the first try
                if try_num:
                    prompt = await send_error_embed(
                        channel=context,
                        title=disp_str("config_try_again_title").format(key),
                        desc=disp_str("config_try_again_desc").format(
                            desc,
                            try_num + 1,
                            response_tries
                        )
                    )

                user_input = await get_input(bot, context, timeout_seconds)
                converted = await converter(
                    context=context,
                    user_input=user_input.content
                )

                await try_del(
                    delete_message,
                    delete_response,
                    prompt,
                    user_input
                )

                if converted is not None:
                    config_vars[key] = converted
                    break

            except asyncio.TimeoutError as e:
                raise timeout_exception from e
        else:
            # This runs when the for completes without breaking, i.e.
            # The user exceeded the maximum number of tries
            raise timeout_exception

    # Successfully configured all items
    await try_del(delete_message, False, message)
    await response_call(context=context, config_vars=config_vars)


# noinspection PyUnresolvedReferences
async def response_param(
        bot: "OpheliaBot",
        context: Context,
        message: Message,
        key_set: Set[str],
        response_call: Callable,
        timeout_seconds: float,
        timeout_exception: Exception,
        delete_message: bool = False,
        delete_response: bool = False
) -> None:
    """
    Waits for parameter/value response from user and calls corresponding
    function.

    :param bot: Ophelia bot instance
    :param context: Command context
    :param message: Message that triggered this function
    :param key_set: Set of keyword param names
    :param response_call: Async callable to call when valid input is
        detected
    :param timeout_seconds: Timeout in seconds to wait for user response
    :param timeout_exception: Exception to raise when command times out
    :param delete_message: Whether to delete the original bot message
    :param delete_response: Whether to delete the user response
    """
    output: dict = {}

    def valid_input(input_text: str) -> bool:
        """
        Evaluates if text input is valid.

        :param input_text: Param: value input
        :return: Whether input text is valid
        """
        if ":" not in input_text:
            return False
        # We assume that the user has attempted to modify multiple
        # parameters and reject it
        if "\n" in input_text:
            return True

        split_input = input_text.split(":")
        key = split_input[0].strip()

        if key in key_set:
            output["name"] = key
            output["value"] = ":".join(split_input[0:]).strip()
            return True

        return False

    try:
        user_input = await bot.wait_for(
            "message",
            timeout=timeout_seconds,
            check=lambda msg: (
                    msg.channel == context.channel
                    and msg.author == context.author
                    and valid_input(msg.content)
            )
        )

        await try_del(delete_message, delete_response, message, user_input)
        await response_call(param_input=output, context=context)

    except asyncio.TimeoutError as e:
        raise timeout_exception from e
