from __future__ import annotations
import motor.motor_asyncio
import discord
from discord.ext import commands, tasks
import aiosqlite
import asyncio
import importlib
import inspect
from typing import List
from colorama import Fore, Style, init
import os
import time
import aiohttp

from utils.config import OWNER_IDS
from utils import getConfig, updateConfig
from .Context import Context

init(autoreset=True)

extensions: List[str] = [
    "cogs",
    "status"
]

class Scyro(commands.Bot):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.all()
        
        # MongoDB Init
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongo_client = None
        self.db = None
        
        super().__init__(
            command_prefix=get_prefix, 
            case_insensitive=True,
            intents=intents,
            status=discord.Status.online,
            strip_after_prefix=True,
            owner_ids=OWNER_IDS,
            allowed_mentions=discord.AllowedMentions(everyone=False, replied_user=False, roles=False)
        )
        
        self.status_index = 0
        self.statuses = [
            {
                "status": discord.Status.online,
                "activity": discord.Game(name="Use /antinuke enable")
            },
            {
                "status": discord.Status.online,
                "activity": discord.Game(name="Watching Scyro")
            },
            {
                "status": discord.Status.online,
                "activity": discord.Game(name="Let me /help ")
            },
            {
                "status": discord.Status.online,
                "activity": discord.Game(name="at Scyro.xyz")
            },
            {
                "status": discord.Status.online,
                "activity": discord.Game(name="Protecting Communities.")
            }
        ]

    async def setup_hook(self):
        # Initialize MongoDB
        if self.mongo_uri:
            try:
                self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
                self.db = self.mongo_client.get_database()
                print(f"{Fore.GREEN}{Style.BRIGHT}✅ [Core] MongoDB Connected Successfully")
            except Exception as e:
                print(f"{Fore.RED}{Style.BRIGHT}❌ [Core] MongoDB Connection Failed: {e}")
        else:
            print(f"{Fore.RED}{Style.BRIGHT}❌ [Core] MONGO_URI not set!")

        # Create database directory if it doesn't exist
        os.makedirs('db', exist_ok=True)
        
        # Load all extensions
        await self.load_extensions()

        # Start the status rotation task
        self.status_rotation.start()

    async def load_extensions(self):
        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(f"{Fore.GREEN}{Style.BRIGHT}Loaded extension {extension}")
            except Exception as e:
                print(f"{Fore.RED}{Style.BRIGHT}Failed to load extension {extension}: {e}")

    async def on_connect(self):
        # Initial status setup - this will be overridden by the rotation task
        await self.change_presence(
            status=discord.Status.do_not_disturb,
            activity=discord.CustomActivity(name='Starting up...')
        )

    def format_guild_count(self, count):
        if count < 1000:
            return f"{count/1000:.3f}k"
        else:
            val = count / 1000
            if val.is_integer():
                return f"{int(val)}k"
            else:
                return f"{val:.1f}k"

    @tasks.loop(minutes=1)
    async def status_rotation(self):
        """Rotate bot status every 1 minute"""
        try:
            # Update the dynamic status
            current_count = len(self.guilds)
            formatted_count = self.format_guild_count(current_count)
            
            # Update the specific status entry (index 1 is the one requested)
            self.statuses[1]["activity"] = discord.Game(
                name=f"/help • {formatted_count} Servers"
            )

            current_status = self.statuses[self.status_index]
            await self.change_presence(
                status=current_status["status"],
                activity=current_status["activity"]
            )
            
            # Move to next status
            self.status_index = (self.status_index + 1) % len(self.statuses)
            
        except Exception as e:
            print(f"{Fore.RED}{Style.BRIGHT}Error updating status: {e}")

    @status_rotation.before_loop
    async def before_status_rotation(self):
        """Wait until the bot is ready before starting status rotation"""
        await self.wait_until_ready()

    async def close(self):
        """Clean shutdown - cancel the tasks"""
        if hasattr(self, 'status_rotation'):
            self.status_rotation.cancel()

        await super().close()

    async def invoke_help_command(self, ctx: Context) -> None:
        return await ctx.send_help(ctx.command)

    async def on_ready(self):
        """Enhanced on_ready without shard information"""
        guild_count = len(self.guilds)
            
        print(f"{Fore.GREEN}{Style.BRIGHT}✅ Bot is ready!")
        print(f"{Fore.BLUE}{Style.BRIGHT}   Handling {guild_count} guilds")

    async def on_guild_join(self, guild):
        """Update when joining a new guild"""
        print(f"{Fore.GREEN}{Style.BRIGHT}Joined new guild: {guild.name} (ID: {guild.id})")

    async def on_guild_remove(self, guild):
        """Update when leaving a guild"""
        print(f"{Fore.YELLOW}{Style.BRIGHT}Left guild: {guild.name} (ID: {guild.id})")


def setup_bot():
    intents = discord.Intents.all()
    bot = Scyro()
    return bot

async def get_prefix(bot: Scyro, message: discord.Message):
    default_prefix = "."
    
    if not hasattr(bot, 'db') or bot.db is None:
        return commands.when_mentioned_or(default_prefix)(bot, message)

    # Check for No Prefix (Global)
    try:
        np_user = await bot.db.no_prefix_users.find_one({"user_id": message.author.id})
        if np_user:
            # If user has NP, allow empty prefix
            # Check if command is invoked with empty prefix, or guild prefix
            # Strategy: Return both guild prefix/default and empty string
            
            # Fetch guild prefix if in guild
            if message.guild:
                guild_config = await getConfig(message.guild.id)
                prefix = guild_config.get("prefix", default_prefix)
                return commands.when_mentioned_or(prefix, "")(bot, message)
            else:
                return commands.when_mentioned_or(default_prefix, "")(bot, message)
    except Exception as e:
        print(f"Error checking NP: {e}")

    # Normal user behavior
    if message.guild:
        guild_config = await getConfig(message.guild.id)
        prefix = guild_config.get("prefix", default_prefix)
        return commands.when_mentioned_or(prefix)(bot, message)
    else:
        return commands.when_mentioned_or(default_prefix)(bot, message)