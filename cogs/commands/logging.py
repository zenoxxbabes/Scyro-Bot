import discord
from discord.ext import commands, tasks
from discord import app_commands
import motor.motor_asyncio
import asyncio
import datetime
import os
import json
import time
from typing import Optional, List, Dict, Any, Union
from collections import defaultdict
from core.ratelimithandler import GlobalRateLimitHandler

# ═══════════════════════════════════════════════════════════════════════════════
#                           🎨 UNIVERSAL EMOJI CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Success/Error Emojis
SUCCESS_EMOJI = "✅"        # Success operations
ERROR_EMOJI = "❌"          # Error messages  
WARNING_EMOJI = "⚠️"        # Warning messages
INFO_EMOJI = "ℹ️"           # Information messages

# Feature Emojis
LOG_EMOJI = "📝"           # Logging related
SETTINGS_EMOJI = "⚙️"      # Settings/configuration
LIST_EMOJI = "📋"          # Lists and displays
SECURITY_EMOJI = "🔐"      # Security/permissions
STATS_EMOJI = "📊"         # Statistics
TIME_EMOJI = "⏰"          # Time/duration related
USER_EMOJI = "👤"          # User related
BOT_EMOJI = "🤖"           # Bot related
CHANNEL_EMOJI = "📺"       # Channel related
SEARCH_EMOJI = "🔍"        # Search operations
BACKUP_EMOJI = "💾"        # Backup operations
MONITOR_EMOJI = "📡"       # Monitoring operations
EXPORT_EMOJI = "📤"        # Export operations

# Action Emojis  
ADD_EMOJI = "➕"           # Add operations
REMOVE_EMOJI = "➖"        # Remove operations
RESET_EMOJI = "🔄"         # Reset operations
VIEW_EMOJI = "👁️"          # View/show operations
EDIT_EMOJI = "✏️"          # Edit operations
DELETE_EMOJI = "🗑️"        # Delete operations
ENABLE_EMOJI = "🟢"        # Enable operations
DISABLE_EMOJI = "🔴"       # Disable operations

# Log Type Emojis
MESSAGE_EMOJI = "💬"       # Message logs
MEMBER_EMOJI = "👥"        # Member logs
VOICE_EMOJI = "🎙️"         # Voice logs
BAN_EMOJI = "🔨"           # Ban logs
MODERATION_EMOJI = "👮"    # Moderation logs
WEBHOOK_EMOJI = "🌐"       # Webhook logs
ROLE_EMOJI = "🏷️"          # Role logs
SERVER_EMOJI = "🏠"        # Server logs
INVITE_EMOJI = "📨"        # Invite logs

# Status Emojis
ONLINE_EMOJI = "🟢"        # Online/active status
OFFLINE_EMOJI = "🔴"       # Offline/inactive status
LOADING_EMOJI = "⏳"       # Loading status
TEST_EMOJI = "🧪"          # Test operations

