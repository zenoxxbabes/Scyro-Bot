import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiChannelCreate(commands.Cog):
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
        print("✅ [AntiChannelCreate] Extension loaded & DB initialized (MongoDB).")

    def can_fetch_audit(self, guild_id, event_name, max_requests=3, interval=5, cooldown_duration=180):
        now = datetime.datetime.now()
        self.event_limits.setdefault(guild_id, {}).setdefault(event_name, []).append(now)

        timestamps = self.event_limits[guild_id][event_name]
        timestamps = [t for t in timestamps if (now - t).total_seconds() <= interval]
        self.event_limits[guild_id][event_name] = timestamps

        if len(timestamps) > max_requests:
            self.cooldowns.setdefault(guild_id, {})[event_name] = now
            return False
        return True

    async def fetch_audit_logs(self, guild, action, target_id, delay=1):
        if not guild.me.guild_permissions.view_audit_log:
            return None
        try:
            # More restrictive time window for recent actions (5 minutes instead of 1 hour)
            cutoff_time = datetime.datetime.now(pytz.utc) - datetime.timedelta(minutes=5)
            async for entry in guild.audit_logs(action=action, limit=5):
                if entry.target.id == target_id and entry.created_at > cutoff_time:
                    await asyncio.sleep(delay)
                    return entry
        except discord.Forbidden:
            # Log permission issues
            pass
        except discord.HTTPException:
            # Log API issues
            pass
        except Exception:
            # Log unexpected errors
            pass
        return None

    async def move_role_below_bot(self, guild):
        bot_top_role = guild.me.top_role
        most_populated_role = max(
            [role for role in guild.roles if role.position < bot_top_role.position and not role.managed and role != guild.default_role],
            key=lambda r: len(r.members),
            default=None
        )
        if most_populated_role:
            try:
                await most_populated_role.edit(position=bot_top_role.position - 1, reason="Emergency: Adjusting roles for security")
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

    async def delete_channel_and_ban(self, channel, executor, delay=2, retries=3):
        # First, try to delete the channel
        while retries > 0:
            try:
                await channel.delete(reason="[ANTINUKE] Channel created by unwhitelisted user | Security Action")
                break
            except discord.NotFound:
                # Channel already deleted
                break
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After', delay)
                    await asyncio.sleep(float(retry_after))
                    retries -= 1
                else:
                    retries -= 1
                    await asyncio.sleep(1)
            except Exception:
                retries -= 1
                await asyncio.sleep(1)
        
        # Then, try to ban the executor
        retries = 3
        while retries > 0:
            try:
                await channel.guild.ban(executor, reason="[ANTINUKE] Channel Create | Unwhitelisted User | Security Action")
                return
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After', delay)
                    await asyncio.sleep(float(retry_after))
                    retries -= 1
                else:
                    retries -= 1
                    await asyncio.sleep(1)
            except Exception:
                retries -= 1
                await asyncio.sleep(1)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        guild = channel.guild
        
        # Additional safety check
        if not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.view_audit_log:
            return

        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "channel_create"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        # Enhanced rate limiting
        if not self.can_fetch_audit(guild.id, "channel_create", max_requests=3, interval=5, cooldown_duration=180):
            await self.move_role_below_bot(guild)
            await asyncio.sleep(5)

        # Add small delay for Audit Log propagation (0.5s is usually enough)
        await asyncio.sleep(0.5)
        
        # Use delay=0 inside fetch to avoid compounding waits
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.channel_create, channel.id, delay=0)
        if logs is None:
            return

        executor = logs.user
        
        # Trusted Users Check
        if executor.id in {guild.owner_id, self.bot.user.id}:
            return
        
        # WHITELIST CHECK: Database
        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
            return

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("chcr"):
            return
        
        # NO ADMIN CHECK HERE! 
        # If they are Admin but not Whitelisted, they get BANNED.
        
        # ACTION: BAN FIRST, THEN DELETE
        await self.ban_and_delete(channel, executor)

    async def ban_and_delete(self, channel, executor):
        # 1. BAN (Priority)
        try:
            await channel.guild.ban(executor, reason="[ANTINUKE] Unwhitelisted Channel Create")
        except:
            pass # Continue to delete even if ban fails (e.g. already banned)
            
        # 2. DELETE CHANNEL
        try:
            await channel.delete(reason="[ANTINUKE] Reverting Action")
        except:
            pass