import asyncio
import discord
from discord.ext import commands, tasks
from discord.utils import get
import datetime
import random
import requests
import aiohttp
import re
from discord.ext.commands.errors import BadArgument
from discord.ext.commands import Cog
from discord.colour import Color
import hashlib
from utils.Tools import *
from traceback import format_exception
import discord
from discord.ext import commands
import datetime
from discord import ButtonStyle
from discord.ui import Button, View
import psutil
import time
from datetime import datetime, timezone, timedelta
import sqlite3
import aiosqlite
import json
import os
from typing import *
import string


lawda = [
  '8', '3821', '23', '21', '313', '43', '29', '76', '11', '9',
  '44', '470', '318' , '26', '69'
]

# Enhanced data for realistic fake information
COUNTRY_CODES = [
  '+1', '+7', '+20', '+27', '+30', '+31', '+32', '+33', '+34', '+36', '+39', '+40', '+41', 
  '+43', '+44', '+45', '+46', '+47', '+48', '+49', '+51', '+52', '+53', '+54', '+55', '+56', 
  '+57', '+58', '+60', '+61', '+62', '+63', '+64', '+65', '+66', '+81', '+82', '+84', '+86', 
  '+90', '+91', '+92', '+93', '+94', '+95', '+98', '+212', '+213', '+216', '+218', '+220', 
  '+221', '+222', '+223', '+224', '+225', '+226', '+227', '+228', '+229', '+230', '+231'
]

CREDIT_CARD_TYPES = [
  {'name': 'Visa', 'prefix': '4', 'length': 16},
  {'name': 'MasterCard', 'prefix': '5', 'length': 16},
  {'name': 'American Express', 'prefix': '34', 'length': 15},
  {'name': 'American Express', 'prefix': '37', 'length': 15},
  {'name': 'Discover', 'prefix': '6', 'length': 16}
]

RICKROLL_INDICATORS = [
  "rickroll", "rick roll", "rick astley", "never gonna give you up", 
  "never gonna let you down", "never gonna run around", "never gonna desert you",
  "dqw4w9wgxcq", "youtube.com/watch?v=dqw4w9wgxcq", "youtu.be/dqw4w9wgxcq",
  "rickrolled", "rick rolled", "astley", "give you up", "let you down",
  "run around and desert", "make you cry", "say goodbye", "tell a lie",
  "hurt you", "rick roll'd", "rickroll'd", "together forever"
]

SUSPICIOUS_DOMAINS = [
  "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "short.link",
  "tiny.cc", "is.gd", "buff.ly", "ift.tt", "youtu.be"
]

class AvatarView(View):
  def __init__(self, user, member, author_id, banner_url):
    super().__init__()
    self.user = user
    self.member = member
    self.author_id = author_id
    self.banner_url = banner_url

    if self.user.avatar.is_animated():
      self.add_item(Button(label='GIF', url=self.user.avatar.with_format('gif').url, style=discord.ButtonStyle.link))
    self.add_item(Button(label='PNG', url=self.user.avatar.with_format('png').url, style=discord.ButtonStyle.link))
    self.add_item(Button(label='JPEG', url=self.user.avatar.with_format('jpg').url, style=discord.ButtonStyle.link))
    self.add_item(Button(label='WEBP', url=self.user.avatar.with_format('webp').url, style=discord.ButtonStyle.link))

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author_id:
      await interaction.response.send_message(
        "Uh oh! That message doesn't belong to you. You must run this command to interact with it.",
        ephemeral=True
      )
      return False
    return True

  @discord.ui.button(label='Server Avatar', style=discord.ButtonStyle.success, custom_id='server_avatar_button')
  async def server_avatar(self, interaction: discord.Interaction, button: Button):
    if not self.member.guild_avatar:
      await interaction.response.send_message(
        "This user doesn't have a different guild avatar.",
        ephemeral=True
      )
    else:
      embed = interaction.message.embeds[0]
      embed.set_image(url=self.member.guild_avatar.url)
      await interaction.response.edit_message(embed=embed)

  @discord.ui.button(label='User Banner', style=discord.ButtonStyle.success, custom_id='banner_button')
  async def banner(self, interaction: discord.Interaction, button: Button):
    if not self.banner_url:
      await interaction.response.send_message(
        "This user doesn't have a banner.",
        ephemeral=True
      )
    else:
      embed = interaction.message.embeds[0]
      embed.set_image(url=self.banner_url)
      await interaction.response.edit_message(embed=embed)

