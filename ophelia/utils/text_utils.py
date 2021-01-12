"""Text analysis util functions module."""

import re
import unicodedata
from typing import Any, Callable, List, Optional, Union

import emoji
from discord import Emoji
from discord.ext.commands import Bot

from ophelia.utils.time_utils import utc_time_now

HTTP_REGEX = (
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\."
    r"[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
)
EMOTE_REGEX = r"<a?:[A-Za-z0-9-_]*:([0-9]+)>"


async def stringify(
        user_input: Any,
        none_string: Optional[str] = None,
        **_
) -> Optional[str]:
    """
    Async wrapper for str.

    :param user_input: Input to be converted into a string
    :param none_string: String to be converted to empty string, case-
        insensitive
    :return: Converted string, or None if conversion failed
    """
    try:
        stringed = str(user_input)
        if stringed.strip().lower() == none_string:
            return ""

        return stringed
    except ValueError:
        return None


async def nonify(user_input: Any, **_) -> Optional[str]:
    """
    Wrapper for stringify with "None" as the none string.

    :param user_input: Input to be converted into a string
    :return: Converted string, or None if conversion failed
    """
    return await stringify(user_input, "none")


async def nonify_link(user_input: Any, **_) -> Optional[str]:
    """
    Wrapper for nonify that checks if the user input is a valid HTTP or
    HTTPS string.

    This doesn't actually ensure that the input is a link, but it does
    prevent most cases where the user accidentally inputs a link.

    :param user_input: Input to be converted into a string
    :return: Converted string, or none if conversion failed
    """
    nonified = await nonify(user_input)

    # If it's not none and it contains something, check if it starts
    # with HTTP or HTTPS
    if nonified is not None and len(nonified) > 0:
        link = re.search(HTTP_REGEX, nonified)
        if not link:
            return None

        return link.group()

    return nonified


async def intify(
        user_input: Any,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        accept_zero: bool = False,
        **_
) -> Optional[int]:
    """
    Async wrapper for int.

    :param user_input: Input to be converted into an int
    :param minimum: Minimum integer (inclusive)
    :param maximum: Maximum integer (inclusive)
    :param accept_zero: Whether to accept zero regardless of range
    :return: Converted int, or None if conversion failed
    """
    try:
        inted = int(user_input)
        if accept_zero and inted == 0:
            return 0
        if minimum is not None and inted < minimum:
            return None
        if maximum is not None and inted > maximum:
            return None

        return inted
    except ValueError:
        return None


async def time_bounded_intify(user_input: Any, **_) -> Optional[int]:
    """
    Wrapped intify function bounded by the current time.

    :param user_input: Input to be passed to intify
    :return: Converted int or None if conversion failed
    """
    return await intify(user_input, minimum=int(utc_time_now().timestamp()))


async def optional_time_bounded_intify(user_input: any, **_) -> Optional[int]:
    """
    Wrapped intify function bounded by the current time but also
    accepting zero.

    :param user_input: Input to be passed to intify
    :return: Converted int or None if converstion failed
    """
    return await intify(
        user_input,
        minimum=int(utc_time_now().timestamp()),
        accept_zero=True
    )


def bounded_intify(
        minimum: Optional[int] = None,
        maximum: Optional[int] = None
) -> Callable:
    """
    Generate an intify function with given boundary.

    :param minimum: Minimum integer (inclusive)
    :param maximum: Maximum integer (inclusive)
    :return: Async intify callable with given bounds
    """

    async def func(user_input: Any, **_) -> Optional[int]:
        """
        Inner function.

        :param user_input: Input to be passed to intify
        :return: Converted int or None if conversion failed
        """
        return await intify(user_input, minimum, maximum)

    return func


