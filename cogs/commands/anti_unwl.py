import discord
from discord.ext import commands
import motor.motor_asyncio
import os
from utils.Tools import *


class Unwhitelist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.wl_col = self.db["antinuke_whitelist"]
        self.extra_col = self.db["extraowners"]
        self.antinuke_col = self.db["antinuke"]

    async def cog_load(self):
         print("✅ [Unwhitelist] Extension loaded & DB initialized (MongoDB).")

    @commands.hybrid_command(name='unwhitelist', aliases=['unwl'], help="Unwhitelist a user from antinuke")
    @commands.has_permissions(administrator=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def unwhitelist(self, ctx, member: discord.Member = None):
        if ctx.guild.member_count < 2:
            embed = discord.Embed(
                color=0x2b2d31,
                description="> ❌ | Your Server Doesn't Meet My 30 Member Criteria"
            )
            return await ctx.send(embed=embed)

        # Check Extra Owner
        check = await self.extra_col.find_one({"guild_id": ctx.guild.id, "owner_id": ctx.author.id})

        # Check Antinuke Status
        antinuke = await self.antinuke_col.find_one({"guild_id": ctx.guild.id})
        
        is_owner = ctx.author.id == ctx.guild.owner_id
        if not is_owner and not check:
            embed = discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=0x2b2d31,
                description="Only Server Owner or Extra Owner can Run this Command!"
            )
            return await ctx.send(embed=embed)

        if not antinuke or not antinuke.get("status"):
            embed = discord.Embed(
                color=0x2b2d31,
                description=(
                    f"**{ctx.guild.name} Security Settings <:security:1396477817000034385>\n"
                    "Ohh NO! looks like your server doesn't enabled security\n\n"
                    "Current Status : <:disabled:1396473518962507866>\n\n"
                    "To enable use `antinuke enable` **"
                )
            )
            return await ctx.send(embed=embed)

        if not member:
            embed = discord.Embed(
                color=0x2b2d31,
                title="__**Unwhitelist Commands**__",
                description="**Removes user from whitelisted users which means that the antinuke module will now take actions on them if they trigger it.**"
            )
            embed.add_field(name="__**Usage**__", value="<a:dot:1396429135588626442>`unwhitelist @user/id`\n<a:dot:1396429135588626442> `unwl @user`")
            return await ctx.send(embed=embed)

        data = await self.wl_col.find_one({"guild_id": ctx.guild.id, "user_id": member.id})

        if not data:
            embed = discord.Embed(title="<:no:1396838761605890090> Error",
                color=0x2b2d31,
                description=f"<@{member.id}> is not a whitelisted member."
            )
            return await ctx.send(embed=embed)

        await self.wl_col.delete_one({"guild_id": ctx.guild.id, "user_id": member.id})

        embed = discord.Embed(title="<:yes:1396838746862784582> Success",
            color=0x2b2d31,
            description=f"User <@!{member.id}> has been removed from the whitelist."
        )
        await ctx.send(embed=embed)


 