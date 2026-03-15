import discord
from discord.ext import commands
from discord import ui
import motor.motor_asyncio
import asyncio
import os
from utils.Tools import *

class WarnView(ui.View):
    def __init__(self, user, author):
        super().__init__(timeout=60)
        self.user = user
        self.author = author
        self.message = None


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("You are not allowed to interact with this!", ephemeral=True)
            return False
        return True


    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


    @ui.button(style=discord.ButtonStyle.gray, emoji="<:bin:1409169036285313155>")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()



class Warn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = 0x2b2d31
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.warns_col = self.db["warns"]

    async def cog_load(self):
        # Create index unique on (guild_id, user_id)
        await self.warns_col.create_index(
            [("guild_id", 1), ("user_id", 1)],
            unique=True
        )
        print("✅ [Warn] Extension loaded & DB initialized (MongoDB).")

    def get_user_avatar(self, user):
        return user.avatar.url if user.avatar else user.default_avatar.url


    async def add_warn(self, guild_id: int, user_id: int):
        await self.warns_col.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"count": 1}},
            upsert=True
        )

    async def get_total_warns(self, guild_id: int, user_id: int):
        doc = await self.warns_col.find_one({"guild_id": guild_id, "user_id": user_id})
        return doc["count"] if doc else 0


    async def reset_warns(self, guild_id: int, user_id: int):
        # We can either delete the doc or keyset count to 0. Deleting is cleaner if count 0 means no record.
        # But if we want to keep history later, maybe keeping it is better.
        # For now, deleting seems fine or setting to 0.
        # The SQL code did UPDATE warns SET warns = 0.
        await self.warns_col.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"count": 0}},
            upsert=True
        )


    @commands.hybrid_command(
        name="warn",
        help="Warn a user in the server",
        usage="warn <user> [reason]",
        aliases=["warnuser"])
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    #@commands.bot_has_permissions(manage_messages=True)
    async def warn(self, ctx, user: discord.Member, *, reason=None):
        if user == ctx.author:
            return await ctx.reply("You cannot warn yourself.")


        if user == ctx.bot.user:
            return await ctx.reply("You cannot warn me.")


        if not ctx.author == ctx.guild.owner:
            if user == ctx.guild.owner:
                return await ctx.reply("I cannot warn the server owner.")


            if ctx.author.top_role <= user.top_role:
                return await ctx.reply("You cannot Warn a member with a higher or equal role.")


        if ctx.guild.me.top_role <= user.top_role:
            return await ctx.reply("I cannot Warn a member with a higher or equal role.")


        if user not in ctx.guild.members:
            return await ctx.reply("The user is not a member of this server.")
        try:
            
            await self.add_warn(ctx.guild.id, user.id)
            total_warns = await self.get_total_warns(ctx.guild.id, user.id)


            
            reason_to_send = reason or "No reason provided"
            try:
                await user.send(f"You have been warned in **{ctx.guild.name}** by **{ctx.author}**. Reason: {reason_to_send}")
                dm_status = "Yes"
            except discord.Forbidden:
                dm_status = "No"
            except discord.HTTPException:
                dm_status = "No"


            embed = discord.Embed(description=f"> <a:dot:1396429135588626442> **Target User:** [{user}](https://discord.com/users/{user.id})\n"
                                              f"> <a:dot:1396429135588626442> **User Mention:** {user.mention}\n"
                                              f"> <a:dot:1396429135588626442> **Reason:** {reason_to_send}\n"
                                              f"> <a:dot:1396429135588626442> **Total Warns:** {total_warns}",
                                              color=self.color)
            embed.set_author(name=f"Warned {user.name}", icon_url=self.get_user_avatar(user))
            embed.add_field(name="> <a:dot:1396429135588626442> Moderator:", value=ctx.author.mention, inline=False)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=self.get_user_avatar(ctx.author))
            embed.timestamp = discord.utils.utcnow()


            view = WarnView(user=user, author=ctx.author)
            message = await ctx.send(embed=embed, view=view)
            view.message = message
            
            # Logging Integration
            logging_cog = self.bot.get_cog("Logging")
            if logging_cog:
                data = {
                    'description': f"**{user.mention}** has been warned by {ctx.author.mention}.\n**Reason:** {reason_to_send}\n**Total Warns:** {total_warns}\n[Jump to Message]({message.jump_url})"
                }
                logging_cog.queue_event(ctx.guild.id, 'moderation', data)
                asyncio.create_task(logging_cog.log_to_history(ctx.guild.id, "moderation", "warn", user.id, message.channel.id, f"Warned by {ctx.author.name}: {reason_to_send}"))
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            print(f"Error during warn command: {e}")


    @commands.hybrid_command(
        name="clearwarns",
        help="Clear all warnings for a user",
        aliases=["clearwarn" , "clearwarnings"],
        usage="clearwarns <user>")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def clearwarns(self, ctx, user: discord.Member):
        try:
            await self.reset_warns(ctx.guild.id, user.id)
            embed = discord.Embed(description=f"<:yes:1396838746862784582> | All warnings have been cleared for **{user}** in this guild.", color=self.color)
            embed.set_author(name=f"Warnings Cleared", icon_url=self.get_user_avatar(user))
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=self.get_user_avatar(ctx.author))
            embed.timestamp = discord.utils.utcnow()


            await ctx.send(embed=embed)
            
            # Logging Integration
            logging_cog = self.bot.get_cog("Logging")
            if logging_cog:
                data = {
                    'description': f"**{user.mention}** warnings have been cleared by {ctx.author.mention}."
                }
                logging_cog.queue_event(ctx.guild.id, 'moderation', data)
                asyncio.create_task(logging_cog.log_to_history(ctx.guild.id, "moderation", "clearwarns", user.id, ctx.channel.id, f"Warnings cleared by {ctx.author.name}"))
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            print(f"Error during clearwarns command: {e}")
