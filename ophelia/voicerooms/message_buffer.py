"""Message buffering module."""

import asyncio
from typing import Dict, List

from discord import Message, TextChannel

from ophelia import settings
from ophelia.output import disp_str, send_message
from ophelia.utils.text_utils import (
    escape_formatting, group_strings,
    string_wrap
)

LOG_WRAP = 1500
BUFFER_SIZE = settings.voiceroom_buffer_size


class MessageBuffer:
    """
    Log buffer for message log buffering.

    Messages logged in temporary voice rooms are buffered so that the
    bot doesn't send too many messages at once while trying to log.
    """

    __slots__ = ["message_buffer", "lock", "current_size"]

    def __init__(self) -> None:
        """Initializer for the MessageBuffer class."""
        self.message_buffer: Dict[TextChannel, List[str]] = {}
        self.lock = asyncio.Lock()
        self.current_size = 0

    @staticmethod
    def format_message(message: Message) -> List[str]:
        """
        Format a message into a printable format.

        :param message: Discord message
        """
        log_list = list()
        log_list.append(disp_str("voicerooms_log_header").format(
            channel=message.channel.name,
            name=escape_formatting(message.author.name),
            discrim=message.author.discriminator,
            id=message.author.id
        ))

        if message.attachments:
            log_list.append(disp_str("voicerooms_log_attachments").format(
                ", ".join(
                    escape_formatting(a.filename) for a in message.attachments
                )
            ))

        if message.content:
            log_list += [
                disp_str("voicerooms_log_tail").format(s)
                for s in string_wrap(
                    escape_formatting(message.content), LOG_WRAP
                )
            ]

        return log_list

    async def dump(self) -> None:
        """Post all buffered messages."""
        async with self.lock:
            channel: TextChannel
            for channel, content_list in self.message_buffer.items():
                compacted_list = group_strings(content_list)
                for content in compacted_list:
                    await send_message(channel=channel, text=content)

            self.current_size = 0
            self.message_buffer.clear()

    async def log_message(self, channel: TextChannel, message: Message) -> None:
        """
        Adds a message to log.

        :param channel: Log channel
        :param message: Message logged
        """
        async with self.lock:

            self.message_buffer.setdefault(channel, []).extend(
                self.format_message(message)
            )
            self.current_size += 1

        if self.current_size >= BUFFER_SIZE:
            await self.dump()