class Logging(commands.Cog):
    """Advanced server logging system with comprehensive event tracking and management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_log_setups = {}
        self.guild_circuit_breakers = {} # Guild ID -> Timestamp until when disabled
        
        # ─────────────── LOGGING QUEUE SYSTEM ───────────────
        # Structure: queue[guild_id][log_type] = [EventData, ...]
        self.log_queue = defaultdict(lambda: defaultdict(list))
        self.queue_lock = asyncio.Lock()
        
        # Internal caches
        self.voice_cooldowns = {} # (user_id, guild_id) -> timestamp

        # MongoDB Setup
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.settings = None
        self.history = None
        
        self.bot.loop.create_task(self.init_db())
        self.flush_loop.start()

    async def init_db(self):
        """Initialize MongoDB connection"""
        if not self.mongo_uri:
            print(f"{ERROR_EMOJI} [Logging] MONGO_URI not found!")
            return

        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            self.db = self.client.get_database()
            self.settings = self.db.logging_settings
            self.history = self.db.logging_history
            
            # Indexes
            await self.settings.create_index("guild_id", unique=True)
            await self.history.create_index([("guild_id", 1), ("timestamp", -1)])
            
            print(f"{SUCCESS_EMOJI} [Logging] MongoDB connected.")
        except Exception as e:
            print(f"{ERROR_EMOJI} [Logging] DB Init Error: {e}")

    def cog_unload(self):
        self.flush_loop.cancel()

    async def ensure_log_channel(self, guild: discord.Guild, log_type: str) -> Optional[discord.TextChannel]:
        """Ensures a log channel exists for the given type, creating it if necessary."""
        # Default Log Channel Mapping
        DEFAULT_LOG_CHANNELS = {
            'messages': 'message-logs',
            'members': 'member-logs',
            'voice': 'voice-logs',
            'roles': 'role-logs',
            'channels': 'channel-logs',
            'bans': 'ban-logs',
            'moderation': 'mod-logs',
            'server': 'server-logs',
        }
        
        # Check DB first
        channel_id = await self.get_log_channel(guild.id, log_type)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel: return channel
        
        # If not in DB or channel deleted, try to find by name or create
        target_name = DEFAULT_LOG_CHANNELS.get(log_type, f'{log_type}-logs')
        category_name = "Scyro Logs"
        
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
                }
                category = await guild.create_category(category_name, overwrites=overwrites)
            except discord.Forbidden:
                return None 

        channel = discord.utils.get(category.text_channels, name=target_name)
        
        if not channel:
            try:
                channel = await category.create_text_channel(target_name)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=False),
                    guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True, embed_links=True)
                }
                await channel.edit(overwrites=overwrites)
            except discord.Forbidden:
                return None

        # Update DB with new channel
        if channel:
             await self.set_log_channel(guild.id, log_type, channel.id, self.bot.user.id, "Auto-Setup")

        return channel

    async def cleanup_old_channel(self, guild: discord.Guild, log_type: str, old_channel_id: int):
        """Deletes an old bot-created log channel if it's no longer used."""
        if not old_channel_id: return
        
        try:
            channel = guild.get_channel(int(old_channel_id))
            if not channel: return
            
            if not channel.category or channel.category.name != "Scyro Logs": 
                return
            
            await channel.delete(reason=f"Logging channel replaced for {log_type}")
            
        except Exception:
            pass

    async def cog_load(self):
        print(f"{SUCCESS_EMOJI} Logging cog loaded.")

    async def cog_unload(self):
        self.flush_loop.cancel()

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           🔧 QUEUE & BATCHING LOGIC
    # ═══════════════════════════════════════════════════════════════════════════════

    def queue_event(self, guild_id: int, log_type: str, data: Dict[str, Any]):
        """Add an event to the volatile memory queue"""
        if GlobalRateLimitHandler.should_fail_fast():
            return 
        if guild_id in self.guild_circuit_breakers:
            if time.time() < self.guild_circuit_breakers[guild_id]:
                return 
            del self.guild_circuit_breakers[guild_id]

        # Use async safe append if strictly needed, but dict operations are atomic enough for this usage
        if len(self.log_queue[guild_id][log_type]) < 50: 
            self.log_queue[guild_id][log_type].append(data)

    @tasks.loop(seconds=3)
    async def flush_loop(self):
        """Periodically flush queued logs to Discord"""
        if GlobalRateLimitHandler.should_fail_fast():
            self.log_queue.clear()
            return

        async with self.queue_lock:
            pending_guilds = list(self.log_queue.keys())
        
        for guild_id in pending_guilds:
            if GlobalRateLimitHandler.should_fail_fast():
                self.log_queue.clear()
                return
            await self.process_guild_queue(guild_id)

    async def process_guild_queue(self, guild_id: int):
        """Process all logs for a specific guild"""
        guild_logs = self.log_queue.pop(guild_id, {})
        if not guild_logs:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return 
        
        for log_type, events in guild_logs.items():
            if not events: continue
            if not await self.is_log_type_enabled(guild_id, log_type): continue

            channel_id = await self.get_log_channel(guild_id, log_type)
            if not channel_id: continue

            channel = guild.get_channel(channel_id)
            if not channel: continue

            embeds = []
            if log_type == "voice": embeds = self.batch_voice_events(events)
            elif log_type == "members": embeds = self.batch_member_events(events)
            elif log_type == "roles": embeds = self.batch_role_events(events)
            else: embeds = self.batch_generic_events(log_type, events)

            for i in range(0, len(embeds), 10):
                chunk = embeds[i:i+10]
                try:
                    await channel.send(embeds=chunk)
                    asyncio.create_task(self.update_log_stats(guild_id))
                    await asyncio.sleep(0.5)
                except discord.HTTPException as e:
                    if e.status == 429:
                        print(f"⚠️ GUILD RATE LIMIT (429) in {guild_id}. Pausing logs for 2 mins.")
                        self.guild_circuit_breakers[guild_id] = time.time() + 120
                        return
                except Exception: pass

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           🧩 BATCH STRATEGIES
    # ═══════════════════════════════════════════════════════════════════════════════

    def create_simple_embed(self, title, description, color, footer_text=None, thumbnail=None):
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if footer_text: embed.set_footer(text=footer_text)
        if thumbnail: embed.set_thumbnail(url=thumbnail)
        return embed

    def batch_voice_events(self, events: List[Dict]) -> List[discord.Embed]:
        embeds = []
        for e in events:
            # Voice Join/Leave/Move - Simplified aesthetic
            if e['type'] == 'join':
                desc = f"{e['user_mention']} joined 🔉 {e['channel_mention']}."
                title = "Member joined voice channel"
                color = 0x2ecc71 # Green
            elif e['type'] == 'leave':
                desc = f"{e['user_mention']} left 🔉 {e['channel_mention']}."
                title = "Member left voice channel"
                color = 0xe74c3c # Red
            elif e['type'] == 'move':
                desc = f"{e['user_mention']} moved\n{e['before_channel_mention']} ➜ {e['after_channel_mention']}"
                title = "Member moved voice channel"
                color = 0x3498db # Blue
            elif e['type'] == 'server_mute':
                desc = f"{e['user_mention']} was **Server Muted** in {e['channel_mention']}"
                title = "Member Server Muted"
                color = 0xe67e22 # Orange
            elif e['type'] == 'server_unmute':
                desc = f"{e['user_mention']} was **Server Unmuted** in {e['channel_mention']}"
                title = "Member Server Unmuted"
                color = 0x2ecc71 # Green
            elif e['type'] == 'server_deaf':
                desc = f"{e['user_mention']} was **Server Deafened** in {e['channel_mention']}"
                title = "Member Server Deafened"
                color = 0xe67e22 # Orange
            elif e['type'] == 'server_undeaf':
                desc = f"{e['user_mention']} was **Server Undeafened** in {e['channel_mention']}"
                title = "Member Server Undeafened"
                color = 0x2ecc71 # Green
            
            embed = discord.Embed(title=title, description=desc, color=color)
            embed.set_author(name=e['user_name'], icon_url=e.get('avatar_url'))
            embed.set_footer(text=f"Id: {e['user_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
            embeds.append(embed)
        return embeds

    def batch_member_events(self, events: List[Dict]) -> List[discord.Embed]:
        joins = [e for e in events if e['type'] == 'join']
        leaves = [e for e in events if e['type'] == 'leave']
        kicks = [e for e in events if e['type'] == 'kick']
        embeds = []
        
        # Helper to get guild member count ordinal
        def get_ordinal(n):
            return f"{n}{'th' if 11<=n%100<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10, 'th')}"

        for e in joins:
            # Join Embed - Green sidebar
            guild = self.bot.get_guild(e.get('guild_id')) # We need to pass guild_id in event data or fetch it
            # Since we don't have guild object readily available in this loop context easily without passing it, 
            # let's assume we can fetch member count roughly or use what's passed. 
            # Ideally we pass member_count in event data.
            
            # Reconstruct datetime objects
            created_at = datetime.datetime.fromtimestamp(e['created_at_ts'], datetime.timezone.utc)
            joined_at = datetime.datetime.fromtimestamp(e['timestamp'], datetime.timezone.utc)
            
            embed = discord.Embed(description=f"**Member Joined**\n\n{e['user_mention']} is {get_ordinal(e.get('member_count', 0))} to join the server\nAccount created at: <t:{int(e['created_at_ts'])}:F> (<t:{int(e['created_at_ts'])}:R>)", color=0x2ecc71) # Green
            embed.set_author(name=e['user_name'], icon_url=e.get('avatar_url'))
            embed.set_footer(text=f"Id: {e['user_id']} • {joined_at.strftime('%d-%m-%Y %H:%M')}")
            embeds.append(embed)

        for e in leaves:
            # Leave Embed - Red sidebar
            created_at = datetime.datetime.fromtimestamp(e['created_at_ts'], datetime.timezone.utc)
            joined_at = datetime.datetime.fromtimestamp(e['joined_at_ts'], datetime.timezone.utc) if e.get('joined_at_ts') else None
            
            embed = discord.Embed(title="Member Left", description=f"{e['user_mention']} ({e['user_id']}) left the server.", color=0xe74c3c) # Red
            embed.set_author(name=e['user_name'], icon_url=e.get('avatar_url'))
            
            roles_str = e.get('roles', 'None')
            embed.add_field(name="Roles:", value=roles_str, inline=False)
            if joined_at:
                embed.add_field(name="Joined at:", value=f"<t:{int(e['joined_at_ts'])}:F> (<t:{int(e['joined_at_ts'])}:R>)", inline=False)
            embed.add_field(name="Created at:", value=f"<t:{int(e['created_at_ts'])}:F> (<t:{int(e['created_at_ts'])}:R>)", inline=False)
            
            embed.set_footer(text=f"Id: {e['user_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
            embeds.append(embed)

        for e in kicks:
            # Kick Embed - Orange/Red sidebar
            timestamp = datetime.datetime.fromtimestamp(e['timestamp'], datetime.timezone.utc)
            
            embed = discord.Embed(title="Member Kicked", description=f"{e['user_mention']} has been kicked.", color=0xe67e22) # Orange
            embed.set_author(name=e['user_name'], icon_url=e.get('avatar_url'))
            
            embed.add_field(name="Moderator:", value=f"{e.get('moderator_mention', 'Unknown')} ({e.get('moderator_name', 'Unknown')})", inline=False)
            embed.add_field(name="Reason:", value=e.get('reason', 'No reason provided'), inline=False)
            
            embed.set_footer(text=f"Id: {e['user_id']} • {timestamp.strftime('%d-%m-%Y %H:%M')}")
            embeds.append(embed)
            
        return embeds

    def batch_role_events(self, events: List[Dict]) -> List[discord.Embed]:
        embeds = []
        # Separate member updates versus role object updates
        member_updates = [e for e in events if e.get('user_id') and e.get('subtype') in ('add', 'remove')]
        role_updates = [e for e in events if e.get('subtype') not in ('add', 'remove')]

        # 1. Member Role Changes (Assignment/Removal)
        by_user = defaultdict(list)
        for e in member_updates: by_user[e['user_id']].append(e)

        for user_id, user_events in by_user.items():
            # Aesthetics: Purple bar for Role Removed? Screenshot: "Role Removed" text, Purple bar.
            # We'll do individual embeds for now to match screenshot "Role Removed"
            for e in user_events:
                 if e['subtype'] == 'remove':
                     # Screenshot: Header "Role Removed", Role: @~ Blessers, Id: ...
                     embed = discord.Embed(title="Role Removed", color=0x9b59b6) # Purple
                     embed.add_field(name="Role:", value=f"{e['role_mention']}", inline=True)
                     embed.add_field(name="User:", value=f"<@{e['user_id']}>", inline=True)
                     
                     exc = e.get('executor')
                     if exc:
                         embed.add_field(name="Removed By:", value=f"<@{exc['id']}>", inline=False)
                     else:
                         embed.add_field(name="Removed By:", value="Unknown", inline=False)
                         
                     embed.set_footer(text=f"Role Id: {e['role_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
                     embeds.append(embed)
                 elif e['subtype'] == 'add':
                     embed = discord.Embed(title="Role Added", color=0x2ecc71) # Green
                     embed.add_field(name="Role:", value=f"{e['role_mention']}", inline=True)
                     embed.add_field(name="User:", value=f"<@{e['user_id']}>", inline=True)
                     
                     exc = e.get('executor')
                     if exc:
                         embed.add_field(name="Given By:", value=f"<@{exc['id']}>", inline=False)
                     else:
                         embed.add_field(name="Given By:", value="Unknown", inline=False)

                     embed.set_footer(text=f"Role Id: {e['role_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
                     embeds.append(embed)

        # 2. Guild Role Object Changes (Color, Create, Delete, Edit)
        for e in role_updates:
            if e['subtype'] == 'color_change':
                # Deprecated or specific color change only
                 embed = discord.Embed(title="Role Color Changed", color=0x9b59b6)
                 embed.add_field(name="Role:", value=e['role_mention'], inline=False)
                 embed.add_field(name="Updated By:", value=e['executor_mention'], inline=False)
                 embed.add_field(name="Old Color:", value=str(e.get('old_color_value', '?')), inline=False)
                 embed.add_field(name="New Color:", value=str(e.get('new_color_value', '?')), inline=False)
                 embed.set_footer(text=f"Role Id: {e['role_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
                 embeds.append(embed)
            elif e['subtype'] == 'edit':
                 # General Edit (Name, Color, Hoist, Mentionable)
                 embed = discord.Embed(title="Role Updated", color=0x3498db) # Blue
                 embed.description = "\n".join(e.get('changes', []))
                 embed.add_field(name="Role:", value=e['role_mention'], inline=False)
                 embed.add_field(name="Updated By:", value=e['executor_mention'], inline=False)
                 embed.set_footer(text=f"Role Id: {e['role_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
                 embeds.append(embed)
            elif e['subtype'] == 'create':
                 embed = discord.Embed(title="Role Created", color=0x2ecc71)
                 embed.add_field(name="Role:", value=e['role_mention'], inline=False)
                 embed.add_field(name="Created By:", value=e['executor_mention'], inline=False)
                 embed.set_footer(text=f"Role Id: {e['role_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
                 embeds.append(embed)
            elif e['subtype'] == 'delete':
                 embed = discord.Embed(title="Role Deleted", color=0xe74c3c)
                 embed.add_field(name="Role:", value=e['role_name'], inline=False)
                 embed.add_field(name="Deleted By:", value=e['executor_mention'], inline=False)
                 embed.set_footer(text=f"Role Id: {e['role_id']} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}")
                 embeds.append(embed)

        return embeds

    def batch_generic_events(self, log_type, events: List[Dict]) -> List[discord.Embed]:
        embeds = []
        for e in events:
            if 'embed_data' in e:
                embed = discord.Embed.from_dict(e['embed_data'])
                embeds.append(embed)
            elif 'description' in e:
                embeds.append(self.create_simple_embed(f"{LOG_EMOJI} {log_type.title()} Log", e['description'], 0x3498db))
        return embeds

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           📝 HELPERS
    # ═══════════════════════════════════════════════════════════════════════════════

    def create_embed(self, title: str, description: str, color: int = 0x2b2d31, emoji: str = INFO_EMOJI) -> discord.Embed:
        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text="Scyro Advanced Logging System", icon_url=self.bot.user.avatar.url if self.bot.user else None)
        return embed

    async def log_to_history(self, guild_id: int, log_type: str, event_type: str, user_id: int = None, channel_id: int = None, content: str = ""):
        try:
            await self.history.insert_one({
                "guild_id": guild_id,
                "log_type": log_type,
                "event_type": event_type,
                "user_id": user_id,
                "channel_id": channel_id,
                "content": content[:500],
                "timestamp": datetime.datetime.now(datetime.timezone.utc)
            })
        except: pass

    async def set_log_channel(self, guild_id, log_type, channel_id, moderator_id=None, moderator_name=None):
        try:
            current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await self.settings.update_one(
                {"guild_id": guild_id},
                {"$set": {
                    log_type: channel_id,
                    "configured_by": f"{moderator_name} ({moderator_id})" if moderator_id else None,
                    "config_timestamp": current_time
                }},
                upsert=True
            )
        except Exception as e:
            print(f"Error setting log channel: {e}")

    async def get_log_channel(self, guild_id, log_type):
        doc = await self.settings.find_one({"guild_id": guild_id})
        return doc.get(log_type) if doc else None

    async def get_all_log_settings(self, guild_id):
        return await self.settings.find_one({"guild_id": guild_id})

    async def is_log_type_enabled(self, guild_id, log_type):
        doc = await self.settings.find_one({"guild_id": guild_id})
        if not doc: return False
        # If the channel is set, it's enabled by default in new schema
        return bool(doc.get(log_type))

    async def update_log_stats(self, guild_id):
        try:
            current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await self.settings.update_one(
                {"guild_id": guild_id},
                {"$inc": {"total_logs": 1}, "$set": {"last_log_time": current_time}},
                upsert=True
            )
        except: pass

    async def store_created_resources(self, guild_id, channel_ids, category_id):
        try:
            await self.settings.update_one(
                {"guild_id": guild_id},
                {"$set": {"created_channels": channel_ids, "created_category": category_id}},
                upsert=True
            )
        except: pass

    async def cleanup_created_resources(self, guild_id):
        try:
            settings = await self.get_all_log_settings(guild_id)
            if not settings: return [], False
            guild = self.bot.get_guild(int(guild_id))
            if not guild: return [], False
            created_channels = json.loads(settings.get('created_channels', '[]'))
            created_category_id = settings.get('created_category')
            deleted_channels = []
            deleted_category = False
            for channel_id in created_channels:
                try:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        await channel.delete(reason="Logging reset")
                        deleted_channels.append(channel.name)
                except: pass
            if created_category_id:
                try:
                    category = guild.get_channel(created_category_id)
                    if category:
                        await category.delete(reason="Logging reset")
                        deleted_category = True
                except: pass
            return deleted_channels, deleted_category
        except: return [], False

    async def has_any_log_settings(self, guild_id):
        settings = await self.get_all_log_settings(guild_id)
        if not settings: return False
        log_types = ["messages", "members", "voice", "channels", "roles", "bans", "moderation", "server"]
        for t in log_types:
            if settings.get(t): return True
        return False

    async def _perform_auto_setup(self, ctx_or_interaction, user):
        """Auto Setup Routine: Creates channels and Category"""
        guild = ctx_or_interaction.guild
        category_name = "Scyro Logs"
        log_channels_to_create = {
            "messages": "message-logs",
            "members": "member-logs",
            "voice": "voice-logs",
            "channels": "channel-logs",
            "roles": "role-logs",
            "bans": "ban-logs", 
            "moderation": "mod-logs",
            "server": "server-logs"
        }
        everyone_perms = discord.PermissionOverwrite(read_messages=False, send_messages=False, connect=False)
        bot_perms = discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
        everyone_role = guild.default_role
        created_channel_ids = []
        created_category_id = None
        
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name, overwrites={everyone_role: everyone_perms, guild.me: bot_perms})
            created_category_id = category.id
            
        for log_type, channel_name in log_channels_to_create.items():
            existing = discord.utils.get(category.text_channels, name=channel_name)
            if not existing:
                new_ch = await guild.create_text_channel(channel_name, category=category, overwrites={everyone_role: everyone_perms, guild.me: bot_perms})
                created_channel_ids.append(new_ch.id)
                await self.set_log_channel(guild.id, log_type, new_ch.id, user.id, user.display_name)
            else:
                 await self.set_log_channel(guild.id, log_type, existing.id, user.id, user.display_name)
                 
        await self.store_created_resources(guild.id, created_channel_ids, created_category_id)
        return created_channel_ids, created_category_id

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           👂 EVENT LISTENERS
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot: return
        try:
            data = {
                'type': 'join', 
                'guild_id': member.guild.id,
                'user_id': member.id, 
                'user_name': member.name, # Use name not display_name for author field usually
                'user_mention': member.mention, 
                'created_at_ts': member.created_at.timestamp(),
                'timestamp': member.joined_at.timestamp() if member.joined_at else time.time(),
                'member_count': member.guild.member_count,
                'avatar_url': member.display_avatar.url
            }
            self.queue_event(member.guild.id, 'members', data)
            asyncio.create_task(self.log_to_history(member.guild.id, "members", "join", member.id, None, f"{member.name} joined"))
        except Exception as e: print(f"Error in on_member_join: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.bot: return
        try:
            # Check for Kick
            audit_log_entry = await self.get_audit_log_entry(member.guild, discord.AuditLogAction.kick, member)
            is_kick = False
            moderator = None
            reason = None
            
            if audit_log_entry:
                is_kick = True
                moderator = audit_log_entry.user
                reason = audit_log_entry.reason or "Not Provided"

            roles = [r.mention for r in member.roles if r.name != "@everyone"]
            roles_str = ", ".join(roles) if roles else "None"

            if is_kick:
                data = {
                    'type': 'kick',
                    'guild_id': member.guild.id,
                    'user_id': member.id,
                    'user_name': member.name,
                    'user_mention': member.mention,
                    'moderator_mention': moderator.mention,
                    'moderator_name': moderator.name,
                    'reason': reason,
                    'timestamp': time.time(),
                    'avatar_url': member.display_avatar.url
                }
            else:
                data = {
                    'type': 'leave', 
                    'guild_id': member.guild.id,
                    'user_id': member.id, 
                    'user_name': member.name, 
                    'user_mention': member.mention,
                    'created_at_ts': member.created_at.timestamp(),
                    'joined_at_ts': member.joined_at.timestamp() if member.joined_at else None,
                    'roles': roles_str,
                    'timestamp': time.time(),
                    'avatar_url': member.display_avatar.url
                }

            self.queue_event(member.guild.id, 'members', data)
            
            action_type = "kick" if is_kick else "leave"
            msg = f"{member.name} was kicked" if is_kick else f"{member.name} left"
            asyncio.create_task(self.log_to_history(member.guild.id, "members", action_type, member.id, None, msg))
        except Exception as e: print(f"Error in on_member_remove: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        try:
            now = time.time()
            # Cooldown check only for frequent state changes (flapping), 
            # but mute/deaf might be spammy so good to keep cooldown or separate it.
            # Existing cooldown logic:
            key = (member.id, member.guild.id)
            if key in self.voice_cooldowns:
                if now - self.voice_cooldowns[key] < 2: return # Reduced to 2s to allow quick toggles but stop spam
            self.voice_cooldowns[key] = now
            if len(self.voice_cooldowns) > 2000: self.voice_cooldowns.clear()

            event_type = None
            channel_name = None
            channel_id = None
            
            # 1. Join/Leave/Move
            if not before.channel and after.channel:
                event_type = 'join'
                channel_name = after.channel.name
                channel_id = after.channel.id
            elif before.channel and not after.channel:
                event_type = 'leave'
                channel_name = before.channel.name
                channel_id = before.channel.id
            elif before.channel and after.channel and before.channel.id != after.channel.id:
                event_type = 'move'
                channel_name = after.channel.name
                channel_id = after.channel.id
            
            # 2. Server Mute/Deaf (Mod Actions)
            # We treat these as 'moderation' logs usually, or 'voice' logs?
            # User asked for "mod logs(kick timeout/mute)". 
            # If we send to 'moderation', it uses batch_generic_events (Generic Embed).
            # If we send to 'voice', it uses batch_voice_events (Green/Red embeds).
            # Let's send to 'voice' for now as it matches the event source.
            
            if after.channel:
                channel_name = after.channel.name
                channel_id = after.channel.id

            if before.mute != after.mute:
                event_type = 'server_mute' if after.mute else 'server_unmute'
            elif before.deaf != after.deaf:
                event_type = 'server_deaf' if after.deaf else 'server_undeaf'

            if event_type:
                data = {
                    'type': event_type, 'user_id': member.id, 'user_name': member.display_name, 'user_mention': member.mention,
                    'channel_name': channel_name, 'channel_mention': f"<#{channel_id}>" if channel_id else "Unknown",
                    'before_channel': before.channel.name if before.channel else None,
                    'before_channel_mention': before.channel.mention if before.channel else None,
                    'after_channel': after.channel.name if after.channel else None,
                    'after_channel_mention': after.channel.mention if after.channel else None,
                    'timestamp': now,
                    'avatar_url': member.display_avatar.url
                }
                self.queue_event(member.guild.id, 'voice', data)
        except: pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            # Fetch audit log once for the set of changes
            executor = None
            try:
                entry = await self.get_audit_log_entry(after.guild, discord.AuditLogAction.member_role_update, after)
                if entry: executor = entry.user
            except: pass
            
            executor_data = {'id': executor.id, 'name': executor.name} if executor else None

            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            for r in added:
                self.queue_event(after.guild.id, 'roles', {
                    'type': 'role_update', 'subtype': 'add', 'user_id': after.id, 
                    'user_name': after.display_name, 'role_name': r.name, 'role_id': r.id, 'role_mention': r.mention,
                    'executor': executor_data
                })

            # Check for Timeout (Communication Disabled)
            if before.timed_out_until != after.timed_out_until:
                if after.timed_out_until:
                    # Timeout Added
                    entry = await self.get_audit_log_entry(after.guild, discord.AuditLogAction.member_update, after)
                    executor = entry.user if entry else None
                    reason = entry.reason if entry else "No reason provided"
                    duration = after.timed_out_until - datetime.datetime.now(datetime.timezone.utc)
                    
                    data = {
                        'description': f"**{after.mention}** has been timed out for {str(duration).split('.')[0]}.\n**Reason:** {reason}\n**Moderator:** {executor.mention if executor else 'Unknown'}"
                    }
                    self.queue_event(after.guild.id, 'moderation', data)
                    asyncio.create_task(self.log_to_history(after.guild.id, "moderation", "timeout", after.id, None, f"Timed out by {executor.name if executor else 'Unknown'}"))
                else:
                    # Timeout Removed
                    entry = await self.get_audit_log_entry(after.guild, discord.AuditLogAction.member_update, after)
                    executor = entry.user if entry else None
                    data = {
                        'description': f"**{after.mention}** timeout has been removed.\n**Moderator:** {executor.mention if executor else 'Unknown'}"
                    }
                    self.queue_event(after.guild.id, 'moderation', data)
                    asyncio.create_task(self.log_to_history(after.guild.id, "moderation", "untimeout", after.id, None, f"Timeout removed by {executor.name if executor else 'Unknown'}"))
            for r in removed:
                self.queue_event(after.guild.id, 'roles', {
                    'type': 'role_update', 'subtype': 'remove', 'user_id': after.id, 
                    'user_name': after.display_name, 'role_name': r.name, 'role_id': r.id, 'role_mention': r.mention,
                    'executor': executor_data
                })

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild: return
        try:
            # Aesthetic: Message sent by @ZENOOX was deleted in #voice-log
            # Message content: ...
            desc = f"Message sent by {message.author.mention} was deleted in {message.channel.mention}"
            
            embed_dict = {  
                # Visuals: Just a clean embed with content
                # Author of embed: user? No, screenshot shows "zenoxxfromhell" as author. Wait, that's the bot/webhook or the user?
                # Screenshot 2: "zenoxxfromhell" (the user?) "Message sent by @ZENOOX was deleted in #voice-log"
                # It seems the embed AUTHOR is the user who sent the message.
                'author': {'name': message.author.name, 'icon_url': message.author.display_avatar.url},
                'description': desc,
                'color': 0xe74c3c, # Red/Orange
                'fields': [],
                'footer': {'text': f"Author: {message.author.id}, Message Id: {message.id} • {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}"}
            }
            content = message.content
            if not content and message.attachments: content = "*(Attachment only)*"
            elif not content: content = "*(No content)*"
            
            embed_dict['fields'].append({'name': 'Message content:', 'value': content[:1000], 'inline': False})
            
            self.queue_event(message.guild.id, 'messages', {'embed_data': embed_dict})
            asyncio.create_task(self.log_to_history(message.guild.id, "messages", "delete", message.author.id, message.channel.id))
        except: pass

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        try:
            changes = []
            if before.name != after.name:
                changes.append(f"**Name:** {before.name} -> {after.name}")
            if before.color != after.color:
                changes.append(f"**Color:** {before.color} -> {after.color}")
            if before.hoist != after.hoist:
                changes.append(f"**Hoist:** {before.hoist} -> {after.hoist}")
            if before.mentionable != after.mentionable:
                changes.append(f"**Mentionable:** {before.mentionable} -> {after.mentionable}")
                
            if changes:
                entry = await self.get_audit_log_entry(after.guild, discord.AuditLogAction.role_update, after)
                executor = entry.user if entry else None
                
                desc = "\n".join(changes)
                
                # We reuse 'role_update' type but maybe generic 'update' subtype to handle description?
                # batch_role_events handles 'color_change' specifically. 
                # Let's use 'role_edit' and handle it in batch_role_events or just use Generic Embed Data.
                # Actually batch_generic_events handles embeds if 'embed_data' is present.
                # But 'roles' log type uses batch_role_events.
                # Let's construct a full embed data here and bypass batch_role_events specific logic if possible,
                # OR update batch_role_events to handle 'edit'.
                # batch_role_events: iterate events. if subtype not add/remove -> assumes color_change?
                # Let's look at batch_role_events (Line 368):
                # if e['subtype'] == 'color_change': ...
                # elif e['subtype'] == 'create': ...
                # elif e['subtype'] == 'delete': ...
                # So if I use 'edit', it will be ignored unless I update batch_role_events.
                
                # Plan: Use 'embed_data' field in event. batch_role_events MIGHT not check for embed_data.
                # batch_generic_events DOES check for embed_data.
                # Log type is 'roles'. process_guild_queue calls batch_role_events.
                # So I MUST update batch_role_events OR update ensure batch_role_events handles embed_data.
                
                # Let's update batch_role_events to fallback to embed_data or handle 'edit'.
                # For now, I'll stick to updating on_guild_role_update and then I'll update batch_role_events.
                
                data = {
                    'type': 'role_update',
                    'subtype': 'edit',
                    'role_id': after.id,
                    'role_name': after.name,
                    'role_mention': after.mention,
                    'changes': changes,
                    'executor_mention': executor.mention if executor else "Unknown",
                    'timestamp': time.time()
                }
                self.queue_event(after.guild.id, 'roles', data)
        except: pass

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        try:
            entry = await self.get_audit_log_entry(role.guild, discord.AuditLogAction.role_create, role)
            executor = entry.user if entry else None
            data = {
                'type': 'role_update', 'subtype': 'create',
                'role_id': role.id, 'role_name': role.name, 'role_mention': role.mention,
                'executor_mention': executor.mention if executor else "Unknown", 'timestamp': time.time()
            }
            self.queue_event(role.guild.id, 'roles', data)
        except: pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        try:
            entry = await self.get_audit_log_entry(role.guild, discord.AuditLogAction.role_delete, role)
            executor = entry.user if entry else None
            data = {
                'type': 'role_update', 'subtype': 'delete',
                'role_id': role.id, 'role_name': role.name,
                'executor_mention': executor.mention if executor else "Unknown", 'timestamp': time.time()
            }
            self.queue_event(role.guild.id, 'roles', data)
        except: pass

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild: return
        if before.content == after.content: return
        try:
            desc = f"Message edited in {before.channel.mention} [Jump to Message]({after.jump_url})"
            embed_dict = {
                'title': f"{EDIT_EMOJI} Message Edited", 'description': desc, 'color': 0x3498db,
                'fields': [
                    {'name': 'Before', 'value': (before.content[:900] + "...") if before.content else "*(No content)*", 'inline': False},
                    {'name': 'After', 'value': (after.content[:900] + "...") if after.content else "*(No content)*", 'inline': False}
                ],
                'footer': {'text': f"ID: {before.author.id}"}, 'author': {'name': before.author.display_name, 'icon_url': before.author.display_avatar.url}
            }
            self.queue_event(before.guild.id, 'messages', {'embed_data': embed_dict})
            asyncio.create_task(self.log_to_history(before.guild.id, "messages", "edit", before.author.id, before.channel.id))
        except: pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        try:
            entry = await self.get_audit_log_entry(channel.guild, discord.AuditLogAction.channel_create, channel)
            executor = entry.user if entry else None

            embed_dict = {
                'title': "Channel Created", 
                'color': 0x2ecc71,
                'fields': [
                    {'name': 'Name', 'value': channel.mention, 'inline': True},
                    {'name': 'Type', 'value': str(channel.type).capitalize(), 'inline': True},
                    {'name': 'Category', 'value': channel.category.mention if channel.category else "None", 'inline': True},
                    {'name': 'Created By', 'value': f"{executor.mention} (`{executor.id}`)" if executor else "Unknown", 'inline': False}
                ],
                'footer': {'text': f"Channel ID: {channel.id}"},
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            self.queue_event(channel.guild.id, 'channels', {'embed_data': embed_dict})
            asyncio.create_task(self.log_to_history(channel.guild.id, "channels", "create", None, channel.id, f"Channel {channel.name} created"))
        except: pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        try:
            entry = await self.get_audit_log_entry(channel.guild, discord.AuditLogAction.channel_delete, channel)
            executor = entry.user if entry else None

            # Deleted channels can't be mentioned, so we visually simulate it: #name
            name_display = f"#{channel.name}" if hasattr(channel, 'name') and str(channel.type) in ('text', 'voice', 'stage', 'forum', 'news') else channel.name

            embed_dict = {
                'title': "Channel Deleted", 
                'color': 0xe74c3c,
                'fields': [
                    {'name': 'Name', 'value': name_display, 'inline': True},
                    {'name': 'Type', 'value': str(channel.type).capitalize(), 'inline': True},
                    {'name': 'Category', 'value': channel.category.mention if channel.category else "None", 'inline': True},
                    {'name': 'Deleted By', 'value': f"{executor.mention} (`{executor.id}`)" if executor else "Unknown", 'inline': False}
                ],
                'footer': {'text': f"Channel ID: {channel.id}"},
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            self.queue_event(channel.guild.id, 'channels', {'embed_data': embed_dict})
            asyncio.create_task(self.log_to_history(channel.guild.id, "channels", "delete", None, channel.id, f"Channel {channel.name} deleted"))
        except: pass

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        try:
            if before.name == after.name and before.category == after.category: return
            
            entry = await self.get_audit_log_entry(after.guild, discord.AuditLogAction.channel_update, after)
            executor = entry.user if entry else None

            fields = [
                {'name': 'Channel', 'value': f"{after.mention} (`{after.id}`)", 'inline': False},
                {'name': 'Updated By', 'value': f"{executor.mention} (`{executor.id}`)" if executor else "Unknown", 'inline': False}
            ]

            if before.name != after.name: 
                fields.append({'name': 'Name Update', 'value': f"**Before:** #{before.name}\n**After:** {after.mention}", 'inline': True})
            if before.category != after.category: 
                before_cat = before.category.mention if before.category else "None"
                after_cat = after.category.mention if after.category else "None"
                fields.append({'name': 'Category Update', 'value': f"**Before:** {before_cat}\n**After:** {after_cat}", 'inline': True})

            embed_dict = {
                'title': "Channel Updated", 
                'color': 0x3498db,
                'fields': fields,
                'footer': {'text': f"Channel ID: {after.id}"},
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            self.queue_event(after.guild.id, 'channels', {'embed_data': embed_dict})
        except: pass

    async def get_audit_log_entry(self, guild, action, target):
        """Helper to fetch the most recent relevant audit log entry"""
        try:
            if not guild.me.guild_permissions.view_audit_log: return None
            async for entry in guild.audit_logs(limit=3, action=action):
                if entry.target.id == target.id:
                    # Check transparency: entry should be recent (within 10s)
                    if (datetime.datetime.now(datetime.timezone.utc) - entry.created_at).total_seconds() < 20:
                        return entry
            return None
        except: return None

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        try:
             entry = await self.get_audit_log_entry(after, discord.AuditLogAction.guild_update, after)
             executor = entry.user if entry else None
             changes = []
             if before.name != after.name: changes.append(f"**Name:** {before.name} -> {after.name}")
             if before.icon != after.icon: changes.append(f"**Icon:** [Old]({before.icon.url if before.icon else 'None'}) -> [New]({after.icon.url if after.icon else 'None'})")
             if before.banner != after.banner: changes.append(f"**Banner:** [Old]({before.banner.url if before.banner else 'None'}) -> [New]({after.banner.url if after.banner else 'None'})")
             
             if changes:
                 desc = f"Server updated by {executor.mention if executor else 'Unknown'}\n" + "\n".join(changes)
                 self.queue_event(after.id, 'server', {'description': desc})
        except: pass

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        try:
            # Better to check diff
            added = [e for e in after if e not in before]
            removed = [e for e in before if e not in after]
            
            if added:
                desc = f"**Emojis Added:** " + ", ".join([str(e) for e in added])
                self.queue_event(guild.id, 'server', {'description': desc})
            if removed:
                desc = f"**Emojis Removed:** " + ", ".join([e.name for e in removed])
                self.queue_event(guild.id, 'server', {'description': desc})
        except: pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        try:
            entry = await self.get_audit_log_entry(guild, discord.AuditLogAction.ban, user)
            executor = entry.user if entry else None
            reason = entry.reason if entry else "No reason provided"
            
            embed_dict = {
                'title': "Member Banned", 
                'color': 0xe74c3c, # Red
                'thumbnail': {'url': user.display_avatar.url},
                'fields': [
                    {'name': '👤 User', 'value': f"{user.mention} (`{user.id}`)", 'inline': True},
                    {'name': '🛡️ Moderator', 'value': f"{executor.mention} (`{executor.id}`)" if executor else "Unknown", 'inline': True},
                    {'name': '📝 Reason', 'value': reason, 'inline': False}
                ],
                'footer': {'text': f"User ID: {user.id} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            self.queue_event(guild.id, 'bans', {'embed_data': embed_dict})
            asyncio.create_task(self.log_to_history(guild.id, "bans", "ban", user.id, None, f"{user.name} banned by {executor.name if executor else 'Unknown'}"))
        except: pass

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        try:
            entry = await self.get_audit_log_entry(guild, discord.AuditLogAction.unban, user)
            executor = entry.user if entry else None
            reason = entry.reason if entry else "No reason provided"

            embed_dict = {
                'title': "Member Unbanned", 
                'color': 0x2ecc71, # Green
                'thumbnail': {'url': user.display_avatar.url},
                'fields': [
                    {'name': '👤 User', 'value': f"{user.mention} (`{user.id}`)", 'inline': True},
                    {'name': '🛡️ Moderator', 'value': f"{executor.mention} (`{executor.id}`)" if executor else "Unknown", 'inline': True},
                    {'name': '📝 Reason', 'value': reason, 'inline': False}
                ],
                'footer': {'text': f"User ID: {user.id}"},
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            self.queue_event(guild.id, 'bans', {'embed_data': embed_dict})
            asyncio.create_task(self.log_to_history(guild.id, "bans", "unban", user.id, None, f"{user.name} unbanned by {executor.name if executor else 'Unknown'}"))
        except: pass

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           🎮 PREFIX COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.group(name='logging', invoke_without_command=True, aliases=['logs'])
    @commands.has_permissions(administrator=True)
    async def prefix_log_group(self, ctx):
        embed = self.create_embed("Scyro Logging System", f"{LOG_EMOJI} **Advanced System**\n\n`{ctx.prefix}logs setup` - Interactive Setup\n`{ctx.prefix}logs config` - View Config\n`{ctx.prefix}logs reset` - Reset Config", 0x3498db, LOG_EMOJI)
        await ctx.reply(embed=embed)

    @prefix_log_group.command(name='setup')
    @commands.has_permissions(administrator=True)
    async def prefix_logs_setup(self, ctx):
        # We need to bridge between Context and Interaction-based views
        # Create a mock interaction-like object for the view IF the view depends on .user 
        # But wait, LogSetupView expects `initial_int` to check user. 
        # We can construct the view with the Context object but we need to adapt the view slightly or
        # create a wrapper. 
        # Actually, let's just modify the Views to accept either Context OR Interaction.
        
        # Hack to make the view work for both:
        class ContextAdapter:
            def __init__(self, ctx): self.user = ctx.author; self.guild = ctx.guild

        embed = self.create_embed(
            "Logging Setup", 
            f"Click **Auto Setup** below to automatically create and configure all logging channels in a dedicated category.\n\n{INFO_EMOJI} *This will create 8 new channels.*",
            0x5865F2, SETTINGS_EMOJI
        )
        view = self.LogSetupView(self, ContextAdapter(ctx))
        view.message = await ctx.reply(embed=embed, view=view)

    @prefix_log_group.command(name='config')
    @commands.has_permissions(administrator=True)
    async def prefix_logs_config(self, ctx):
        settings = await self.get_all_log_settings(ctx.guild.id)
        if not settings: 
            return await ctx.reply(embed=self.create_embed("No Configuration", f"Logging is not set up. Use `{ctx.prefix}logs setup`.", 0xE74C3C, WARNING_EMOJI))
        
        embed = self.create_embed(f"Logging Configuration", f"**Server:** {ctx.guild.name}\n**Status:** {ONLINE_EMOJI} Active", 0x2b2d31, SETTINGS_EMOJI)
        
        log_map = {
            "messages": MESSAGE_EMOJI, "members": MEMBER_EMOJI, "voice": VOICE_EMOJI, 
            "roles": ROLE_EMOJI, "channels": CHANNEL_EMOJI, "bans": BAN_EMOJI,
            "moderation": MODERATION_EMOJI, "server": SERVER_EMOJI
        }
        
        description = []
        for ltype, emoji in log_map.items():
            cid = settings.get(ltype)
            status = f"{OFFLINE_EMOJI} Disabled"
            if cid:
                ch = ctx.guild.get_channel(cid)
                if ch: status = f"{ONLINE_EMOJI} {ch.mention}"
                else: status = f"{WARNING_EMOJI} *Channel Deleted*"
            description.append(f"{emoji} **{ltype.title()}:** {status}")
            
        embed.description += "\n\n" + "\n".join(description)
        await ctx.reply(embed=embed)

    @prefix_log_group.command(name='reset')
    @commands.has_permissions(administrator=True)
    async def prefix_logs_reset(self, ctx):
        class ContextAdapter:
            def __init__(self, ctx): self.user = ctx.author; self.guild = ctx.guild
            
        embed = self.create_embed(
            "⚠️ Confirm Reset", 
            "Are you sure you want to **delete all logging channels** and **reset configuration**?\n\nThis action cannot be undone.", 
            0xE74C3C, WARNING_EMOJI
        )
        view = self.ConfirmResetView(self, ContextAdapter(ctx))
        view.message = await ctx.reply(embed=embed, view=view)


    # ═══════════════════════════════════════════════════════════════════════════════
    #                           🎮 SLASH COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════════

    class LogSetupView(discord.ui.View):
        def __init__(self, cog, initial_int):
            super().__init__(timeout=180)
            self.cog = cog
            self.initial_int = initial_int

        @discord.ui.button(label="Auto Setup", style=discord.ButtonStyle.success, emoji="✨")
        async def auto_setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user != self.initial_int.user:
                return await interaction.response.send_message(f"❌ You don't own this interaction.", ephemeral=True)
            
            await interaction.response.defer()
            try:
                # Use Mock Context for compatibility
                class MockCtx:
                    def __init__(self, i): self.guild = i.guild 
                
                await self.cog._perform_auto_setup(MockCtx(interaction), interaction.user)
                
                embed = self.cog.create_embed(
                    "Setup Complete", 
                    f"{SUCCESS_EMOJI} **All logging channels have been created!**\n\nYou can now view them in the `Scyro Logs` category.",
                    0x57F287, SUCCESS_EMOJI
                )
                for child in self.children: child.disabled = True
                await interaction.edit_original_response(embed=embed, view=self)
            except Exception as e:
                await interaction.followup.send(f"{ERROR_EMOJI} Setup failed: {str(e)}")

    class ConfirmResetView(discord.ui.View):
        def __init__(self, cog, initial_int):
            super().__init__(timeout=60)
            self.cog = cog
            self.initial_int = initial_int

        @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
        async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user != self.initial_int.user:
                return await interaction.response.send_message("❌ Not authorized.", ephemeral=True)
            
            await interaction.response.defer()
            await self.cog.cleanup_created_resources(interaction.guild.id)
            try:
                await self.cog.settings.delete_one({"guild_id": interaction.guild.id})
            except Exception as e:
                print(f"Error resetting logging config: {e}")

            embed = self.cog.create_embed("Reset Complete", "All logging configuration and channels have been deleted.", 0xe74c3c, DELETE_EMOJI)
            for child in self.children: child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user != self.initial_int.user:
                return await interaction.response.send_message("❌ Not authorized.", ephemeral=True)
            await interaction.response.send_message("Reset cancelled.", ephemeral=True)
            self.stop()


    logs_group = app_commands.Group(name="logging", description="Advanced Logging Management")

    @logs_group.command(name="setup", description="Interactive setup for logging channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_setup(self, interaction: discord.Interaction):
        embed = self.create_embed(
            "Logging Setup", 
            f"Click **Auto Setup** below to automatically create and configure all logging channels in a dedicated category.\n\n{INFO_EMOJI} *This will create 8 new channels.*",
            0x5865F2, SETTINGS_EMOJI
        )
        await interaction.response.send_message(embed=embed, view=self.LogSetupView(self, interaction))

    @logs_group.command(name="config", description="View current logging configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_config(self, interaction: discord.Interaction):
        settings = await self.get_all_log_settings(interaction.guild.id)
        if not settings: 
            return await interaction.response.send_message(
                embed=self.create_embed("No Configuration", "Logging is not set up. Use `/logging setup`.", 0xE74C3C, WARNING_EMOJI), 
                ephemeral=True
            )
        
        embed = self.create_embed(f"Logging Configuration", f"**Server:** {interaction.guild.name}\n**Status:** {ONLINE_EMOJI} Active", 0x2b2d31, SETTINGS_EMOJI)
        
        # Log Types to Emoji Map
        log_map = {
            "messages": MESSAGE_EMOJI, "members": MEMBER_EMOJI, "voice": VOICE_EMOJI, 
            "roles": ROLE_EMOJI, "channels": CHANNEL_EMOJI, "bans": BAN_EMOJI,
            "moderation": MODERATION_EMOJI, "server": SERVER_EMOJI
        }
        
        description = []
        for ltype, emoji in log_map.items():
            cid = settings.get(ltype)
            status = f"{OFFLINE_EMOJI} Disabled"
            if cid:
                ch = interaction.guild.get_channel(cid)
                if ch:
                    status = f"{ONLINE_EMOJI} {ch.mention}"
                else:
                    status = f"{WARNING_EMOJI} *Channel Deleted*"
            description.append(f"{emoji} **{ltype.title()}:** {status}")
            
        embed.description += "\n\n" + "\n".join(description)
        await interaction.response.send_message(embed=embed)

    @logs_group.command(name="reset", description="Reset all logging configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def logs_reset(self, interaction: discord.Interaction):
        embed = self.create_embed(
            "⚠️ Confirm Reset", 
            "Are you sure you want to **delete all logging channels** and **reset configuration**?\n\nThis action cannot be undone.", 
            0xE74C3C, WARNING_EMOJI
        )
        await interaction.response.send_message(embed=embed, view=self.ConfirmResetView(self, interaction), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Logging(bot))
