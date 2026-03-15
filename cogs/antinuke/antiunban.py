import discord
from discord.ext import commands
import motor.motor_asyncio
from datetime import timedelta, datetime
import asyncio
import os

class AntiUnban(commands.Cog):
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
        print("✅ [AntiUnban] Extension loaded & DB initialized (MongoDB).")

    async def fetch_audit_logs(self, guild, action, target_id):
        if not guild.me.guild_permissions.view_audit_log:
            return None
        try:
            # More restrictive time window for recent actions (5 minutes instead of 1 hour)
            cutoff_time = datetime.now() - timedelta(minutes=5)
            async for entry in guild.audit_logs(limit=5, action=action):
                if entry.target.id == target_id and entry.created_at > cutoff_time:
                    return entry
        except discord.Forbidden:
            # Log permission issues
            pass
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    retry_after = float(retry_after)
                    await asyncio.sleep(retry_after)
                    return await self.fetch_audit_logs(guild, action, target_id)
        except Exception as e:
            # Log unexpected errors
            pass
        return None

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        # Additional safety check
        if not guild.me.guild_permissions.ban_members or not guild.me.guild_permissions.view_audit_log:
            return
            
        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "unban"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass

        # Add delay to prevent race conditions
        await asyncio.sleep(0.5)
        
        log_entry = await self.fetch_audit_logs(guild, discord.AuditLogAction.unban, user.id)
        if log_entry is None:
            return

        executor = log_entry.user

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

        # Check Extra Owner
        extra_owner_doc = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": executor.id})
        if extra_owner_doc:
            return

        # Check Whitelist
        whitelist_doc = await self.whitelist_col.find_one({"guild_id": guild.id, "user_id": executor.id})
        if whitelist_doc and whitelist_doc.get("ban"):
            return

        await self.ban_executor(guild, executor, user)

    async def ban_executor(self, guild, executor, user):
        # First, try to ban the executor
        retries = 3
        while retries > 0:
            try:
                await guild.ban(executor, reason="[ANTINUKE] Member Unban | Unwhitelisted User | Security Action")
                break
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
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                retries -= 1
                await asyncio.sleep(1)
        
        # Then, try to re-ban the user
        retries = 3
        while retries > 0:
            try:
                await guild.ban(user, reason="[ANTINUKE] Reverting unban by unwhitelisted user | Security Action")
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
            except discord.errors.RateLimited as e:
                await asyncio.sleep(e.retry_after)
                retries -= 1
            except Exception:
                retries -= 1
                await asyncio.sleep(1)
