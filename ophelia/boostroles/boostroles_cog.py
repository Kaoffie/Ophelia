"""
Boostroles module.

Automatically tracks server boosts and adds/removes reward custom roles
based on boost status.
"""
import functools
import os
from typing import Callable, Dict, Optional

import yaml
from discord import Guild, Member, Role
from discord.ext import commands
from discord.ext.commands import Context
from loguru import logger

from ophelia import settings
from ophelia.boostroles.boostroles_guild import (
    BoostrolesGuild,
    InvalidBoostroleGuild
)
from ophelia.output.error_handler import OpheliaCommandError
from ophelia.output.output import send_simple_embed

CONFIG_PATH = settings.file_boostroles_config


class BoostrolesCog(commands.Cog, name="boostroles"):
    """
    Boost role tracker.

    View, add, or delete server boost reward roles.
    """

    __slots__ = ["bot", "boost_guilds"]

    # Using forward references to avoid cyclic imports
    # noinspection PyUnresolvedReferences
    def __init__(self, bot: "OpheliaBot") -> None:
        """
        Initializer for the BoostrolesCog class.

        :param bot: Ophelia bot object
        """
        self.bot = bot
        self.boost_guilds: Dict[int, BoostrolesGuild] = {}

    # pylint: disable=too-few-public-methods
    class BoostroleDecorators:
        """
        Decorators for checking relevant staff roles before executing
        commands.
        """

        @classmethod
        def guild_staff_check(cls, func: Callable) -> Callable:
            """
            Decorator for checking if the guild has been set up and the
            caller has the staff role.

            :param func: Async function to be wrapped
            :return: Wrapped function
            """

            @functools.wraps(func)
            async def wrapped(
                    self: "BoostrolesCog",
                    context: Context,
                    *args,
                    **kwargs
            ) -> None:
                """
                Inner function.

                :param self: BoostrolesCog instance
                :param context: Command context
                :param args: Arguments
                :param kwargs: Keyword arguments
                """
                guild_id = context.guild.id
                if guild_id not in self.boost_guilds:
                    return

                boost_guild: BoostrolesGuild = self.boost_guilds[guild_id]
                is_staff = boost_guild.staff_role in context.author.roles
                if is_staff:
                    return await func(self, context, *args, **kwargs)

            return wrapped

    # pylint: enable=too-few-public-methods

    async def cog_save_all(self) -> None:
        """Save all configured boost roles."""
        await self.save_roles()

    async def save_roles(self) -> None:
        """Save all role configurations for future use."""
        guilds_dict = {}
        for guild_id, boost_guild in self.boost_guilds.items():
            guilds_dict[str(guild_id)] = await boost_guild.to_dict()

        with open(CONFIG_PATH, "w", encoding="utf-8") as save_target:
            yaml.dump(
                guilds_dict,
                save_target,
                default_flow_style=False
            )

    async def load_roles(self) -> None:
        """Load all role configurations for use."""
        if not os.path.exists(CONFIG_PATH):
            return

        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            guilds_dict = yaml.safe_load(file)
            if guilds_dict is None:
                return

            for guild_id_str, guild_dict in guilds_dict.items():
                guild_id = int(guild_id_str)
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    logger.warning(
                        "Failed to parse guild ID {} in boostroles",
                        guild_id_str
                    )
                    continue

                try:
                    self.boost_guilds[int(guild_id_str)] = (
                        await BoostrolesGuild.from_dict(
                            guild,
                            guild_dict
                        )
                    )
                except InvalidBoostroleGuild:
                    logger.warning(
                        "Failed to parse guild boostrole config for guild {}",
                        guild_id_str
                    )

    @commands.Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        """
        Listens for when a member gains or loses the default nitro boost
        role.

        :param before: Member object before update
        :param after: Member object after update
        """
        if before.roles == after.roles:
            return

        guild_id = after.guild.id
        if guild_id not in self.boost_guilds:
            return

        booster_role = after.guild.premium_subscriber_role
        if booster_role is None:
            return

        before_set = set(before.roles)
        after_set = set(after.roles)
        new_roles = after_set.symmetric_difference(before_set)

        if booster_role in new_roles:
            boost_guild: BoostrolesGuild = self.boost_guilds[guild_id]
            await boost_guild.update_booster(after)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: Role) -> None:
        """
        Listens for when a boost role is deleted.

        :param role: Deleted role
        """
        if role.guild.id in self.boost_guilds:
            boost_guild: BoostrolesGuild = self.boost_guilds[role.guild.id]
            await boost_guild.unlink_role(role.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: Member) -> None:
        """
        Listens for when a boost role target leaves the server.

        :param member: Member who left
        """
        if member.guild.id in self.boost_guilds:
            boost_guild: BoostrolesGuild = self.boost_guilds[member.guild.id]
            await boost_guild.unlink_target(member)

    @commands.group("boost", invoke_without_command=True)
    @commands.bot_has_permissions(administrator=True)
    @commands.guild_only()
    async def boostroles(self, context: Context, *_) -> None:
        """
        Main boost role command, displays list of subcommands.

        :param context: Command context
        """
        await send_simple_embed(context, "boostroles")

    @boostroles.command(name="list", aliases=["sync"])
    @BoostroleDecorators.guild_staff_check
    async def sync_roles(self, context: Context) -> None:
        """
        Sync boost roles in a guild.

        :param context: Command context
        """
        await send_simple_embed(context, "boostroles_wait")
        boost_guild: BoostrolesGuild = self.boost_guilds[context.guild.id]
        list_str = await boost_guild.update_roles()
        await send_simple_embed(
            context,
            "boostroles_list",
            list_str,
            split=True
        )

    @boostroles.command(name="link")
    @BoostroleDecorators.guild_staff_check
    async def link_roles(
            self,
            context: Context,
            booster: Member,
            role: Role,
            target: Optional[Member]
    ) -> None:
        """
        Links a role with a booster and a target.

        :param context: Command context
        :param booster: Server booster
        :param role: Boost reward role
        :param target: Member that the role is awarded to
        """
        boost_guild: BoostrolesGuild = self.boost_guilds[context.guild.id]
        await boost_guild.link_role(role, booster, target)
        await send_simple_embed(context, "boostroles_link_success")

    @boostroles.command(name="add")
    @BoostroleDecorators.guild_staff_check
    async def add_role(
            self,
            context: Context,
            booster: Member,
            target: Member,
            colour: str,
            *name: str
    ) -> None:
        """
        Add a boost role.

        :param context: Command context
        :param booster: Server booster
        :param target: Member that the role is awarded to
        :param colour: Role colour
        :param name: Role name
        """
        boost_guild: BoostrolesGuild = self.boost_guilds[context.guild.id]
        role_name = " ".join(name)

        try:
            role = await boost_guild.add_role(
                booster,
                target,
                colour,
                role_name
            )

            await send_simple_embed(
                context,
                "boostroles_add_success",
                role.mention
            )
        except InvalidBoostroleGuild as e:
            raise OpheliaCommandError("boostroles_add_error") from e

    @boostroles.command(name="setup")
    @commands.has_guild_permissions(administrator=True)
    async def setup_boostroles(
            self,
            context: Context,
            ref_role: Role,
            staff_role: Role
    ) -> None:
        """
        Setup or reconfigure boost roles.

        :param context: Command context
        :param ref_role: Reference role for creating new boost roles
        :param staff_role: Staff role required to add boost roles
        """
        guild: Guild = context.guild
        ref_perms = ref_role.permissions
        ref_insertion_pos = ref_role.position
        ref_mentionable = ref_role.mentionable

        if guild.id not in self.boost_guilds:
            booster_role = guild.premium_subscriber_role
            if booster_role is None:
                raise OpheliaCommandError("boostroles_no_booster_role")

            self.boost_guilds[guild.id] = BoostrolesGuild(
                guild=guild,
                boostroles={},
                role_perms=ref_perms,
                insertion_pos=ref_insertion_pos,
                mentionable=ref_mentionable,
                staff_role=staff_role
            )

            await send_simple_embed(context, "boostroles_setup_success")
            return

        boost_guild = self.boost_guilds[guild.id]
        await boost_guild.update(
            ref_perms,
            ref_insertion_pos,
            ref_mentionable,
            staff_role
        )

        await send_simple_embed(context, "boostroles_update_success")
