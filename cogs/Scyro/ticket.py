import discord
from discord.ext import commands


class _ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Ticket commands"""
  
    def help_custom(self):
		       emoji = '<:ticket:1348340622154793041>'
		       label = "Ticket"
		       description = ""
		       return emoji, label, description

    @commands.group()
    async def __Ticket__(self, ctx: commands.Context):
        """`setticket` , `ticket`"""