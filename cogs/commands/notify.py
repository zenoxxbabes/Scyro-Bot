import discord
from discord.ext import commands
from discord import app_commands
import motor.motor_asyncio
import datetime
import os
import asyncio
import aiohttp
import re
from utils.Tools import *

# ═══════════════════════════════════════════════════════════════════════════════
#                           🎨 EMOJI CONFIGURATION - EDIT THESE EASILY
# ═══════════════════════════════════════════════════════════════════════════════

# Status Emojis
SUCCESS_EMOJI = "✅"        # Success messages
ERROR_EMOJI = "❌"          # Error messages
WARNING_EMOJI = "⚠️"        # Warning messages
INFO_EMOJI = "ℹ️"           # Info messages

# Platform Emojis
TWITCH_EMOJI = "🟣"         # Twitch platform
YOUTUBE_EMOJI = "🔴"        # YouTube platform
LIVE_EMOJI = "🔴"           # Live indicator
UPLOAD_EMOJI = "📹"         # Upload indicator

# Feature Emojis
NOTIF_EMOJI = "🔔"          # Notifications
ROLE_EMOJI = "🏷️"          # Roles
CHANNEL_EMOJI = "📺"        # Channels
LIST_EMOJI = "📋"          # Lists/settings
RESET_EMOJI = "🔄"         # Reset operations
SETTINGS_EMOJI = "⚙️"      # Settings
LINK_EMOJI = "🔗"          # Links
VIDEO_EMOJI = "🎬"         # Video content

class NotifCommands(commands.Cog):
    """Advanced notification system for Twitch and YouTube streaming alerts and uploads"""
    
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.streaming_coll = None
        self.channel_coll = None
        self.loop_task = self.bot.loop.create_task(self.setup_db())
        self.recent_notifications = {}
        self.channel_cache = {}  # Cache for channel data
        self.stream_cache = set() # Cache for guilds with active stream notifications
        
        # Start background task for checking uploads
        self.upload_check_task = self.bot.loop.create_task(self.check_uploads_loop())

    async def setup_db(self):
        """Initialize the database"""
        if not self.mongo_uri:
            print("MONGO_URI not found!")
            return

        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client.get_database()
        self.streaming_coll = self.db.notify_streaming
        self.channel_coll = self.db.notify_channels
        
        # Indexes
        await self.streaming_coll.create_index([("guild_id", 1), ("type", 1)], unique=False)
        await self.channel_coll.create_index([("guild_id", 1), ("channel_url", 1)], unique=False)
        
        # Load cache
        async for doc in self.streaming_coll.find({}, {"guild_id": 1}):
            self.stream_cache.add(doc["guild_id"])
            
        print(f"{SUCCESS_EMOJI} Notify System MongoDB Connected & Cache Loaded ({len(self.stream_cache)} guilds)")

    def create_embed(self, title: str, description: str, color: int = 0x2f3136) -> discord.Embed:
        """Create a standardized embed"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text="Scyro Notification System")
        return embed

    def extract_channel_info(self, url):
        """Extract channel information from URL"""
        # YouTube patterns
        youtube_patterns = [
            r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
            r'youtube\.com/c/([a-zA-Z0-9_-]+)',
            r'youtube\.com/@([a-zA-Z0-9_.-]+)',
            r'youtube\.com/user/([a-zA-Z0-9_-]+)',
            r'youtu\.be/([a-zA-Z0-9_-]+)'
        ]
        
        # Twitch patterns
        twitch_patterns = [
            r'twitch\.tv/([a-zA-Z0-9_-]+)'
        ]
        
        for pattern in youtube_patterns:
            match = re.search(pattern, url)
            if match:
                return "youtube", match.group(1)
        
        for pattern in twitch_patterns:
            match = re.search(pattern, url)
            if match:
                return "twitch", match.group(1)
                
        return None, None

    async def get_youtube_channel_name(self, channel_id):
        """Get YouTube channel name (placeholder - would need YouTube API)"""
        # This would require YouTube Data API v3
        # For now, return the channel ID
        return f"Channel ({channel_id})"

    async def check_uploads_loop(self):
        """Background task to check for new uploads"""
        try:
            await self.bot.wait_until_ready()
        except asyncio.CancelledError:
            return
        
        while not self.bot.is_closed():
            try:
                if self.channel_coll is None:
                    await asyncio.sleep(10)
                    continue

                rows = await self.channel_coll.find({}).to_list(length=None)
                
                for row in rows:
                    # This would check for new uploads using APIs
                    # Implementation would depend on YouTube Data API and Twitch API
                    pass
                    
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                print(f"Error in upload check loop: {e}")
                await asyncio.sleep(60)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              🎮 PREFIX COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.group(invoke_without_command=True, name='notify', aliases=['notif'])
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def notify(self, ctx):
        """Main notification command"""
        embed = self.create_embed(
            f"{NOTIF_EMOJI} Notification System",
            "**Comprehensive streaming and upload notification system**",
            0x3498db
        )
        
        embed.add_field(
            name=f"{LIVE_EMOJI} **Streaming Notifications**",
            value=f"""
