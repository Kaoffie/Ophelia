"""Member Event Module."""

from discord import Guild

from ophelia.events.calendar.base_event import BaseEvent


class MemberEvent(BaseEvent):
    """Member-initiated events"""

    __slots__ = []

    @staticmethod
    def config_name() -> str:
        """Type Name used in configuration."""
        return "member_event"

    @staticmethod
    async def load_from_dict(config_dict: dict, guild: Guild) -> "MemberEvent":
        """
        Loads member event object from configuration parameters.

        :param config_dict: Dictionary containing configuration
            parameters
        :param guild: Event guild
        :return: Member event object
        :raises EventLoadError: Invalid arguments passed
        """
        base_dict = await BaseEvent.base_event_params(config_dict, guild)
        event = MemberEvent(**base_dict)
        return event

    async def save_to_dict(self) -> dict:
        """
        Saves member event to dictionary containing config parameters
        so that it may be reloaded again.

        :return: Dictionary containing configuration parameters
        """
        save_dict = await super().save_to_dict()
        save_dict["type"] = "member_event"

        return save_dict
