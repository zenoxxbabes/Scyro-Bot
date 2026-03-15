import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import os

class TopCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.topcheck_settings = self.db["topcheck_settings"]
        
    async def cog_load(self):
        print("✅ [TopCheck] Extension loaded & DB initialized (MongoDB).")

    async def is_topcheck_enabled(self, guild_id: int):
        doc = await self.topcheck_settings.find_one({"guild_id": guild_id})
        return doc and doc.get("enabled", False)

    async def enable_topcheck(self, guild_id: int):
        await self.topcheck_settings.update_one(
            {"guild_id": guild_id},
            {"$set": {"enabled": True}},
            upsert=True
        )

    async def disable_topcheck(self, guild_id: int):
        await self.topcheck_settings.update_one(
            {"guild_id": guild_id},
            {"$set": {"enabled": False}},
            upsert=True
        )

    @commands.group(
        name="topcheck",
        help="Manage topcheck settings for the server.",
        invoke_without_command=True)
    @commands.guild_only()
    async def topcheck(self, ctx):
        embed = discord.Embed(title="Top Check System",
                              description=(
        "This system ensures that the bot’s role is positioned higher than the user’s top role before executing specific commands.\n\n"
        "When topcheck is enabled, only users with roles above the bot's (Scyro) role can perform certain moderation actions. "
        "If topcheck is disabled, any user with the required permissions for a command can execute it.\n\n"
        "**Moderation actions affected by topcheck:**\n"
        "- BAN\n"
        "- KICK\n"
        "- ROLE DELETE\n"
        "- ROLE CREATE\n"
        "- MEMBER UPDATE\n\n"
        "__**Subcommands:**__\n"
        f"• `{ctx.prefix}topcheck enable` - Enables top check for the server.\n"
        f"• `{ctx.prefix}topcheck disable` - Disables top check for the server."
    ),
                              color=0x2b2d31)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)
        await ctx.send(embed=embed)

    @topcheck.command(
        name="enable",
        help="Enable topcheck for the guild")
    @commands.guild_only()
    async def topcheck_enable(self, ctx):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply("<a:alert:1396429026842644584> Only the **Server Owner** can enable topcheck.")
        if await self.is_topcheck_enabled(ctx.guild.id):
            return await ctx.reply("<a:alert:1396429026842644584> Topcheck is already enabled for this server.")
        await self.enable_topcheck(ctx.guild.id)
        await ctx.reply(" Topcheck has been Successfully enabled for this server.")

    @topcheck.command(
        name="disable",
        help="Disable topcheck for the guild")
    @commands.guild_only()
    async def topcheck_disable(self, ctx):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply("Only the **Server Owner** can disable topcheck.")
        if not await self.is_topcheck_enabled(ctx.guild.id):
            return await ctx.reply("<a:alert:1396429026842644584> Topcheck is not enabled for this server.")
        await self.disable_topcheck(ctx.guild.id)
        await ctx.reply(" Topcheck has been Successfully disabled for this server.")

 