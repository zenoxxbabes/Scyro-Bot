import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import random
import datetime
import os

class AntiEmojiCreate(commands.Cog):
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
    print("✅ [AntiEmojiCreate] Extension loaded & DB initialized (MongoDB).")

  async def fetch_audit_logs(self, guild, action):
    if not guild.me.guild_permissions.view_audit_log:
      return None
    try:
      await asyncio.sleep(random.uniform(0.5, 2.0))
      # More restrictive time window for recent actions (5 minutes instead of 1 hour)
      cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=5)
      async for entry in guild.audit_logs(action=action, limit=5):
        if entry.created_at > cutoff_time:
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
          return await self.fetch_audit_logs(guild, action)
    except Exception as e:
      # Log unexpected errors
      pass
    return None

  @commands.Cog.listener()
  async def on_guild_emojis_update(self, guild, before, after):
    # Additional safety check
    if not guild.me.guild_permissions.ban_members or not guild.me.guild_permissions.view_audit_log:
      return
      
    if len(after) > len(before):
        # Check Antinuke Status
        antinuke_doc = await self.antinuke_col.find_one({"guild_id": guild.id})
        if not antinuke_doc or not antinuke_doc.get("status"):
            return

        # Check Module Status
        module_doc = await self.modules_col.find_one({"guild_id": guild.id, "module": "emoji_create"})
        if module_doc and not module_doc.get("enabled", True):
            return
        if not module_doc:
             pass # Enabled by default if missing

        # Add delay to prevent race conditions
        await asyncio.sleep(0.5)
        
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.emoji_create)
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
        await guild.ban(executor, reason="[ANTINUKE] Emoji Create | Unwhitelisted User | Security Action")
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
    return