class General(commands.Cog):

  def __init__(self, bot, *args, **kwargs):
    self.bot = bot
    self.aiohttp = aiohttp.ClientSession()
    self._URL_REGEX = r'(?P<url><[^: >]+:\/[^ >]+>|(?:https?|steam):\/\/[^\s<]+[^<.,:;\"\'\]\s])'
    self.color = 0x2b2d31  # Black color
    self.db_path = "db/polls.db"  # Database path for polls
    self.poll_emojis = {
      1: "**``-``**",
      2: "**``-``**",
      3: "**``-``**",
      4: "**``-``**",
      5: "**``-``**",
      6: "**``-``**",
      7: "**``-``**",
      8: "**``-``**",
      9: "**``-``**"
    }
    self.active_polls = {}  # In-memory storage for active poll tasks
    self.check_expired_polls.start()

  async def cog_unload(self):
    self.check_expired_polls.cancel()
    # Cancel all active poll tasks
    for poll_id, task in self.active_polls.items():
      if not task.done():
        task.cancel()

  def generate_fake_credit_card(self):
    """Generate a realistic fake credit card number"""
    card_type = random.choice(CREDIT_CARD_TYPES)
    prefix = card_type['prefix']
    length = card_type['length']
    
    # Generate the remaining digits
    remaining_length = length - len(prefix) - 1  # -1 for check digit
    digits = prefix
    
    for _ in range(remaining_length):
      digits += str(random.randint(0, 9))
    
    # Add a fake check digit
    digits += str(random.randint(0, 9))
    
    # Format with spaces for readability
    formatted = ""
    for i, digit in enumerate(digits):
      if i > 0 and i % 4 == 0:
        formatted += " "
      formatted += digit
    
    return formatted

  def generate_fake_phone(self):
    """Generate a realistic fake phone number with international code"""
    country_code = random.choice(COUNTRY_CODES)
    
    if country_code == '+1':  # US/Canada format
      area_code = random.randint(200, 999)
      exchange = random.randint(200, 999)
      number = random.randint(1000, 9999)
      return f"{country_code}-{area_code}-{exchange}-{number}"
    elif country_code == '+91':  # India format
      number = random.randint(6000000000, 9999999999)
      return f"{country_code}-{number}"
    elif country_code == '+44':  # UK format
      number = random.randint(1000000000, 9999999999)
      return f"{country_code}-{number}"
    else:  # Generic international format
      number = random.randint(100000000, 9999999999)
      return f"{country_code}-{number}"

  def generate_fake_ip(self):
    """Generate a realistic fake IP address"""
    # Common private IP ranges for more realistic results
    ranges = [
      (192, 168, random.randint(1, 255), random.randint(1, 254)),
      (10, random.randint(0, 255), random.randint(0, 255), random.randint(1, 254)),
      (172, random.randint(16, 31), random.randint(0, 255), random.randint(1, 254)),
      # Some public IP ranges
      (8, 8, 8, random.randint(1, 254)),
      (1, 1, 1, random.randint(1, 254)),
      (random.randint(50, 200), random.randint(1, 255), random.randint(1, 255), random.randint(1, 254))
    ]
    
    ip_parts = random.choice(ranges)
    return f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{ip_parts[3]}"

  async def setup_database(self):
    """Initialize the polls database table"""
    # Create db directory if it doesn't exist
    os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("""
        CREATE TABLE IF NOT EXISTS active_polls (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          message_id INTEGER UNIQUE,
          channel_id INTEGER,
          guild_id INTEGER,
          author_id INTEGER,
          question TEXT,
          options TEXT,
          end_time TIMESTAMP,
          votes TEXT DEFAULT '{}'
        )
      """)
      await db.commit()

  @commands.hybrid_command(
    usage="Avatar <member>",
    name='avatar',
    aliases=['av'],
    help="Get User avater/Guild avatar & Banner of a user."
  )
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def _user(self, ctx, member: Optional[Union[discord.Member, discord.User]] = None):
    try:
      # Get shard info
      if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
          shard_id = ctx.bot.shard_id
      else:
          shard_id = getattr(ctx.bot, '_shard_id', 0)
      
      if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
          shard_count = ctx.bot.shard_count
      else:
          shard_count = getattr(ctx.bot, '_shard_count', 1)
      
      shard_id = shard_id if shard_id is not None else 0
      shard_count = shard_count if shard_count is not None else 1
      
      if member is None:
        member = ctx.author
      user = await self.bot.fetch_user(member.id)

      banner_url = user.banner.url if user.banner else None

      description = f"[`PNG`]({user.avatar.with_format('png').url}) | [`JPG`]({user.avatar.with_format('jpg').url}) | [`WEBP`]({user.avatar.with_format('webp').url})"
      if user.avatar.is_animated():
        description += f" | [`GIF`]({user.avatar.with_format('gif').url})"
      if banner_url:
        description += f" | [`Banner`]({banner_url})"

      embed = discord.Embed(
        color=self.color,
        description=description
      )
      embed.set_author(name=f"{member}", icon_url=member.avatar.url if member.avatar else member.default_avatar.url)
      embed.set_image(url=user.avatar.url)
      
      embed.set_footer(text=f"Requested By {ctx.author}",
                       icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)

      view = AvatarView(user, member, ctx.author.id, banner_url)
      await ctx.send(embed=embed, view=view)
    except Exception as e:
      print(f"Error: {e}")
      
  @commands.hybrid_command(
    name="servericon",
    help="Get the server icon",
    usage="Servericon"
  )
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def servericon(self, ctx: commands.Context):
    server = ctx.guild
    if server.icon is None:
      await ctx.reply("This server does not have an icon.")
      return

    webp = server.icon.replace(format='webp')
    jpg = server.icon.replace(format='jpg')
    png = server.icon.replace(format='png')

    description = f"[`PNG`]({png}) | [`JPG`]({jpg}) | [`WEBP`]({webp})"
    if server.icon.is_animated():
      gif = server.icon.replace(format='gif')
      description += f" | [`GIF`]({gif})"

    avemb = discord.Embed(
      color=self.color,
      title=f"{server}'s Icon",
      description=description
    )
    avemb.set_image(url=server.icon.url)
    
    avemb.set_footer(
      text=f"Requested By {ctx.author}",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )

    view = discord.ui.View()
    view.add_item(Button(label="Download Icon", url=server.icon.url, style=ButtonStyle.link))

    await ctx.send(embed=avemb, view=view)

  @commands.hybrid_command(name="membercount",
                           help="Get total member count of the server",
                           usage="membercount",
                           aliases=["mc"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 2, commands.BucketType.user)
  async def membercount(self, ctx: commands.Context):
    total_members = len(ctx.guild.members)
    total_humans = len([member for member in ctx.guild.members if not member.bot])
    total_bots = len([member for member in ctx.guild.members if member.bot])

    online = len([member for member in ctx.guild.members if member.status == discord.Status.online])
    offline = len([member for member in ctx.guild.members if member.status == discord.Status.offline])
    idle = len([member for member in ctx.guild.members if member.status == discord.Status.idle])
    dnd = len([member for member in ctx.guild.members if member.status == discord.Status.do_not_disturb])

    embed = discord.Embed(title="Member Statistics",
                          color=0x2b2d31)
    embed.add_field(name="**``-``** Count Stats:",
                    value=f"**``•``** Total Members: {total_members}\n**``•``** Total Humans: {total_humans}\n**``•``** Total Bots: {total_bots}",
                    inline=False)

    embed.add_field(name="**``-``** Presence Stats:", value=f"**``•``** Online: {online}\n**``•``** Dnd: {dnd}\n**``•``** Idle: {idle}\n**``•``** Offline: {offline}", inline=False)
    
    embed.set_footer(
      text=f"Requested by {ctx.author}",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )

    await ctx.send(embed=embed)

  @commands.command(name="stats", aliases=["stat"], usage="stats")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  async def stats(self, ctx: commands.Context):
    """Show system performance statistics"""
    # Import BOT_START_TIME inside the function to avoid circular import
    from main import BOT_START_TIME
    
    # Get system stats
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    ram_percent = memory.percent
    
    # Calculate uptime
    uptime = datetime.now() - BOT_START_TIME
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    
    # Get guild count
    guild_count = len(ctx.bot.guilds)
    
    # Get total members and channels (convert generators to lists)
    total_members = len([user for user in ctx.bot.get_all_members()])
    total_channels = len([channel for channel in ctx.bot.get_all_channels()])
    
    # Create embed
    embed = discord.Embed(
      title="Statistics of Scyro! <:stats:1433759391030579252>",
      color=0x2b2d31,
      timestamp=datetime.utcnow()
    )
    
    # Display information
    embed.add_field(
      name="<a:statsinfo:1433759965654548480> Information:",
      value=f" Total Guilds: **{guild_count}**\nTotal Members: **{total_members}**\nTotal Channels: **{total_channels}**",
      inline=False
    )
    
    embed.add_field(
      name="<:perform:1433760539888193577> Performance:",
      value=f" Ping: **{int(ctx.bot.latency * 1000)}ms**\n CPU: **Ryzen 9 [5900X]**\n RAM: **4 GB [DDR5]**\n Uptime: **__{uptime_str}__**",
      inline=False
    )
    
    embed.set_footer(
      text=f"Requested by {ctx.author}",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )
    
    await ctx.send(embed=embed)

  # ==================== ADVANCED POLL SYSTEM ====================

  @commands.hybrid_group(name="poll", description="Advanced poll management system")
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def poll(self, ctx):
    """Advanced poll management system"""
    if ctx.invoked_subcommand is None:
      embed = discord.Embed(
        title="📊 Advanced Poll System",
        description="Create interactive polls with multiple options and time limits!",
        color=self.color
      )
      embed.add_field(
        name="📝 Create Poll",
        value="`/poll create <question> [time] <option1> <option2> [option3]...`\nCreate a new poll with 2-9 options",
        inline=False
      )
      embed.add_field(
        name="📊 List Polls",
        value="`/poll list`\nShow all active polls in this server",
        inline=False
      )
      embed.add_field(
        name="🛑 End Poll",
        value="`/poll end <message_id>`\nForcefully end a poll early",
        inline=False
      )
      embed.add_field(
        name="ℹ️ Settings",
        value="• **Default time:** 24 hours\n• **Min options:** 2\n• **Max options:** 9\n• **Time formats:** `1h`, `30m`, `2d`, `1h30m`",
        inline=False
      )
      embed.set_footer(text=f"Requested by {ctx.author.name}", 
                       icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
      await ctx.send(embed=embed)

  @poll.command(name="create", description="Create a new poll with multiple options")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  async def poll_create(self, ctx, question: str, time: str = "24h", option1: str = None, 
                       option2: str = None, option3: str = None, option4: str = None,
                       option5: str = None, option6: str = None, option7: str = None,
                       option8: str = None, option9: str = None):
    """Create a poll with up to 9 options"""
    
    # Get shard info
    if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
        shard_id = ctx.bot.shard_id
    else:
        shard_id = getattr(ctx.bot, '_shard_id', 0)
    
    if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
        shard_count = ctx.bot.shard_count
    else:
        shard_count = getattr(ctx.bot, '_shard_count', 1)
    
    shard_id = shard_id if shard_id is not None else 0
    shard_count = shard_count if shard_count is not None else 1
    
    # Collect non-None options
    options = [opt for opt in [option1, option2, option3, option4, option5, 
                             option6, option7, option8, option9] if opt is not None]
    
    if len(options) < 2:
      embed = discord.Embed(
        title="❌ Invalid Poll",
        description="A poll must have at least **2 options**!",
        color=discord.Color.red()
      )
      return await ctx.send(embed=embed, ephemeral=True)

    if len(options) > 9:
      embed = discord.Embed(
        title="❌ Too Many Options",
        description="A poll can have maximum **9 options**!",
        color=discord.Color.red()
      )
      return await ctx.send(embed=embed, ephemeral=True)

    # Parse time duration
    try:
      duration = self.parse_time(time)
    except ValueError as e:
      embed = discord.Embed(
        title="❌ Invalid Time Format",
        description=f"{str(e)}\n\n**Examples:** `1h`, `30m`, `2d`, `1h30m`",
        color=discord.Color.red()
      )
      return await ctx.send(embed=embed, ephemeral=True)

    # Create poll embed
    embed = discord.Embed(
      title=f"<a:help:1396429146518720623> {question}",
      description=f"> **``•``** **Poll created by** __{ctx.author.mention}__\n",
      color=self.color,
      timestamp=datetime.utcnow()
    )

    options_text = ""
    for i, option in enumerate(options, 1):
      options_text += f"> {self.poll_emojis[i]} **{option}**\n"
    
    embed.add_field(name="**``•``** Options:", value=options_text, inline=False)
    
    end_time = datetime.utcnow() + duration
    embed.add_field(
      name="**``•``** Ends:",
      value=f"<t:{int(end_time.timestamp())}:R>",
      inline=True
    )
    embed.add_field(name="**``•``** Votes:", value="**0** total votes", inline=True)

    # Send poll message
    poll_message = await ctx.send(embed=embed)

    # Add reactions
    for i in range(1, len(options) + 1):
      await poll_message.add_reaction(self.poll_emojis[i])

    # Store poll in database
    await self.setup_database()
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("""
        INSERT INTO active_polls 
        (message_id, channel_id, guild_id, author_id, question, options, end_time, votes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      """, (
        poll_message.id, ctx.channel.id, ctx.guild.id, ctx.author.id,
        question, json.dumps(options), end_time.isoformat(), '{}'
      ))
      await db.commit()

    # Update embed with poll ID
    embed.set_footer(text=f"Poll ID: {poll_message.id}")
    await poll_message.edit(embed=embed)

    # Schedule poll ending
    task = asyncio.create_task(self.end_poll_after_timeout(poll_message.id, duration.total_seconds()))
    self.active_polls[poll_message.id] = task



  @poll.command(name="list", description="Show all active polls in this server")
  @blacklist_check()
  @ignore_check()
  async def poll_list(self, ctx):
    """List all active polls in the server"""
    await self.setup_database()
    
    async with aiosqlite.connect(self.db_path) as db:
      async with db.execute("""
        SELECT message_id, question, end_time, author_id
        FROM active_polls 
        WHERE guild_id = ?
        ORDER BY end_time ASC
      """, (ctx.guild.id,)) as cursor:
        polls = await cursor.fetchall()

    if not polls:
      embed = discord.Embed(
        title="📊 Active Polls",
        description="No active polls found in this server.",
        color=self.color
      )
      return await ctx.send(embed=embed)

    embed = discord.Embed(
      title="📊 Active Polls",
      description=f"Found **{len(polls)}** active poll(s) in this server:",
      color=self.color
    )

    for message_id, question, end_time_str, author_id in polls:
      try:
        end_time = datetime.fromisoformat(end_time_str)
        author = self.bot.get_user(author_id)
        author_name = author.name if author else "Unknown User"
        
        embed.add_field(
          name=f"🗳️ {question[:45]}{'...' if len(question) > 45 else ''}",
          value=f"**ID:** `{message_id}`\n"
                f"**Author:** {author_name}\n"
                f"**Ends:** <t:{int(end_time.timestamp())}:R>",
          inline=False
        )
      except Exception:
        continue

    await ctx.send(embed=embed)

  @poll.command(name="end", description="Forcefully end an active poll")
  @blacklist_check()
  @ignore_check()
  async def poll_end(self, ctx, message_id: str):
    """End a poll early by message ID"""
    try:
      msg_id = int(message_id)
    except ValueError:
      embed = discord.Embed(
        title="❌ Invalid Message ID",
        description="Please provide a valid **numeric** message ID.",
        color=discord.Color.red()
      )
      return await ctx.send(embed=embed, ephemeral=True)

    await self.setup_database()
    
    async with aiosqlite.connect(self.db_path) as db:
      async with db.execute("""
        SELECT author_id FROM active_polls 
        WHERE message_id = ? AND guild_id = ?
      """, (msg_id, ctx.guild.id)) as cursor:
        poll_data = await cursor.fetchone()

    if not poll_data:
      embed = discord.Embed(
        title="❌ Poll Not Found",
        description="No active poll found with that ID in this server.",
        color=discord.Color.red()
      )
      return await ctx.send(embed=embed, ephemeral=True)

    # Check permissions
    poll_author_id = poll_data[0]
    if ctx.author.id != poll_author_id and not ctx.author.guild_permissions.manage_messages:
      embed = discord.Embed(
        title="❌ No Permission",
        description="You can only end polls **you created** or need **Manage Messages** permission.",
        color=discord.Color.red()
      )
      return await ctx.send(embed=embed, ephemeral=True)

    # Cancel the scheduled task if it exists
    if msg_id in self.active_polls:
      self.active_polls[msg_id].cancel()
      del self.active_polls[msg_id]

    # End the poll
    await self.finalize_poll(msg_id)
    
    embed = discord.Embed(
      title="✅ Poll Ended",
      description=f"Poll **`{msg_id}`** has been ended successfully.",
      color=discord.Color.green()
    )
    await ctx.send(embed=embed)

  @tasks.loop(minutes=5)
  async def check_expired_polls(self):
    """Check for expired polls every 5 minutes"""
    await self.setup_database()
    
    try:
      current_time = datetime.utcnow()
      async with aiosqlite.connect(self.db_path) as db:
        async with db.execute("""
          SELECT message_id, end_time FROM active_polls
          WHERE end_time <= ?
        """, (current_time.isoformat(),)) as cursor:
          expired_polls = await cursor.fetchall()
        
        for message_id, end_time_str in expired_polls:
          await self.finalize_poll(message_id)
          
    except Exception as e:
      print(f"Error checking expired polls: {e}")

  @check_expired_polls.before_loop
  async def before_check_expired_polls(self):
    try:
      await self.bot.wait_until_ready()
    except asyncio.CancelledError:
      pass

  def parse_time(self, time_str: str) -> timedelta:
    """Parse time string into timedelta (e.g., '1h30m', '2d', '45m')"""
    if not time_str:
      return timedelta(hours=24)
    
    time_str = time_str.lower().strip()
    total_seconds = 0
    
    # Parse different time units
    import re
    
    # Find all time components
    pattern = r'(\d+)([dhms])'
    matches = re.findall(pattern, time_str)
    
    if not matches:
      raise ValueError("Invalid time format. Use combinations of: **d** (days), **h** (hours), **m** (minutes), **s** (seconds)")
    
    for amount, unit in matches:
      amount = int(amount)
      if unit == 'd':
        total_seconds += amount * 24 * 3600
      elif unit == 'h':
        total_seconds += amount * 3600
      elif unit == 'm':
        total_seconds += amount * 60
      elif unit == 's':
        total_seconds += amount
    
    if total_seconds == 0:
      raise ValueError("Time cannot be **0**")
    
    if total_seconds > 30 * 24 * 3600:  # 30 days max
      raise ValueError("Maximum poll duration is **30 days**")
    
    return timedelta(seconds=total_seconds)

  def format_duration(self, duration: timedelta) -> str:
    """Format timedelta into readable string"""
    total_seconds = int(duration.total_seconds())
    
    days = total_seconds // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60
    
    parts = []
    if days > 0:
      parts.append(f"{days}d")
    if hours > 0:
      parts.append(f"{hours}h")
    if minutes > 0:
      parts.append(f"{minutes}m")
    
    return " ".join(parts) if parts else "less than 1 minute"

  async def end_poll_after_timeout(self, message_id: int, timeout: float):
    """End a poll after the specified timeout"""
    try:
      await asyncio.sleep(timeout)
      await self.finalize_poll(message_id)
    except asyncio.CancelledError:
      pass  # Poll was ended manually
    finally:
      # Clean up the task reference
      if message_id in self.active_polls:
        del self.active_polls[message_id]

  async def finalize_poll(self, message_id: int):
    """Finalize a poll by calculating results and updating the message"""
    await self.setup_database()
    
    async with aiosqlite.connect(self.db_path) as db:
      # Get poll data
      async with db.execute("""
        SELECT channel_id, question, options, votes, author_id, end_time
        FROM active_polls WHERE message_id = ?
      """, (message_id,)) as cursor:
        poll_data = await cursor.fetchone()
      
      if not poll_data:
        return
      
      channel_id, question, options_json, votes_json, author_id, end_time_str = poll_data
      options = json.loads(options_json)
      votes = json.loads(votes_json) if votes_json else {}
      
      # Get the channel and message
      try:
        channel = self.bot.get_channel(channel_id)
        if not channel:
          return
        
        message = await channel.fetch_message(message_id)
        if not message:
          return
        
        # Calculate results
        results = {}
        total_votes = 0
        
        for reaction in message.reactions:
          emoji_str = str(reaction.emoji)
          for i, emoji in self.poll_emojis.items():
            if emoji == emoji_str and i <= len(options):
              # Subtract 1 for the bot's reaction
              vote_count = reaction.count - 1
              results[i] = vote_count
              total_votes += vote_count
              break
        
        # Create results embed
        embed = discord.Embed(
          title=f"📊 {question} (ENDED)",
          description=f"Poll ended • Total votes: **{total_votes}**",
          color=discord.Color.red(),
          timestamp=datetime.utcnow()
        )
        
        # Add end time field
        embed.add_field(
          name="<a:7596clock:1413390466979991572> Ended:",
          value=f"<t:{int(datetime.fromisoformat(end_time_str).timestamp())}:R>",
          inline=True
        )        
        if total_votes > 0:
          results_text = ""
          max_votes = max(results.values()) if results else 0
          
          for i, option in enumerate(options, 1):
            votes_count = results.get(i, 0)
            percentage = (votes_count / total_votes * 100) if total_votes > 0 else 0
            
            # Add winner emoji
            winner_mark = "👑 " if votes_count == max_votes and max_votes > 0 else ""
            progress_bar = "█" * int(percentage // 5) + "░" * (20 - int(percentage // 5))
            
            results_text += f"{self.poll_emojis[i]} {winner_mark}**{option}**\n"
            results_text += f"`{progress_bar}` **{votes_count}** votes (**{percentage:.1f}%**)\n\n"
          
          embed.add_field(name="🏆 Final Results:", value=results_text, inline=False)
          
          # Send poll winner announcement
          try:
              # Find the winning option
              winning_option_index = max(results, key=results.get)
              winning_option = options[winning_option_index - 1]
              author = self.bot.get_user(author_id)
              if channel and author:
                  winner_msg = f"<@{author_id}>, Option **{winning_option}** Won the Poll."
                  await channel.send(winner_msg)
          except Exception as e:
              print(f"Error sending poll winner message: {e}")
        else:
          embed.add_field(name="📊 Results:", value="**No votes were cast.**", inline=False)
        
        embed.set_footer(text=f"Poll ID: {message_id} • Ended")
        
        # Update message and clear reactions
        await message.edit(embed=embed)
        await message.clear_reactions()
        
        # Remove poll from database
        await db.execute("DELETE FROM active_polls WHERE message_id = ?", (message_id,))
        await db.commit()
        
      except Exception as e:
        print(f"Error finalizing poll {message_id}: {e}")

  # ==================== OTHER COMMANDS ====================

  @commands.command(name="hack",
    help="hack someone's discord account",
    usage="Hack <member>")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def hack(self, ctx: commands.Context, member: discord.Member):
    stringi = member.name
    
    lund = await ctx.send(f"<a:heker:1419583839025627166> **Initializing hack on {member.mention}...**")
    await asyncio.sleep(1.5)
    
    # Generate realistic fake data
    fake_email = f"{''.join(letter for letter in stringi if letter.isalnum())}{random.choice(lawda)}@{'gmail.com' if random.randint(1,10) <= 7 else random.choice(['yahoo.com', 'hotmail.com', 'outlook.com', 'protonmail.com'])}"
    fake_password = f"{member.name}{random.randint(100, 9999)}!@"
    fake_ip = self.generate_fake_ip()
    fake_phone = self.generate_fake_phone()
    fake_credit_card = self.generate_fake_credit_card()
    
    # Additional fake data
    fake_mac = ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])
    fake_browser = random.choice(["Chrome 118.0.5993.70", "Firefox 119.0", "Safari 17.1", "Edge 118.0.2088.46"])
    fake_os = random.choice(["Windows 11 Pro", "macOS Ventura 13.6", "Ubuntu 22.04 LTS", "Android 14"])
    fake_location = random.choice(["New York, NY", "London, UK", "Tokyo, JP", "Mumbai, IN", "Sydney, AU", "Berlin, DE", "Toronto, CA"])
    
    embed = discord.Embed(
      title=f"<a:heker:1419583839025627166> **Successfully Hacked {member.display_name}!**",
      description=f"**🎯 Target Acquired:** {member.mention}",
      color=0x2b2d31,  # Black color as requested
      timestamp=datetime.utcnow()
    )
    
    embed.add_field(
      name="🔐 **Account Credentials**",
      value=(
        f"**📧 Email:** `{fake_email}`\n"
        f"**🔑 Password:** `{fake_password}`\n"
        f"**🆔 User ID:** `{member.id}`"
      ),
      inline=False
    )
    
    embed.add_field(
      name="🌐 **Network Information**",
      value=(
        f"**🖥️ IP Address:** `{fake_ip}`\n"
        f"**📱 Phone:** `{fake_phone}`\n"
        f"**🔗 MAC Address:** `{fake_mac}`"
      ),
      inline=False
    )
    
    embed.add_field(
      name="💳 **Financial Data**",
      value=(
        f"**💳 Credit Card:** `{fake_credit_card}`\n"
        f"**📅 Expiry:** `{random.randint(1, 12):02d}/{random.randint(25, 29)}`\n"
        f"**🔒 CVV:** `{random.randint(100, 999)}`"
      ),
      inline=False
    )
    
    embed.add_field(
      name="🖥️ **System Information**",
      value=(
        f"**💻 OS:** `{fake_os}`\n"
        f"**🌐 Browser:** `{fake_browser}`\n"
        f"**📍 Location:** `{fake_location}`"
      ),
      inline=False
    )
    
    embed.add_field(
      name="📊 **Discord Analytics**",
      value=(
        f"**📅 Account Created:** <t:{int(member.created_at.timestamp())}:R>\n"
        f"**⏰ Joined Server:** <t:{int(member.joined_at.timestamp())}:R>\n"
        f"**⚡ Status:** `{'Online' if str(member.status) != 'offline' else 'Offline'}`"
      ),
      inline=False
    )
    
    embed.add_field(
      name="⚠️ **Security Breach Status**",
      value="🔴 **FULLY COMPROMISED** • All systems penetrated successfully",
      inline=False
    )
    
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    
    embed.set_footer(
      text=f"Hacked By {ctx.author} • Data Extraction Complete",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )
    
    await ctx.send(embed=embed)
    await lund.delete()

  @commands.command(name="wizz", usage="Wizz")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def wizz(self, ctx: commands.Context):
    """Enhanced wizz command with more realistic fake destruction sequence"""
    
    # Get shard info
    if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
        shard_id = ctx.bot.shard_id
    else:
        shard_id = getattr(ctx.bot, '_shard_id', 0)
    
    if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
        shard_count = ctx.bot.shard_count
    else:
        shard_count = getattr(ctx.bot, '_shard_count', 1)
    
    shard_id = shard_id if shard_id is not None else 0
    shard_count = shard_count if shard_count is not None else 1
    
    # Initial warning
    warning_msg = await ctx.send(f"⚠️ **INITIALIZING WIZZ PROTOCOL ON `{ctx.guild.name}`**")
    await asyncio.sleep(2)
    
    # Scanning phase
    scan_msg = await ctx.send(f"🔍 **Scanning server infrastructure...**")
    await asyncio.sleep(1.5)
    
    # Server analysis
    analysis_msg = await ctx.send(f"📊 **Analyzing {len(ctx.guild.channels)} channels and {len(ctx.guild.roles)} roles...**")
    await asyncio.sleep(1.5)
    
    # Permission bypass
    bypass_msg = await ctx.send(f"🔓 **Bypassing administrator permissions...**")
    await asyncio.sleep(1)
    
    # Payload deployment
    payload_msg = await ctx.send(f"💣 **Deploying destruction payload...**")
    await asyncio.sleep(1)
    
    # Mass deletion simulation
    delete_channels = await ctx.send(f"🗑️ **Deleting {len(ctx.guild.channels)} channels... [████████░░] 80%**")
    await asyncio.sleep(1)
    
    delete_roles = await ctx.send(f"👑 **Removing {len(ctx.guild.roles)} roles... [██████████] 100%**")
    await asyncio.sleep(1)
    
    delete_members = await ctx.send(f"👥 **Banning {len(ctx.guild.members)} members... [██████░░░░] 60%**")
    await asyncio.sleep(1)
    
    webhooks_msg = await ctx.send(f"🪝 **Destroying webhooks and integrations...**")
    await asyncio.sleep(0.8)
    
    emojis_msg = await ctx.send(f"😀 **Purging custom emojis and stickers...**")
    await asyncio.sleep(0.8)
    
    settings_msg = await ctx.send(f"⚙️ **Corrupting server settings...**")
    await asyncio.sleep(0.8)
    
    final_msg = await ctx.send(f"💀 **Installing permanent backdoor...**")
    await asyncio.sleep(1)
    
    # Cleanup phase
    cleanup_msg = await ctx.send(f"🧹 **Cleaning traces...**")
    await asyncio.sleep(1)
    
    # Delete all progress messages
    messages_to_delete = [
      warning_msg, scan_msg, analysis_msg, bypass_msg, payload_msg,
      delete_channels, delete_roles, delete_members, webhooks_msg,
      emojis_msg, settings_msg, final_msg, cleanup_msg
    ]
    
    for msg in messages_to_delete:
      try:
        await msg.delete()
      except:
        pass
    
    # Final success embed
    embed = discord.Embed(
      title="💀 **WIZZ PROTOCOL COMPLETED**",
      description=(
        f"**<:yes:1396838746862784582> Successfully Wizzed `{ctx.guild.name}`**\n\n"
        f"🗑️ **Deleted:** {len(ctx.guild.channels)} channels\n"
        f"👑 **Removed:** {len(ctx.guild.roles)} roles\n"
        f"👥 **Banned:** {len(ctx.guild.members)} members\n"
        f"💣 **Status:** Server completely destroyed\n"
        f"⏰ **Time taken:** {random.randint(15, 25)} seconds\n"
        f"🔒 **Backdoor:** Installed and active"
      ),
      color=0x2b2d31,
      timestamp=ctx.message.created_at
    )
    
    embed.add_field(
      name="⚠️ **DAMAGE REPORT**",
      value=(
        f"🔴 **Server Status:** Completely Destroyed\n"
        f"💀 **Recovery:** Impossible\n"
        f"🚫 **Restore Point:** None Available"
      ),
      inline=False
    )
    
    shard_display_id = shard_id + 1
    embed.set_footer(
      text=f"💀 Wizzed By {ctx.author} • Server Annihilated • Shard {shard_display_id}/{shard_count}",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )
    embed.set_image(url="https://media.giphy.com/media/3o7527pa7qs9kCG78A/giphy.gif")
    
    await ctx.send(embed=embed)

  @commands.hybrid_command(
    name="urban",
    description="Searches for specified phrase on urbandictionary",
    help="Get meaning of specified phrase",
    usage="Urban <phrase>")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def urban(self, ctx: commands.Context, *, phrase):
    # Get shard info
    if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
        shard_id = ctx.bot.shard_id
    else:
        shard_id = getattr(ctx.bot, '_shard_id', 0)
    
    if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
        shard_count = ctx.bot.shard_count
    else:
        shard_count = getattr(ctx.bot, '_shard_count', 1)
    
    shard_id = shard_id if shard_id is not None else 0
    shard_count = shard_count if shard_count is not None else 1
    
    async with self.aiohttp.get(
        "http://api.urbandictionary.com/v0/define?term={}".format(
          phrase)) as urb:
      urban = await urb.json()
      try:
        embed = discord.Embed(title=f"Meaning of \"{phrase}\"", color=self.color)
        embed.add_field(name="__Definition:__",
                        value=urban['list'][0]['definition'].replace(
                          '[', '').replace(']', ''))
        embed.add_field(name="__Example:__",
                        value=urban['list'][0]['example'].replace('[',
                                                                  '').replace(
                                                                    ']', ''))

        embed.add_field(name="__Author:__",
                        value=urban['list'][0]['author'].replace('[',
                                                                  '').replace(
                                                                    ']', ''))

        embed.add_field(name="__Written On:__",
                        value=urban['list'][0]['written_on'].replace('[',
                                                                  '').replace(
                                                                    ']', ''))
        
        shard_display_id = shard_id + 1
        embed.set_footer(
      text=f"Requested By {ctx.author} • Shard {shard_display_id}/{shard_count}",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
      )
        temp = await ctx.reply(embed=embed, mention_author=True)
        await asyncio.sleep(45)
        await temp.delete()
        await ctx.message.delete()
      except:
        pass

  @commands.command(name="rickroll",
                           help="Advanced detection of rickroll and suspicious URLs",
                           usage="Rickroll <url>")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def rickroll(self, ctx: commands.Context, *, url: str):
    """Enhanced rickroll detection with advanced scanning"""
    
    # Get shard info
    if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
        shard_id = ctx.bot.shard_id
    else:
        shard_id = getattr(ctx.bot, '_shard_id', 0)
    
    if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
        shard_count = ctx.bot.shard_count
    else:
        shard_count = getattr(ctx.bot, '_shard_count', 1)
    
    shard_id = shard_id if shard_id is not None else 0
    shard_count = shard_count if shard_count is not None else 1
    
    if not re.match(self._URL_REGEX, url):
      raise BadArgument("❌ Invalid URL format provided")

    # Remove angle brackets if present
    url = url.strip('<>')
    
    checking_msg = await ctx.send("🔍 **Scanning URL for threats...**")
    
    try:
      # Enhanced detection
      async with self.aiohttp.get(url, allow_redirects=True, timeout=10) as response:
        content = str(await response.content.read()).lower()
        final_url = str(response.url).lower()
        
        # Check for rickroll indicators
        rickroll_score = 0
        detected_indicators = []
        
        # Check content for rickroll indicators
        for indicator in RICKROLL_INDICATORS:
          if indicator in content or indicator in final_url:
            rickroll_score += 1
            detected_indicators.append(indicator)
        
        # Check for suspicious domains
        suspicious_domain = False
        for domain in SUSPICIOUS_DOMAINS:
          if domain in final_url:
            suspicious_domain = True
            break
        
        # Check for YouTube rickroll video IDs
        youtube_rickroll_ids = ["dqw4w9wgxcq", "oHg5SJYRHA0", "6_b7RDuLwcI"]
        youtube_rickroll = any(vid_id in final_url for vid_id in youtube_rickroll_ids)
        
        # Determine threat level
        if rickroll_score >= 3 or youtube_rickroll:
          threat_level = "🔴 **CRITICAL**"
          threat_color = discord.Color.red()
          verdict = "**RICKROLL DETECTED**"
        elif rickroll_score >= 1 or suspicious_domain:
          threat_level = "🟡 **SUSPICIOUS**"
          threat_color = discord.Color.yellow()
          verdict = "**POTENTIALLY SUSPICIOUS**"
        else:
          threat_level = "🟢 **SAFE**"
          threat_color = discord.Color.green()
          verdict = "**URL APPEARS SAFE**"
        
        await checking_msg.delete()
        
        embed = discord.Embed(
          title="🛡️ **Advanced URL Scanner Results**",
          description=f"**Verdict:** {verdict}",
          color=threat_color,
          timestamp=datetime.utcnow()
        )
        
        embed.add_field(
          name="📊 **Scan Results**",
          value=(
            f"**🎯 Target URL:** `{url[:50]}{'...' if len(url) > 50 else ''}`\n"
            f"**🔄 Final URL:** `{final_url[:50]}{'...' if len(final_url) > 50 else ''}`\n"
            f"**⚠️ Threat Level:** {threat_level}\n"
            f"**🔢 Risk Score:** {rickroll_score}/10"
          ),
          inline=False
        )
        
        if detected_indicators:
          embed.add_field(
            name="🚨 **Detected Indicators**",
            value=f"``````",
            inline=False
          )
        
        embed.add_field(
          name="🔍 **Technical Details**",
          value=(
            f"**📡 Response Code:** `{response.status}`\n"
            f"**🌐 Domain Check:** `{'Suspicious' if suspicious_domain else 'Clean'}`\n"
            f"**🎥 YouTube Scan:** `{'Rickroll Detected' if youtube_rickroll else 'Clean'}`\n"
            f"**📝 Content Size:** `{len(content)} bytes`"
          ),
          inline=False
        )
        
        if rickroll_score >= 1:
          embed.add_field(
            name="⚠️ **Security Recommendation**",
            value="🛑 **DO NOT CLICK** - This link appears to be a rickroll or malicious redirect!",
            inline=False
          )
        
        shard_display_id = shard_id + 1
        embed.set_footer(
          text=f"Scanned by {ctx.author} • Advanced Detection Engine • Shard {shard_display_id}/{shard_count}",
          icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )
        
        await ctx.reply(embed=embed, mention_author=True)
        
    except asyncio.TimeoutError:
      await checking_msg.delete()
      embed = discord.Embed(
        title="⏰ **Scan Timeout**",
        description="**URL scan timed out** - This could indicate a suspicious redirect or slow server.",
        color=discord.Color.orange()
      )
      await ctx.reply(embed=embed, mention_author=True)
      
    except Exception as e:
      await checking_msg.delete()
      embed = discord.Embed(
        title="❌ **Scan Error**",
        description=f"**Unable to scan URL** - `{str(e)}`",
        color=discord.Color.red()
      )
      await ctx.reply(embed=embed, mention_author=True)

  @commands.command(name="hash",
                           help="Hashes provided text with provided algorithm")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def hash(self, ctx: commands.Context, algorithm: str, *, message):
    # Get shard info
    if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
        shard_id = ctx.bot.shard_id
    else:
        shard_id = getattr(ctx.bot, '_shard_id', 0)
    
    if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
        shard_count = ctx.bot.shard_count
    else:
        shard_count = getattr(ctx.bot, '_shard_count', 1)
    
    shard_id = shard_id if shard_id is not None else 0
    shard_count = shard_count if shard_count is not None else 1
    
    algos: dict[str, str] = {
      "md5": hashlib.md5(bytes(message.encode("utf-8"))).hexdigest(),
      "sha1": hashlib.sha1(bytes(message.encode("utf-8"))).hexdigest(),
      "sha224": hashlib.sha224(bytes(message.encode("utf-8"))).hexdigest(),
      "sha3_224": hashlib.sha3_224(bytes(message.encode("utf-8"))).hexdigest(),
      "sha256": hashlib.sha256(bytes(message.encode("utf-8"))).hexdigest(),
      "sha3_256": hashlib.sha3_256(bytes(message.encode("utf-8"))).hexdigest(),
      "sha384": hashlib.sha384(bytes(message.encode("utf-8"))).hexdigest(),
      "sha3_384": hashlib.sha3_384(bytes(message.encode("utf-8"))).hexdigest(),
      "sha512": hashlib.sha512(bytes(message.encode("utf-8"))).hexdigest(),
      "sha3_512": hashlib.sha3_512(bytes(message.encode("utf-8"))).hexdigest(),
      "blake2b": hashlib.blake2b(bytes(message.encode("utf-8"))).hexdigest(),
      "blake2s": hashlib.blake2s(bytes(message.encode("utf-8"))).hexdigest()
    }
    embed = discord.Embed(color=0x2b2d31,
                          title="🔐 Hashed \"{}\"".format(message))
    if algorithm.lower() not in list(algos.keys()):
      for algo in list(algos.keys()):
        hashValue = algos[algo]
        embed.add_field(name=algo.upper(), value="``````".format(hashValue), inline=False)
    else:
      embed.add_field(name=algorithm.upper(),
                      value="``````".format(algos[algorithm.lower()]),
                      inline=False)
    
    shard_display_id = shard_id + 1
    embed.set_footer(
      text=f"Requested By {ctx.author} • Shard {shard_display_id}/{shard_count}",
      icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )
    await ctx.reply(embed=embed, mention_author=True)

  @commands.command(name="invite",
                           aliases=['scyro'],
                           description="Get Support & Bot invite link!")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def invite(self, ctx: commands.Context):
    # Get shard info
    if hasattr(ctx.bot, 'shard_id') and ctx.bot.shard_id is not None:
        shard_id = ctx.bot.shard_id
    else:
        shard_id = getattr(ctx.bot, '_shard_id', 0)
    
    if hasattr(ctx.bot, 'shard_count') and ctx.bot.shard_count is not None:
        shard_count = ctx.bot.shard_count
    else:
        shard_count = getattr(ctx.bot, '_shard_count', 1)
    
    shard_id = shard_id if shard_id is not None else 0
    shard_count = shard_count if shard_count is not None else 1
    
    embed = discord.Embed(title="  Scyro Invite & Support!",
      description=
      f"> <a:dot:1396429135588626442> **[Invite Scyro](https://discord.com/oauth2/authorize?client_id=1387046835322880050&scope=bot%20applications.commands&permissions=30030655231&redirect_uri=https%3A%2F%2Fdsc.gg%2Fscyrogg)** <a:dot:1396429135588626442> **[Get Support](https://dsc.gg/scyrogg)**\n> <a:dot:1396429135588626442> **Scyro** — your all-in-one Discord companion. Secure, manage, and grow your server with ease.",
      color=0x9D00FF)

    embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/1387046835322880050/1f8316ab90e1fa59fb8d8c05c2cf0f29.png?size=1024")
    embed.set_image(url="https://cdn.discordapp.com/banners/1387046835322880050/3b93e8d25e7973342d8bc49ef893c4b8.png?size=512")
    
    shard_display_id = shard_id + 1
    embed.set_footer(text=f"Requested by {ctx.author.name} • Shard {shard_display_id}/{shard_count}",
                     icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    invite = Button(
      label='Invite',
      style=discord.ButtonStyle.link,
      url=
      'https://discord.com/oauth2/authorize?client_id=1387046835322880050&permissions=40110184181268398&integration_type=0&scope=applications.commands+bot&redirect_uri=https%3A%2F%2Fdsc.gg%2Fscyrogg&response_type=code'
    )
    support = Button(label='Support',
                    style=discord.ButtonStyle.link,
                    url=f'https://dsc.gg/scyrogg')
    vote = Button(label='Website',
                      style=discord.ButtonStyle.link,
                      url='https://scyro.xyz')
    view = View()
    view.add_item(invite)
    view.add_item(support)
    view.add_item(vote)
    await ctx.send(embed=embed, view=view)

async def setup(bot):
  await bot.add_cog(General(bot))
























