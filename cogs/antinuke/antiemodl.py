import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import random
import datetime
import os

class AntiEmojiDelete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.blacklist_col = self.db["blacklist"]
        self.antinuke_col = self.db["antinuke"]
        self.modules_col = self.db["antinuke_modules"]
        self.whitelist_col = self.db["antinuke_whitelist"]
        self.extra_col = self.db["extraowners"]

    async def cog_load(self):
        print("✅ [AntiEmojiDelete] Extension loaded & DB initialized (MongoDB).")

    async def fetch_audit_logs(self, guild, action):
        try:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            logs = [entry async for entry in guild.audit_logs(action=action, limit=1, after=datetime.datetime.utcnow() - datetime.timedelta(seconds=3))]
            if logs:
                return logs[0]
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    retry_after = float(retry_after)
                    await asyncio.sleep(retry_after)
                    return await self.fetch_audit_logs(guild, action)
        except Exception as e:
            print(f"An error occurred while fetching audit logs: {e}")
        return None

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        if len(after) < len(before):
            # Check Antinuke Status
            antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
            if not antinuke_doc or not antinuke_doc.get("status"):
                return

            # Check Module Status
            module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "emoji_delete"})
            if module_doc and not module_doc.get("enabled", True):
                return
            if not module_doc:
                 pass # Enabled by default if missing

            logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.emoji_delete)
            if logs is None:
                return

            executor = logs.user
            difference = discord.utils.utcnow() - logs.created_at
            if difference.total_seconds() > 3600:
                return

            if executor.id in {guild.owner_id, self.bot.user.id}:
                return

            # Check Extra Owner
            extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
            if extra_owner_doc:
                return

            # Check Whitelist
            whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
            if whitelist_doc and whitelist_doc.get("mngstemo"):
                return

            await self.ban_executor(guild, executor)

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="[ANTINUKE] Emoji Delete | Unwhitelisted User | Security Action")
                return
            except discord.Forbidden:
                print(f"Failed to ban {executor.id} due to missing permissions.")
                return
            except discord.HTTPException as e:
                print(f"Failed to ban {executor.id} due to HTTPException: {e}")
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                        print(f"Rate limit encountered while banning. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                    else:
                        return
                else:
                    return
            except discord.errors.RateLimited as e:
                print(f"Rate limit encountered while banning: {e}. Retrying in {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception as e:
                print(f"An unexpected error occurred while banning {executor.id}: {e}")
                return

        print(f"Failed to ban {executor.id} after multiple attempts due to rate limits.")
