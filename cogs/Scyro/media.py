import discord
from discord.ext import commands


class _media(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Media commands"""
  
    def help_custom(self):
		      emoji = '<:circle2:1348326520581521469>'
		      label = "Media Commands"
		      description = ""
		      return emoji, label, description

    @commands.group()
    async def __Media__(self, ctx: commands.Context):
        """`media` , `media setup ` , `media remove` , `media config` , `media bypass` , `media bypass add` , `media bypass remove` , `media bypass show`"""