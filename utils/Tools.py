import json, sys, os
import discord
from discord.ext import commands
from core import Context
import motor.motor_asyncio
import os

# Helper to get DB
def get_database():
    mongo_url = os.getenv("MONGO_URI")
    if not mongo_url:
        return None
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    return client.get_default_database()

async def is_topcheck_enabled(guild_id: int, bot=None):
    try:
        if bot and hasattr(bot, 'db') and bot.db is not None:
             db = bot.db
        else:
             db = get_database()
             
        if db is None: return False
        
        doc = await db.topcheck_settings.find_one({"guild_id": guild_id})
        return doc and doc.get("enabled", False)
    except Exception:
        return False

# ... JSON utils ...

async def getConfig(guildID, bot=None):
    try:
        if bot and hasattr(bot, 'db') and bot.db is not None:
             db = bot.db
        else:
             db = get_database()
             
        if db is None: return {"prefix": "."}

        doc = await db.prefixes.find_one({"guild_id": guildID})
        if doc:
            return {"prefix": doc.get("prefix", ".")}
        else:
            defaultConfig = {"prefix": "."}
            await updateConfig(guildID, defaultConfig, bot)
            return defaultConfig
    except Exception as e:
        print(f"Error in getConfig: {e}")
        return {"prefix": "."}

async def updateConfig(guildID, data, bot=None):
    try:
        if bot and hasattr(bot, 'db') and bot.db is not None:
             db = bot.db
        else:
             db = get_database()
             
        if db is None: return

        await db.prefixes.update_one(
            {"guild_id": guildID},
            {"$set": {"prefix": data["prefix"]}},
            upsert=True
        )
    except Exception as e:
        print(f"Error in updateConfig: {e}")


def restart_program():
  python = sys.executable
  os.execl(python, python, *sys.argv)


def blacklist_check():

  async def predicate(ctx):
    if not hasattr(ctx.bot, 'db') or ctx.bot.db is None:
        return True # Fail open if DB issue
        
    try:
        # Check User Blacklist
        if await ctx.bot.db.user_blacklist.find_one({"user_id": ctx.author.id}):
            return False

        # Check Guild Blacklist
        if await ctx.bot.db.guild_blacklist.find_one({"guild_id": ctx.guild.id}):
            return False
            
        return True
    except Exception:
        return True

  return commands.check(predicate)
    

async def get_ignore_data(guild_id: int, bot=None) -> dict:
    data = {
        "channel": set(),
        "user": set(),
        "command": set(),
        "bypassuser": set(),
    }
    
    # If no bot or no db, return empty (fail safe)
    if not bot or not hasattr(bot, 'db') or bot.db is None:
        return data

    try:
        # Ignore Module Collections
        # Assuming Ignore cog uses:
        # db.ignored_channels, db.ignored_users, db.ignored_commands, db.bypassed_users
        
        # Channels
        async for doc in bot.db.ignored_channels.find({"guild_id": guild_id}):
            data["channel"].add(str(doc["channel_id"]))
            
        # Users
        async for doc in bot.db.ignored_users.find({"guild_id": guild_id}):
            data["user"].add(str(doc["user_id"]))
            
        # Commands
        async for doc in bot.db.ignored_commands.find({"guild_id": guild_id}):
            data["command"].add(doc["command_name"].strip().lower())
            
        # Bypassed Users
        async for doc in bot.db.bypass_users.find({"guild_id": guild_id}):
            data["bypassuser"].add(str(doc["user_id"]))
            
    except Exception as e:
        print(f"Error fetching ignore data: {e}")

    return data

def ignore_check():
    async def predicate(ctx):
        # Pass ctx.bot to get_ignore_data
        data = await get_ignore_data(ctx.guild.id, ctx.bot)
        ch = data["channel"]
        iuser = data["user"]
        cmd = data["command"]
        buser = data["bypassuser"]

        if str(ctx.author.id) in buser:
            return True
        if str(ctx.channel.id) in ch or str(ctx.author.id) in iuser:
            return False

        command_name = ctx.command.name.strip().lower()
        aliases = [alias.strip().lower() for alias in ctx.command.aliases]
        if command_name in cmd or any(alias in cmd for alias in aliases):
            return False

        return True

    return commands.check(predicate)

def top_check():
    async def predicate(ctx):
        if not ctx.guild:
            return True

        if getattr(ctx, "invoked_with", None) in ["help", "h"]:
            return True

        topcheck_enabled = await is_topcheck_enabled(ctx.guild.id, ctx.bot)

        if not topcheck_enabled:
            return True

        if ctx.author != ctx.guild.owner and ctx.author.top_role.position <= ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title="<:alert:1348340453803687966> Access Denied", 
                description="Your top role must be at a **higher** position than my top role.",
                color=0x000000
            )
            embed.set_footer(
                text=f"“{ctx.command.qualified_name}” command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return False

        return True

    return commands.check(predicate)