def is_chinese(char: str) -> bool:
    """
    Checks if a given character is in Chinese.

    :param char: Character to check
    :return: Whether character is a Chinese character
    """
    char_ord = ord(char)
    if char_ord < 3400:
        return False

    # CJK Unified Ideographs
    if (
            0x4e00 <= char_ord <= 0x9fff        # Unified Ideographs
            or 0x3400 <= char_ord <= 0x4dbf     # Extension A
            or 0x20000 <= char_ord <= 0x2a6df   # Extension B
            or 0xf900 <= char_ord <= 0xfaff     # CJK Compat
            or 0x2f800 <= char_ord <= 0x2fa1f   # Compat Supplement
    ):
        return True

    # Rare characters are omitted for the sake of speed
    return False


def is_possibly_emoji(string: str) -> bool:
    """
    Checks if a string looks like a single emoji or custom emote.

    :param string: Input string
    :return: Whether string looks like an emote
    """
    emote_repr = string.strip()

    if emote_repr in emoji.UNICODE_EMOJI:
        return True

    matches = re.search(EMOTE_REGEX, emote_repr)
    if matches:
        return True
    if emote_repr.isnumeric():
        return True

    return False


def extract_emoji(string: str, bot: Bot) -> Optional[Union[str, Emoji]]:
    """
    Extracts a single emoji or custom emote from the input string.

    :param string: Input string
    :param bot: Discord bot object
    :return: Either a string containing a unicode emoji, or a Discord
        emoji object representing a custom emote, or None if no emojis
        are found
    """
    emote_repr = string.strip()
    if emote_repr in emoji.UNICODE_EMOJI:
        return emote_repr

    matches = re.search(EMOTE_REGEX, emote_repr)
    if matches:
        emote_id = int(matches.group(1))
    elif emote_repr.isnumeric():
        emote_id = int(emote_repr)
    else:
        return None

    # This is not a coroutine
    emote = bot.get_emoji(emote_id)
    return emote


def remove_accents(text: str) -> str:
    """
    Removes accents and modifying characters from input text.

    :param text: Text to remove accents from
    :return: Input text with accents removed
    """
    return "".join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) not in ['Mn', 'Me']
    )


def escape_formatting(text: str) -> str:
    """
    Replaces characters used in Discord formatting with similar-looking
    characters.

    :param text: Text to escape
    :return: Escaped text string
    """
    # This does not return a one-tuple.
    return (
        text.replace("`", "‵")  # Grave accent -> Reversed prime
            .replace("*", "⚹")  # Asterisk -> Sextile
            .replace("~", "˜")  # Tilde -> Small tilde
            .replace("_", "＿")  # Low line -> Full-width low line
    )


def escape_json_formatting(text: str) -> str:
    """
    Replaces characters that might confuse json with escaped characters.

    :param text: Text to escape
    :return: Escaped text string
    """
    # This does not return a one-tuple.
    return (
        text.replace("\\", "\\\\")  # Replace one backslash with two
            .replace('"', r'\"')
    )


def group_strings(
        strings: List[str],
        joiner: str = "\n",
        max_length: int = 2000
) -> List[str]:
    """
    Join a list of strings with groups no longer than the max length.

    This is used for when the bot has a ton of messages it needs to send
    and we'd like to reduce the number of actual messages sent by
    grouping all small messages together.

    :param strings: List of strings to group
    :param joiner: Joiner to join strings
    :param max_length: Maximum joined string length
    :return: List of joined strings
    """
    if not strings:
        return []

    return_list = []
    while strings:
        if len(strings) == 1:
            return_list.append(strings[0])
            break

        buffer = ""
        length_test = strings[0]

        # Truncate.
        if len(length_test) > max_length:
            length_test = length_test[:max_length]

        index = 0
        while index < len(strings) - 1 and len(length_test) <= max_length:
            index += 1
            buffer = length_test
            length_test += joiner + strings[index]

        return_list.append(buffer)
        strings = strings[index:]

    return return_list


def string_wrap(text: str, wrap_length: int) -> List[str]:
    """
    Split a string into groups of wrap length.

    :param text: Original text
    :param wrap_length: Length at which the string has to be wrapped
    :return: List of wrapped strings
    """
    string_list = []
    while text:
        string_list.append(text[:wrap_length])
        text = text[wrap_length:]

    return string_list
