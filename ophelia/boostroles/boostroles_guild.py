"""Guild boost roles manager module."""

from typing import Dict, Optional

from discord import Guild, Member, Permissions, Role
from loguru import logger

from ophelia.output.output import disp_str
from ophelia.utils.discord_utils import (
    ARGUMENT_FAIL_EXCEPTIONS,
    FETCH_FAIL_EXCEPTIONS
)


class InvalidBoostroleError(Exception):
    """
    When a boostrole is configured incorrectly.

    Typically occurs when a role has been deleted or the booster or the
    target has left the server.
    """


class InvalidBoostroleGuild(Exception):
    """When a server's boostrole config is configured incorrectly."""


class Boostrole:
    """For storing and working with individual boost roles."""

    __slots__ = ["role", "booster", "target"]

    def __init__(
            self,
            role: Role,
            booster: Member,
            target: Optional[Member] = None
    ) -> None:
        """
        Initializer for the Boostrole class.

        :param role: Boost reward role
        :param booster: Booster to track
        :param target: Member that the reward role is given to
        """
        self.role = role
        self.booster = booster
        if target is not None:
            self.target = target
        else:
            self.target = booster

    async def get_dict(self) -> dict:
        """Save the role to a dictionary for YAML dumping."""
        return {
            "booster": self.booster.id,
            "target": self.target.id
        }

    @classmethod
    async def from_dict(
            cls,
            guild: Guild,
            role_id: int,
            role_dict: dict
    ) -> "Boostrole":
        """
        Generate a boost role from a configured dictionary.

        :param guild: Discord guild containing boost role
        :param role_id: ID of boost role
        :param role_dict: Dictionary containing role configuration
        :return: Boostrole object
        :raises InvalidBoostroleError: When role configured wrongly
        """
        try:
            booster_id = role_dict["booster"]
            target_id = role_dict["target"]

            role = guild.get_role(role_id)
            booster = await guild.fetch_member(booster_id)
            target = await guild.fetch_member(target_id)

            if role is None:
                raise KeyError

            return cls(role, booster, target)

        except (*FETCH_FAIL_EXCEPTIONS, KeyError) as e:
            raise InvalidBoostroleError from e

    async def check_boost_status(
            self,
            guild: Guild,
            booster_role: Role
    ) -> bool:
        """
        Check if the booster is still boosting.

        :param guild: Discord guild
        :param booster_role: Server booster role (The pink one)
        :return: If the booster is still boosting (True) or has stopped
            boosting (False)
        """
        try:
            self.booster = await guild.fetch_member(self.booster.id)
            return booster_role in self.booster.roles
        except FETCH_FAIL_EXCEPTIONS:
            return False

    async def update_role(self, guild: Guild, booster_role: Role) -> bool:
        """
        Updates the target's role list based on the booster's boost
        status.

        :param guild: Discord guild
        :param booster_role: Server booster role (The pink one)
        :return If the booster is still boosting (True) or has stopped
            boosting, thus triggering a role removal (False)
        """
        is_boosting = await self.check_boost_status(guild, booster_role)
        try:
            if not is_boosting:
                logger.trace(
                    "Removing boost role {} from {}",
                    self.role.name,
                    self.target.display_name
                )
                await self.target.remove_roles(self.role)
            else:
                logger.trace(
                    "Adding boost role {} to {}",
                    self.role.name,
                    self.target.display_name
                )
                await self.target.add_roles(self.role)
        except FETCH_FAIL_EXCEPTIONS:
            logger.warning(
                "Could not add/remove role {}; "
                "perhaps user has left guild?",
                self.role.name if self.role is not None
                else self.target.display_name
            )

        return is_boosting