`{ctx.prefix}notify stream twitch <role> <channel>` - Live stream alerts
`{ctx.prefix}notify stream youtube <role> <channel>` - Live stream alerts
            """,
            inline=False
        )
        
        embed.add_field(
            name=f"{UPLOAD_EMOJI} **Upload Notifications**",
            value=f"""
`{ctx.prefix}notify twitch <channel_url> <role> <channel>` - Twitch uploads
`{ctx.prefix}notify youtube <channel_url> <role> <channel>` - YouTube uploads
            """,
            inline=False
        )
        
        embed.add_field(
            name=f"{SETTINGS_EMOJI} **Management**",
            value=f"""
`{ctx.prefix}notify list` - View all notifications
`{ctx.prefix}notify remove <type>` - Remove notifications
`{ctx.prefix}notify reset` - Reset all settings
            """,
            inline=False
        )
        
        embed.add_field(
            name=f"{INFO_EMOJI} **How It Works**",
            value=f"""
{LIVE_EMOJI} **Stream Alerts** - Notifies when members go live
{UPLOAD_EMOJI} **Upload Alerts** - Notifies when channels upload new content
{NOTIF_EMOJI} **Auto Ping** - Pings specified roles automatically
            """,
            inline=False
        )
        
        await ctx.reply(embed=embed)

    @notify.group(name='stream', invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def stream_notify(self, ctx):
        """Stream notification management"""
        embed = self.create_embed(
            f"{LIVE_EMOJI} Stream Notifications",
            "**Set up notifications for when server members go live**",
            0x9146ff
        )
        
        embed.add_field(
            name="Available Commands",
            value=f"""
