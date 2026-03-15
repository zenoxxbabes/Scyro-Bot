import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiMemberUpdate(commands.Cog):
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
        print("✅ [AntiMemberUpdate] Extension loaded & DB initialized (MongoDB).")

    async def is_blacklisted_guild(self, guild_id):
        doc = await self.blacklist_col.find_one({"guild_id": guild_id})
        return bool(doc)

    async def fetch_audit_logs(self, guild, action, target_id):
        if not guild.me.guild_permissions.ban_members:
            return None
        try:
            async for entry in guild.audit_logs(action=action, limit=1):
                if entry.target.id == target_id:
                    now = datetime.datetime.now(pytz.utc)
                    created_at = entry.created_at
                    difference = (now - created_at).total_seconds() * 1000
                    if difference < 3600000:
                        return entry
        except Exception:
            pass
        return None

    def can_fetch_audit(self, guild_id, event_name, max_requests=5, interval=10, cooldown_duration=300):
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
    async def on_member_update(self, before, after):
        guild = before.guild

        if await self.is_blacklisted_guild(guild.id):
            return

        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "member_update"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        if not self.can_fetch_audit(guild.id, 'member_update'):
            return

        log_entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.member_role_update, after.id)
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
        if whitelist_doc and whitelist_doc.get("memup"):
            return

        try:
            new_role = next(role for role in after.roles if role not in before.roles)
        except StopIteration:
            return

        if any([
            new_role.permissions.ban_members,
            new_role.permissions.administrator,
            new_role.permissions.manage_guild,
            new_role.permissions.manage_channels,
            new_role.permissions.manage_roles,
            new_role.permissions.mention_everyone,
            new_role.permissions.manage_webhooks
        ]):
            await self.take_action_and_revert(after, executor, new_role)
            await asyncio.sleep(3)

    async def take_action_and_revert(self, member, executor, new_role):
        retries = 3
        reason = "[ANTINUKE] Member Role Update with Dangerous Permissions | Unwhitelisted User | Security Action"
        while retries > 0:
            try:
                await member.remove_roles(new_role, reason=reason)
                await member.guild.ban(executor, reason=reason)
                return
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        await asyncio.sleep(float(retry_after))
                        retries -= 1
                else:
                    return
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                return
        return