class BoostrolesGuild:
    """For managing boost roles in a guild."""

    __slots__ = [
        "guild",
        "booster_role",
        "boostroles",
        "role_perms",
        "insertion_pos",
        "mentionable",
        "staff_role"
    ]

    def __init__(
            self,
            guild: Guild,
            boostroles: Dict[int, Boostrole],
            role_perms: Permissions,
            insertion_pos: int,
            mentionable: bool,
            staff_role: Role
    ) -> None:
        """
        Initializer for the BoostrolesGuild class.

        :param guild: Discord guild
        :param boostroles: List of boost roles
        :param role_perms: Default role permissions
        :param insertion_pos: Position to insert new boost roles
        :param mentionable: Whether new boost roles should be
            mentionable
        :param staff_role: Guild staff role
        """
        self.guild = guild
        self.booster_role = guild.premium_subscriber_role
        self.boostroles = boostroles
        self.role_perms = role_perms
        self.insertion_pos = insertion_pos
        self.mentionable = mentionable
        self.staff_role = staff_role

    async def update(
            self,
            role_perms: Permissions,
            insertion_pos: int,
            mentionable: bool,
            staff_role: Role
    ) -> None:
        """
        Update the guild configuration with new parameters.

        :param role_perms: Default role permissions
        :param insertion_pos: Position to insert new boost roles
        :param mentionable: Whether new boost roles should be
            mentionable
        :param staff_role: Guild staff role
        """
        self.role_perms = role_perms
        self.insertion_pos = insertion_pos
        self.mentionable = mentionable
        self.staff_role = staff_role

    async def to_dict(self) -> dict:
        """
        Generate a dictionary of boost role config options.

        :return: Boost role guild config in a dictionary
        """
        return {
            "role_perms": self.role_perms.value,
            "insertion_pos": self.insertion_pos,
            "mentionable": self.mentionable,
            "staff_role": self.staff_role.id,
            "boostroles": {
                str(role_id): await role.get_dict()
                for role_id, role in self.boostroles.items()
            }
        }

    @classmethod
    async def from_dict(
            cls,
            guild: Guild,
            guild_dict: dict
    ) -> "BoostrolesGuild":
        """
        Generates a boostrole guild from a dictionary of configurations.

        :param guild: Discord guild
        :param guild_dict: Dictionary containing all the configuration
            options and boostroles for a guild
        :return:
        :raises InvalidBoostroleGuild: When guild_dict is badly
            configured
        """
        boostroles: Dict[int, Boostrole] = {}
        try:
            role_perms = Permissions(guild_dict["role_perms"])
            insertion_pos = guild_dict["insertion_pos"]
            mentionable = guild_dict["mentionable"]
            staff_role = guild.get_role(guild_dict["staff_role"])
            if staff_role is None:
                raise KeyError

            for role_id_str, role_dict in guild_dict["boostroles"].items():
                role_id = int(role_id_str)
                try:
                    boostrole = await Boostrole.from_dict(
                        guild,
                        role_id,
                        role_dict
                    )
                    boostroles[role_id] = boostrole
                except InvalidBoostroleError:
                    logger.warning("Failed to parse boostrole: {}", role_dict)

            return cls(
                guild,
                boostroles,
                role_perms,
                insertion_pos,
                mentionable,
                staff_role
            )
        except KeyError as e:
            raise InvalidBoostroleGuild from e

    async def link_role(
            self,
            role: Role,
            booster: Member,
            target: Member
    ) -> None:
        """
        Links a role to a booster and a target.

        :param role: Role to track
        :param booster: Booster who contributed the role
        :param target: Member who was awarded the role
        """
        self.boostroles[role.id] = Boostrole(role, booster, target)

    async def add_role(
            self,
            booster: Member,
            target: Member,
            hex_colour: str,
            name: str
    ) -> Role:
        """
        Creates a new boost role and assigns it to a booster and target.

        :param booster: Member who boosted the server
        :param target: Member whom this new role is awarded to
        :param hex_colour: Colour of the new role in hex RGB
        :param name: Name of new role
        :return Newly added role
        :raises InvalidBoostroleError: When boost role parameters are
            invalid
        """
        try:
            colour_int = int(hex_colour, 16)
            role: Role = await self.guild.create_role(
                name=name,
                colour=colour_int,
                permissions=self.role_perms,
                mentionable=self.mentionable
            )

            await role.edit(position=self.insertion_pos)
            await self.link_role(role, booster, target)
            await target.add_roles(role)
            return role

        except ARGUMENT_FAIL_EXCEPTIONS as e:
            raise InvalidBoostroleError from e

    async def update_roles(self) -> str:
        """
        Updates all boost roles in the guild and generates a role list.

        :return: Boost role status list formated in a string
        """
        str_builder = []
        for boostrole in self.boostroles.values():
            status = await boostrole.update_role(self.guild, self.booster_role)
            booster = boostrole.booster.mention
            target = boostrole.target.mention
            status = (
                disp_str("boostroles_status_true") if status
                else disp_str("boostroles_status_false")
            )

            if booster == target:
                str_builder.append(disp_str("boostroles_list_item").format(
                    role=boostrole.role.mention,
                    booster=booster,
                    status=status
                ))
            else:
                str_builder.append(disp_str("boostroles_list_full_item").format(
                    role=boostrole.role.mention,
                    booster=booster,
                    target=target,
                    status=status
                ))

        return "\n".join(str_builder)

    async def unlink_role(self, role_id: int) -> None:
        """
        Remove a role from the boost role records.

        :param role_id: Role ID of the removed role
        """
        self.boostroles.pop(role_id, None)

    async def unlink_target(self, member: Member) -> None:
        """
        Remove all the roles that a member is the target of in the boost
        role records.

        :param member: Target member
        """
        to_remove = []
        for boostrole in self.boostroles.values():
            if member == boostrole.target:
                to_remove.append(boostrole.role.id)

        for role_id in to_remove:
            await self.unlink_role(role_id)

    async def update_booster(self, member: Member) -> None:
        """
        Update any boost roles that a member might have as a booster.

        :param member: Guild member
        """
        for boostrole in self.boostroles.values():
            if member == boostrole.booster:
                await boostrole.update_role(self.guild, self.booster_role)
