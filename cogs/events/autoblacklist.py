import discord
from core import Scyro, Cog
from discord.ext import commands
import motor.motor_asyncio
from datetime import datetime, timedelta
import os

OWNER_ID = 1218037361926209640  # Bot owner ID

class AutoBlacklist(Cog):
    def __init__(self, client: Scyro):
        self.client = client
        # Updated to require 7 commands spam before blacklisting
        self.spam_cd_mapping = commands.CooldownMapping.from_cooldown(7, 10, commands.BucketType.member)
        self.spam_command_mapping = commands.CooldownMapping.from_cooldown(7, 15, commands.BucketType.member)
        # Updated threshold to 7
        self.spam_threshold = 7
        self.spam_window = timedelta(minutes=10)
        
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.blacklist_col = self.db["blacklist"]
        self.bypass_col = self.db["blacklist_bypass"]
        self.premium_col = self.db["premium_users"]
        
        self.bot_user_id = self.client.user.id if self.client.user else None
        # Initialize mention spam count
        self.mention_spam_count = {}

    async def cog_load(self):
        # Update bot_user_id if not set during init
        if not self.bot_user_id and self.client.user:
            self.bot_user_id = self.client.user.id

    async def add_to_blacklist(self, user_id=None, guild_id=None, reason="Auto-Blacklist: Spam"):
        # Skip owner
        if user_id == OWNER_ID:
            return

        # Only allow user blacklisting automatically, guilds can only be blacklisted by owner
        if guild_id:
            return

        # Check if user is bypassed (immune to automatic blacklisting)
        if await self._is_user_bypassed(user_id):
            return

        # Check if user has premium - if so, don't blacklist them
        if await self._is_user_premium(user_id):
            return

        try:
            timestamp = datetime.utcnow()
            if user_id:
                # Upsert to avoid duplicates, although insert_one with try/except is also fine
                # Using custom "type" field to differentiate from guild blacklist if merged
                await self.blacklist_col.update_one(
                    {"type": "user", "id": user_id},
                    {"$set": {
                        "reason": reason,
                        "timestamp": timestamp
                    }},
                    upsert=True
                )
        except Exception as e:
            print(f"[AutoBlacklist] Database error: {e}")

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _is_user_bypassed(self, user_id: int) -> bool:
        """Check if a user is bypassed (immune to automatic blacklisting)"""
        try:
            doc = await self.bypass_col.find_one({"user_id": user_id})
            return doc is not None
        except Exception:
            return False
    
    async def _is_user_premium(self, user_id: int) -> bool:
        """Check if a user has an active premium tier"""
        try:
            doc = await self.premium_col.find_one({"user_id": user_id})
            if not doc:
                return False
            
            expires_at = doc.get("expires_at")
            if not expires_at: 
                # If no expiry is set, assume valid if record exists? Or invalid?
                # Assuming valid if record exists but no expiry date (lifetime/subscription)
                return True 
                
            # Handle both string (iso) and datetime objects
            if isinstance(expires_at, str):
                try:
                    expiry_dt = datetime.fromisoformat(expires_at)
                except ValueError:
                    return False
            elif isinstance(expires_at, datetime):
                expiry_dt = expires_at
            else:
                return False
                
            return expiry_dt > datetime.utcnow()
        except Exception:
            # If we can't check premium status, assume they don't have premium
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or message.author.id == OWNER_ID:
            return
            
        # Ensure bot_user_id is set
        if not self.bot_user_id:
            self.bot_user_id = self.client.user.id

        # Track user spam
        bucket = self.spam_cd_mapping.get_bucket(message)
        if bucket:
            retry = bucket.update_rate_limit()
            if retry:
                # Check DB if blacklisted
                # We use find_one for quick check. 
                # Logic: If already blacklisted, ignore (return).
                is_blacklisted = await self.blacklist_col.find_one({"type": "user", "id": message.author.id})
                if is_blacklisted:
                    return

                # Mention spam detection - require 7 mentions before blacklisting
                # Only check if spamming AND mentioning bot
                if message.content in (f'<@{self.bot_user_id}>', f'<@!{self.bot_user_id}>'):
                    # Track mention spam attempts
                    user_id = message.author.id
                    self.mention_spam_count[user_id] = self.mention_spam_count.get(user_id, 0) + 1
                    
                    # Only blacklist after 7 mention spam attempts
                    if self.mention_spam_count[user_id] >= 7:
                        await self.add_to_blacklist(user_id=message.author.id, reason="Auto-Blacklist: Mention Spam")
                        
                        embed = discord.Embed(
                            title="<a:warn:1396429222066782228> User Blacklisted",
                            description=(
                                f"{message.author.mention} has been blacklisted for repeatedly mentioning the bot.\n"
                                f"Contact our **[Support Server](https://dsc.gg/scyrogg)** if this is a mistake."
                            ),
                            color=discord.Color.red(),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_footer(text="Scyro AutoBlacklist System")
                        try:
                            await message.channel.send(embed=embed)
                        except discord.Forbidden:
                            pass
                    return

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.author.bot or ctx.author.id == OWNER_ID:
            return

        bucket = self.spam_command_mapping.get_bucket(ctx.message)
        if bucket:
            retry = bucket.update_rate_limit()
            if retry:
                is_blacklisted = await self.blacklist_col.find_one({"type": "user", "id": ctx.author.id})
                if is_blacklisted:
                    return

                await self.add_to_blacklist(user_id=ctx.author.id, reason="Auto-Blacklist: Command Spam")
                
                embed = discord.Embed(
                    title="<a:warn:1396429222066782228> User Blacklisted",
                    description=(
                        f"{ctx.author.mention} has been blacklisted for spamming commands.\n"
                        f"Contact our **[Support Server](https://dsc.gg/scyrogg)** if this is a mistake."
                    ),
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="Scyro AutoBlacklist System")
                try:
                    await ctx.reply(embed=embed)
                except discord.Forbidden:
                    pass