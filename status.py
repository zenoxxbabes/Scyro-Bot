import discord
from discord.ext import commands, tasks
import asyncio

class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = 1434130318842925166
        self.message_id = None 
        self.status_task.start()

    def cog_unload(self):
        self.status_task.cancel()

    @tasks.loop(minutes=1)
    async def status_task(self):
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                return

            if not channel.permissions_for(channel.guild.me).send_messages:
                return

            # Generate the automatic timestamp code
            uptime_str = discord.utils.format_dt(self.bot.launch_time, style='R')

            embed = discord.Embed(title="Scyro Stats", color=0x2f3136)

            if not self.bot.is_ready():
                embed.color = 0xff0000
                embed.description = "🌟 **Status:** Offline / Starting..."
            else:
                embed.color = 0x00ff00
                embed.description = "**Status:** 🟢 Online"
                embed.add_field(name="Uptime", value=uptime_str, inline=False)
                embed.add_field(name="Ping", value=f"{round(self.bot.latency * 1000)} ms", inline=False)
                embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=False)
                embed.add_field(name="Users", value=str(len(self.bot.users)), inline=False)
                embed.add_field(name="Commands", value=str(len(self.bot.commands)), inline=False)  
                embed.add_field(name="Invite Link", value="[Click Here](https://discord.com/api/oauth2/authorize?client_id=1362680985497636885&permissions=8&scope=bot)", inline=False)
                embed.add_field(name="Website", value="[Support](https://scyro.xyz/discord)", inline=False)
                
            embed.set_footer(text="By ZENOXX")
            if self.bot.user:
                 embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
            # Rate Limit Safe Edit
            from core.ratelimithandler import safe_message_edit
            
            if self.message_id:
                try:
                    # Try fetching to ensure it exists
                    msg = await channel.fetch_message(self.message_id)
                    await safe_message_edit(msg, embed=embed)
                except discord.NotFound:
                    # Message deleted, send new one
                    msg = await channel.send(embed=embed)
                    self.message_id = msg.id
                except Exception:
                    # Any other error, ignore this loop
                    pass
            else:
                msg = await channel.send(embed=embed)
                self.message_id = msg.id

        except Exception as e:
            print(f"Error in status task: {e}")

    @status_task.before_loop
    async def before_status(self):
        try:
            await self.bot.wait_until_ready()
        except asyncio.CancelledError:
            pass

async def setup(bot):
    # Ensure this is set when the bot starts
    bot.launch_time = discord.utils.utcnow()
    await bot.add_cog(StatusCog(bot))