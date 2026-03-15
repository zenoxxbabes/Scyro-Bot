import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import re
import unicodedata
import json
from datetime import timedelta, datetime
import difflib
import logging
from typing import Optional, List
import hashlib
from utils.Tools import *
import os

class PunishmentConfigView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.settings = {}

    @discord.ui.select(
        placeholder="🎯 Select punishment type for violations...",
        options=[
            discord.SelectOption(
                label="Warning Only",
                value="warn",
                description="Send warning message without punishment",
                emoji="⚠️"
            ),
            discord.SelectOption(
                label="Timeout (Mute)",
                value="timeout",
                description="Temporarily timeout violating users",
                emoji="🔇"
            ),
            discord.SelectOption(
                label="Kick from Server",
                value="kick", 
                description="Kick users who violate rules",
                emoji="👢"
            ),
            discord.SelectOption(
                label="Temporary Ban",
                value="tempban",
                description="Temporarily ban violating users",
                emoji="🔨"
            ),
            discord.SelectOption(
                label="Permanent Ban",
                value="ban",
                description="Permanently ban violating users",
                emoji="⛔"
            )
        ]
    )
    async def punishment_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can use this!", ephemeral=True)
            return

        self.settings['punishment_type'] = select.values[0]
        
        # Update the view based on selection
        await self.update_view(interaction)

    @discord.ui.select(
        placeholder="⏰ Select punishment duration...",
        options=[
            discord.SelectOption(label="5 Minutes", value="300", emoji="⏱️"),
            discord.SelectOption(label="15 Minutes", value="900", emoji="⏱️"),
            discord.SelectOption(label="30 Minutes", value="1800", emoji="⏱️"),
            discord.SelectOption(label="1 Hour", value="3600", emoji="🕐"),
            discord.SelectOption(label="3 Hours", value="10800", emoji="🕒"),
            discord.SelectOption(label="6 Hours", value="21600", emoji="🕕"),
            discord.SelectOption(label="12 Hours", value="43200", emoji="🕛"),
            discord.SelectOption(label="24 Hours", value="86400", emoji="📅"),
            discord.SelectOption(label="7 Days", value="604800", emoji="📅"),
            discord.SelectOption(label="Permanent", value="0", emoji="♾️")
        ]
    )
    async def duration_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can use this!", ephemeral=True)
            return

        self.settings['duration'] = int(select.values[0])
        await self.update_view(interaction)

    @discord.ui.select(
        placeholder="🔍 Select word recognition sensitivity...",
        options=[
            discord.SelectOption(
                label="Low Sensitivity",
                value="low",
                description="Only exact matches (0.95 similarity)",
                emoji="🟢"
            ),
            discord.SelectOption(
                label="Medium Sensitivity", 
                value="medium",
                description="Moderate detection (0.80 similarity)",
                emoji="🟡"
            ),
            discord.SelectOption(
                label="High Sensitivity",
                value="high", 
                description="Strict detection (0.65 similarity)",
                emoji="🔴"
            ),
            discord.SelectOption(
                label="Maximum Sensitivity",
                value="maximum",
                description="Very strict detection (0.50 similarity)",
                emoji="⚫"
            )
        ]
    )
    async def sensitivity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can use this!", ephemeral=True)
            return

        sensitivity_map = {
            "low": 0.95,
            "medium": 0.80, 
            "high": 0.65,
            "maximum": 0.50
        }
        
        self.settings['sensitivity'] = select.values[0]
        self.settings['similarity_threshold'] = sensitivity_map[select.values[0]]
        await self.update_view(interaction)

    @discord.ui.button(label="💾 Save Configuration", style=discord.ButtonStyle.success, row=4)
    async def save_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can use this!", ephemeral=True)
            return

        if len(self.settings) < 2:  # At minimum need punishment_type and sensitivity
            await interaction.response.send_message(
                "❌ **Incomplete Configuration**\nPlease select punishment type and sensitivity level!", 
                ephemeral=True
            )
            return

        # Set default duration if not set for punishments that don't need it
        if 'duration' not in self.settings:
            if self.settings['punishment_type'] in ['warn', 'kick', 'ban']:
                self.settings['duration'] = 0
            else:
                self.settings['duration'] = 300  # Default 5 minutes

        # Save to database with proper error handling
        try:
            # Ensure guild exists in database first
            await self.cog.ensure_guild_settings(self.guild_id)
            
            # Now update the settings
            await self.cog.settings_collection.update_one(
                {"guild_id": self.guild_id},
                {"$set": {
                    "punishment_type": self.settings['punishment_type'],
                    "punishment_duration": self.settings['duration'],
                    "sensitivity_level": self.settings['sensitivity'],
                    "similarity_threshold": self.settings['similarity_threshold']
                }},
                upsert=True
            )

            # Success embed
            embed = discord.Embed(
                title="✅ **Configuration Saved Successfully!**",
                description="Punishment settings have been updated and are now active!",
                color=self.cog.success_color,
                timestamp=discord.utils.utcnow()
            )

            punishment_names = {
                "warn": "Warning Only",
                "timeout": "Timeout (Mute)", 
                "kick": "Kick from Server",
                "tempban": "Temporary Ban",
                "ban": "Permanent Ban"
            }

            duration_text = "Permanent" if self.settings['duration'] == 0 else self.format_duration(self.settings['duration'])
            
            embed.add_field(
                name="⚡ **Punishment Type**",
                value=punishment_names.get(self.settings['punishment_type'], self.settings['punishment_type']),
                inline=True
            )
            
            embed.add_field(
                name="⏰ **Duration**", 
                value=duration_text,
                inline=True
            )
            
            embed.add_field(
                name="🔍 **Sensitivity**",
                value=f"{self.settings['sensitivity'].title()} ({self.settings['similarity_threshold']})",
                inline=True
            )

            embed.set_footer(text="Settings are now active and will be applied to new violations")
            
            # Disable all components
            for item in self.children:
                item.disabled = True

            await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logging.error(f"[Blacklist] Error saving punishment config: {e}")
            await interaction.response.send_message(
                f"❌ **Database Error!**\n``````\nTry running the command again to fix database schema.",
                ephemeral=True
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=4)
    async def cancel_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can use this!", ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ **Configuration Cancelled**",
            description="No changes have been made to punishment settings.",
            color=self.cog.error_color
        )
        
        for item in self.children:
            item.disabled = True
            
        await interaction.response.edit_message(embed=embed, view=self)

    async def update_view(self, interaction):
        # Create updated embed showing current selections
        embed = discord.Embed(
            title="⚙️ **Punishment Configuration**",
            description="Configure how violations are handled in your server",
            color=self.cog.embed_color,
            timestamp=discord.utils.utcnow()
        )

        if 'punishment_type' in self.settings:
            punishment_names = {
                "warn": "⚠️ Warning Only",
                "timeout": "🔇 Timeout (Mute)",
                "kick": "👢 Kick from Server", 
                "tempban": "🔨 Temporary Ban",
                "ban": "⛔ Permanent Ban"
            }
            embed.add_field(
                name="⚡ **Selected Punishment**",
                value=punishment_names.get(self.settings['punishment_type'], self.settings['punishment_type']),
                inline=True
            )

        if 'duration' in self.settings:
            duration_text = "Permanent" if self.settings['duration'] == 0 else self.format_duration(self.settings['duration'])
            embed.add_field(
                name="⏰ **Selected Duration**",
                value=duration_text,
                inline=True
            )

        if 'sensitivity' in self.settings:
            sensitivity_names = {
                "low": "🟢 Low Sensitivity",
                "medium": "🟡 Medium Sensitivity",
                "high": "🔴 High Sensitivity", 
                "maximum": "⚫ Maximum Sensitivity"
            }
            embed.add_field(
                name="🔍 **Selected Sensitivity**",
                value=sensitivity_names.get(self.settings['sensitivity'], self.settings['sensitivity']),
                inline=True
            )

        # Show which options are still needed
        needed = []
        if 'punishment_type' not in self.settings:
            needed.append("Punishment Type")
        if 'duration' not in self.settings and self.settings.get('punishment_type') in ['timeout', 'tempban']:
            needed.append("Duration") 
        if 'sensitivity' not in self.settings:
            needed.append("Sensitivity Level")

        if needed:
            embed.add_field(
                name="📝 **Still Needed**",
                value="• " + "\n• ".join(needed),
                inline=False
            )

        # Hide duration selector for punishments that don't need it
        if 'punishment_type' in self.settings:
            duration_select = self.children[1]  # Second select menu
            if self.settings['punishment_type'] in ['warn', 'kick', 'ban']:
                duration_select.disabled = True
                if self.settings['punishment_type'] == 'ban':
                    self.settings['duration'] = 0  # Permanent
                else:
                    self.settings['duration'] = 0  # No duration needed
            else:
                duration_select.disabled = False

        embed.set_footer(text="Select from the dropdowns below to configure punishment settings")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            await interaction.edit_original_response(embed=embed, view=self)

    def format_duration(self, seconds):
        if seconds == 0:
            return "Permanent"
        elif seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            return f"{seconds // 3600} hours"
        else:
            return f"{seconds // 86400} days"

    async def on_timeout(self):
        # Disable all components when timeout occurs
        for item in self.children:
            item.disabled = True

