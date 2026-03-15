import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import os


class AntiRepeatedText(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_threshold = 3  # Number of repeated messages to trigger action
        self.time_window = 10   # Time window in seconds to check for repeats
        self.user_message_cache = defaultdict(list)  # Cache user messages: {user_id: [(content, timestamp)]}
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.settings_col = self.db["automod_settings"]
        self.rules_col = self.db["automod_rules"]
        self.ignored_col = self.db["automod_ignored"]

    async def cog_load(self):
        print("✅ [AntiRepeatedText] Extension loaded & DB initialized (MongoDB).")

    async def is_automod_enabled(self, guild_id):
        doc = await self.settings_col.find_one({"guild_id": guild_id})
        return doc and doc.get("enabled", False)

    async def is_anti_repeated_text_enabled(self, guild_id):
        doc = await self.rules_col.find_one({"guild_id": guild_id, "rule": "anti_repeated_text"})
        return doc and doc.get("enabled", False)

    async def get_ignored_channels(self, guild_id):
        cursor = self.ignored_col.find({"guild_id": guild_id, "type": "channel"})
        return [doc["target_id"] for doc in await cursor.to_list(length=None)]

    async def get_ignored_roles(self, guild_id):
        cursor = self.ignored_col.find({"guild_id": guild_id, "type": "role"})
        return [doc["target_id"] for doc in await cursor.to_list(length=None)]

    async def get_punishment(self, guild_id):
        doc = await self.rules_col.find_one({"guild_id": guild_id, "rule": "anti_repeated_text"})
        return doc.get("punishment") if doc else None

    async def log_action(self, guild, user, channel, action, reason):
        doc = await self.settings_col.find_one({"guild_id": guild.id})
        log_channel_id = doc.get("log_channel") if doc else None

        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title="Automod Log: Anti Repeated Text", color=0xff0000)
                embed.add_field(name="User", value=user.mention, inline=False)
                embed.add_field(name="Action", value=action, inline=False)
                embed.add_field(name="Channel", value=channel.mention, inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.set_footer(text=f"User ID: {user.id}")
                avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
                embed.set_thumbnail(url=avatar_url)
                embed.timestamp = discord.utils.utcnow()
                await log_channel.send(embed=embed)

    def clean_old_messages(self, user_id):
        """Remove messages older than the time window"""
        now = datetime.utcnow()
        self.user_message_cache[user_id] = [
            (content, timestamp) for content, timestamp in self.user_message_cache[user_id]
            if (now - timestamp).total_seconds() <= self.time_window
        ]

    def count_repeated_messages(self, user_id, message_content):
        """Count how many times the same message was sent by user in time window"""
        return sum(1 for content, timestamp in self.user_message_cache[user_id] 
                  if content.lower().strip() == message_content.lower().strip())

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.guild:
            return

        guild = message.guild
        user = message.author
        channel = message.channel
        guild_id = guild.id

        if not await self.is_automod_enabled(guild_id) or not await self.is_anti_repeated_text_enabled(guild_id):
            return

        if user == guild.owner or user == self.bot.user:
            return

        ignored_channels = await self.get_ignored_channels(guild_id)
        if channel.id in ignored_channels:
            return

        ignored_roles = await self.get_ignored_roles(guild_id)
        if any(role.id in ignored_roles for role in user.roles):
            return

        # Skip empty messages or messages with only whitespace
        if not message.content.strip():
            return

        user_id = user.id
        message_content = message.content

        # Clean old messages from cache
        self.clean_old_messages(user_id)

        # Count how many times this exact message was sent recently
        repeat_count = self.count_repeated_messages(user_id, message_content)

        if repeat_count >= self.spam_threshold:
            punishment = await self.get_punishment(guild_id)
            action_taken = None
            reason = f"Repeated Text Spam ({repeat_count + 1} identical messages)"

            try:
                if punishment == "Mute":
                    timeout_duration = discord.utils.utcnow() + timedelta(minutes=5)
                    await user.edit(timed_out_until=timeout_duration, reason=reason)
                    action_taken = "Muted for 5 minutes"
                elif punishment == "Kick":
                    await user.kick(reason=reason)
                    action_taken = "Kicked"
                elif punishment == "Ban":
                    await user.ban(reason=reason)
                    action_taken = "Banned"
                else:
                    return # No punishment configured

                # Delete the repeated message
                await message.delete()

                # Send warning embed
                simple_embed = discord.Embed(title="Automod Anti Repeated Text", color=0xff0000)
                simple_embed.description = f"<:yes:1396838746862784582> | {user.mention} has been successfully **{action_taken}** for **Sending Repeated Messages.**"
                simple_embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1294125691587006525.png")
                
                simple_embed.set_footer(text='Use the "automod logging" command to get automod logs if it is not enabled.', icon_url=self.bot.user.avatar.url)
                
                await channel.send(embed=simple_embed, delete_after=30)

                # Clear user's message cache after punishment to prevent multiple punishments
                self.user_message_cache[user_id].clear()

                await self.log_action(guild, user, channel, action_taken, reason)

            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass
            except Exception:
                pass
        else:
            # Add current message to cache
            self.user_message_cache[user_id].append((message_content, datetime.utcnow()))

    @commands.Cog.listener()
    async def on_rate_limit(self, message):
        await asyncio.sleep(10)

    # Optional: Clean up cache periodically to prevent memory buildup
    @commands.Cog.listener()
    async def on_ready(self):
        """Clean up message cache every 5 minutes"""
        while True:
            await asyncio.sleep(300)  # 5 minutes
            for user_id in list(self.user_message_cache.keys()):
                self.clean_old_messages(user_id)
                # Remove empty entries
                if not self.user_message_cache[user_id]:
                    del self.user_message_cache[user_id]
