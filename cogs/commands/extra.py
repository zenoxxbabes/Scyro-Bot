import os 
import discord
from discord.ext import commands
import datetime
import sys
from discord.ui import Button, View
import psutil
import time
from utils.Tools import *
from discord.ext import commands
from discord.ext.commands import BucketType, cooldown
import requests
from typing import *
from utils import *
from utils.config import BotName, serverLink
from utils import Paginator, DescriptionEmbedPaginator, FieldPagePaginator, TextPaginator
from core import Cog, Scyro, Context
from typing import Optional
 
import asyncio
import aiohttp

start_time = time.time()

def datetime_to_seconds(thing: datetime.datetime):
  current_time = datetime.datetime.fromtimestamp(time.time())
  return round(
    round(time.time()) +
    (current_time - thing.replace(tzinfo=None)).total_seconds())

tick = "<:yes:1396838746862784582>"
cross = "<:no:1396838761605890090>"

class RoleInfoView(View):
  def __init__(self, role: discord.Role, author_id):
    super().__init__(timeout=180)
    self.role = role
    self.author_id = author_id

  @discord.ui.button(label='View Permissions', emoji="<:admin:1396429010585780295>", style=discord.ButtonStyle.secondary)
  async def show_permissions(self, interaction: discord.Interaction, button: Button):
    if interaction.user.id != self.author_id:
          await interaction.response.send_message("This interaction belongs to someone else.", ephemeral=True)
          return

    permissions = [perm.replace("_", " ").title() for perm, value in self.role.permissions if value]
    permission_text = ", ".join(permissions) if permissions else "No special permissions"
    
    embed = discord.Embed(
        title=f"<:admin:1396429010585780295> Role Permissions",
        description=f"**{self.role.name}**",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="__Permissions:__", 
        value=permission_text[:1000], 
        inline=False
    )
    embed.set_footer(text=f"Role ID: {self.role.id}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

class OverwritesView(View):
  def __init__(self, channel, author_id):
      super().__init__(timeout=180)
      self.channel = channel
      self.author_id = author_id

  @discord.ui.button(label='View Overwrites', emoji="<:gear:1409149841082155078>", style=discord.ButtonStyle.secondary)
  async def show_overwrites(self, interaction: discord.Interaction, button: Button):
      if interaction.user.id != self.author_id:
          await interaction.response.send_message("This interaction belongs to someone else.", ephemeral=True)
          return

      overwrites = []
      for target, perms in self.channel.overwrites.items():
          permissions = {
              "View Channel": perms.view_channel,
              "Send Messages": perms.send_messages,
              "Read History": perms.read_message_history,
              "Manage Messages": perms.manage_messages,
              "Embed Links": perms.embed_links,
              "Attach Files": perms.attach_files,
              "Manage Channel": perms.manage_channels,
              "Administrator": perms.administrator
          }

          overwrites.append(f"**{target.name}**\n" +
                            "\n".join(f"  {perm}: {'🟢' if value else '🔴' if value is False else '⚫'}" for perm, value in permissions.items()))

      embed = discord.Embed(
          title="<:gear:1409149841082155078> Channel Overwrites",
          description=f"**#{self.channel.name}**",
          color=0x2b2d31,
          timestamp=discord.utils.utcnow()
      )
      embed.add_field(
          name="Permission Overwrites", 
          value="\n\n".join(overwrites)[:1000] if overwrites else "No custom overwrites", 
          inline=False
      )
      embed.set_footer(text="🟢 = Allowed • 🔴 = Denied • ⚫ = Default")
      
      await interaction.response.send_message(embed=embed, ephemeral=True)

class VoteView(View):
  def __init__(self):
      super().__init__(timeout=None)
      self.add_item(discord.ui.Button(label="Vote", emoji="🔗", style=discord.ButtonStyle.link, url="https://top.gg/bot/1387046835322880050/vote"))

class UserInfoView(View):
  def __init__(self, member: Union[discord.Member, discord.User], author_id: int):
      super().__init__(timeout=180)
      self.member = member
      self.author_id = author_id

  @discord.ui.button(label='User Avatar', emoji="👤", style=discord.ButtonStyle.secondary)
  async def show_avatar(self, interaction: discord.Interaction, button: Button):
      if interaction.user.id != self.author_id:
          await interaction.response.send_message("This interaction belongs to someone else.", ephemeral=True)
          return

      embed = discord.Embed(
          title=f"{self.member.display_name}'s Avatar",
          color=0x2b2d31,
          timestamp=discord.utils.utcnow()
      )
      embed.set_image(url=self.member.display_avatar.url)
      embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
      
      await interaction.response.send_message(embed=embed, ephemeral=True)

  @discord.ui.button(label='User Banner', emoji="🖼️", style=discord.ButtonStyle.secondary)
  async def show_banner(self, interaction: discord.Interaction, button: Button):
      if interaction.user.id != self.author_id:
          await interaction.response.send_message("This interaction belongs to someone else.", ephemeral=True)
          return

      try:
          user_with_banner = await interaction.client.fetch_user(self.member.id)
          if not user_with_banner.banner:
              await interaction.response.send_message("This user doesn't have a banner set.", ephemeral=True)
              return

          embed = discord.Embed(
              title=f"{self.member.display_name}'s Banner",
              color=0x2b2d31,
              timestamp=discord.utils.utcnow()
          )
          embed.set_image(url=user_with_banner.banner.url)
          embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
          
          await interaction.response.send_message(embed=embed, ephemeral=True)
      except Exception as e:
          await interaction.response.send_message("Unable to fetch user banner.", ephemeral=True)

class ServerInfoView(View):
  def __init__(self, guild: discord.Guild, author_id: int):
      super().__init__(timeout=180)
      self.guild = guild
      self.author_id = author_id

  @discord.ui.button(label='Server Icon', emoji="📸", style=discord.ButtonStyle.grey)
  async def show_icon(self, interaction: discord.Interaction, button: Button):
      if interaction.user.id != self.author_id:
          await interaction.response.send_message("This interaction belongs to someone else.", ephemeral=True)
          return

      if not self.guild.icon:
          await interaction.response.send_message("This server doesn't have an icon set.", ephemeral=True)
          return

      embed = discord.Embed(
          title=f"{self.guild.name}'s Icon",
          color=0x2b2d31,
          timestamp=discord.utils.utcnow()
      )
      embed.set_image(url=self.guild.icon.url)
      embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
      
      await interaction.response.send_message(embed=embed, ephemeral=True)

  @discord.ui.button(label='Server Banner', emoji="🖼️", style=discord.ButtonStyle.grey)
  async def show_banner(self, interaction: discord.Interaction, button: Button):
      if interaction.user.id != self.author_id:
          await interaction.response.send_message("This interaction belongs to someone else.", ephemeral=True)
          return

      if not self.guild.banner:
          await interaction.response.send_message("This server doesn't have a banner set.", ephemeral=True)
          return

      embed = discord.Embed(
          title=f"{self.guild.name}'s Banner",
          color=0x2b2d31,
          timestamp=discord.utils.utcnow()
      )
      embed.set_image(url=self.guild.banner.url)
      embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
      
      await interaction.response.send_message(embed=embed, ephemeral=True)

class Extra(commands.Cog):

  def __init__(self, bot):
    self.bot = bot
    self.color = 0x2b2d31  # Discord Blurple
    self.start_time = datetime.datetime.now()

  @commands.hybrid_group(name="banner", invoke_without_command=True)
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def banner(self, ctx):
    """View server and user banners"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if ctx.invoked_subcommand is None:
        embed = discord.Embed(
          title="<:925041humble:1413372860289777694> Banner Commands",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.add_field(
          name="Available Commands:",
          value="`banner server` - View server banner\n`banner user [user]` - View user banner",
          inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in banner command: {e}")
      await ctx.send("An error occurred while processing the banner command.", ephemeral=True)

  @banner.command(name="server")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  async def server_banner(self, ctx):
    """Display the server's banner"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if not ctx.guild.banner:
        embed = discord.Embed(
          title="<:925041humble:1413372860289777694> Server Banner",
          description=f"**{ctx.guild.name}** doesn't have a banner set",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
      else:
        formats = []
        formats.append(f"[PNG]({ctx.guild.banner.replace(format='png')})")
        formats.append(f"[JPG]({ctx.guild.banner.replace(format='jpg')})")
        formats.append(f"[WEBP]({ctx.guild.banner.replace(format='webp')})")
        if ctx.guild.banner.is_animated():
          formats.append(f"[GIF]({ctx.guild.banner.replace(format='gif')})")
        
        embed = discord.Embed(
          title=" Server Banner",
          description=f"**{ctx.guild.name}**",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.add_field(
          name="Download Formats:", 
          value=" • ".join(formats), 
          inline=False
        )
        embed.set_image(url=ctx.guild.banner)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in server banner command: {e}")
      await ctx.send("An error occurred while fetching the server banner.", ephemeral=True)

  @banner.command(name="user")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  async def user_banner(self, ctx, member: Optional[Union[discord.Member, discord.User]] = None):
    """Display a user's banner"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if member is None:
        member = ctx.author
      
      bannerUser = await self.bot.fetch_user(member.id)
      if not bannerUser.banner:
        embed = discord.Embed(
          title="<:925041humble:1413372860289777694> User Banner",
          description=f"**{member.display_name}** doesn't have a banner set",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
      else:
        formats = []
        formats.append(f"[PNG]({bannerUser.banner.replace(format='png')})")
        formats.append(f"[JPG]({bannerUser.banner.replace(format='jpg')})")
        formats.append(f"[WEBP]({bannerUser.banner.replace(format='webp')})")
        if bannerUser.banner.is_animated():
          formats.append(f"[GIF]({bannerUser.banner.replace(format='gif')})")
        
        embed = discord.Embed(
          title="<:925041humble:1413372860289777694> User Banner",
          description=f"**{member.display_name}**",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.add_field(
          name="Download Formats", 
          value=" • ".join(formats), 
          inline=False
        )
        embed.set_image(url=bannerUser.banner)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in user banner command: {e}")
      await ctx.send("An error occurred while fetching the user banner.", ephemeral=True)

  @commands.hybrid_command(name='roleinfo', aliases=["ri"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def roleinfo(self, ctx, role: discord.Role):
    """Get detailed information about a role"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      embed = discord.Embed(
        title=f"<:7696newspaper2:1412039654516985956> {role.name}",
        color=role.color if role.color != discord.Color.default() else self.color,
        timestamp=discord.utils.utcnow()
      )
      
      # General Information
      total_roles = len(ctx.guild.roles) - 1
      role_position = total_roles - role.position
      
      embed.add_field(
        name="**__General Information:__**",
        value=f" **ID:** `{role.id}`\n **Members:** {len(role.members)}\n **Position:** {role_position}/{total_roles}\n **Color:** {str(role.color)}",
        inline=False
      )
      
      # Role Properties
      embed.add_field(
        name="**__Role Properties:__**",
        value=f"**Mentionable:** {tick if role.mentionable else cross}\n **Hoisted:** {tick if role.hoist else cross}\n> **Managed:** {tick if role.managed else cross}\n **Integration:** {tick if role.managed else cross}",
        inline=False
      )
      
      # Creation Date
      embed.add_field(
        name="**__Creation Date:__**",
        value=f" **Created:** <t:{int(role.created_at.timestamp())}:F>\n **Created:** <t:{int(role.created_at.timestamp())}:R>",
        inline=False
      )
      
      embed.set_footer(text=f"Role ID: {role.id}")

      view = RoleInfoView(role, ctx.author.id)
      await ctx.send(embed=embed, view=view)
    except Exception as e:
      print(f"Error in roleinfo command: {e}")
      await ctx.send("An error occurred while fetching role information.", ephemeral=True)

  @commands.hybrid_command(name="channelinfo", aliases=['cinfo', 'ci'])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def channelinfo(self, ctx, channel: discord.TextChannel = None):
    """Get detailed information about a text channel"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if channel is None:
        channel = ctx.channel
        
      embed = discord.Embed(
        title=f"<:46419discordchannelfromvega:1409183750557929634> #{channel.name}",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      # General Information
      embed.add_field(
        name="**__General Information:__**",
        value=f" **ID:** `{channel.id}`\n **Category:** {channel.category.name if channel.category else 'None'}\n **Position:** #{channel.position}\n **NSFW:** {tick if channel.is_nsfw() else cross}",
        inline=False
      )
      
      # Channel Settings
      embed.add_field(
        name="**__Channel Settings:__**",
        value=f" **Slowmode:** {channel.slowmode_delay}s\n**Type:** Text Channel\n **Overwrites:** {len(channel.overwrites)}\n **Created:** <t:{int(channel.created_at.timestamp())}:R>",
        inline=False
      )
      
      # Channel Topic
      if channel.topic:
        topic = channel.topic[:100] + "..." if len(channel.topic) > 100 else channel.topic
        embed.add_field(
          name="**__Channel Topic:__**",
          value=f" {topic}",
          inline=False
        )
      
      embed.set_footer(text=f"Channel ID: {channel.id}")
      
      view = OverwritesView(channel, ctx.author.id)
      await ctx.send(embed=embed, view=view)
    except Exception as e:
      print(f"Error in channelinfo command: {e}")
      await ctx.send("An error occurred while fetching channel information.", ephemeral=True)

  @commands.hybrid_command(name="vcinfo")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def vcinfo(self, ctx, channel: discord.VoiceChannel = None):
    """Get detailed information about a voice channel"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if channel is None:
        embed = discord.Embed(
          title="<:56055colorizedvoicelocked:1413387482254278697> Voice Channel Information",
          description="Please specify a valid voice channel",
          color=0x9b59b6,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
        return
        
      embed = discord.Embed(
        title=f"<:56055colorizedvoicelocked:1413387482254278697> {channel.name}",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      # General Information
      embed.add_field(
        name="General Information",
        value=f" **ID:** `{channel.id}`\n **Category:** {channel.category.name if channel.category else 'None'}\n **Region:** {channel.rtc_region or 'Automatic'}\n **Members:** {len(channel.members)}",
        inline=False
      )
      
      # Channel Settings
      embed.add_field(
        name="**__Channel Settings:__**",
        value=f" **User Limit:** {channel.user_limit or 'Unlimited'}\n **Bitrate:** {channel.bitrate//1000} kbps\n **Created:** <t:{int(channel.created_at.timestamp())}:R>",
        inline=False
      )

      embed.set_footer(text=f"Channel ID: {channel.id}")
      await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in vcinfo command: {e}")
      await ctx.send("An error occurred while fetching voice channel information.", ephemeral=True)

  @commands.command(name="permissions", aliases=["perms"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def keyperms(self, ctx, member: discord.Member = None):
    """Check key permissions for a user"""
    try:
      if member is None:
        member = ctx.author
        
      # Key permissions to check
      key_permissions = []
      perms = member.guild_permissions

      if perms.administrator:
        key_permissions.append("Administrator")
      if perms.manage_guild:
        key_permissions.append("Manage Server")
      if perms.manage_roles:
        key_permissions.append("Manage Roles")
      if perms.manage_channels:
        key_permissions.append("Manage Channels")
      if perms.kick_members:
        key_permissions.append("Kick Members")
      if perms.ban_members:
        key_permissions.append("Ban Members")
      if perms.moderate_members:
        key_permissions.append("Moderate Members")
      if perms.manage_messages:
        key_permissions.append("Manage Messages")
      if perms.manage_webhooks:
        key_permissions.append("Manage Webhooks")
      if perms.mention_everyone:
        key_permissions.append("Mention Everyone")

      embed = discord.Embed(
        title=f"<a:candle:1396477060469362688> {member.display_name}",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      # User Information
      embed.add_field(
        name="**__User Information__**",
        value=f" **ID:** `{member.id}`\n **Top Role:** {member.top_role.mention}",
        inline=False
      )
      
      # Key Permissions
      perms_text = ", ".join(key_permissions) if key_permissions else "No special permissions"
      embed.add_field(
        name="**__Key Permissions:__**",
        value=f" {perms_text}",
        inline=False
      )

      embed.set_footer(text=f"User ID: {member.id}")
      await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in permissions command: {e}")
      await ctx.send("An error occurred while checking permissions.")

  @commands.hybrid_command(name="report", aliases=["bug"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 30, commands.BucketType.channel)
  async def report(self, ctx, *, bug):
    """Report a bug or issue to the developers"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      channel = self.bot.get_channel(1431938058600579154)
      
      if not channel:
        embed = discord.Embed(
          title="<a:alert:1396429026842644584> Report Error",
          description="Bug reporting channel not found. Please contact the developers directly.",
          color=0x9b59b6,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
        return
      
      # Report embed for developers
      embed = discord.Embed(
        title="<:yes:1396838746862784582> Bug Report Received",
        color=0x9b59b6,
        timestamp=discord.utils.utcnow()
      )
      embed.add_field(
        name="**__Bug Description:__**",
        value=f" {bug[:1000]}",
        inline=False
      )
      embed.add_field(name="Reporter", value=f"> {ctx.author}\n> `{ctx.author.id}`", inline=True)
      embed.add_field(name="Server", value=f"> {ctx.guild.name}\n> `{ctx.guild.id}`", inline=True)
      embed.add_field(name="Channel", value=f"> #{ctx.channel.name}\n> `{ctx.channel.id}`", inline=True)
      embed.set_footer(text="Bug Report System")
      
      await channel.send(embed=embed)
      
      # Confirmation embed for user
      confirm_embed = discord.Embed(
        title="<:yes:1396838746862784582> Bug Report Submitted",
        description="Your bug report has been successfully submitted to our development team",
        color=0x24292f,
        timestamp=discord.utils.utcnow()
      )
      confirm_embed.add_field(
        name="**What happens next?**",
        value=" • Our team will review your report\n> • You may be contacted for details\n> • Check our support server for updates",
        inline=False
      )
      confirm_embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
      await ctx.send(embed=confirm_embed)
      
    except Exception as e:
      error_embed = discord.Embed(
        title="<:no:1396838761605890090> Report Failed",
        description="Failed to submit bug report. Please try again later.",
        color=0x9b59b6,
        timestamp=discord.utils.utcnow()
      )
      error_embed.set_footer(text=f"Error: {str(e)[:100]}")
      await ctx.send(embed=error_embed)

  @commands.hybrid_command(name="ping", aliases=['latency'])
  @ignore_check()
  @blacklist_check()
  @commands.cooldown(1, 2, commands.BucketType.user)
  async def ping(self, ctx):
    """PONG! Provide bot latency"""
    try:
      if ctx.interaction:
        await ctx.defer()
      
      # Bot Ping (WebSocket latency)
      bot_ping = int(self.bot.latency * 1000)
      
      # API Ping (response time)
      api_start = time.perf_counter()
      if ctx.interaction:
        msg = await ctx.interaction.followup.send("<a:loadingbro:1456977689922769080> Measuring ping...", wait=True)
      else:
        msg = await ctx.reply("<a:loadingbro:1456977689922769080> Measuring ping...")
      api_end = time.perf_counter()
      api_ping = round((api_end - api_start) * 1000, 2)
      
      # Database Ping
      db_start = time.perf_counter()
      try:
        # Use existing MongoDB connection from bot
        if hasattr(self.bot, 'db') and self.bot.db is not None:
             await self.bot.db.command("ping")
             db_end = time.perf_counter()
             db_ping = round((db_end - db_start) * 1000, 2)
        else:
             db_ping = "Offline"
      except Exception:
        db_ping = "N/A"
      
      # Determine ping quality emojis
      def get_ping_emoji(ping_value):
        if isinstance(ping_value, str):  # For "N/A" values
          return "<:830682wifilovered:1413389782834348082>"  # High ping emoji
        elif ping_value < 100:
          return "<:243110wifilovegreen:1413389760076189736>"  # Good ping emoji
        elif ping_value <= 200:
          return "<:566013wifiloveyellow:1413389770905747496>"  # Mid ping emoji
        else:
          return "<:830682wifilovered:1413389782834348082>"  # High ping emoji
      
      bot_emoji = get_ping_emoji(bot_ping)
      api_emoji = get_ping_emoji(api_ping)
      db_emoji = get_ping_emoji(db_ping)
      
      # Create embed
      embed = discord.Embed(
        title="🏓 Pong!",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      embed.add_field(
        name="**__Latency Metrics:__**",
        value=f"{bot_emoji} **Bot Ping:** `{bot_ping}ms`\n{db_emoji} **DB Ping:** `{db_ping}ms`",
        inline=False
      )
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
      
      # Edit the message with the embed
      if ctx.interaction:
        await msg.edit(content=None, embed=embed)
      else:
        await msg.edit(content=None, embed=embed)
    except Exception as e:
      print(f"Error in ping command: {e}")
      await ctx.send("An error occurred while checking latency.", ephemeral=True)

  @commands.hybrid_command(name="uptime")
  @blacklist_check() 
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def uptime(self, ctx):
    """Check how long the bot has been running"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      uptime_seconds = int(round(time.time() - start_time))
      uptime_timedelta = datetime.timedelta(seconds=uptime_seconds)

      embed = discord.Embed(
        title="<a:7596clock:1413390466979991572> Scyro's Uptime",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      # Current Uptime
      embed.add_field(
        name="Last Rebooted:",
        value=f"<a:loadinggg:1444652687332343919> **{uptime_timedelta.days}** days, **{uptime_timedelta.seconds // 3600}** hours, **{(uptime_timedelta.seconds // 60) % 60}** minutes ago ",
        inline=False
      )
      
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
      await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in uptime command: {e}")
      await ctx.send("An error occurred while fetching uptime information.", ephemeral=True)

  @commands.hybrid_command(name="botinfo", aliases=["info", "bi"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def botinfo(self, ctx):
    """Get detailed information about Scyro bot"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      # Statistics
      uptime_seconds = int(round(time.time() - start_time))
      uptime_timedelta = datetime.timedelta(seconds=uptime_seconds)
      uptime_str = f"{uptime_timedelta.days}d {uptime_timedelta.seconds // 3600}h {(uptime_timedelta.seconds // 60) % 60}m"
      
      total_guilds = len(self.bot.guilds)
      # Fix: Convert generator to list before getting length
      total_users = len([user for user in self.bot.get_all_members()])
      total_channels = len([channel for channel in self.bot.get_all_channels()])
      
      embed = discord.Embed(
        title="  Scyro Information",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      embed.set_thumbnail(url=self.bot.user.display_avatar.url)
      
      # Basic Information
      embed.add_field(
        name="Details",
        value=(
          "```"
          "Bot Tag:  Scyro™#6420\n"
          f"ID: {self.bot.user.id}\n"
          "Created: 24 June 2025\n"
          "```"
        ),
        inline=False
      )

      # Development
      embed.add_field(
        name="Development",
        value=(
          "```"
          "Creator:  zenoxxfromhell\n"
          f"Version: v4.3.1\n"
          "Language: Python 3.11\n"
          "```"
        ),
        inline=False
      )

      # Network
      embed.add_field(
        name="Network",
        value=(
          "```"
          f"Servers: {total_guilds:,}\n"
          f"Users: {total_users:,}\n"
          f"Channels: {total_channels:,}\n"
          "```"
        ),
        inline=False
      )

      # Metrics
      embed.add_field(
        name="Metrics",
        value=(
          "```"
          f"Latency: {int(self.bot.latency * 1000)}ms\n"
          f"Uptime: {uptime_str}\n"
          f"Status: 🟢 Online\n"
          "```"
        ),
        inline=False
      )
      
      embed.set_footer(text=f"Serving {total_guilds:,} communities worldwide", icon_url=self.bot.user.display_avatar.url)

      # Action buttons
      view = discord.ui.View(timeout=300)
      
      buttons = [
        ("Invite Bot", "https://discord.com/oauth2/authorize?client_id=1387046835322880050&permissions=40110184181268398&scope=applications.commands+bot&redirect_uri=https%3A%2F%2Fdsc.gg%2Fscyrogg&response_type=code", discord.ButtonStyle.link),
        ("Support", "https://dsc.gg/scyrogg", discord.ButtonStyle.link),
        ("Website", "https://scyro.xyz", discord.ButtonStyle.link),
      ]
      
      for label, url, style in buttons:
        button = discord.ui.Button(label=label, url=url, style=style)
        view.add_item(button)

      await ctx.send(embed=embed, view=view)
    except Exception as e:
      print(f"Error in botinfo command: {e}")
      await ctx.send("An error occurred while fetching bot information.", ephemeral=True)

  @commands.hybrid_command(name="serverinfo", aliases=["sinfo", "si"])
  @blacklist_check() 
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def serverinfo(self, ctx):
    """Get detailed information about the current server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      guild = ctx.guild
      
      embed = discord.Embed(
        title=f"__**{guild.name}'s Information**__",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
      
      # About Section
      owner_name = f"{guild.owner} ({guild.owner.mention})" if guild.owner else "Unknown"
      embed.add_field(
        name="**__About:__**",
        value=f"**Name:** {guild.name}\n**ID:** {guild.id}\n**Owner:** {owner_name}\n**Created At:** <t:{int(guild.created_at.timestamp())}:F>\n**Members:** {len(guild.members)}\n**Channels:** {len(guild.channels)}\n**Roles:** {len(guild.roles)}\n**Description:** {guild.description or 'No description available'}",
        inline=False
      )
      
      # Extra Section
      embed.add_field(
        name="**__Extra:__**",
        value=f"**Default Notifications:** {guild.default_notifications.name.title()}\n**Explicit Media Content Filter:** {guild.explicit_content_filter.name.title()}\n**Upload Limit:** {round(guild.filesize_limit / 1024 / 1024)} MB\n**Inactive Timeout:** {guild.afk_timeout // 60} minutes\n**2FA Requirements:** {'True' if guild.mfa_level else 'False'}",
        inline=False
      )

      embed.set_footer(text=f"Server ID: {guild.id}")
      
      # Add buttons view
      view = ServerInfoView(guild, ctx.author.id)
      
      if guild.banner:
        embed.set_image(url=guild.banner.url)

      await ctx.send(embed=embed, view=view)
    except Exception as e:
      print(f"Error in serverinfo command: {e}")
      await ctx.send("An error occurred while fetching server information.", ephemeral=True)
        
  @commands.hybrid_command(name="userinfo", aliases=["whois", "ui"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  async def _userinfo(self, ctx, member: Optional[Union[discord.Member, discord.User]] = None):
    """Get detailed information about a user"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if member is None:
        member = ctx.author
      
      # Try to get member object if user provided
      if isinstance(member, discord.User):
        try:
          member = await ctx.guild.fetch_member(member.id)
        except discord.NotFound:
          pass
      
      embed = discord.Embed(
        title=f"__**{member.display_name if hasattr(member, 'display_name') else member.name}'s Info**__",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      embed.set_thumbnail(url=member.display_avatar.url)
      
      # User Details
      embed.add_field(
        name="**__User Details:__**",
        value=f"**Username:** `{member.name}`\n**ID:** `{member.id}`\n**Bot Account:** {tick if member.bot else cross}\n**System User:** {tick if getattr(member, 'system', False) else cross}",
        inline=False
      )
      
      # Account Creation
      embed.add_field(
        name="**__Account Created:__**",
        value=f"<t:{int(member.created_at.timestamp())}:F>\n<t:{int(member.created_at.timestamp())}:R>",
        inline=False
      )
      
      # Server-specific information (if member is in guild)
      if hasattr(member, 'joined_at') and member.joined_at:
        embed.add_field(
          name="**__Server Joined:__**",
          value=f"<t:{int(member.joined_at.timestamp())}:F>\n<t:{int(member.joined_at.timestamp())}:R>",
          inline=False
        )
        
        # Join position
        join_position = len([m for m in ctx.guild.members if m.joined_at and m.joined_at <= member.joined_at])
        embed.add_field(
          name="**__Join Position:__**",
          value=f"#{join_position:,} out of {len(ctx.guild.members):,} members",
          inline=False
        )
      
      # Status
      if hasattr(member, 'status'):
        status_map = {
          discord.Status.online: "<:online:1409167017407152138>",
          discord.Status.idle: "<:idle:1409166997383811122>", 
          discord.Status.dnd: "<:dnd:1409166987807948800>",
          discord.Status.offline: "<:offline:1409167008829935698>"
        }
        embed.add_field(
          name="**__Status:__**",
          value=status_map.get(member.status, 'Unknown'),
          inline=False
        )
      
      # Top role
      if hasattr(member, 'top_role'):
        embed.add_field(
          name="**__Highest Role:__**",
          value=member.top_role.mention,
          inline=False
        )
      
      # User badges
      if member.public_flags:
        badges = []
        flag_names = {
          'staff': '<:39520discordstaff:1412061536083644506>',
          'partner': '<:49532partner:1409180501633142956>',
          'hypesquad': '<:20100hypersquadevents:1412062585787781171>',
          'bug_hunter': '<:14433bughunter:1409180480116625481>',
          'hypesquad_bravery': '<:7878iconhypesquadbravery:1409180443923976212>',
          'hypesquad_brilliance': '<:60978hypersquadbrilliance:1409180585997500498>', 
          'hypesquad_balance': '<:58534hypersquadbalanceking:1409180556054495273>',
          'early_supporter': '<:518379earlysupporterbadge:1409180652859035708>',
          'verified_bot_developer': '<:4228_discord_bot_dev:1412062216525713418>',
          'active_developer': '<:63557discordactivedeveloper:1409180602581909667>'
        }
        
        for flag_name, flag_value in member.public_flags:
          if flag_value and flag_name in flag_names:
            badges.append(flag_names[flag_name])
        
        if badges:
          embed.add_field(
            name="**__Badges:__**",
            value="\n".join([f"• {badge}" for badge in badges[:5]]),
            inline=False
          )
      
      # Premium info
      if hasattr(member, 'premium_since') and member.premium_since:
        embed.add_field(
          name="**__Server Booster:__**",
          value=f"Since <t:{int(member.premium_since.timestamp())}:R>",
          inline=False
        )

      embed.set_footer(text=f"User ID: {member.id}")
      
      # Try to get banner
      try:
        user_with_banner = await self.bot.fetch_user(member.id)
        if user_with_banner.banner:
          embed.set_image(url=user_with_banner.banner.url)
      except:
        pass
      
      # Add buttons view
      view = UserInfoView(member, ctx.author.id)
      
      await ctx.send(embed=embed, view=view)
    except Exception as e:
      print(f"Error in userinfo command: {e}")
      await ctx.send("An error occurred while fetching user information.", ephemeral=True)

  @commands.command(name="boostcount", aliases=["bc"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def boosts(self, ctx):
    """Check the server's boost status and statistics"""
    try:
      boosts = ctx.guild.premium_subscription_count
      level = ctx.guild.premium_tier
      
      embed = discord.Embed(
        title=f"<:nitroboost:1420349391352627230> {ctx.guild.name}",
        color=0x9B59B6,
        timestamp=discord.utils.utcnow()
      )
      
      # Current Statistics
      embed.add_field(
        name="**__Current Statistics__**",
        value=f" **Boost Level:** `{level}`\n> **Total Boosts:** `{boosts}`\n> **Active Boosters:** `{len(ctx.guild.premium_subscribers)}`",
        inline=False
      )
      
      # Next level requirements
      next_level_reqs = {0: 2, 1: 7, 2: 14}
      if level < 3:
        needed = next_level_reqs[level] - boosts
        embed.add_field(
          name="**__Next Level Progress__**",
          value=f" **Level `{level + 1}`:** `{needed}` more needed\n> **Progress:** `{boosts}/{next_level_reqs[level]}`",
          inline=False
        )
      else:
        embed.add_field(
          name="**__Max Level Achieved__**",
          value="**This server has reached the maximum boost level!**",
          inline=False
        )
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
      await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in boostcount command: {e}")

  @commands.hybrid_group(name="list", invoke_without_command=True)
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def __list_(self, ctx: commands.Context):
    """List various server information like roles, members, etc."""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if ctx.subcommand_passed is None:
        await ctx.send_help(ctx.command)
        ctx.command.reset_cooldown(ctx)
    except Exception as e:
      print(f"Error in list command: {e}")

  @__list_.command(name="bans", aliases=["ban"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.has_permissions(view_audit_log=True)
  @commands.bot_has_permissions(view_audit_log=True)
  async def list_ban(self, ctx):
    """List all banned users in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      bans = []
      async for ban_entry in ctx.guild.bans():
        bans.append(ban_entry.user)
        
      if len(bans) == 0:
        embed = discord.Embed(
          title="<:banhammer:1409414586704199840> Banned Users",
          description=f"> **{ctx.guild.name}** has no banned users",
          color=0x9b59b6,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
      else:
        entries = [f"`{no:02d}` {mem}" for no, mem in enumerate(bans, start=1)]
        embeds = DescriptionEmbedPaginator(
          entries=entries,
          title=f"<:banhammer:1409414586704199840> Banned Users • {len(bans)}",
          description=f"> **{ctx.guild.name}**",
          per_page=10).get_pages()
        paginator = Paginator(ctx, embeds)
        await paginator.paginate()
    except Exception as e:
      print(f"Error in list bans command: {e}")
      await ctx.send("An error occurred while fetching banned users list.", ephemeral=True)

  @__list_.command(name="inrole", aliases=["inside-role"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_inrole(self, ctx, role: discord.Role):
    """List all members who have a specific role"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if not role.members:
        embed = discord.Embed(
          title="<:7696newspaper2:1412039654516985956> Members in Role",
          description=f"**{role.name}** has no members.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      entries = [
        f"`{no:02d}` {mem} • <t:{int(mem.created_at.timestamp())}:D>"
        for no, mem in enumerate(role.members, start=1)
      ]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:7696newspaper2:1412039654516985956> Members in Role • {len(role.members)}",
        description=f"**{role.name}**",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list inrole command: {e}")
      await ctx.send("An error occurred while fetching role members list.", ephemeral=True)

  @__list_.command(name="emojis", aliases=["emoji"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_emojis(self, ctx):
    """List all custom emojis in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if not ctx.guild.emojis:
        embed = discord.Embed(
          title="<:gear:1409149841082155078> Server Emojis",
          description=f"**{ctx.guild.name}** has no custom emojis.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      entries = [f"`{no:02d}` {e} `{e}`" for no, e in enumerate(ctx.guild.emojis, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:gear:1409149841082155078> Server Emojis • {len(ctx.guild.emojis)}",
        description=f"**{ctx.guild.name}**",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list emojis command: {e}")
      await ctx.send("An error occurred while fetching emojis list.", ephemeral=True)

  @__list_.command(name="roles", aliases=["role"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  async def list_roles(self, ctx):
    """List all roles in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      entries = [f"`{no:02d}` {e.mention} `{e.id}`" for no, e in enumerate(ctx.guild.roles, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:7696newspaper2:1412039654516985956> Server Roles • {len(ctx.guild.roles)}",
        description=f"**{ctx.guild.name}**\n\n> Use the navigation buttons below to browse through the role list.",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list roles command: {e}")
      await ctx.send("An error occurred while fetching roles list.", ephemeral=True)

  @__list_.command(name="admins", aliases=["admin"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_admin(self, ctx):
    """List all administrators in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      mems = [mem for mem in ctx.guild.members if mem.guild_permissions.administrator]
      
      if not mems:
        embed = discord.Embed(
          title="<:49548donateadmin:1409180518058168440> Server Administrators",
          description=f"**{ctx.guild.name}** has no administrators.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      try:
        mems = sorted(mems, key=lambda mem: (
          mem.bot, 
          mem.joined_at if mem.joined_at is not None else datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        ))
      except Exception:
        mems = mems
        
      entries = [f"`{no:02d}` {mem} • <t:{int(mem.created_at.timestamp())}:D>" for no, mem in enumerate(mems, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:49548donateadmin:1409180518058168440> Server Administrators • `{len(mems)}`",
        description=f"**{ctx.guild.name}**",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list admins command: {e}")
      await ctx.send("An error occurred while fetching administrators list.", ephemeral=True)

  @__list_.command(name="invoice", aliases=["invc"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def listusers(self, ctx):
    """List all users currently in your voice channel"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if not ctx.author.voice:
        embed = discord.Embed(
          title="<:56055colorizedvoicelocked:1413387482254278697> Voice Channel Required",
          description="You must be connected to a voice channel to use this command",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      members = ctx.author.voice.channel.members
      if not members:
        embed = discord.Embed(
          title="<:56055colorizedvoicelocked:1413387482254278697> Voice Channel Members",
          description=f"**{ctx.author.voice.channel.name}** has no members.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed)
        
      entries = [f"`{n:02d}` {member}" for n, member in enumerate(members, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:56055colorizedvoicelocked:1413387482254278697> Voice Channel Members • `{len(members)}`",
        description=f"**{ctx.author.voice.channel.name}**").get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list invoice command: {e}")
      await ctx.send("An error occurred while fetching voice channel members list.", ephemeral=True)

  @__list_.command(name="moderators", aliases=["mods"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_mod(self, ctx):
    """List all moderators in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      mems = [mem for mem in ctx.guild.members if mem.guild_permissions.ban_members or mem.guild_permissions.kick_members]
      
      if not mems:
        embed = discord.Embed(
          title="<:89807yellowadmingradient:1409180629542633483> Server Moderators",
          description=f"**{ctx.guild.name}** has no moderators.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      try:
        mems = sorted(mems, key=lambda mem: mem.joined_at if mem.joined_at is not None else datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc))
      except Exception:
        mems = mems
        
      entries = [f"`{no:02d}` {mem} • <t:{int(mem.created_at.timestamp())}:D>" for no, mem in enumerate(mems, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:89807yellowadmingradient:1409180629542633483> Server Moderators • `{len(mems)}`",
        description=f"**{ctx.guild.name}**",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list moderators command: {e}")
      await ctx.send("An error occurred while fetching moderators list.", ephemeral=True)

  @__list_.command(name="early", aliases=["sup"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_early(self, ctx):
    """List all early supporters in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      mems = [memb for memb in ctx.guild.members if memb.public_flags.early_supporter]
      
      if not mems:
        embed = discord.Embed(
          title="<:518379earlysupporterbadge:1409180652859035708> Early Supporters",
          description=f"**{ctx.guild.name}** has no early supporters.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      mems = sorted(mems, key=lambda memb: memb.created_at)
      entries = [f"`{no:02d}` {mem} • <t:{int(mem.created_at.timestamp())}:D>" for no, mem in enumerate(mems, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:518379earlysupporterbadge:1409180652859035708> Early Supporters • `{len(mems)}`",
        description=f"**{ctx.guild.name}**",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list early command: {e}")
      await ctx.send("An error occurred while fetching early supporters list.", ephemeral=True)

  @__list_.group(name="join", invoke_without_command=True)
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_join(self, ctx: commands.Context):
    """List members sorted by server join date"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      if ctx.subcommand_passed is None:
        # Default behavior when no subcommand is specified
        await ctx.send_help(ctx.command)
        ctx.command.reset_cooldown(ctx)
    except Exception as e:
      print(f"Error in list join command: {e}")

  @list_join.command(name="date")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def list_join_date(self, ctx):
    """List members sorted by server join date"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      mems = [mem for mem in ctx.guild.members if mem.joined_at is not None]
      
      if not mems:
        embed = discord.Embed(
          title="<:totalmembers:1409167038408167444> Members by Join Date",
          description=f"**{ctx.guild.name}** has no members with join dates to display.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
        
      try:
        mems = sorted(mems, key=lambda memb: memb.joined_at)
      except Exception:
        mems = mems
        
      entries = [f"`{no:02d}` {mem} • <t:{int(mem.joined_at.timestamp())}:D>" for no, mem in enumerate(mems, start=1)]
      embeds = DescriptionEmbedPaginator(
        entries=entries,
        title=f"<:totalmembers:1409167038408167444> Members by Join Date • `{len(mems)}`",
        description=f"**{ctx.guild.name}**",
        per_page=10).get_pages()
      paginator = Paginator(ctx, embeds)
      await paginator.paginate()
    except Exception as e:
      print(f"Error in list join date command: {e}")
      await ctx.send("An error occurred while fetching join date list.", ephemeral=True)

  # NEW REDESIGNED COMMANDS

  @commands.hybrid_command(name="boosters", aliases=["serverboost"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def new_boosters(self, ctx):
    """Display enhanced server boosters information with statistics"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      guild = ctx.guild
      boosters = guild.premium_subscribers
      
      if not boosters:
        embed = discord.Embed(
          title="<:boost:1409163194336940163> Server Boosters",
          description=f"**{guild.name}** currently has no boosters",
          color=0x9B59B6,
          timestamp=discord.utils.utcnow()
        )
        embed.add_field(
          name="**__Boost Information__**",
          value=f" **Current Level:** `{guild.premium_tier}`\n> **Total Boosts:** `0`\n> **Boosters Needed:** `2` for Level 1",
          inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
      
      # Sort boosters by boost date
      try:
        sorted_boosters = sorted(boosters, key=lambda m: m.premium_since if m.premium_since else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
      except:
        sorted_boosters = boosters
      
      embed = discord.Embed(
        title=f"<:nitroboost:1420349391352627230> {ctx.guild.name}",
        color=0x9B59B6,
        timestamp=discord.utils.utcnow()
      )
      
      # Current Statistics
      embed.add_field(
        name="**__Current Statistics__**",
        value=f" **Boost Level:** `{level}`\n> **Total Boosts:** `{boosts}`\n> **Active Boosters:** `{len(ctx.guild.premium_subscribers)}`",
        inline=False
      )
      
      # Next level requirements
      next_level_reqs = {0: 2, 1: 7, 2: 14}
      if level < 3:
        needed = next_level_reqs[level] - boosts
        embed.add_field(
          name="**__Next Level Progress__**",
          value=f" **Level `{level + 1}`:** `{needed}` more needed\n> **Progress:** `{boosts}/{next_level_reqs[level]}`",
          inline=False
        )
      else:
        embed.add_field(
          name="**Max Level Achieved**",
          value=" This server has reached the maximum boost level!",
          inline=False
        )
      
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
      await ctx.send(embed=embed)
      
    except Exception as e:
      print(f"Error in new boosters command: {e}")
      await ctx.send("An error occurred while fetching boosters information.", ephemeral=True)

  @commands.hybrid_command(name="botlist", aliases=["serverbots"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def new_bots(self, ctx):
    """Display enhanced bot list with detailed statistics"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      guild = ctx.guild
      bots = [member for member in guild.members if member.bot]
      
      if not bots:
        embed = discord.Embed(
          title="<:bot:1409157600775372941> Server Bots",
          description=f"**{guild.name}** has no bots",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
      
      # Sort bots by join date
      try:
        sorted_bots = sorted(bots, key=lambda m: m.joined_at if m.joined_at else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
      except:
        sorted_bots = bots
      
      # Statistics
      online_bots = len([bot for bot in bots if bot.status != discord.Status.offline])
      verified_bots = len([bot for bot in bots if bot.public_flags.verified_bot])
      
      embed = discord.Embed(
        title=f"<:bot:1409157600775372941> Server Bots • {len(bots)}",
        description=f"**{guild.name}**",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      embed.add_field(
        name="**__Bot Statistics:__**",
        value=f" **Total Bots:** `{len(bots)}`\n> **Online:** `{online_bots}`\n> **Verified:** `{verified_bots}`\n> **Bot Ratio:** `{(len(bots)/len(guild.members)*100):.1f}%`",
        inline=True
      )
      
      embed.add_field(
        name="**__Server Stats:__**",
        value=f" **Total Members:** `{len(guild.members)}`\n> **Humans:** `{len(guild.members) - len(bots)}`\n> **Created:** <t:{int(guild.created_at.timestamp())}:R>",
        inline=True
      )
      
      # Recent bots (first 10)
      recent_bots = []
      for i, bot in enumerate(sorted_bots[:10], 1):
        status_emoji = {
          discord.Status.online: "<:online:1409167017407152138>",
          discord.Status.idle: "<:idle:1409166997383811122>",
          discord.Status.dnd: "<:dnd:1409166987807948800>",
          discord.Status.offline: "<:offline:1409167008829935698>"
        }.get(bot.status, "<:offline:1409167008829935698>")
        
        verified = "✓" if bot.public_flags.verified_bot else ""
        join_date = f"<t:{int(bot.joined_at.timestamp())}:R>" if bot.joined_at else "Unknown"
        recent_bots.append(f"`{i:02d}` {status_emoji} {bot.mention}{verified} • {join_date}")
      
      if recent_bots:
        embed.add_field(
          name="__Recent Bots:__",
          value="\n".join(recent_bots),
          inline=False
        )
      
      if len(bots) > 10:
        embed.add_field(
          name="**__Additional Info:__**",
          value=f" Use `/list bots` to see all {len(bots)} bots with pagination",
          inline=False
        )
      
      embed.set_footer(text=f"✓ = Verified Bot • Server ID: {guild.id}")
      await ctx.send(embed=embed)
      
    except Exception as e:
      print(f"Error in new bots command: {e}")
      await ctx.send("An error occurred while fetching bots information.", ephemeral=True)

  @commands.hybrid_command(name="developers", aliases=["activedevs"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def new_developers(self, ctx):
    """Display enhanced active developers list with additional info"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      guild = ctx.guild
      developers = [member for member in guild.members if member.public_flags.active_developer]
      
      if not developers:
        embed = discord.Embed(
          title="<:63557discordactivedeveloper:1409180602581909667> Active Developers",
          description=f"**{guild.name}** has no active developers",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.add_field(
          name="**__About Active Developer Badge:__**",
          value=" This badge is awarded to developers who have created and maintain active Discord applications",
          inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
      
      # Sort by join date
      try:
        sorted_devs = sorted(developers, key=lambda m: m.joined_at if m.joined_at else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
      except:
        sorted_devs = developers
      
      embed = discord.Embed(
        title=f"<:63557discordactivedeveloper:1409180602581909667> Active Developers • {len(developers)}",
        description=f"**{guild.name}**",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
      )
      
      # Statistics
      online_devs = len([dev for dev in developers if dev.status != discord.Status.offline])
      bot_devs = len([dev for dev in developers if dev.public_flags.verified_bot_developer])
      
      embed.add_field(
        name="**__Developer Statistics:__**",
        value=f" **Total Developers:** `{len(developers)}`\n> **Currently Online:** `{online_devs}`\n> **Bot Developers:** `{bot_devs}`",
        inline=True
      )
      
      embed.add_field(
        name="**__Badge Information:__**",
        value=f" **Requirement:** Active Discord apps\n> **Rarity:** Very Rare\n> **Server Percentage:** `{(len(developers)/len(guild.members)*100):.2f}%`",
        inline=True
      )
      
      # Developer list
      dev_list = []
      for i, dev in enumerate(sorted_devs, 1):
        status_emoji = {
          discord.Status.online: "<:online:1409167017407152138>",
          discord.Status.idle: "<:idle:1409166997383811122>",
          discord.Status.dnd: "<:dnd:1409166987807948800>",
          discord.Status.offline: "<:offline:1409167008829935698>"
        }.get(dev.status, "<:offline:1409167008829935698>")
        
        # Additional badges
        extra_badges = []
        if dev.public_flags.verified_bot_developer:
          extra_badges.append("<:4228_discord_bot_dev:1412062216525713418>")
        if dev.public_flags.early_supporter:
          extra_badges.append("<:518379earlysupporterbadge:1409180652859035708>")
        if dev.public_flags.staff:
          extra_badges.append("<:39520discordstaff:1412061536083644506>")
        
        badges_text = "".join(extra_badges)
        join_date = f"<t:{int(dev.joined_at.timestamp())}:R>" if dev.joined_at else "Unknown"
        dev_list.append(f"`{i:02d}` {status_emoji} {dev.mention} {badges_text}\n     └ Joined {join_date}")
      
      if dev_list:
        # Split into chunks if too long
        dev_text = "\n".join(dev_list)
        if len(dev_text) > 1000:
          dev_text = dev_text[:950] + f"\n... and {len(developers) - 3} more"
        
        embed.add_field(
          name="**__Active Developers:__**",
          value=dev_text,
          inline=False
        )
      
      embed.set_footer(text="These members actively contribute to Discord's ecosystem")
      await ctx.send(embed=embed)
      
    except Exception as e:
      print(f"Error in new developers command: {e}")
      await ctx.send("An error occurred while fetching developers information.", ephemeral=True)

  @commands.hybrid_command(name="oldest", aliases=["oldestaccounts"])
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def new_oldest(self, ctx):
    """Display the oldest Discord accounts in the server"""
    try:
      if ctx.interaction:
        await ctx.defer()
        
      guild = ctx.guild
      
      # Filter out members with None created_at (shouldn't happen but safety first)
      members = [mem for mem in guild.members if mem.created_at is not None]
      
      if not members:
        embed = discord.Embed(
          title="<:totalmembers:1409167038408167444> Oldest Accounts",
          description=f"**{guild.name}** has no members to display",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=embed)
      
      # Sort by account creation date (oldest first)
      try:
        oldest_members = sorted(members, key=lambda m: m.created_at)[:15]
      except:
        oldest_members = members[:15]
      
      embed = discord.Embed(
        title="<:totalmembers:1409167038408167444> Oldest Discord Accounts",
        description=f"**{guild.name}** • Top 15 oldest accounts",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      # Statistics about the oldest accounts
      if oldest_members:
        oldest_account = oldest_members[0]
        newest_in_top = oldest_members[-1]
        
        embed.add_field(
          name="**__Account Statistics__**",
          value=f" **Oldest Account:** {oldest_account.mention}\n> **Created:** <t:{int(oldest_account.created_at.timestamp())}:D>\n> **Age:** <t:{int(oldest_account.created_at.timestamp())}:R>",
          inline=False
        )
        
        # Calculate average age of server
        try:
          total_age = sum((datetime.datetime.now(datetime.timezone.utc) - m.created_at).days for m in members)
          avg_age = total_age / len(members)
          embed.add_field(
            name="**__Server Analytics__**",
            value=f" **Average Account Age:** `{avg_age:.0f}` days\n> **Total Members:** `{len(members):,}`\n> **Date Range:** `{(newest_in_top.created_at - oldest_account.created_at).days}` days",
            inline=False
          )
        except:
          embed.add_field(
            name="**__Server Info__**",
            value=f" **Total Members:** `{len(members):,}`\n> **Showing:** Top 15 oldest\n> **Server Created:** <t:{int(guild.created_at.timestamp())}:R>",
            inline=False
          )
      
      # List of oldest members
      member_list = []
      for i, member in enumerate(oldest_members, 1):
        # Calculate account age
        account_age = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
        
        # Status indicator
        status_emoji = {
          discord.Status.online: "<:online:1409167017407152138>",
          discord.Status.idle: "<:idle:1409166997383811122>",
          discord.Status.dnd: "<:dnd:1409166987807948800>",
          discord.Status.offline: "<:offline:1409167008829935698>"
        }.get(getattr(member, 'status', discord.Status.offline), "<:offline:1409167008829935698>")
        
        # Special badges for really old accounts
        age_badge = ""
        if account_age > 2555:  # ~7 years
          age_badge = "👑"  # Crown for very old accounts
        elif account_age > 1825:  # ~5 years
          age_badge = "⭐"  # Star for old accounts
        
        member_list.append(f"`{i:02d}` {status_emoji} {member.mention} {age_badge}\n     └ <t:{int(member.created_at.timestamp())}:D> • `{account_age}` days old")
      
      if member_list:
        # Split into two fields if too long
        member_text = "\n".join(member_list)
        if len(member_text) > 1000:
          mid_point = len(member_list) // 2
          
          embed.add_field(
            name="__Oldest Accounts (1-8):__",
            value="\n".join(member_list[:mid_point]),
            inline=False
          )
          embed.add_field(
            name="__Oldest Accounts (9-15):__",
            value="\n".join(member_list[mid_point:]),
            inline=False
          )
        else:
          embed.add_field(
            name="__Oldest Accounts:__",
            value=member_text,
            inline=False
          )
      
      embed.set_footer(text="👑 = 7+ years • ⭐ = 5+ years • Ages calculated from Discord account creation")
      await ctx.send(embed=embed)
      
    except Exception as e:
      print(f"Error in new oldest command: {e}")
      await ctx.send("An error occurred while fetching oldest accounts information.", ephemeral=True)

  @commands.command(name="joined-at")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def joined_at(self, ctx):
    """Check when you joined this server"""
    try:
      if not ctx.author.joined_at:
        embed = discord.Embed(
          title="<:gear:1409149841082155078> Join Information Error",
          description="Unable to retrieve your join date information.",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"User ID: {ctx.author.id}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
        return
        
      embed = discord.Embed(
        title=f"<:gear:1409149841082155078> {ctx.author.display_name}",
        color=self.color,
        timestamp=discord.utils.utcnow()
      )
      
      embed.add_field(
        name="**__Server Joined__**",
        value=f"> <t:{int(ctx.author.joined_at.timestamp())}:F>\n> <t:{int(ctx.author.joined_at.timestamp())}:R>",
        inline=False
      )
      
      join_position = len([m for m in ctx.guild.members if m.joined_at and m.joined_at <= ctx.author.joined_at])
      embed.add_field(
        name="**__Join Position__**",
        value=f" #{join_position:,} out of {len(ctx.guild.members):,} members",
        inline=False
      )
      
      embed.set_footer(text=f"User ID: {ctx.author.id}", icon_url=ctx.author.display_avatar.url)
      await ctx.send(embed=embed)
    except Exception as e:
      print(f"Error in joined-at command: {e}")
      await ctx.send("An error occurred while fetching join information.")

  @commands.command(name="github")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def github(self, ctx, *, search_query):
    """Search for GitHub repositories"""
    try:
      response = requests.get(f"https://api.github.com/search/repositories?q={search_query}")
      json_data = response.json()

      if json_data["total_count"] == 0:
        embed = discord.Embed(
          title="<:info:1409161358733213716> GitHub Search Results",
          color=self.color,
          timestamp=discord.utils.utcnow()
        )
        embed.add_field(
          name="**__GitHub Search Results__**",
          value=f" <:info:1409161358733213716> No repositories found matching: **{search_query}**",
          inline=False
        )
        embed.set_footer(text=f"Search: {search_query}")
        await ctx.send(embed=embed)
      else:
        repo = json_data['items'][0]
        embed = discord.Embed(
          title=f"<:gear:1409149841082155078> {repo['full_name']}",
          url=repo['html_url'],
          color=0x9b59b6,
          timestamp=discord.utils.utcnow()
        )
        
        if repo['description']:
          desc = repo['description'][:150] + "..." if len(repo['description']) > 150 else repo['description']
          embed.add_field(
            name="**__Description__**", 
            value=f"{desc}", 
            inline=False
          )
        
        embed.add_field(
          name="**__Statistics__**", 
          value=f"**Stars:** `{repo['stargazers_count']:,}`\n> **Forks:** `{repo['forks_count']:,}`\n> **Language:** `{repo['language'] or 'Unknown'}`", 
          inline=False
        )
        
        embed.set_footer(text=f"Search: {search_query}")
        await ctx.send(embed=embed)
        
    except Exception as e:
      embed = discord.Embed(
        title="<a:alert:1396429026842644584> GitHub Search Error",
        description="Failed to search GitHub repositories. Please try again later.",
        color=0x9b59b6,
        timestamp=discord.utils.utcnow()
      )
      embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
      await ctx.send(embed=embed)

  @commands.command(name="vote")
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def vote(self, ctx):
    """Vote for Scyro to access premium features"""
    embed = discord.Embed(
      title="💎 Vote for Scyro",
      description="You can get a chance to access Scyro premium features by just voting. Vote from the button below and [join us](https://dsc.gg/scyrogg) for rewards.",
      color=self.color,
      timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
    
    view = VoteView()
    await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Extra(bot))