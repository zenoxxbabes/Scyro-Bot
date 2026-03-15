import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
from datetime import timedelta
import os

class AntiEveryone(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.blacklist_col = self.db["blacklist"]
        self.antinuke_col = self.db["antinuke"]
        self.modules_col = self.db["antinuke_modules"]
        self.whitelist_col = self.db["antinuke_whitelist"]
        self.extra_col = self.db["extraowners"]

    async def cog_load(self):
        print("✅ [AntiEveryone] Extension loaded & DB initialized (MongoDB).")

    async def can_message_delete(self, guild_id, event_name, max_requests=5, interval=10, cooldown_duration=300):
        now = datetime.datetime.now()
        self.event_limits.setdefault(guild_id, {}).setdefault(event_name, []).append(now)

        timestamps = self.event_limits[guild_id][event_name]
        timestamps = [t for t in timestamps if (now - t).total_seconds() <= interval]
        self.event_limits[guild_id][event_name] = timestamps

        if len(timestamps) > max_requests:
            return False

        return True

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or not message.mention_everyone:
            return

        guild = message.guild

        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "everyone"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        if message.author.id in {guild.owner_id, self.bot.user.id}:
            return

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": message.author.id})
        if extra_owner_doc:
             return

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": message.author.id})
        if whitelist_doc and whitelist_doc.get("meneve"):
            return
        
        if not await self.can_message_delete(guild.id, 'mention_everyone'):
            return

        try:
            await self.timeout_user(message.author)
            await self.delete_everyone_messages(message.channel)
        except Exception as e:
            print(f"An unexpected error occurred while handling {message.author.id}: {e}")

    async def timeout_user(self, user):
        if not isinstance(user, discord.Member):
             return

        retries = 3
        duration = 60 * 60  
        while retries > 0:
            try:
                await user.edit(timed_out_until=discord.utils.utcnow() + timedelta(seconds=duration), reason="[ANTINUKE] Mentioned Everyone/Here | Unwhitelisted User | Security Action")
                return  
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                print(f"Failed to timeout {user.id} due to HTTPException: {e}")
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                        print(f"Rate limit encountered while timing out. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                else:
                    return
            except discord.errors.RateLimited as e:
                print(f"Rate limit encountered while timing out: {e}. Retrying in {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception as e:
                print(f"An unexpected error occurred while timing out {user.id}: {e}")
                return

        print(f"Failed to timeout {user.id} after multiple attempts due to rate limits.")

    async def delete_everyone_messages(self, channel):
        retries = 3
        while retries > 0:
            try:
                async for msg in channel.history(limit=100):
                    if msg.mention_everyone:
                        await msg.delete()
                        await asyncio.sleep(3)  
                return  
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                print(f"Failed to delete messages due to HTTPException: {e}")
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                        print(f"Rate limit encountered while deleting messages. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                else:
                    return
            except discord.errors.RateLimited as e:
                print(f"Rate limit encountered while deleting messages: {e}. Retrying in {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception as e:
                print(f"An unexpected error occurred while deleting messages: {e}")
                return

        print(f"Failed to delete messages after multiple attempts due to rate limits.")