`{ctx.prefix}notify stream twitch <role> <channel>` - Twitch stream alerts
`{ctx.prefix}notify stream youtube <role> <channel>` - YouTube stream alerts
            """,
            inline=False
        )
        
        await ctx.reply(embed=embed)

    @stream_notify.command(name='twitch')
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def stream_twitch(self, ctx, role: discord.Role, channel: discord.TextChannel):
        """Set Twitch stream notifications"""
        existing = await self.streaming_coll.find_one({
            "guild_id": ctx.guild.id, 
            "type": "twitch"
        })
        
        if existing:
            return await ctx.reply(embed=self.create_embed(
                f"{WARNING_EMOJI} Already Configured", 
                "Twitch stream notifications already set. Use reset first.", 
                0xe67e22))

        await self.streaming_coll.insert_one({
            "guild_id": ctx.guild.id, 
            "type": "twitch", 
            "role_id": role.id, 
            "channel_id": channel.id
        })
        self.stream_cache.add(ctx.guild.id)

        embed = self.create_embed(
            f"{SUCCESS_EMOJI} Twitch Stream Notifications Set", 
            f"{TWITCH_EMOJI} **Twitch stream notifications configured**\n{ROLE_EMOJI} **Role:** {role.mention}\n{CHANNEL_EMOJI} **Channel:** {channel.mention}\n\n{INFO_EMOJI} **Effect:** When server members go live on Twitch, {role.mention} will be pinged in {channel.mention}", 
            0x9146ff
        )
        await ctx.reply(embed=embed)

    @stream_notify.command(name='youtube')
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def stream_youtube(self, ctx, role: discord.Role, channel: discord.TextChannel):
        """Set YouTube stream notifications"""
        existing = await self.streaming_coll.find_one({
            "guild_id": ctx.guild.id, 
            "type": "youtube"
        })
        
        if existing:
            return await ctx.reply(embed=self.create_embed(
                f"{WARNING_EMOJI} Already Configured", 
                "YouTube stream notifications already set. Use reset first.", 
                0xe67e22))

        await self.streaming_coll.insert_one({
            "guild_id": ctx.guild.id, 
            "type": "youtube", 
            "role_id": role.id, 
            "channel_id": channel.id
        })
        self.stream_cache.add(ctx.guild.id)

        embed = self.create_embed(
            f"{SUCCESS_EMOJI} YouTube Stream Notifications Set", 
            f"{YOUTUBE_EMOJI} **YouTube stream notifications configured**\n{ROLE_EMOJI} **Role:** {role.mention}\n{CHANNEL_EMOJI} **Channel:** {channel.mention}\n\n{INFO_EMOJI} **Effect:** When server members go live on YouTube, {role.mention} will be pinged in {channel.mention}", 
            0xff0000
        )
        await ctx.reply(embed=embed)

    @notify.command(name='twitch')
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def notify_twitch(self, ctx, channel_url: str, role: discord.Role, channel: discord.TextChannel):
        """Set Twitch channel upload notifications"""
        platform, channel_id = self.extract_channel_info(channel_url)
        
        if platform != "twitch":
            return await ctx.reply(embed=self.create_embed(
                f"{ERROR_EMOJI} Invalid URL",
                "Please provide a valid Twitch channel URL.\n\n**Examples:**\n• `https://twitch.tv/username`\n• `twitch.tv/username`",
                0xe74c3c
            ))

        existing = await self.channel_coll.find_one({
            "guild_id": ctx.guild.id, 
            "channel_url": channel_url
        })
        
        if existing:
            return await ctx.reply(embed=self.create_embed(
                f"{WARNING_EMOJI} Already Added",
                f"This Twitch channel is already being monitored.\n\n{LIST_EMOJI} Use `{ctx.prefix}notify list` to see all notifications.",
                0xe67e22
            ))

        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self.channel_coll.insert_one({
            "guild_id": ctx.guild.id, 
            "platform": "twitch", 
            "channel_url": channel_url, 
            "channel_name": channel_id, 
            "role_id": role.id, 
            "discord_channel_id": channel.id, 
            "created_at": current_time
        })

        embed = self.create_embed(
            f"{SUCCESS_EMOJI} Twitch Channel Added",
            f"{TWITCH_EMOJI} **Twitch upload notifications configured**\n\n{LINK_EMOJI} **Channel:** `{channel_id}`\n{ROLE_EMOJI} **Role:** {role.mention}\n{CHANNEL_EMOJI} **Discord Channel:** {channel.mention}\n\n{UPLOAD_EMOJI} **What happens:** When this Twitch channel uploads new content, {role.mention} will be pinged in {channel.mention} with the message: **\"Check out this new banger.\"**",
            0x9146ff
        )
        await ctx.reply(embed=embed)

    @notify.command(name='youtube')
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def notify_youtube(self, ctx, channel_url: str, role: discord.Role, channel: discord.TextChannel):
        """Set YouTube channel upload notifications"""
        platform, channel_id = self.extract_channel_info(channel_url)
        
        if platform != "youtube":
            return await ctx.reply(embed=self.create_embed(
                f"{ERROR_EMOJI} Invalid URL",
                "Please provide a valid YouTube channel URL.\n\n**Examples:**\n• `https://youtube.com/@username`\n• `https://youtube.com/channel/UC...`\n• `youtube.com/c/channelname`",
                0xe74c3c
            ))

        existing = await self.channel_coll.find_one({
            "guild_id": ctx.guild.id, 
            "channel_url": channel_url
        })
        
        if existing:
            return await ctx.reply(embed=self.create_embed(
                f"{WARNING_EMOJI} Already Added",
                f"This YouTube channel is already being monitored.\n\n{LIST_EMOJI} Use `{ctx.prefix}notify list` to see all notifications.",
                0xe67e22
            ))

        # Get channel name (would use YouTube API in production)
        channel_name = await self.get_youtube_channel_name(channel_id)
        
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self.channel_coll.insert_one({
            "guild_id": ctx.guild.id, 
            "platform": "youtube", 
            "channel_url": channel_url, 
            "channel_name": channel_name, 
            "role_id": role.id, 
            "discord_channel_id": channel.id, 
            "created_at": current_time
        })

        embed = self.create_embed(
            f"{SUCCESS_EMOJI} YouTube Channel Added",
            f"{YOUTUBE_EMOJI} **YouTube upload notifications configured**\n\n{LINK_EMOJI} **Channel:** `{channel_name}`\n{ROLE_EMOJI} **Role:** {role.mention}\n{CHANNEL_EMOJI} **Discord Channel:** {channel.mention}\n\n{UPLOAD_EMOJI} **What happens:** When this YouTube channel uploads new videos, {role.mention} will be pinged in {channel.mention} with the message: **\"Check out this new banger.\"**",
            0xff0000
        )
        await ctx.reply(embed=embed)

    @notify.command(name='list')
    async def list_notifications(self, ctx):
        """View all notification settings"""
        stream_rows = await self.streaming_coll.find({"guild_id": ctx.guild.id}).to_list(length=None)
        channel_rows = await self.channel_coll.find({"guild_id": ctx.guild.id}).to_list(length=None)

        if not stream_rows and not channel_rows:
            return await ctx.reply(embed=self.create_embed(
                f"{INFO_EMOJI} No Notifications",
                f"No notifications configured yet.\n\n{SETTINGS_EMOJI} Use `{ctx.prefix}notify` to see setup options.",
                0xe67e22
            ))

        embed = self.create_embed(
            f"{LIST_EMOJI} All Notification Settings",
            f"**Notification configuration for {ctx.guild.name}**",
            0x3498db
        )

        # Stream notifications
        if stream_rows:
            stream_text = ""
            for row in stream_rows:
                notif_type = row.get("type")
                role_id = row.get("role_id")
                channel_id = row.get("channel_id")
                
                role = ctx.guild.get_role(role_id)
                channel = ctx.guild.get_channel(channel_id)
                emoji = TWITCH_EMOJI if notif_type == 'twitch' else YOUTUBE_EMOJI
                
                if role and channel:
                    stream_text += f"{emoji} **{notif_type.title()}:** {role.mention} → {channel.mention}\n"
            
            if stream_text:
                embed.add_field(name=f"{LIVE_EMOJI} Stream Notifications", value=stream_text, inline=False)

        # Channel notifications
        if channel_rows:
            channel_text = ""
            for row in channel_rows:
                platform = row.get("platform")
                channel_name = row.get("channel_name")
                role_id = row.get("role_id")
                discord_channel_id = row.get("discord_channel_id")
                
                role = ctx.guild.get_role(role_id)
                channel = ctx.guild.get_channel(discord_channel_id)
                emoji = TWITCH_EMOJI if platform == 'twitch' else YOUTUBE_EMOJI
                
                if role and channel:
                    name = channel_name or "Unknown Channel"
                    channel_text += f"{emoji} **{name}:** {role.mention} → {channel.mention}\n"
            
            if channel_text:
                embed.add_field(name=f"{UPLOAD_EMOJI} Upload Notifications", value=channel_text, inline=False)

        embed.add_field(
            name=f"{INFO_EMOJI} System Status",
            value=f"**Total Configurations:** {len(stream_rows) + len(channel_rows)}\n**Status:** {SUCCESS_EMOJI} Active",
            inline=False
        )

        await ctx.reply(embed=embed)

    @notify.command(name='remove')
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def remove_notification(self, ctx, notification_type: str):
        """Remove specific notification type"""
        valid_types = ["twitch-stream", "youtube-stream", "twitch-uploads", "youtube-uploads", "all"]
        
        if notification_type.lower() not in valid_types:
            return await ctx.reply(embed=self.create_embed(
                f"{ERROR_EMOJI} Invalid Type",
                f"Please specify a valid notification type:\n\n**Stream Notifications:**\n• `twitch-stream`\n• `youtube-stream`\n\n**Upload Notifications:**\n• `twitch-uploads`\n• `youtube-uploads`\n\n**Other:**\n• `all` - Remove everything",
                0xe74c3c
            ))

        if notification_type == "all":
            await self.streaming_coll.delete_many({"guild_id": ctx.guild.id})
            await self.channel_coll.delete_many({"guild_id": ctx.guild.id})
            message = "All notifications have been removed"
        elif notification_type.endswith("-stream"):
            platform = notification_type.split("-")[0]
            await self.streaming_coll.delete_many({"guild_id": ctx.guild.id, "type": platform})
            # We don't remove from cache here as other platform might still be active
            message = f"{platform.title()} stream notifications removed"
        elif notification_type.endswith("-uploads"):
            platform = notification_type.split("-")[0]
            await self.channel_coll.delete_many({"guild_id": ctx.guild.id, "platform": platform})
            message = f"{platform.title()} upload notifications removed"
        
        embed = self.create_embed(
            f"{SUCCESS_EMOJI} Notifications Removed",
            f"**{message}**\n\n{SETTINGS_EMOJI} Use `{ctx.prefix}notify` to set up new notifications.",
            0x2ecc71
        )
        await ctx.reply(embed=embed)

    @notify.command(name='reset')
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def reset_notifications(self, ctx):
        """Reset all notification settings"""
        stream_count = await self.streaming_coll.count_documents({"guild_id": ctx.guild.id})
        channel_count = await self.channel_coll.count_documents({"guild_id": ctx.guild.id})

        total_count = stream_count + channel_count
        
        if total_count == 0:
            return await ctx.reply(embed=self.create_embed(
                f"{INFO_EMOJI} Nothing to Reset",
                "No notification configurations found.",
                0xe67e22
            ))

        # Confirmation
        confirm_embed = self.create_embed(
            f"{WARNING_EMOJI} Confirm Reset",
            f"**Are you sure you want to reset ALL notification settings?**\n\nThis will remove:\n{LIVE_EMOJI} **{stream_count}** stream notifications\n{UPLOAD_EMOJI} **{channel_count}** upload notifications\n\n**This action cannot be undone!**",
            0xe67e22
        )
        
        view = discord.ui.View(timeout=30)
        
        async def confirm_callback(interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message(f"{ERROR_EMOJI} Only the command author can confirm this.", ephemeral=True)
            
            await self.streaming_coll.delete_many({"guild_id": ctx.guild.id})
            await self.channel_coll.delete_many({"guild_id": ctx.guild.id})
            self.stream_cache.discard(ctx.guild.id)
            
            success_embed = self.create_embed(
                f"{SUCCESS_EMOJI} All Settings Reset",
                f"**All notification settings have been reset**\n\n{SETTINGS_EMOJI} Use `{ctx.prefix}notify` to set up new notifications.",
                0x2ecc71
            )
            await interaction.response.edit_message(embed=success_embed, view=None)
        
        async def cancel_callback(interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message(f"{ERROR_EMOJI} Only the command author can cancel this.", ephemeral=True)
                
            cancel_embed = self.create_embed(
                f"{INFO_EMOJI} Reset Cancelled",
                "Configuration reset has been cancelled.",
                0x95a5a6
            )
            await interaction.response.edit_message(embed=cancel_embed, view=None)
        
        confirm_btn = discord.ui.Button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji=RESET_EMOJI)
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, emoji=ERROR_EMOJI)
        
        confirm_btn.callback = confirm_callback
        cancel_btn.callback = cancel_callback
        
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        
        await ctx.reply(embed=confirm_embed, view=view)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              ⚡ SLASH COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════════

    notify_group = app_commands.Group(name="notify", description="Comprehensive notification system")

    @notify_group.command(name="twitch", description="Set Twitch channel upload notifications")
    @app_commands.describe(
        channel_url="The Twitch channel URL to monitor",
        role="The role to ping when uploads are detected",
        channel="The Discord channel to send notifications to"
    )
    async def notify_twitch_slash(self, interaction: discord.Interaction, channel_url: str, role: discord.Role, channel: discord.TextChannel):
        """Set Twitch channel upload notifications"""
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=self.create_embed(f"{ERROR_EMOJI} No Permission", "Administrator required.", 0xe74c3c), 
                ephemeral=True)

        platform, channel_id = self.extract_channel_info(channel_url)
        
        if platform != "twitch":
            return await interaction.response.send_message(embed=self.create_embed(
                f"{ERROR_EMOJI} Invalid URL",
                "Please provide a valid Twitch channel URL.",
                0xe74c3c
            ), ephemeral=True)

        existing = await self.channel_coll.find_one({
            "guild_id": interaction.guild.id, 
            "channel_url": channel_url
        })
        
        if existing:
            return await interaction.response.send_message(embed=self.create_embed(
                f"{WARNING_EMOJI} Already Added",
                "This Twitch channel is already being monitored.",
                0xe67e22
            ), ephemeral=True)

        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self.channel_coll.insert_one({
            "guild_id": interaction.guild.id, 
            "platform": "twitch", 
            "channel_url": channel_url, 
            "channel_name": channel_id, 
            "role_id": role.id, 
            "discord_channel_id": channel.id, 
            "created_at": current_time
        })

        embed = self.create_embed(
            f"{SUCCESS_EMOJI} Twitch Channel Added",
            f"{TWITCH_EMOJI} **Twitch upload notifications configured**\n\n{LINK_EMOJI} **Channel:** `{channel_id}`\n{ROLE_EMOJI} **Role:** {role.mention}\n{CHANNEL_EMOJI} **Channel:** {channel.mention}",
            0x9146ff
        )
        await interaction.response.send_message(embed=embed)

    @notify_group.command(name="youtube", description="Set YouTube channel upload notifications")
    @app_commands.describe(
        channel_url="The YouTube channel URL to monitor",
        role="The role to ping when uploads are detected", 
        channel="The Discord channel to send notifications to"
    )
    async def notify_youtube_slash(self, interaction: discord.Interaction, channel_url: str, role: discord.Role, channel: discord.TextChannel):
        """Set YouTube channel upload notifications"""
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=self.create_embed(f"{ERROR_EMOJI} No Permission", "Administrator required.", 0xe74c3c), 
                ephemeral=True)

        platform, channel_id = self.extract_channel_info(channel_url)
        
        if platform != "youtube":
            return await interaction.response.send_message(embed=self.create_embed(
                f"{ERROR_EMOJI} Invalid URL",
                "Please provide a valid YouTube channel URL.",
                0xe74c3c
            ), ephemeral=True)

        existing = await self.channel_coll.find_one({
            "guild_id": interaction.guild.id, 
            "channel_url": channel_url
        })
        
        if existing:
            return await interaction.response.send_message(embed=self.create_embed(
                f"{WARNING_EMOJI} Already Added",
                "This YouTube channel is already being monitored.",
                0xe67e22
            ), ephemeral=True)

        channel_name = await self.get_youtube_channel_name(channel_id)
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        await self.channel_coll.insert_one({
            "guild_id": interaction.guild.id, 
            "platform": "youtube", 
            "channel_url": channel_url, 
            "channel_name": channel_name, 
            "role_id": role.id, 
            "discord_channel_id": channel.id, 
            "created_at": current_time
        })

        embed = self.create_embed(
            f"{SUCCESS_EMOJI} YouTube Channel Added",
            f"{YOUTUBE_EMOJI} **YouTube upload notifications configured**\n\n{LINK_EMOJI} **Channel:** `{channel_name}`\n{ROLE_EMOJI} **Role:** {role.mention}\n{CHANNEL_EMOJI} **Channel:** {channel.mention}",
            0xff0000
        )
        await interaction.response.send_message(embed=embed)

    @notify_group.command(name="list", description="View all notification settings")
    async def notify_list_slash(self, interaction: discord.Interaction):
        """View all notification settings"""
        stream_rows = await self.streaming_coll.find({"guild_id": interaction.guild.id}).to_list(length=None)
        channel_rows = await self.channel_coll.find({"guild_id": interaction.guild.id}).to_list(length=None)

        if not stream_rows and not channel_rows:
            return await interaction.response.send_message(embed=self.create_embed(
                f"{INFO_EMOJI} No Notifications",
                "No notifications configured yet.",
                0xe67e22
            ), ephemeral=True)

        embed = self.create_embed(
            f"{LIST_EMOJI} Notification Settings",
            f"**Configuration for {interaction.guild.name}**",
            0x3498db
        )

        if stream_rows:
            stream_text = ""
            for row in stream_rows:
                notif_type = row.get("type")
                role_id = row.get("role_id")
                channel_id = row.get("channel_id")
                
                role = interaction.guild.get_role(role_id)
                channel = interaction.guild.get_channel(channel_id)
                emoji = TWITCH_EMOJI if notif_type == 'twitch' else YOUTUBE_EMOJI
                
                if role and channel:
                    stream_text += f"{emoji} **{notif_type.title()}:** {role.mention} → {channel.mention}\n"
            
            if stream_text:
                embed.add_field(name=f"{LIVE_EMOJI} Stream Notifications", value=stream_text, inline=False)

        if channel_rows:
            channel_text = ""
            for row in channel_rows:
                platform = row.get("platform")
                channel_name = row.get("channel_name")
                role_id = row.get("role_id")
                discord_channel_id = row.get("discord_channel_id")
                
                role = interaction.guild.get_role(role_id)
                channel = interaction.guild.get_channel(discord_channel_id)
                emoji = TWITCH_EMOJI if platform == 'twitch' else YOUTUBE_EMOJI
                
                if role and channel:
                    name = channel_name or "Unknown Channel"
                    channel_text += f"{emoji} **{name}:** {role.mention} → {channel.mention}\n"
            
            if channel_text:
                embed.add_field(name=f"{UPLOAD_EMOJI} Upload Notifications", value=channel_text, inline=False)

        await interaction.response.send_message(embed=embed)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              🎬 STREAM & UPLOAD DETECTION
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        """Detect streaming and send notifications"""
        if after.bot or not after.guild:
            return

        # Optimization: Skip if guild has no stream notifications configured
        if after.guild.id not in self.stream_cache:
            return

        streaming = next((activity for activity in after.activities if isinstance(activity, discord.Streaming)), None)
        
        if streaming:
            stream_type = None
            if "twitch.tv" in streaming.url.lower():
                stream_type = "twitch"
            elif "youtube.com" in streaming.url.lower() or "youtu.be" in streaming.url.lower():
                stream_type = "youtube"
            
            if not stream_type:
                return

            # Spam protection
            user_key = f"{after.guild.id}_{after.id}_{stream_type}"
            current_time = datetime.datetime.now(datetime.timezone.utc)
            
            if user_key in self.recent_notifications:
                last_notification = self.recent_notifications[user_key]
                if (current_time - last_notification).total_seconds() < 1800:  # 30 minutes
                    return

            # Get notification settings
            row = await self.streaming_coll.find_one({
                "guild_id": after.guild.id, 
                "type": stream_type
            })
            
            if row:
                role_id = row.get("role_id")
                channel_id = row.get("channel_id")
                
                role = after.guild.get_role(role_id)
                channel = after.guild.get_channel(channel_id)

                if role and channel:
                    # Check permissions
                    if not channel.permissions_for(after.guild.me).send_messages:
                        return

                    # Create notification
                    emoji = TWITCH_EMOJI if stream_type == 'twitch' else YOUTUBE_EMOJI
                    color = 0x9146ff if stream_type == 'twitch' else 0xff0000
                    
                    embed = discord.Embed(
                        title=f"{after.display_name} is now live!",
                        description=f"{after.mention} is streaming on {stream_type.capitalize()}",
                        color=color,
                        timestamp=current_time
                    )
                    
                    embed.add_field(name="Stream Title", value=streaming.name or "No title", inline=False)
                    embed.add_field(name="Platform", value=f"{emoji} {stream_type.capitalize()}", inline=True)
                    embed.add_field(name="Watch", value=f"[Click here]({streaming.url})", inline=True)
                    
                    if after.avatar:
                        embed.set_thumbnail(url=after.display_avatar.url)
                    
                    embed.set_footer(text=f"{LIVE_EMOJI} Live on {stream_type.capitalize()}")

                    try:
                        await channel.send(content=role.mention, embed=embed)
                        self.recent_notifications[user_key] = current_time
                        
                        # Clean up old entries
                        cutoff_time = current_time - datetime.timedelta(hours=2)
                        self.recent_notifications = {
                            k: v for k, v in self.recent_notifications.items() 
                            if v > cutoff_time
                        }
                    except:
                        pass

    async def send_upload_notification(self, guild_id, platform, channel_name, video_title, video_url, role_id, discord_channel_id):
        """Send upload notification"""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
            
        role = guild.get_role(role_id)
        channel = guild.get_channel(discord_channel_id)
        
        if not role or not channel:
            return
            
        emoji = TWITCH_EMOJI if platform == 'twitch' else YOUTUBE_EMOJI
        color = 0x9146ff if platform == 'twitch' else 0xff0000
        
        embed = discord.Embed(
            title=f"{VIDEO_EMOJI} New {platform.title()} Upload!",
            description=f"**{channel_name}** just uploaded new content!",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        embed.add_field(name="Video Title", value=video_title, inline=False)
        embed.add_field(name="Platform", value=f"{emoji} {platform.title()}", inline=True)
        embed.add_field(name="Watch Now", value=f"[Click here]({video_url})", inline=True)
        
        embed.set_footer(text=f"{UPLOAD_EMOJI} New upload detected")
        
        try:
            await channel.send(content=f"{role.mention} Check out this new banger.", embed=embed)
        except:
            pass


async def setup(bot):
    cog = NotifCommands(bot)
    bot.tree.add_command(cog.notify_group)
    await bot.add_cog(cog)
    print(f"{SUCCESS_EMOJI} Enhanced Notification System loaded!")