class Blacklist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.embed_color = 0x9B59B6  # Professional purple
        self.success_color = 0x00FF7F  # Spring green
        self.warning_color = 0xFFD700  # Gold
        self.error_color = 0xFF4500   # Red-orange
        self.info_color = 0x87CEEB    # Sky blue
        
        # Advanced filtering settings
        self.similarity_threshold = 0.75
        self.max_repeating_chars = 4
        self.zalgo_threshold = 3
        
        # Punishment escalation system
        self.punishment_levels = {
            1: {"action": "warn", "duration": None, "description": "Warning"},
            2: {"action": "warn", "duration": None, "description": "Second Warning"},
            3: {"action": "timeout", "duration": 300, "description": "5-minute timeout"},
            4: {"action": "timeout", "duration": 1800, "description": "30-minute timeout"},
            5: {"action": "timeout", "duration": 3600, "description": "1-hour timeout"},
            6: {"action": "kick", "duration": None, "description": "Temporary kick"},
            7: {"action": "ban", "duration": 86400, "description": "24-hour ban"}
        }
        
        # Leetspeak and variation mapping
        self.leetspeak_map = {
            '4': 'a', '@': 'a', '3': 'e', '1': 'i', '!': 'i',
            '0': 'o', '5': 's', '$': 's', '7': 't', '+': 't',
            '2': 'z', '8': 'b', '6': 'g', '9': 'g'
        }

        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        
        # Collections
        self.words_collection = None
        self.bypass_users_collection = None
        self.bypass_roles_collection = None
        self.strikes_collection = None
        self.logs_collection = None
        self.whitelist_collection = None
        self.settings_collection = None
        self.exempt_channels_collection = None
        
        self.bot.loop.create_task(self.init_db())

    # ================= DATABASE INITIALIZATION WITH MIGRATION =================
    async def init_db(self):
        """Initialize MongoDB collections and indexes"""
        if not self.mongo_uri:
            logging.error("[Blacklist] MONGO_URI not found!")
            return

        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            self.db = self.client.get_default_database()
            
            # Initialize collections
            self.words_collection = self.db.blacklist_words
            self.bypass_users_collection = self.db.blacklist_bypass_users
            self.bypass_roles_collection = self.db.blacklist_bypass_roles
            self.strikes_collection = self.db.blacklist_strikes
            self.logs_collection = self.db.blacklist_logs
            self.whitelist_collection = self.db.blacklist_whitelist
            self.settings_collection = self.db.blacklist_settings
            self.exempt_channels_collection = self.db.blacklist_exempt_channels

            # Create Indexes
            await self.words_collection.create_index([("guild_id", 1), ("word", 1)], unique=True)
            await self.bypass_users_collection.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
            await self.bypass_roles_collection.create_index([("guild_id", 1), ("role_id", 1)], unique=True)
            await self.strikes_collection.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
            await self.whitelist_collection.create_index([("guild_id", 1), ("word", 1)], unique=True)
            await self.settings_collection.create_index("guild_id", unique=True)
            await self.exempt_channels_collection.create_index([("guild_id", 1), ("channel_id", 1)], unique=True)

            logging.info("[Blacklist] MongoDB collections and indexes initialized!")
            
        except Exception as e:
            logging.error(f"[Blacklist] Database initialization failed: {e}")

    async def ensure_guild_settings(self, guild_id: int):
        """Ensure guild settings exist"""
        if self.settings_collection is None:
            return

        try:
            # Upsert default settings if not exists
            # $setOnInsert ensures we don't overwrite existing settings
            await self.settings_collection.update_one(
                {"guild_id": guild_id},
                {"$setOnInsert": {
                    "auto_punish": True,
                    "similarity_check": True,
                    "leetspeak_filter": True,
                    "zalgo_filter": True,
                    "log_channel": None,
                    "appeal_channel": None,
                    "staff_role": None,
                    "delete_timeout": 5,
                    "max_strikes": 7,
                    "strike_decay_hours": 24,
                    "punishment_type": 'warn',
                    "punishment_duration": 300,
                    "sensitivity_level": 'medium',
                    "similarity_threshold": 0.75
                }},
                upsert=True
            )
        except Exception as e:
            logging.error(f"[Blacklist] Error ensuring guild settings: {e}")

    # ================= ADVANCED TEXT PROCESSING =================
    def normalize_text(self, text: str) -> str:
        """Normalize text for advanced filtering"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove excessive whitespace and special characters
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', '', text)
        
        # Handle leetspeak
        for leet, normal in self.leetspeak_map.items():
            text = text.replace(leet, normal)
        
        # Remove excessive repeated characters
        text = re.sub(r'(.)\1{' + str(self.max_repeating_chars) + ',}', r'\1', text)
        
        return text.strip()

    def detect_zalgo(self, text: str) -> bool:
        """Detect zalgo text (excessive combining characters)"""
        combining_chars = sum(1 for char in text if unicodedata.combining(char))
        return combining_chars > self.zalgo_threshold

    def generate_variations(self, word: str) -> List[str]:
        """Generate common variations of a word"""
        variations = [word]
        
        # Add spaces between characters
        variations.append(' '.join(word))
        
        # Add dots/periods
        variations.append('.'.join(word))
        
        # Add underscores
        variations.append('_'.join(word))
        
        # Character substitutions
        char_subs = {
            'a': ['@', '4'], 'e': ['3'], 'i': ['1', '!'], 'o': ['0'],
            's': ['5', '$'], 't': ['7', '+'], 'l': ['1'], 'g': ['6', '9']
        }
        
        for original, subs in char_subs.items():
            for sub in subs:
                variations.append(word.replace(original, sub))
        
        return list(set(variations))

    # ================= GUILD SETTINGS MANAGEMENT =================
    async def get_guild_settings(self, guild_id: int) -> dict:
        """Get guild-specific settings"""
        if self.settings_collection is None:
            return {}

        try:
            # Ensure guild settings exist first
            await self.ensure_guild_settings(guild_id)
            
            doc = await self.settings_collection.find_one({"guild_id": guild_id})
            if doc:
                return doc
            else:
                # Return default settings as fallback (should not reach here ideally due to ensure above)
                return {
                    'guild_id': guild_id,
                    'auto_punish': True,
                    'similarity_check': True,
                    'leetspeak_filter': True,
                    'zalgo_filter': True,
                    'log_channel': None,
                    'appeal_channel': None,
                    'staff_role': None,
                    'delete_timeout': 5,
                    'max_strikes': 7,
                    'strike_decay_hours': 24,
                    'punishment_type': 'warn',
                    'punishment_duration': 300,
                    'sensitivity_level': 'medium',
                    'similarity_threshold': 0.75
                }
        except Exception as e:
            logging.error(f"[Blacklist] Error getting guild settings: {e}")
            return {}

    # ================= ENHANCED VIOLATION HANDLER =================
    # ================= ENHANCED VIOLATION HANDLER =================
    async def log_violation(self, message, matched_word: str, action: str):
        """Log violation to database"""
        if self.logs_collection is None:
            return

        try:
            await self.logs_collection.insert_one({
                "guild_id": message.guild.id,
                "user_id": message.author.id,
                "channel_id": message.channel.id,
                "message_content": message.content[:500],
                "matched_word": matched_word,
                "action_taken": action,
                "timestamp": datetime.utcnow()
            })
        except Exception as e:
            logging.error(f"[Blacklist] Error logging violation: {e}")

    async def handle_advanced_violation(self, message, matched_word: str, severity: int = 1):
        """Advanced violation handling with custom punishments"""
        guild_id = message.guild.id
        user_id = message.author.id
        settings = await self.get_guild_settings(guild_id)
        
        # Delete the offending message
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        # Use custom punishment settings
        punishment_type = settings.get('punishment_type', 'warn')
        punishment_duration = settings.get('punishment_duration', 300)
        
        # Create sophisticated violation embed
        embed = discord.Embed(
            title="🚨 **Content Violation Detected**",
            color=self.warning_color,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="👤 **User**", 
            value=f"{message.author.mention}\n`{message.author.display_name}`", 
            inline=True
        )
        
        embed.add_field(
            name="📍 **Location**", 
            value=f"{message.channel.mention}\n`#{message.channel.name}`", 
            inline=True
        )
        
        embed.add_field(
            name="🔍 **Matched Filter**", 
            value=f"`{matched_word}`", 
            inline=True
        )

        # Determine action description
        action_descriptions = {
            "warn": "⚠️ Warning Issued",
            "timeout": f"🔇 Timed out for {self.format_duration(punishment_duration)}",
            "kick": "👢 Kicked from server",
            "tempban": f"🔨 Banned for {self.format_duration(punishment_duration)}",
            "ban": "⛔ Permanently banned"
        }
        
        embed.add_field(
            name="⚡ **Action Taken**", 
            value=action_descriptions.get(punishment_type, "Action applied"),
            inline=True
        )
        
        embed.add_field(
            name="🎯 **Sensitivity Level**",
            value=f"{settings.get('sensitivity_level', 'medium').title()}",
            inline=True
        )
        
        embed.add_field(
            name="🕒 **Timestamp**",
            value=f"<t:{int(datetime.utcnow().timestamp())}:R>",
            inline=True
        )

        # Add preview of filtered content (censored)
        if len(message.content) > 0:
            censored_content = re.sub(
                re.escape(matched_word), 
                "█" * len(matched_word), 
                message.content[:100], 
                flags=re.IGNORECASE
            )
            if len(message.content) > 100:
                censored_content += "..."
            embed.add_field(
                name="📝 **Message Preview**", 
                value=f"``````", 
                inline=False
            )

        embed.set_footer(
            text=f"Advanced AutoMod • Severity: {severity}",
            icon_url=self.bot.user.display_avatar.url
        )
        
        embed.set_thumbnail(url=message.author.display_avatar.url)

        # Send warning message
        try:
            warning_msg = await message.channel.send(
                embed=embed, 
                delete_after=settings.get('delete_timeout', 5)
            )
        except discord.Forbidden:
            pass

        # Apply custom punishment
        if settings.get('auto_punish', True):
            await self.apply_custom_punishment(message.author, message.guild, punishment_type, punishment_duration)

        # Log to staff channel if configured
        if settings.get('log_channel'):
            await self.send_staff_notification(message, matched_word, punishment_type, settings)

        # Log violation
        await self.log_violation(message, matched_word, punishment_type)

    def format_duration(self, seconds):
        """Format duration in human readable format"""
        if seconds == 0:
            return "Permanent"
        elif seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            return f"{seconds // 3600} hours"
        else:
            return f"{seconds // 86400} days"

    async def apply_custom_punishment(self, member: discord.Member, guild: discord.Guild, punishment_type: str, duration: int):
        """Apply custom punishment based on guild settings"""
        try:
            if punishment_type == "timeout" and duration > 0:
                await member.timeout(
                    timedelta(seconds=duration),
                    reason="Automatic punishment - banned word violation"
                )
            elif punishment_type == "kick":
                await member.kick(reason="Automatic punishment - banned word violation")
            elif punishment_type == "tempban" and duration > 0:
                await member.ban(
                    reason="Automatic punishment - banned word violation",
                    delete_message_days=1
                )
                # Schedule unban
                self.bot.loop.create_task(
                    self.schedule_unban(guild, member, duration)
                )
            elif punishment_type == "ban":
                await member.ban(
                    reason="Automatic punishment - banned word violation",
                    delete_message_days=1
                )
                    
        except discord.Forbidden:
            logging.warning(f"[Blacklist] Insufficient permissions to punish {member}")
        except Exception as e:
            logging.error(f"[Blacklist] Error applying punishment: {e}")

    async def schedule_unban(self, guild: discord.Guild, member: discord.Member, duration: int):
        """Schedule automatic unban"""
        await asyncio.sleep(duration)
        try:
            await guild.unban(member, reason="Automatic unban - temporary punishment expired")
        except:
            pass

    async def send_staff_notification(self, message, matched_word: str, punishment_type: str, settings: dict):
        """Send detailed notification to staff"""
        if not settings.get('log_channel'):
            return
            
        try:
            log_channel = self.bot.get_channel(settings['log_channel'])
            if not log_channel:
                return

            embed = discord.Embed(
                title="📋 **Moderation Action Log**",
                color=self.info_color,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="👤 **User Details**",
                value=(
                    f"**User:** {message.author.mention} (`{message.author.id}`)\n"
                    f"**Account Created:** <t:{int(message.author.created_at.timestamp())}:R>\n"
                    f"**Joined Server:** <t:{int(message.author.joined_at.timestamp())}:R>"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📍 **Incident Details**",
                value=(
                    f"**Channel:** {message.channel.mention}\n"
                    f"**Matched Filter:** `{matched_word}`\n"
                    f"**Action:** {punishment_type.title()}\n"
                    f"**Sensitivity:** {settings.get('sensitivity_level', 'medium').title()}"
                ),
                inline=False
            )
            
            if len(message.content) > 0:
                embed.add_field(
                    name="📝 **Original Message**",
                    value=f"``````",
                    inline=False
                )

            embed.set_footer(text="Advanced AutoMod System")
            embed.set_thumbnail(url=message.author.display_avatar.url)
            
            await log_channel.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error sending staff notification: {e}")

    # ================= ADVANCED MESSAGE FILTER =================
    # ================= ADVANCED MESSAGE FILTER =================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Advanced message filtering with custom sensitivity"""
        if message.author.bot or not message.guild:
            return

        # Skip administrators
        if message.author.guild_permissions.administrator:
            return

        # Ensure collections are initialized
        if self.words_collection is None:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        settings = await self.get_guild_settings(guild_id)

        # Use custom similarity threshold from settings
        similarity_threshold = settings.get('similarity_threshold', 0.75)

        # Check if channel is exempt
        try:
            if await self.exempt_channels_collection.find_one({"guild_id": guild_id, "channel_id": message.channel.id}):
                return
        except Exception:
            pass

        # Check bypass status
        try:
            bypass_user = await self.bypass_users_collection.find_one({"guild_id": guild_id, "user_id": user_id})
            if bypass_user:
                if not bypass_user.get("expires_at") or bypass_user["expires_at"] > datetime.utcnow():
                    return
        except Exception:
            pass

        # Check bypass roles
        try:
            bypass_roles_cursor = self.bypass_roles_collection.find({"guild_id": guild_id})
            bypass_role_ids = [doc["role_id"] async for doc in bypass_roles_cursor]
            if any(role.id in bypass_role_ids for role in message.author.roles):
                return
        except Exception:
            pass

        # Zalgo text detection
        if settings.get('zalgo_filter', True) and self.detect_zalgo(message.content):
            await self.handle_advanced_violation(message, "zalgo_text", 2)
            return

        # Get banned words and whitelist
        try:
            # Fetch all banned words for the guild
            banned_items = []
            async for doc in self.words_collection.find({"guild_id": guild_id}):
                banned_items.append((doc["word"], doc.get("pattern"), doc.get("severity", 1), doc.get("is_regex", False)))

            # Fetch whitelist
            whitelist = []
            async for doc in self.whitelist_collection.find({"guild_id": guild_id}):
                whitelist.append(doc["word"].lower())

            if not banned_items:
                return

            # Normalize message content
            original_content = message.content
            normalized_content = self.normalize_text(original_content) if settings.get('leetspeak_filter', True) else original_content.lower()

            # Check whitelist first
            for whitelisted in whitelist:
                if whitelisted in normalized_content:
                    return

            # Advanced pattern matching with custom sensitivity
            for word, pattern, severity, is_regex in banned_items:
                matched = False
                
                if is_regex and pattern:
                    # Regex pattern matching
                    try:
                        if re.search(pattern, original_content, re.IGNORECASE):
                            matched = True
                            matched_word = word
                    except re.error:
                        continue
                else:
                    # Standard word matching with variations
                    word_lower = word.lower()
                    
                    # Direct match
                    if word_lower in normalized_content:
                        matched = True
                        matched_word = word
                    else:
                        # Similarity matching with custom threshold
                        if settings.get('similarity_check', True):
                            content_words = normalized_content.split()
                            for content_word in content_words:
                                if len(content_word) >= 3:  # Avoid false positives on short words
                                    similarity = difflib.SequenceMatcher(None, word_lower, content_word).ratio()
                                    if similarity >= similarity_threshold:
                                        matched = True
                                        matched_word = word
                                        break
                        
                        # Variation matching
                        if not matched:
                            variations = self.generate_variations(word_lower)
                            for variation in variations:
                                if variation in normalized_content:
                                    matched = True
                                    matched_word = word
                                    break

                if matched:
                    await self.handle_advanced_violation(message, matched_word, severity or 1)
                    return

        except Exception as e:
            logging.error(f"[Blacklist] Error in advanced message filter: {e}")

    # ================= MAIN COMMAND GROUP (SLASH + PREFIX) =================
    # ================= MAIN COMMAND GROUP (SLASH + PREFIX) =================
    @commands.hybrid_group(
        name="banword",
        aliases=["bw", "blacklist"],
        invoke_without_command=True,
        description="Advanced automatic moderation system",
        with_app_command=True
    )
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_guild=True)
    async def banword(self, ctx):
        """Advanced automod management system"""
        settings = await self.get_guild_settings(ctx.guild.id)
        
        # Get statistics
        try:
            if self.words_collection:
                banned_count = await self.words_collection.count_documents({"guild_id": ctx.guild.id})
                bypass_count = await self.bypass_users_collection.count_documents({"guild_id": ctx.guild.id})
                violations_week = await self.logs_collection.count_documents({
                    "guild_id": ctx.guild.id, 
                    "timestamp": {"$gt": datetime.utcnow() - timedelta(days=7)}
                })
            else:
                banned_count = bypass_count = violations_week = 0
        except Exception:
            banned_count = bypass_count = violations_week = 0

        embed = discord.Embed(
            title="🛡️ **Advanced Banword System**",
            description="*Comprehensive content moderation with intelligent filtering*",
            color=self.embed_color,
            timestamp=discord.utils.utcnow()
        )
        
        # System Status
        status_emoji = "🟢" if settings.get('auto_punish', True) else "🟡"
        embed.add_field(
            name=f"{status_emoji} **System Status**",
            value=(
                f"**Status:** {'Active' if settings.get('auto_punish', True) else 'Manual'}\n"
                f"**Filtered Words:** {banned_count:,}\n"
                f"**Bypass Users:** {bypass_count:,}\n"
                f"**Violations (7d):** {violations_week:,}"
            ),
            inline=True
        )
        
        # Current Punishment Settings
        punishment_names = {
            "warn": "⚠️ Warning",
            "timeout": "🔇 Timeout",
            "kick": "👢 Kick",
            "tempban": "🔨 Temp Ban",
            "ban": "⛔ Perm Ban"
        }
        
        embed.add_field(
            name="⚡ **Current Punishment**",
            value=(
                f"**Type:** {punishment_names.get(settings.get('punishment_type', 'warn'), settings.get('punishment_type', 'warn'))}\n"
                f"**Duration:** {self.format_duration(settings.get('punishment_duration', 300))}\n"
                f"**Sensitivity:** {settings.get('sensitivity_level', 'medium').title()}"
            ),
            inline=True
        )
        
        # Features Status
        features = []
        features.append(f"{'✅' if settings.get('similarity_check', True) else '❌'} Similarity Detection")
        features.append(f"{'✅' if settings.get('leetspeak_filter', True) else '❌'} Leetspeak Filter")
        features.append(f"{'✅' if settings.get('zalgo_filter', True) else '❌'} Zalgo Protection")
        
        embed.add_field(
            name="⚙️ **Active Features**",
            value="\n".join(features),
            inline=True
        )

        # Command Categories
        embed.add_field(
            name="📝 **Word Management**",
            value=(
                "`/banword add <word>` - Add banned word\n"
                "`/banword remove <word>` - Remove word\n"
                "`/banword list` - View all words\n"
                "`/banword reset` - Clear all words"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚡ **Punishment Config**",
            value=(
                "`/banword punishment` - Configure punishments\n"
                "Use aliases: `bw punishment`, `bw add`, etc.\n"
                "**Works with both slash and prefix commands!**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👥 **User Management**",
            value=(
                "`/banword bypass add <user>` - Add bypass\n"
                "`/banword bypass remove <user>` - Remove bypass\n"
                "`/banword bypass list` - List bypass users\n"
                "`/banword bypass reset` - Clear bypasses"
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • Advanced AutoMod v2.5 Fixed",
            icon_url=ctx.author.display_avatar.url
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        await ctx.send(embed=embed)

    # ================= NEW PUNISHMENT COMMAND (SLASH + PREFIX) =================
    @banword.command(
        name="punishment",
        aliases=["punish", "config"],
        description="Configure punishment settings with interactive menus",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_punishment(self, ctx):
        """Interactive punishment configuration system"""
        
        # Get current settings
        settings = await self.get_guild_settings(ctx.guild.id)
        
        embed = discord.Embed(
            title="⚙️ **Punishment Configuration**",
            description="Configure how violations are handled in your server using the dropdown menus below",
            color=self.embed_color,
            timestamp=discord.utils.utcnow()
        )
        
        # Show current settings
        punishment_names = {
            "warn": "⚠️ Warning Only",
            "timeout": "🔇 Timeout (Mute)",
            "kick": "👢 Kick from Server",
            "tempban": "🔨 Temporary Ban",
            "ban": "⛔ Permanent Ban"
        }
        
        sensitivity_names = {
            "low": "🟢 Low Sensitivity (0.95)",
            "medium": "🟡 Medium Sensitivity (0.80)",
            "high": "🔴 High Sensitivity (0.65)",
            "maximum": "⚫ Maximum Sensitivity (0.50)"
        }
        
        embed.add_field(
            name="🔧 **Current Settings**",
            value=(
                f"**Punishment:** {punishment_names.get(settings.get('punishment_type', 'warn'), settings.get('punishment_type', 'warn'))}\n"
                f"**Duration:** {self.format_duration(settings.get('punishment_duration', 300))}\n"
                f"**Sensitivity:** {sensitivity_names.get(settings.get('sensitivity_level', 'medium'), settings.get('sensitivity_level', 'medium'))}"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 **Instructions**",
            value=(
                "1. Select your preferred **punishment type**\n"
                "2. Choose **duration** (if applicable)\n"
                "3. Set **detection sensitivity**\n"
                "4. Click **Save Configuration**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔍 **Sensitivity Guide**",
            value=(
                "**Low:** Only exact matches and very similar words\n"
                "**Medium:** Moderate detection with some variations\n"
                "**High:** Strict detection with many variations\n"
                "**Maximum:** Very strict, catches most attempts"
            ),
            inline=False
        )
        
        embed.set_footer(
            text=f"Configuring for {ctx.guild.name} • Use dropdowns below",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else ctx.bot.user.display_avatar.url
        )

        # Create the interactive view
        view = PunishmentConfigView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    # ================= ENHANCED WORD MANAGEMENT (SLASH + PREFIX) =================
    @banword.command(
        name="add", 
        aliases=["a"], 
        description="Add a word to the filter with severity",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_add(self, ctx, word: str, severity: int = 1):
        """Add a banned word with severity level"""
        
        if len(word.strip()) < 2:
            embed = discord.Embed(
                title="❌ **Invalid Input**",
                description="Banned word must be at least 2 characters long.",
                color=self.error_color
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        if severity < 1 or severity > 5:
            embed = discord.Embed(
                title="❌ **Invalid Severity**",
                description="Severity must be between 1 (mild) and 5 (severe).",
                color=self.error_color
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        word_clean = word.lower().strip()
        
        try:
            # Check if word already exists
            existing = await self.words_collection.find_one({
                "guild_id": ctx.guild.id, 
                "word": word_clean
            })
            if existing:
                embed = discord.Embed(
                    title="⚠️ **Word Already Exists**",
                    description=f"`{word}` is already banned (Severity: {existing.get('severity', 1)})",
                    color=self.warning_color
                )
                embed.add_field(
                    name="💡 **Suggestion**",
                    value="Use `/banword remove` first, then re-add with new settings.",
                    inline=False
                )
                return await ctx.send(embed=embed, ephemeral=True)
            
            # Add the word
            await self.words_collection.insert_one({
                "guild_id": ctx.guild.id,
                "word": word_clean,
                "severity": severity,
                "created_by": ctx.author.id,
                "created_at": datetime.utcnow()
            })
            
            # Success embed
            embed = discord.Embed(
                title="✅ **Filter Updated**",
                description=f"Successfully added `{word}` to the banned words list",
                color=self.success_color,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="🔍 **Word**", value=f"`{word}`", inline=True)
            embed.add_field(name="⚠️ **Severity**", value=f"**{severity}**/5", inline=True)
            embed.add_field(name="🎯 **Type**", value="Standard Filter", inline=True)
            
            # Show what variations will be caught
            variations = self.generate_variations(word_clean)[:5]  # Show first 5
            if variations:
                embed.add_field(
                    name="🔄 **Will Also Catch**",
                    value="• " + "\n• ".join(f"`{v}`" for v in variations),
                    inline=False
                )
            
            embed.set_footer(
                text=f"Added by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error adding word: {e}")
            embed = discord.Embed(
                title="❌ **System Error**",
                description="Failed to add banned word. Please try again later.",
                color=self.error_color
            )
            await ctx.send(embed=embed, ephemeral=True)

    @banword.command(
        name="remove", 
        aliases=["r", "delete"], 
        description="Remove a word from the filter",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_remove(self, ctx, *, word: str):
        """Remove a banned word"""
        word_clean = word.lower().strip()
        
        try:
            # Get word info before deletion
            word_info = await self.words_collection.find_one({
                "guild_id": ctx.guild.id, 
                "word": word_clean
            })
                
            if not word_info:
                embed = discord.Embed(
                    title="❌ **Word Not Found**",
                    description=f"`{word}` is not in the banned words list.",
                    color=self.error_color
                )
                embed.add_field(
                    name="💡 **Tip**",
                    value="Use `/banword list` to see all banned words.",
                    inline=False
                )
                return await ctx.send(embed=embed, ephemeral=True)
            
            # Remove the word
            await self.words_collection.delete_one({
                "guild_id": ctx.guild.id, 
                "word": word_clean
            })
            
            severity = word_info.get("severity", 1)
            
            embed = discord.Embed(
                title="✅ **Filter Updated**",
                description=f"Successfully removed `{word}` from the banned words list",
                color=self.success_color,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="🔍 **Removed Word**", value=f"`{word}`", inline=True)
            embed.add_field(name="⚠️ **Was Severity**", value=f"**{severity}**/5", inline=True)
            
            embed.set_footer(
                text=f"Removed by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error removing word: {e}")
            embed = discord.Embed(
                title="❌ **System Error**",
                description="Failed to remove banned word. Please try again later.",
                color=self.error_color
            )
            await ctx.send(embed=embed, ephemeral=True)

    @banword.command(
        name="list", 
        aliases=["l", "show"], 
        description="List all banned words",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_list(self, ctx):
        """List all banned words"""
        try:
            cursor = self.words_collection.find({"guild_id": ctx.guild.id}).sort([
                ("severity", -1), 
                ("word", 1)
            ])
            words = []
            async for doc in cursor:
                words.append((doc['word'], doc.get('severity', 1)))
            
            if not words:
                embed = discord.Embed(
                    title="📝 **No Banned Words**",
                    description="No banned words have been set for this server.\n\nUse `/banword add <word>` to add one.",
                    color=self.embed_color
                )
            else:
                # Split words into chunks for better display
                word_chunks = [words[i:i+10] for i in range(0, len(words), 10)]
                
                embed = discord.Embed(
                    title="📋 **Banned Words List**",
                    description=f"Total: **{len(words)}** banned word{'s' if len(words) != 1 else ''}",
                    color=self.embed_color,
                    timestamp=discord.utils.utcnow()
                )
                
                for i, chunk in enumerate(word_chunks[:3]):  # Show max 3 chunks (30 words)
                    field_name = f"**Words {i*10+1}-{min((i+1)*10, len(words))}**"
                    field_value = ""
                    for word, severity in chunk:
                        severity_stars = "⭐" * severity
                        field_value += f"• `{word}` {severity_stars}\n"
                    embed.add_field(name=field_name, value=field_value, inline=False)
                
                if len(words) > 30:
                    embed.add_field(
                        name="**Note**", 
                        value=f"Showing first 30 of {len(words)} banned words", 
                        inline=False
                    )
                
                embed.add_field(
                    name="📖 **Legend**",
                    value="⭐ = Severity Level (1-5 stars)",
                    inline=False
                )
            
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error listing banwords: {e}")
            error_embed = discord.Embed(
                title="❌ **Error**",
                description="Failed to retrieve banned words list.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed)

    @banword.command(
        name="reset", 
        aliases=["clear"], 
        description="Reset all banned words",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_reset(self, ctx):
        """Reset all banned words"""
        try:
            # Get count first
            count = await self.words_collection.count_documents({"guild_id": ctx.guild.id})
            
            if count == 0:
                embed = discord.Embed(
                    title="❌ **No Words to Reset**",
                    description="There are no banned words to clear.",
                    color=self.warning_color
                )
                return await ctx.send(embed=embed)
            
            # Confirmation embed
            confirm_embed = discord.Embed(
                title="⚠️ **Confirm Reset**",
                description=f"Are you sure you want to remove all **{count}** banned words?\n\n**This action cannot be undone!**",
                color=self.warning_color,
                timestamp=discord.utils.utcnow()
            )
            confirm_embed.set_footer(text="React with ✅ to confirm or ❌ to cancel")
            
            msg = await ctx.send(embed=confirm_embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == "✅":
                    await self.words_collection.delete_many({"guild_id": ctx.guild.id})
                    
                    success_embed = discord.Embed(
                        title="✅ **Banned Words Reset**",
                        description=f"Successfully removed all **{count}** banned words from this server.",
                        color=self.success_color,
                        timestamp=discord.utils.utcnow()
                    )
                    success_embed.add_field(name="**Reset by**", value=ctx.author.mention, inline=True)
                    success_embed.set_footer(text="Banword Management")
                    await msg.edit(embed=success_embed)
                else:
                    cancel_embed = discord.Embed(
                        title="❌ **Reset Cancelled**",
                        description="Banned words reset has been cancelled.",
                        color=self.error_color
                    )
                    await msg.edit(embed=cancel_embed)
                    
            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⏰ **Confirmation Timeout**",
                    description="Reset confirmation timed out. No changes made.",
                    color=self.warning_color
                )
                await msg.edit(embed=timeout_embed)
            
            # Clean up reactions
            try:
                await msg.clear_reactions()
            except discord.Forbidden:
                pass
                
        except Exception as e:
            logging.error(f"[Blacklist] Error resetting banwords: {e}")
            error_embed = discord.Embed(
                title="❌ **Error**",
                description="Failed to reset banned words. Please try again.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed)

    # ================= BYPASS MANAGEMENT (SLASH + PREFIX) =================
    @banword.group(
        name="bypass", 
        aliases=["b"], 
        invoke_without_command=True, 
        description="Manage bypass users",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_bypass(self, ctx):
        """Bypass management subgroup"""
        embed = discord.Embed(
            title="👥 **Bypass Management**",
            description="Manage users who can bypass the banword filter",
            color=self.embed_color
        )
        embed.add_field(
            name="**Available Commands**",
            value=(
                "`/banword bypass add <user>` - Add bypass user\n"
                "`/banword bypass remove <user>` - Remove bypass\n"
                "`/banword bypass list` - List bypass users\n"
                "`/banword bypass reset` - Clear all bypasses\n\n"
                "**All commands work with slash (/) and prefix!**"
            ),
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @banword_bypass.command(
        name="add", 
        aliases=["a"], 
        description="Add a user to bypass the filter",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def bypass_add(self, ctx, member: discord.Member):
        """Add user to bypass list"""
        try:
            # Check if already bypassed
            existing = await self.bypass_users_collection.find_one({
                "guild_id": ctx.guild.id, 
                "user_id": member.id
            })
            if existing:
                error_embed = discord.Embed(
                    title="⚠️ **Already Bypassed**",
                    description=f"{member.mention} is already bypassing the banword filter.",
                    color=self.warning_color
                )
                return await ctx.send(embed=error_embed)
            
            # Add to bypass
            await self.bypass_users_collection.insert_one({
                "guild_id": ctx.guild.id,
                "user_id": member.id,
                "created_by": ctx.author.id,
                "created_at": datetime.utcnow()
            })
            
            embed = discord.Embed(
                title="✅ **Bypass Added**",
                description=f"{member.mention} can now bypass the banword filter.",
                color=self.success_color,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="👤 **User**", value=f"{member.display_name}", inline=True)
            embed.add_field(name="➕ **Added by**", value=ctx.author.mention, inline=True)
            embed.set_footer(text="Bypass Management", icon_url=member.display_avatar.url)
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error adding bypass: {e}")
            error_embed = discord.Embed(
                title="❌ **Error**",
                description="Failed to add bypass user. Please try again.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed)

    @banword_bypass.command(
        name="remove", 
        aliases=["r"], 
        description="Remove a user from bypass",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def bypass_remove(self, ctx, member: discord.Member):
        """Remove user from bypass list"""
        try:
            result = await self.bypass_users_collection.delete_one({
                "guild_id": ctx.guild.id, 
                "user_id": member.id
            })
            
            if result.deleted_count == 0:
                error_embed = discord.Embed(
                    title="⚠️ **User Not Bypassed**",
                    description=f"{member.mention} is not bypassing the banword filter.",
                    color=self.warning_color
                )
                return await ctx.send(embed=error_embed)
            
            embed = discord.Embed(
                title="✅ **Bypass Removed**",
                description=f"{member.mention} no longer bypasses the banword filter.",
                color=self.success_color,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="👤 **User**", value=f"{member.display_name}", inline=True)
            embed.add_field(name="➖ **Removed by**", value=ctx.author.mention, inline=True)
            embed.set_footer(text="Bypass Management", icon_url=member.display_avatar.url)
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error removing bypass: {e}")
            error_embed = discord.Embed(
                title="❌ **Error**",
                description="Failed to remove bypass user. Please try again.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed)

    @banword_bypass.command(
        name="list", 
        aliases=["l"], 
        description="List all bypass users",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def bypass_list(self, ctx):
        """List all bypass users"""
        try:
            cursor = self.bypass_users_collection.find({"guild_id": ctx.guild.id}).sort("user_id", 1)
            user_ids = []
            async for doc in cursor:
                user_ids.append(doc['user_id'])
            
            if not user_ids:
                embed = discord.Embed(
                    title="👥 **No Bypass Users**",
                    description="No users are currently bypassing the banword filter.\n\nUse `/banword bypass add <user>` to add one.",
                    color=self.info_color
                )
            else:
                # Get user info
                users_info = []
                for uid in user_ids:
                    member = ctx.guild.get_member(uid)
                    if member:
                        users_info.append(f"• {member.mention} (`{member.display_name}`)")
                    else:
                        users_info.append(f"• <@{uid}> (User left server)")
                
                embed = discord.Embed(
                    title="👥 **Bypass Users List**",
                    description=f"Total: **{len(user_ids)}** user{'s' if len(user_ids) != 1 else ''} bypassing the filter",
                    color=self.embed_color,
                    timestamp=discord.utils.utcnow()
                )
                
                # Split into chunks if too many users
                user_chunks = [users_info[i:i+10] for i in range(0, len(users_info), 10)]
                
                for i, chunk in enumerate(user_chunks[:2]):  # Show max 2 chunks (20 users)
                    field_name = f"**Users {i*10+1}-{min((i+1)*10, len(users_info))}**"
                    field_value = "\n".join(chunk)
                    embed.add_field(name=field_name, value=field_value, inline=False)
                
                if len(users_info) > 20:
                    embed.add_field(
                        name="**Note**", 
                        value=f"Showing first 20 of {len(users_info)} bypass users", 
                        inline=False
                    )
            
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error listing bypass users: {e}")
            error_embed = discord.Embed(
                title="❌ **Error**",
                description="Failed to retrieve bypass users list.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed)

    @banword_bypass.command(
        name="reset", 
        aliases=["clear"], 
        description="Reset all bypass users",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def bypass_reset(self, ctx):
        """Reset all bypass users"""
        try:
            # Get count first
            count = await self.bypass_users_collection.count_documents({"guild_id": ctx.guild.id})
            
            if count == 0:
                embed = discord.Embed(
                    title="❌ **No Bypasses to Reset**",
                    description="There are no bypass users to remove.",
                    color=self.warning_color
                )
                return await ctx.send(embed=embed)
            
            # Reset bypasses
            await self.bypass_users_collection.delete_many({"guild_id": ctx.guild.id})
            
            embed = discord.Embed(
                title="✅ **Bypass List Reset**",
                description=f"Successfully removed all **{count}** bypass user{'s' if count != 1 else ''} from this server.",
                color=self.success_color,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="➖ **Reset by**", value=ctx.author.mention, inline=True)
            embed.set_footer(text="Bypass Management")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"[Blacklist] Error resetting bypass users: {e}")
            error_embed = discord.Embed(
                title="❌ **Error**",
                description="Failed to reset bypass users. Please try again.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed)

    # ================= WHITELIST MANAGEMENT (SLASH + PREFIX) =================
    @banword.group(
        name="whitelist", 
        aliases=["wl", "allow"], 
        invoke_without_command=True, 
        description="Manage whitelisted words",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_whitelist(self, ctx):
        """Whitelist management subgroup"""
        embed = discord.Embed(
            title="✅ **Whitelist Management**",
            description="Manage words that are explicitly allowed (bypasses filter)",
            color=self.embed_color
        )
        embed.add_field(
            name="**Available Commands**",
            value=(
                "`/banword whitelist add <word>` - Whitelist a word\n"
                "`/banword whitelist remove <word>` - Remove from whitelist\n"
                "`/banword whitelist list` - List whitelisted words\n\n"
                "**All commands work with slash (/) and prefix!**"
            ),
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @banword_whitelist.command(name="add", aliases=["a"], description="Add a word to whitelist")
    @commands.has_permissions(manage_guild=True)
    async def whitelist_add(self, ctx, word: str):
        """Add word to whitelist"""
        word_clean = word.lower().strip()
        try:
            # Check if exists
            existing = await self.whitelist_collection.find_one({
                "guild_id": ctx.guild.id, 
                "word": word_clean
            })
            if existing:
                return await ctx.send(embed=discord.Embed(
                    title="⚠️ **Already Whitelisted**",
                    description=f"`{word}` is already in the whitelist.",
                    color=self.warning_color
                ), ephemeral=True)
            
            await self.whitelist_collection.insert_one({
                "guild_id": ctx.guild.id,
                "word": word_clean,
                "created_by": ctx.author.id,
                "created_at": datetime.utcnow()
            })
            
            embed = discord.Embed(
                title="✅ **Whitelist Updated**",
                description=f"Successfully added `{word}` to the whitelist.",
                color=self.success_color
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"[Blacklist] Error adding whitelist: {e}")
            await ctx.send(embed=discord.Embed(title="❌ Error", description="Failed to add to whitelist.", color=self.error_color), ephemeral=True)

    @banword_whitelist.command(name="remove", aliases=["r"], description="Remove a word from whitelist")
    @commands.has_permissions(manage_guild=True)
    async def whitelist_remove(self, ctx, word: str):
        """Remove word from whitelist"""
        word_clean = word.lower().strip()
        try:
            result = await self.whitelist_collection.delete_one({
                "guild_id": ctx.guild.id, 
                "word": word_clean
            })
            if result.deleted_count == 0:
                return await ctx.send(embed=discord.Embed(
                    title="❌ **Not Found**",
                    description=f"`{word}` is not in the whitelist.",
                    color=self.error_color
                ), ephemeral=True)
            
            embed = discord.Embed(
                title="✅ **Whitelist Updated**",
                description=f"Successfully removed `{word}` from the whitelist.",
                color=self.success_color
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"[Blacklist] Error removing whitelist: {e}")
            await ctx.send(embed=discord.Embed(title="❌ Error", description="Failed to remove from whitelist.", color=self.error_color), ephemeral=True)

    @banword_whitelist.command(name="list", aliases=["l"], description="List whitelisted words")
    @commands.has_permissions(manage_guild=True)
    async def whitelist_list(self, ctx):
        """List whitelisted words"""
        try:
            cursor = self.whitelist_collection.find({"guild_id": ctx.guild.id}).sort("word", 1)
            words = [doc['word'] async for doc in cursor]
            
            if not words:
                return await ctx.send(embed=discord.Embed(
                    title="📝 **Whitelist Empty**",
                    description="No words are currently whitelisted.",
                    color=self.info_color
                ))
            
            embed = discord.Embed(
                title="📋 **Whitelisted Words**",
                description=f"Total: **{len(words)}** words",
                color=self.embed_color
            )
            embed.description += "\n\n" + ", ".join(f"`{w}`" for w in words[:50])
            if len(words) > 50:
                embed.description += f"\n...and {len(words)-50} more."
            
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"[Blacklist] Error listing whitelist: {e}")
            await ctx.send(embed=discord.Embed(title="❌ Error", description="Failed to list whitelist.", color=self.error_color), ephemeral=True)

    # ================= EXEMPT CHANNEL MANAGEMENT =================
    @banword.group(
        name="exempt", 
        aliases=["e", "ignore"], 
        invoke_without_command=True, 
        description="Manage exempt channels",
        with_app_command=True
    )
    @commands.has_permissions(manage_guild=True)
    async def banword_exempt(self, ctx):
        """Exempt channel management subgroup"""
        embed = discord.Embed(
            title="🛡️ **Exempt Channels**",
            description="Manage channels where the filter is disabled",
            color=self.embed_color
        )
        embed.add_field(
            name="**Available Commands**",
            value=(
                "`/banword exempt add [channel]` - Exempt a channel\n"
                "`/banword exempt remove [channel]` - Remove exemption\n"
                "`/banword exempt list` - List exempt channels\n\n"
                "**All commands work with slash (/) and prefix!**"
            ),
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @banword_exempt.command(name="add", aliases=["a"], description="Exempt a channel")
    @commands.has_permissions(manage_guild=True)
    async def exempt_add(self, ctx, channel: discord.TextChannel = None):
        """Exempt a channel"""
        target = channel or ctx.channel
        try:
            existing = await self.exempt_channels_collection.find_one({
                "guild_id": ctx.guild.id, 
                "channel_id": target.id
            })
            if existing:
                return await ctx.send(embed=discord.Embed(
                    title="⚠️ **Already Exempt**",
                    description=f"{target.mention} is already exempt.",
                    color=self.warning_color
                ), ephemeral=True)
            
            await self.exempt_channels_collection.insert_one({
                "guild_id": ctx.guild.id,
                "channel_id": target.id,
                "exempt_type": "channel", # placeholder
                "created_by": ctx.author.id,
                "created_at": datetime.utcnow()
            })
            
            embed = discord.Embed(
                title="✅ **Channel Exempted**",
                description=f"{target.mention} is now exempt from the banword filter.",
                color=self.success_color
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"[Blacklist] Error adding exempt channel: {e}")
            await ctx.send(embed=discord.Embed(title="❌ Error", description="Failed to exempt channel.", color=self.error_color), ephemeral=True)

    @banword_exempt.command(name="remove", aliases=["r"], description="Remove channel exemption")
    @commands.has_permissions(manage_guild=True)
    async def exempt_remove(self, ctx, channel: discord.TextChannel = None):
        """Remove channel exemption"""
        target = channel or ctx.channel
        try:
            result = await self.exempt_channels_collection.delete_one({
                "guild_id": ctx.guild.id, 
                "channel_id": target.id
            })
            if result.deleted_count == 0:
                return await ctx.send(embed=discord.Embed(
                    title="❌ **Not Exempt**",
                    description=f"{target.mention} is not exempt.",
                    color=self.error_color
                ), ephemeral=True)
            
            embed = discord.Embed(
                title="✅ **Exemption Removed**",
                description=f"{target.mention} is no longer exempt.",
                color=self.success_color
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"[Blacklist] Error removing exempt channel: {e}")
            await ctx.send(embed=discord.Embed(title="❌ Error", description="Failed to remove exemption.", color=self.error_color), ephemeral=True)

    @banword_exempt.command(name="list", aliases=["l"], description="List exempt channels")
    @commands.has_permissions(manage_guild=True)
    async def exempt_list(self, ctx):
        """List exempt channels"""
        try:
            cursor = self.exempt_channels_collection.find({"guild_id": ctx.guild.id})
            channels = []
            async for doc in cursor:
                ch = ctx.guild.get_channel(doc['channel_id'])
                if ch:
                    channels.append(ch.mention)
                else:
                    channels.append(f"<#{doc['channel_id']}> (Deleted)")
            
            if not channels:
                return await ctx.send(embed=discord.Embed(
                    title="📝 **No Exempt Channels**",
                    description="No channels are exempt.",
                    color=self.info_color
                ))
            
            embed = discord.Embed(
                title="🛡️ **Exempt Channels**",
                description="\n".join(channels),
                color=self.embed_color
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"[Blacklist] Error listing exempt channels: {e}")
            await ctx.send(embed=discord.Embed(title="❌ Error", description="Failed to list exempt channels.", color=self.error_color), ephemeral=True)

    # ================= ERROR HANDLERS =================
    @banword.error
    @banword_add.error
    @banword_remove.error
    @banword_list.error
    @banword_reset.error
    @banword_punishment.error
    @banword_bypass.error
    @bypass_add.error
    @bypass_remove.error
    @bypass_list.error
    @bypass_reset.error
    @banword_whitelist.error
    @whitelist_add.error
    @whitelist_remove.error
    @whitelist_list.error
    @banword_exempt.error
    @exempt_add.error
    @exempt_remove.error
    @exempt_list.error
    async def banword_error_handler(self, ctx, error):
        """Handle banword command errors"""
        if isinstance(error, commands.MissingPermissions):
            error_embed = discord.Embed(
                title="🔒 **Missing Permissions**",
                description="You need `Manage Server` permission to use banword commands!",
                color=self.error_color
            )
            await ctx.send(embed=error_embed, ephemeral=True)
        elif isinstance(error, commands.MemberNotFound):
            error_embed = discord.Embed(
                title="❌ **Member Not Found**",
                description="Could not find that member. Please mention a valid server member.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed, ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            error_embed = discord.Embed(
                title="❓ **Missing Required Argument**",
                description="Please provide all required arguments for this command.",
                color=self.error_color
            )
            await ctx.send(embed=error_embed, ephemeral=True)
        else:
            logging.error(f"[Blacklist] Unhandled error: {error}")

# ================= SETUP =================
async def setup(bot):
    await bot.add_cog(Blacklist(bot))
