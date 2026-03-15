import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiGuildUpdate(commands.Cog):
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
        print("✅ [AntiGuildUpdate] Extension loaded & DB initialized (MongoDB).")

    async def fetch_audit_logs(self, guild, action):
        if not guild.me.guild_permissions.view_audit_log:
            return None
        try:
            # More restrictive time window for recent actions (5 minutes instead of 1 hour)
            cutoff_time = datetime.datetime.now(pytz.utc) - datetime.timedelta(minutes=5)
            async for entry in guild.audit_logs(action=action, limit=5):
                if entry.created_at > cutoff_time:
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

    async def is_blacklisted_guild(self, guild_id):
        doc = await self.blacklist_col.find_one({"guild_id": guild_id})
        return bool(doc)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        guild = before
        
        # Additional safety check
        if not guild.me.guild_permissions.view_audit_log or not guild.me.guild_permissions.ban_members:
            return
            
        if await self.is_blacklisted_guild(guild.id):
            return

        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "guild_update"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        # Enhanced rate limiting
        if not self.can_fetch_audit(guild.id, 'guild_update', max_requests=3, interval=5, cooldown_duration=180):
            return

        # Add delay to prevent race conditions
        await asyncio.sleep(0.5)
        
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.guild_update)
        if logs is None:
            return

        executor = logs.user
        difference = discord.utils.utcnow() - logs.created_at
        # More restrictive time window (5 minutes instead of 1 hour)
        if difference.total_seconds() > 300:
            return

        # Enhanced permission and role checks
        if executor.id in {guild.owner_id, self.bot.user.id}:
            return
            
        # Check if executor is a high-ranking role (admin, etc.)
        try:
            executor_member = await guild.fetch_member(executor.id)
            # Skip if executor has administrator permissions
            if executor_member.guild_permissions.administrator:
                return
        except discord.NotFound:
            # If we can't find the member, proceed with caution
            pass
        except Exception:
            # If any other error occurs, proceed with caution
            pass

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("serverup"):
            return

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
            return

        await self.ban_executor_and_revert_changes(before, after, executor)

    async def ban_executor_and_revert_changes(self, before, after, executor):
        try:
            retries = 3
            while retries > 0:
                try:
                    await self.ban_executor(before, executor)
                    await asyncio.sleep(1)  # Short delay before reverting changes
                    await self.revert_guild_changes(before, after)
                    return
                except discord.Forbidden:
                    return
                except discord.HTTPException as e:
                    if e.status == 429:
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            retry_after = float(retry_after)
                            await asyncio.sleep(retry_after)
                            retries -= 1
                        else:
                            break
                    else:
                        retries -= 1
                        await asyncio.sleep(1)
                except discord.errors.RateLimited as e:
                    await asyncio.sleep(e.retry_after)
                    retries -= 1
                except Exception:
                    retries -= 1
                    await asyncio.sleep(1)
        except Exception:
            # Log error but continue
            pass

    async def ban_executor(self, guild, executor):
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="[ANTINUKE] Guild Update | Unwhitelisted User | Security Action")
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
                        retries -= 1
                        await asyncio.sleep(1)
                else:
                    retries -= 1
                    await asyncio.sleep(1)
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                retries -= 1
                await asyncio.sleep(1)

    async def revert_guild_changes(self, before, after):
        retries = 3
        while retries > 0:
            try:
                changes_made = False
                if before.name != after.name:
                    await after.edit(name=before.name)
                    changes_made = True
                if before.icon != after.icon:
                    await after.edit(icon=before.icon)
                    changes_made = True
                if before.splash != after.splash:
                    await after.edit(splash=before.splash)
                    changes_made = True
                if before.banner != after.banner:
                    await after.edit(banner=before.banner)
                    changes_made = True
                    
                if changes_made:
                    # Log the reverted changes
                    pass
                    
                return
            except discord.Forbidden:
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                        await asyncio.sleep(retry_after)
                        retries -= 1
                    else:
                        retries -= 1
                        await asyncio.sleep(1)
                else:
                    retries -= 1
                    await asyncio.sleep(1)
            except Exception:
                retries -= 1
                await asyncio.sleep(1)

        return
