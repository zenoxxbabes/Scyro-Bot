import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import datetime
import pytz
import os

class AntiBotAdd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.antinuke_col = self.db["antinuke"]
        self.modules_col = self.db["antinuke_modules"]
        self.whitelist_col = self.db["antinuke_whitelist"]
        self.extra_col = self.db["extraowners"]

    async def cog_load(self):
        print("✅ [AntiBotAdd] Extension loaded & DB initialized (MongoDB).")

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
            # More restrictive time window for recent actions (5 minutes instead of 1 hour)
            cutoff_time = datetime.datetime.now(pytz.utc) - datetime.timedelta(minutes=5)
            async for entry in guild.audit_logs(action=action, limit=5):
                if entry.target.id == target_id and entry.created_at > cutoff_time:
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

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not member.bot:
            return

        guild = member.guild
        
        # Additional safety check
        if not guild.me.guild_permissions.kick_members or not guild.me.guild_permissions.view_audit_log:
            return
            
        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "bot"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        # Enhanced rate limiting
        if not self.can_fetch_audit(guild.id, "bot_add", max_requests=3, interval=5, cooldown_duration=180):
            return

        # Add delay to prevent race conditions (Discord Audit Logs are slow)
        await asyncio.sleep(2.0)
        
        # Use delay=0 inside fetch to avoid compounding waits
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.bot_add, member.id)
        if logs is None:
            return

        executor = logs.user
        
        # Enhanced permission and role checks
        if executor.id in {guild.owner_id, self.bot.user.id}:
            return
            
        # Check if executor is a high-ranking role (admin, etc.) - proceed with caution

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("botadd"):
            return

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
            return

        await self.take_action_and_kick_bot(guild, executor, member, "[ANTINUKE] Unwhitelisted user added a bot | Security Action")

    async def take_action_and_kick_bot(self, guild, executor, bot_member, reason, retries=3):
        # Enhanced logging for security events
        try:
            # First, try to kick the bot
            while retries > 0:
                try:
                    await guild.kick(bot_member, reason=reason)
                    break
                except discord.Forbidden:
                    return
                except discord.HTTPException as e:
                    if e.status == 429:
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            await asyncio.sleep(float(retry_after))
                            retries -= 1
                        else:
                            break
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
                    await guild.ban(executor, reason=reason)
                    break
                except discord.Forbidden:
                    return
                except discord.HTTPException as e:
                    if e.status == 429:
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            await asyncio.sleep(float(retry_after))
                            retries -= 1
                        else:
                            break
                    else:
                        retries -= 1
                        await asyncio.sleep(1)
                except Exception:
                    retries -= 1
                    await asyncio.sleep(1)
                    
        except Exception:
            # Log the error but don't stop the process
            pass

async def setup(bot):
    await bot.add_cog(AntiBotAdd(bot))
