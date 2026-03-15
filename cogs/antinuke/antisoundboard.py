import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiSoundboard(commands.Cog):
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
        print("✅ [AntiSoundboard] Extension loaded & DB initialized (MongoDB).")

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
            # Try to match soundboard creation action
            # Note: Discord.py might not have a specific enum constant for this yet if it isn't updated, 
            # but AuditLogAction.expression_create (AutoMod?) 
            # or we rely on generic search if specific action is missing.
            # Assuming AuditLogAction.soundboard_sound_create exists or works via ID.
            # 130 = Soundboard Sound Create
            # 131 = Soundboard Sound Update
            # 132 = Soundboard Sound Delete
            
            # Use getattr to be safe if version is slightly old
            action_type = action
            
            async for entry in guild.audit_logs(action=action_type, limit=5):
                if entry.target.id == target_id and entry.created_at > cutoff_time:
                    return entry
        except:
            pass
        return None

    @commands.Cog.listener()
    async def on_soundboard_sound_create(self, sound):
        await self.handle_soundboard_event(sound, "create")

    @commands.Cog.listener()
    async def on_soundboard_sound_delete(self, sound):
        await self.handle_soundboard_event(sound, "delete")
    
    @commands.Cog.listener()
    async def on_soundboard_sound_update(self, before, after):
        await self.handle_soundboard_event(after, "update")

    async def handle_soundboard_event(self, sound, event_type):
        guild = sound.guild
        if not guild or not guild.me.guild_permissions.ban_members or not guild.me.guild_permissions.view_audit_log:
            return

        # Check Blacklist
        if await self.blacklist_col.find_one({"guild_id": guild.id}):
            return

        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "soundboard"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        # Rate Limit
        if not self.can_fetch_audit(guild.id, 'soundboard'): return
        await asyncio.sleep(0.5)

        # Map event to Audit Log Action
        action_map = {
            "create": discord.AuditLogAction.soundboard_sound_create,
            "delete": discord.AuditLogAction.soundboard_sound_delete,
            "update": discord.AuditLogAction.soundboard_sound_update
        }
        
        # Fallback for older discord.py versions that might not have these enums attributes
        if not hasattr(discord.AuditLogAction, 'soundboard_sound_create'):
             # If constants don't exist, we might skip or try to assume values, but let's assume they exist for now.
             return

        action = action_map.get(event_type)
        if not action: return

        log_entry = await self.fetch_audit_logs(guild, action, sound.id)
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

        await self.ban_executor(guild, executor, f"[ANTINUKE] Unauthorized Soundboard Action | {event_type}")

        if event_type == "create":
            try:
                await sound.delete(reason="[ANTINUKE] Reverting unauthorized sound creation")
            except:
                pass

    async def ban_executor(self, guild, executor, reason):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason=reason)
                return
            except:
                retries -= 1
                await asyncio.sleep(1)

async def setup(bot):
    await bot.add_cog(AntiSoundboard(bot))
