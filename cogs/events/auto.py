import discord
from discord.utils import *
from core import Scyro, Cog
from utils.Tools import *
from utils.config import BotName, serverLink
from discord.ext import commands
from discord.ui import Button, View


class Autorole(Cog):
    def __init__(self, bot: Scyro):
        self.bot = bot

    @commands.Cog.listener(name="on_guild_join")
    async def send_msg_to_adder(self, guild: discord.Guild):
        async for entry in guild.audit_logs(limit=3):
            if entry.action == discord.AuditLogAction.bot_add:
                embed = discord.Embed(
                    title="  Thanks for Adding Scyro!",
                    description=(
                        "**Hey! Thanks** for **Choosing** me for your **Servers.**. <a:candle:1396477060469362688>\n\n"
                        f"**Here’s how to get started:**\n"
                        f" <a:dot:1396429135588626442> My default prefix is **`.`**\n"
                        f" <a:dot:1396429135588626442> Use **`/help or .help`** to explore my commands\n"
                        f" <a:dot:1396429135588626442> Need guides, FAQ, or support?\n <a:dot:1396429135588626442> Check out the **[Support Server]({serverLink})**\n"
                        f"<a:dot:1396429135588626442> **Website:** https://scyro.xyz/\n<a:dot:1396429135588626442> **Dashboard:** https://scyro.xyz/dashboard"
                    ),
                    color=0x9D00FF
                )

                embed.set_thumbnail(
                    url=entry.user.avatar.url if entry.user.avatar else entry.user.default_avatar.url
                )
                embed.set_author(name=guild.name, icon_url=guild.me.display_avatar.url)

                if guild.icon:
                    embed.set_author(name=guild.name, icon_url=guild.icon.url)

                embed.set_footer(
                    text="Scyro",
                    icon_url="https://cdn.discordapp.com/avatars/1387046835322880050/1f8316ab90e1fa59fb8d8c05c2cf0f29.png?size=1024"
                )

                # Buttons
                website_button = Button(label=" Website", style=discord.ButtonStyle.link, url="https://scyro.xyz.app/")
                support_button = Button(label=" Support", style=discord.ButtonStyle.link, url="https://dsc.gg/scyrogg")
                docs_button = Button(label=" Docs", style=discord.ButtonStyle.link, url="https://scyro.xyz/docs")

                view = View()
                view.add_item(support_button)
                view.add_item(website_button)
                view.add_item(docs_button)

                try:
                    await entry.user.send(embed=embed, view=view)
                except Exception as e:
                    print(f"Ohoho! Failed to DM user: {e}")
