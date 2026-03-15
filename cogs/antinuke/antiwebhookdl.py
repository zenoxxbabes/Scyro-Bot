import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiWebhookDelete(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.blacklist_col = self.db["blacklist"]
        self.antinuke_col = self.db["antinuke"]
        self.modules_col = self.db["antinuke_modules"]
        self.whitelist_col = self.db["antinuke_whitelist"]
        self.extra_col = self.db["extraowners"]

    async def cog_load(self):
        print("✅ [AntiWebhookDelete] Extension loaded & DB initialized (MongoDB).")

    async def fetch_audit_logs(self, guild, action, target_id):
        try:
            now = datetime.datetime.now(pytz.utc)
            logs = [entry async for entry in guild.audit_logs(action=action, limit=1)]
            for entry in logs:
                if entry.target.id == target_id:
                    difference = (now - entry.created_at).total_seconds() * 1000
                    if difference < 3600000:  # Only consider entries from the last hour
                        return entry
        except Exception:
            return None
        return None

    def can_fetch_audit(self, guild_id, event_name, max_requests=6, interval=10, cooldown_duration=300):
        now = datetime.datetime.now()
        self.event_limits.setdefault(guild_id, {}).setdefault(event_name, []).append(now)

        timestamps = self.event_limits[guild_id][event_name]
        timestamps = [t for t in timestamps if (now - t).total_seconds() <= interval]
        self.event_limits[guild_id][event_name] = timestamps

        if guild_id in self.cooldowns and event_name in self.cooldowns[guild_id]:
            if (now - self.cooldowns[guild_id][event_name]).total_seconds() < cooldown_duration:
                return False
            del self.cooldowns[guild_id][event_name]

        if len(timestamps) > max_requests:
            self.cooldowns.setdefault(guild_id, {})[event_name] = now
            return False

        return True

    @commands.Cog.listener()
    async def on_webhooks_delete(self, channel):
        guild = channel.guild
        
        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "webhook_delete"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        if not self.can_fetch_audit(guild.id, 'webhook_delete'):
            return

        entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.webhook_delete, channel.id)
        if entry is None:
            return

        executor = entry.user

        if executor.id in {guild.owner_id, self.bot.user.id}:
            return

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
             return

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("mngweb"):
            return

        try:
            await self.ban_executor(guild, executor)
            await asyncio.sleep(3)
        except Exception:
            return

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="[ANTINUKE] Webhook Delete | Unwhitelisted User | Security Action")
                return
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                else:
                    return
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                return

            retries -= 1
