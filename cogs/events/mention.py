from utils import getConfig  
import discord
from discord.ext import commands
from utils.Tools import get_ignore_data
import motor.motor_asyncio
import os

class Mention(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.color = 0x9D00FF  # Purple color
        self.bot_name = "Scyro"
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.blacklist_col = self.db["blacklist"]

    async def is_blacklisted(self, message):
        if not message.guild:
            return False
            
        # Check guild blacklist
        if await self.blacklist_col.find_one({"type": "guild", "id": message.guild.id}):
            return True
            
        # Check user blacklist
        if await self.blacklist_col.find_one({"type": "user", "id": message.author.id}):
            return True

        return False

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # Check blacklist
        if await self.is_blacklisted(message):
            return

        # Check ignore data (Assuming get_ignore_data handles its own DB connections or is already migrated?)
        # Phase 3 migrated ignore.py, but utils.Tools might typically use global DB or something.
        # Assuming get_ignore_data is compatible or will be updated if needed.
        # Ideally, this should use self.bot.get_cog('Ignore') logic if possible, but keep util if it works.
        try:
            ignore_data = await get_ignore_data(message.guild.id)
            if str(message.author.id) in ignore_data["user"] or str(message.channel.id) in ignore_data["channel"]:
                return
        except Exception:
            pass # Fail safe if ignore data fetch fails

        if message.reference and message.reference.resolved:
            if isinstance(message.reference.resolved, discord.Message):
                if message.reference.resolved.author.id == self.bot.user.id:
                    return

        guild_id = message.guild.id
        # getConfig likely returns a dict with 'prefix'. Ensuring async consistency.
        data = await getConfig(guild_id, self.bot) 
        prefix = data["prefix"]

        if self.bot.user in message.mentions:
            # Only if it's strictly the mention and nothing else
            if len(message.content.strip().split()) == 1:
                embed = discord.Embed(
                    title=f"  Heyy I'm {self.bot_name}!",
                    color=self.color,
                    description=(
                        f"The Best bot for **Moderation and Utility**, keeping your Server **Safe** and **Smart**.\n\n"
                        f"<a:help:1396429146518720623> **Need Help?**\n"
                        f"<a:dot:1396429135588626442> Use `{prefix}help` to get the Information of the bot\n"
                        f"<a:dot:1396429135588626442> For **Security Setup**, type `{prefix}antinuke enable`\n"
                        f"<a:dot:1396429135588626442> If you **Need Assistance**, join our **[Support Server.](https://dsc.gg/scyrogg)**\n\n"
                        f"<a:dot:1396429135588626442> **Website:** https://scyro.xyz/\n<a:dot:1396429135588626442> **Dashboard:** https://scyro.xyz/dashboard"
                    )
                )
                embed.set_thumbnail(url=self.bot.user.avatar.url)
                embed.set_footer(text="Scyro", icon_url=self.bot.user.avatar.url)

                buttons = [
                    discord.ui.Button(label=" Website", style=discord.ButtonStyle.link, url="https://scyro.xyz"),
                    discord.ui.Button(label=" Docs", style=discord.ButtonStyle.link, url="https://scyro.xyz/docs"),
                    discord.ui.Button(label=" Invite", style=discord.ButtonStyle.link, url="https://discord.com/oauth2/authorize?client_id=1387046835322880050&scope=bot%20applications.commands&permissions=30030655231&redirect_uri=https%3A%2F%2Fdsc.gg%2Fscyrogg"),
                    discord.ui.Button(label=" Support", style=discord.ButtonStyle.link, url="https://dsc.gg/scyrogg"),
                ]

                view = discord.ui.View()
                for button in buttons:
                    view.add_item(button)

                try:
                    await message.channel.send(embed=embed, view=view)
                except discord.Forbidden:
                    pass
