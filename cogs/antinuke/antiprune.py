import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiPrune(commands.Cog):
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
        print("✅ [AntiPrune] Extension loaded & DB initialized (MongoDB).")

    async def fetch_audit_logs(self, guild, action):
        try:
            async for entry in guild.audit_logs(action=action, limit=1):
                now = datetime.datetime.now(pytz.utc)
                created_at = entry.created_at
                difference = (now - created_at).total_seconds() * 1000
                    
                if difference >= 3600000:
                    return None

                return entry
    
        except Exception as e:
            print(f"Error fetching audit logs: {e}")
        return None

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        
        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "prune"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        log_entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.member_prune)
        if log_entry is None:
            return

        executor = log_entry.user
        
        if executor.id in {guild.owner_id, self.bot.user.id}:
            return

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
             return

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("prune"):
            return

        await self.ban_executor(guild, executor)

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="[ANTINUKE] Member Prune | Unwhitelisted User | Security Action")
                return
            except discord.Forbidden:
                print(f"Failed to ban {executor.id} due to missing permissions.")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                        print(f"Rate limit encountered. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                else:
                    print(f"HTTPException encountered: {e}")
                    return
            except discord.errors.RateLimited as e:
                print(f"Rate limit encountered while banning: {e}. Retrying in {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception as e:
                print(f"An unexpected error occurred while banning {executor.id}: {e}")
                return

        print(f"Failed to ban {executor.id} after multiple attempts due to rate limits.")
