import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiSticker(commands.Cog):
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
        print("✅ [AntiSticker] Extension loaded & DB initialized (MongoDB).")

    def can_fetch_audit(self, guild_id, event_name, max_requests=3, interval=5, cooldown_duration=180):
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

    async def fetch_audit_logs(self, guild, action, target_id):
        if not guild.me.guild_permissions.view_audit_log:
            return None
        try:
            cutoff_time = datetime.datetime.now(pytz.utc) - datetime.timedelta(minutes=5)
            async for entry in guild.audit_logs(action=action, limit=5):
                if entry.target.id == target_id and entry.created_at > cutoff_time:
                    return entry
        except:
            pass
        return None

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        # Security & Feature Checks
        if not guild.me.guild_permissions.ban_members or not guild.me.guild_permissions.view_audit_log:
            return

        # Check Blacklist
        if await self.blacklist_col.find_one({"guild_id": guild.id}):
            return

        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "sticker"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        action = None
        target = None
        
        if len(before) < len(after): # Created
            action = discord.AuditLogAction.sticker_create
            for sticker in after:
                if sticker not in before:
                    target = sticker
                    break
        elif len(before) > len(after): # Deleted
            action = discord.AuditLogAction.sticker_delete
            for sticker in before:
                if sticker not in after:
                    target = sticker
                    break
        else: # Updated
            action = discord.AuditLogAction.sticker_update
            for b, a in zip(before, after):
                if b.name != a.name:
                    target = a
                    break
            if not target: return
        
        if not target: return

        if not self.can_fetch_audit(guild.id, 'sticker_update'): return
        await asyncio.sleep(0.5)

        log_entry = await self.fetch_audit_logs(guild, action, target.id)
        if not log_entry: return

        executor = log_entry.user

        if executor.id in {guild.owner_id, self.bot.user.id}: return

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
             return

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("mngstemo"):
            return

        await self.ban_executor(guild, executor, f"[ANTINUKE] Unauthorized Sticker Action | {action.name}")
        
        if action == discord.AuditLogAction.sticker_create:
            try:
                await target.delete(reason="[ANTINUKE] Reverting unauthorized sticker creation")
            except:
                pass

    async def ban_executor(self, guild, executor, reason):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason=reason)
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(float(e.response.headers.get('Retry-After', 1)))
                retries -= 1
                await asyncio.sleep(1)
            except:
                retries -= 1
                await asyncio.sleep(1)

async def setup(bot):
    await bot.add_cog(AntiSticker(bot))
