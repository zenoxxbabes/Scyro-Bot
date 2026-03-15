import discord
import json
import aiosqlite
from discord.ext import commands
from utils.config import serverLink
from core import Scyro, Cog, Context
from utils.Tools import get_ignore_data


class Errors(Cog):
    def __init__(self, client: Scyro):
        self.client = client
        # Global cooldown mapping for all commands
        self.global_cooldown = commands.CooldownMapping.from_cooldown(
            rate=1, 
            per=5,   # 5 second global cooldown
            type=commands.BucketType.user
        )
        # Track if cooldown was triggered
        self.cooldown_active = set()
        
        # Register global check
        self.client.check(self.global_cooldown_check)

    async def global_cooldown_check(self, ctx: Context) -> bool:
        """Check global cooldown for all commands"""
        if ctx.author.bot:
            return True
            
        # Bypass cooldown for owners
        from utils.config import OWNER_IDS
        if ctx.author.id in OWNER_IDS:
            return True
        
        # Apply global cooldown check
        bucket = self.global_cooldown.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        
        if retry_after:
            # Mark that cooldown is active for this user
            self.cooldown_active.add(ctx.author.id)
            # Raise cooldown error to trigger error handler
            raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.user)
        
        return True  # Pass the check

    async def safe_respond(self, ctx, content=None, embed=None, delete_after=None):
        """Safely respond to context, handling already acknowledged interactions"""
        try:
            # Check if interaction exists and is not already responded to
            if hasattr(ctx, 'interaction') and ctx.interaction:
                if not ctx.interaction.response.is_done():
                    if embed:
                        await ctx.interaction.response.send_message(embed=embed, ephemeral=True, delete_after=delete_after)
                    else:
                        await ctx.interaction.response.send_message(content=content, ephemeral=True, delete_after=delete_after)
                else:
                    # Use followup if already responded
                    if embed:
                        await ctx.interaction.followup.send(embed=embed, ephemeral=True, delete_after=delete_after)
                    else:
                        await ctx.interaction.followup.send(content=content, ephemeral=True, delete_after=delete_after)
            else:
                # Regular message response for prefix commands
                if embed:
                    await ctx.send(embed=embed, delete_after=delete_after)
                else:
                    await ctx.send(content=content, delete_after=delete_after)
        except discord.HTTPException:
            # If all else fails, try a basic send without delete_after
            try:
                if embed:
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(content=content)
            except discord.HTTPException:
                pass  # Give up if we still can't send

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error):
        if ctx.command is None:
            return

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.CommandOnCooldown):
            self.cooldown_active.discard(ctx.author.id)  # Mark as handled
            embed = discord.Embed(
                color=discord.Color.dark_purple(), 
                description=f"> <a:7596clock:1413390466979991572> {ctx.author.mention}: You are on **cooldown.** Retry after **{error.retry_after:.2f}s**"
            )
            embed.set_author(name="Cooldown", icon_url=self.client.user.avatar.url)
            # embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1251052632949395538.png")
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            await self.safe_respond(ctx, embed=embed, delete_after=5)
            return

        # Suppress other errors if cooldown was active
        if ctx.author.id in self.cooldown_active:
            self.cooldown_active.discard(ctx.author.id)
            return

        if isinstance(error, commands.CheckFailure):
            data = await get_ignore_data(ctx.guild.id)
            ch = data["channel"]
            iuser = data["user"]
            cmd = data["command"]
            buser = data["bypassuser"]

            if str(ctx.author.id) in buser:
                return

            if str(ctx.channel.id) in ch:
                embed = discord.Embed(
                    color=discord.Color.dark_purple(),
                    description=f"> <a:alert:1396429026842644584> {ctx.author.mention}: This **channel** is ignored! Try again in another channel."
                )
                embed.set_author(name="Restricted", icon_url=self.client.user.avatar.url)
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
                await self.safe_respond(ctx, embed=embed, delete_after=8)
                return

            if str(ctx.author.id) in iuser:
                embed = discord.Embed(
                    color=discord.Color.dark_purple(),
                    description=f"> <a:alert:1396429026842644584> {ctx.author.mention}: You are an **ignored user**! Try again in another server."
                )
                embed.set_author(name="Restricted", icon_url=self.client.user.avatar.url)
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
                await self.safe_respond(ctx, embed=embed, delete_after=8)
                return

            if ctx.command.name in cmd or any(alias in cmd for alias in ctx.command.aliases):
                embed = discord.Embed(
                    color=discord.Color.dark_purple(),
                    description=f"> <a:alert:1396429026842644584> {ctx.author.mention}: This **command is ignored**! Try other commands."
                )
                embed.set_author(name="Restricted", icon_url=self.client.user.avatar.url)
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
                await self.safe_respond(ctx, embed=embed, delete_after=8)
                return

        if isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                color=discord.Color.dark_purple(), 
                description=f"> <a:alert:1396429026842644584> {ctx.author.mention}: You can't use my commands in **DMs**."
            )
            embed.set_author(name="Review Command", icon_url=self.client.user.avatar.url)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            await self.safe_respond(ctx, embed=embed, delete_after=20)
            return

        if isinstance(error, commands.TooManyArguments):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.MaxConcurrencyReached):
            embed = discord.Embed(
                color=discord.Color.dark_purple(), 
                description=f"> <a:7596clock:1413390466979991572> {ctx.author.mention}: This command is **already running.** Wait for it to finish."
            )
            embed.set_author(name="Command Running", icon_url=self.client.user.avatar.url)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            await self.safe_respond(ctx, embed=embed, delete_after=5)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.MissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in error.missing_permissions]
            fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1]) if len(missing) > 2 else " and ".join(missing)
            embed = discord.Embed(
                color=discord.Color.dark_purple(), 
                description=f"> <a:alert:1396429026842644584> {ctx.author.mention}: You lack **{fmt}** Permission to use **{ctx.command.name}**!"
            )
            embed.set_author(name="Missing Permissions", icon_url=self.client.user.avatar.url)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            await self.safe_respond(ctx, embed=embed, delete_after=7)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = discord.Embed(
                color=discord.Color.dark_purple(), 
                description=f"> <a:alert:1396429026842644584> {ctx.author.mention}: I need **{missing}** Permission to run **{ctx.command.qualified_name}**!"
            )
            embed.set_author(name="Missing Permissions", icon_url=self.client.user.avatar.url)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            await self.safe_respond(ctx, embed=embed, delete_after=7)
            return

        if isinstance(error, discord.HTTPException):
            return

        if isinstance(error, commands.CommandInvokeError):
            return


async def setup(client: Scyro):
    await client.add_cog(Errors(client))