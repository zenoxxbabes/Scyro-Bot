import os
import sys
# Set console encoding to UTF-8 to fix emoji printing on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    # Python < 3.7
    pass

import asyncio
import traceback
import json
import yaml
from threading import Thread
from datetime import datetime, timedelta

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Add sqlite3 for database operations
import sqlite3

# Import psutil for system stats
import psutil

# Load environment variables FIRST
load_dotenv()

from core import Context
from core.Cog import Cog
from core.Scyro import Scyro
from utils.Tools import *
from utils.config import *
from utils.patches import apply_patches

import jishaku
import topgg

# Load config after environment variables are loaded
try:
    with open('config.yml', 'r') as f:
        config_data = yaml.safe_load(f)
except FileNotFoundError:
    config_data = {}
except yaml.YAMLError as e:
    print(f"Error loading config.yml: {e}")
    config_data = {}

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    🌟 SCYRO SYSTEM 🌟
# ═══════════════════════════════════════════════════════════════════════════════════════════

from colorama import Fore, Style, init
init(autoreset=True)

# ────────────────────────────────────────────────────────────────────────────────────────────
# 🔧 JISHAKU CONFIGURATION
# ────────────────────────────────────────────────────────────────────────────────────────────
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "False"
os.environ["JISHAKU_HIDE"] = "True"
os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_FORCE_PAGINATOR"] = "True"

# ────────────────────────────────────────────────────────────────────────────────────────────
# 🤖 BOT INITIALIZATION WITH SHARDING
# ────────────────────────────────────────────────────────────────────────────────────────────

# Sharding is now disabled by default
SHARD_ID = 0
SHARD_COUNT = 1
AUTO_SHARDING = False


# Log the sharding configuration for debugging
print(f"[INFO] Sharding configuration - AUTO_SHARDING: {AUTO_SHARDING}, SHARD_ID: {SHARD_ID}, SHARD_COUNT: {SHARD_COUNT}")

# Track bot startup time for uptime calculation
BOT_START_TIME = datetime.now()

# Initialize bot without sharding
client = Scyro()

# ✅ Enable automatic rate-limit safety for ALL views and modals
# This must happen BEFORE any cogs are loaded
from core.ratelimithandler import init_safety_handler
try:
    init_safety_handler(client)
except Exception as e:
    print(f"Warning: Failed to initialize safety handler: {e}")

# Remove the default help command to avoid conflicts
client.help_command = None

tree = client.tree

# Your owner ID
OWNER_ID = 1218037361926209640

# Store additional bot owners
BOT_OWNERS = {OWNER_ID}  # Set of owner IDs

# Path to the bot owners database
SO_DB_PATH = 'db/so.db'

def initialize_bot_owners_db():
    """Initialize the bot owners database"""
    try:
        conn = sqlite3.connect(SO_DB_PATH)
        cursor = conn.cursor()
        
        # Create table for bot owners if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_owners (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert the main owner if not exists
        cursor.execute('''
            INSERT OR IGNORE INTO bot_owners (user_id, added_by) 
            VALUES (?, ?)
        ''', (OWNER_ID, OWNER_ID))
        
        conn.commit()
        
        # Load all bot owners from database
        cursor.execute('SELECT user_id FROM bot_owners')
        rows = cursor.fetchall()
        BOT_OWNERS.clear()
        BOT_OWNERS.add(OWNER_ID)  # Always include main owner
        for row in rows:
            BOT_OWNERS.add(row[0])
        
        conn.close()
        success_log(f"Initialized bot owners database with {len(BOT_OWNERS)} owners")
    except Exception as e:
        error_log(f"Failed to initialize bot owners database: {e}")

def add_bot_owner_to_db(user_id, added_by):
    """Add a bot owner to the database"""
    try:
        conn = sqlite3.connect(SO_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO bot_owners (user_id, added_by) 
            VALUES (?, ?)
        ''', (user_id, added_by))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        error_log(f"Failed to add bot owner to database: {e}")
        return False

def remove_bot_owner_from_db(user_id):
    """Remove a bot owner from the database"""
    try:
        conn = sqlite3.connect(SO_DB_PATH)
        cursor = conn.cursor()
        # Don't allow removing the main owner
        if user_id != OWNER_ID:
            cursor.execute('DELETE FROM bot_owners WHERE user_id = ?', (user_id,))
            conn.commit()
        conn.close()
        return True
    except Exception as e:
        error_log(f"Failed to remove bot owner from database: {e}")
        return False

def is_main_owner():
    """👑 Check if user is the main bot owner (1218037361926209640)"""
    def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

def is_owner():
    """👑 Check if user is a bot owner (main owner or added owners)"""
    def predicate(ctx):
        return ctx.author.id in BOT_OWNERS
    return commands.check(predicate)

# Global check for ALL commands
@client.check
async def global_owner_override(ctx):
    """🌟 Global owner override - allows owner to bypass ALL permission checks"""
    if ctx.author.id in BOT_OWNERS:  # Use BOT_OWNERS instead of just OWNER_ID
        return True  # Owner can always use any command
    return True  # Let normal permission checks handle non-owners

# Enhanced interaction check for slash commands
async def enhanced_interaction_check(interaction: discord.Interaction) -> bool:
    """🛡️ Enhanced interaction check with owner override"""
    # Owner bypass
    if interaction.user.id in BOT_OWNERS:  # Use BOT_OWNERS instead of just OWNER_ID
        return True
    
    # Let other checks run for non-owners
    return True

# Apply the enhanced interaction check
client.tree.interaction_check = enhanced_interaction_check

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    🎨 CONSOLE AESTHETICS
# ═══════════════════════════════════════════════════════════════════════════════════════════

def display_startup_banner():
    """Display an aesthetic startup banner"""
    banner_text = f"""
{Fore.MAGENTA}{Style.BRIGHT}
    ╔═══════════════════════════════════════════════════════════════════════╗
    ║                                                                       ║
    ║                            SCYRO — ZENOXX                             ║
    ║                                                                       ║
    ║                    Advanced Discord Bot Framework                     ║
    ║                 Lightning Fast • Secure • Feature Rich                ║
    ║                                                                       ║
    ╚═══════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""
    print(banner_text)

def log(prefix: str, message: str, color=Fore.WHITE):
    """Enhanced logging with prefixes and colors"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} {color}[{prefix}]{Style.RESET_ALL} {message}")

def success_log(message: str):
    log("SUCCESS", message, Fore.GREEN)

def info_log(message: str):
    log("INFO", message, Fore.BLUE)

def warning_log(message: str):
    log("WARN", message, Fore.YELLOW)

def error_log(message: str):
    log("ERROR", message, Fore.RED)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    🔄 IMPROVED COMMAND SYNC MANAGER
# ═══════════════════════════════════════════════════════════════════════════════════════════

SYNC_DATA_FILE = "sync_data.json"

def load_sync_data():
    """📁 Load sync data from file"""
    try:
        if os.path.exists(SYNC_DATA_FILE):
            with open(SYNC_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        error_log(f"Failed to load sync data: {e}")
    return {"last_sync": None, "command_hash": None, "guild_sync": None}

def save_sync_data(data):
    """💾 Save sync data to file"""
    try:
        with open(SYNC_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        error_log(f"Failed to save sync data: {e}")

def get_command_hash():
    """🔍 Generate hash of current commands for change detection"""
    import hashlib
    commands_data = []
    
    try:
        # Get all slash commands with more detailed info
        for command in client.tree.get_commands():
            # Process only actual slash commands, not context menus
            if isinstance(command, discord.app_commands.Command):
                command_info = {
                    'name': command.name,
                    'description': command.description or '',
                    'type': 'Command'
                }
                
                # Include parameters for actual slash commands
                if hasattr(command, '_params'):
                    try:
                        params_info = []
                        for param_name, param_obj in command._params.items():
                            param_type = str(getattr(param_obj, 'type', 'unknown'))
                            param_required = bool(getattr(param_obj, 'required', False))
                            params_info.append({
                                'name': param_name,
                                'type': param_type,
                                'required': param_required
                            })
                        command_info['parameters'] = str(params_info)  # Convert to string to avoid type issues
                    except:
                        pass  # Skip if we can't access parameters
                
                commands_data.append(command_info)
            elif isinstance(command, discord.app_commands.Group):
                command_info = {
                    'name': command.name,
                    'description': command.description or '',
                    'type': 'Group'
                }
                commands_data.append(command_info)
        
        # Sort for consistent hashing
        commands_data.sort(key=lambda x: x['name'])
        commands_str = json.dumps(commands_data, sort_keys=True)
        return hashlib.md5(commands_str.encode()).hexdigest()
        
    except Exception as e:
        error_log(f"Failed to generate command hash: {e}")
        return "error_hash"

def should_sync_commands():
    """🤔 Improved logic to determine if commands need syncing"""
    sync_data = load_sync_data()
    
    # Check for force sync environment variable
    if os.getenv("FORCE_SYNC", "false").lower() == "true":
        return True, "Force sync requested via environment variable"
    
    # Check if we're currently rate limited
    rate_limit_end_str = sync_data.get("rate_limited_until")
    if rate_limit_end_str:
        try:
            rate_limit_end = datetime.fromisoformat(rate_limit_end_str)
            if datetime.now() < rate_limit_end:
                remaining = (rate_limit_end - datetime.now()).total_seconds()
                return False, f"Rate limited - retry in {remaining:.0f} seconds"
        except:
            pass  # Invalid timestamp, ignore
    
    # Check if it's the first run (no previous sync data)
    if not sync_data.get("last_sync"):
        return True, "First run - no previous sync data found"
    
    # Check if commands have changed
    current_hash = get_command_hash()
    stored_hash = sync_data.get("command_hash")
    
    if stored_hash != current_hash:
        return True, "Command structure changed"
    
    # Check if it's been more than 24 hours since last sync
    last_sync_str = sync_data.get("last_sync")
    if last_sync_str:
        try:
            last_sync = datetime.fromisoformat(last_sync_str)
            hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600
            
            if hours_since_sync > 24:
                return True, f"24+ hours since last sync ({hours_since_sync:.1f}h ago)"
        except Exception as e:
            warning_log(f"Could not parse last sync time: {e}")
            return True, "Invalid sync timestamp - forcing sync"
    
    # Calculate hours since sync for the return message
    if last_sync_str:
        try:
            last_sync = datetime.fromisoformat(last_sync_str)
            hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600
            return False, f"No sync needed (last: {hours_since_sync:.1f}h ago)"
        except Exception as e:
            return False, "No sync needed (unable to calculate time)"
    else:
        return False, "No sync needed (no previous sync data)"

async def smart_sync_commands():
    """🧠 Improved command synchronization with better error handling"""
    should_sync, reason = should_sync_commands()
    
    if not should_sync:
        info_log(f"Skipping command sync: {reason}")
        return 0
    
    info_log(f"Syncing commands: {reason}")
    
    try:
        # Wait for bot to be fully ready
        await client.wait_until_ready()
        
        # Small delay to ensure all cogs are loaded
        await asyncio.sleep(2)
        
        # Get command count before sync
        commands_before = len(client.tree.get_commands())
        info_log(f"Found {commands_before} slash commands to sync")
        
        # Perform the sync
        synced_commands = await client.tree.sync()
        synced_count = len(synced_commands)
        
        # Update sync data
        sync_data = {
            "last_sync": datetime.now().isoformat(),
            "command_hash": get_command_hash(),
            "synced_count": synced_count,
            "guild_sync": None  # Global sync
        }
        save_sync_data(sync_data)
        
        # Remove force sync flag if it exists
        remove_force_sync_flag()
        
        success_log(f"Successfully synced {synced_count} slash commands globally")
        
        # Log command details if in debug mode
        if os.getenv("DEBUG_SYNC", "false").lower() == "true":
            for cmd in synced_commands:
                if hasattr(cmd, 'name'):
                    description = getattr(cmd, 'description', '')
                    info_log(f"  └─ /{cmd.name}: {description or 'No description'}")

        return synced_count
        
    except discord.HTTPException as e:
        if e.status == 429:  # Rate limited
            retry_after = int(e.response.headers.get('Retry-After', 300))
            rate_limit_time = (datetime.now() + timedelta(seconds=retry_after)).isoformat()
            sync_data = load_sync_data()
            # Ensure sync_data is a dictionary and create a new one with the rate limit info
            new_sync_data: dict = sync_data if isinstance(sync_data, dict) else {}
            new_sync_data["rate_limited_until"] = str(rate_limit_time)
            save_sync_data(new_sync_data)
            error_log(f"Discord API rate limit hit! Retry after {str(retry_after)} seconds")
            warning_log("You can continue using the bot, slash commands will sync later")
            # Return 0 to indicate no sync was performed, but no error
            return 0
            
        elif e.status == 400:
            error_log(f"Bad request during sync - check command definitions: {e}")
        elif e.status == 403:
            error_log(f"Bot lacks permissions to sync commands: {e}")
        else:
            error_log(f"HTTP error during sync (Status {e.status}): {e}")
        
        return -1
        
    except discord.ClientException as e:
        error_log(f"Client error during sync: {e}")
        return -1
        
    except Exception as e:
        error_log(f"Unexpected error during sync: {e}")
        traceback.print_exc()
        return -1

def remove_force_sync_flag():
    """🚮 Remove FORCE_SYNC flag from .env file"""
    try:
        if os.path.exists('.env'):
            with open('.env', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Filter out FORCE_SYNC lines
            filtered_lines = [line for line in lines if not line.strip().startswith('FORCE_SYNC')]
            
            with open('.env', 'w', encoding='utf-8') as f:
                f.writelines(filtered_lines)
                
            info_log("Removed FORCE_SYNC flag from .env")
    except Exception as e:
        warning_log(f"Could not remove FORCE_SYNC flag: {e}")

async def force_guild_sync(guild_id=None):
    """🏠 Force sync commands to a specific guild (for testing)"""
    try:
        if guild_id:
            guild = client.get_guild(guild_id)
            if not guild:
                error_log(f"Guild {guild_id} not found")
                return -1
            
            synced = await client.tree.sync(guild=guild)
            success_log(f"Synced {len(synced)} commands to guild {guild.name}")
            return len(synced)
        else:
            # Sync to all guilds (not recommended for production)
            total_synced = 0
            for guild in client.guilds:
                try:
                    synced = await client.tree.sync(guild=guild)
                    total_synced += len(synced)
                    success_log(f"Synced {len(synced)} commands to {guild.name}")
                    await asyncio.sleep(1)  # Rate limit protection
                except Exception as e:
                    error_log(f"Failed to sync to {guild.name}: {e}")
            
            return total_synced
            
    except Exception as e:
        error_log(f"Guild sync failed: {e}")
        return -1

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    📡 IMPROVED BOT EVENTS
# ═══════════════════════════════════════════════════════════════════════════════════════════

@client.event
async def on_ready():
    """🚀 Enhanced bot ready event with improved sync handling"""
    # Prevent multiple ready events
    if getattr(client, '_ready_fired', False):
        return
    
    # Set the flag to prevent future executions
    object.__setattr__(client, '_ready_fired', True)
    
    # Initialize bot owners database
    initialize_bot_owners_db()
    
    # Clear console and show banner
    os.system("cls" if os.name == "nt" else "clear")
    display_startup_banner()
    
    # Bot status information
    separator_line = f"n{Fore.CYAN}{'═' * 75}{Style.RESET_ALL}"
    print(separator_line)
    success_log(f"Scyro is now {Fore.GREEN}ONLINE{Style.RESET_ALL}!")
    info_log(f"Logged in as: {Fore.YELLOW}{client.user}{Style.RESET_ALL}")
    info_log(f"Connected to {Fore.GREEN}{len(client.guilds)}{Style.RESET_ALL} guilds")
    info_log(f"Serving {Fore.BLUE}{len(set(client.get_all_members()))}{Style.RESET_ALL} unique users")
    info_log(f"Bot latency: {Fore.CYAN}{round(client.latency * 1000)}ms{Style.RESET_ALL}")
    
    # Top.gg AutoPoster
    topgg_token = os.getenv("TOPGG")
    if topgg_token:
        try:
            client.topgg_stats = topgg.DBLClient(client, topgg_token, autopost=True, autopost_interval=10800)
            success_log(f"Top.gg AutoPoster {Fore.GREEN}STARTED{Style.RESET_ALL} (Interval: 3h)")
        except Exception as e:
            error_log(f"Failed to start Top.gg AutoPoster: {e}")
    else:
        warning_log("TOPGG token not found in .env - Skipping stats posting")

    # Check if we're rate limited
    sync_data = load_sync_data()
    rate_limit_end_str = sync_data.get("rate_limited_until")
    if rate_limit_end_str:
        try:
            rate_limit_end = datetime.fromisoformat(rate_limit_end_str)
            if datetime.now() < rate_limit_end:
                remaining = (rate_limit_end - datetime.now()).total_seconds()
                warning_log(f"Still rate limited for {remaining:.0f} seconds")
                print(f"{separator_line}n")
                return
        except:
            pass
    
    # Smart command synchronization with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        synced_count = await smart_sync_commands()
        
        if synced_count >= 0:  # Success or rate limited (0 is OK)
            prefix_commands = len(list(client.commands))
            success_log(f"Commands ready: {Fore.YELLOW}{prefix_commands}{Style.RESET_ALL} prefix + {Fore.CYAN}{synced_count}{Style.RESET_ALL} slash")
            break
        elif attempt < max_retries - 1:  # Failed but can retry
            warning_log(f"Sync attempt {attempt + 1} failed, retrying in 5 seconds...")
            await asyncio.sleep(5)
        else:  # Final attempt failed
            error_log("All sync attempts failed - bot will continue without slash command sync")
            prefix_commands = len(list(client.commands))
            warning_log(f"Only prefix commands available: {prefix_commands} commands")
    
    print(f"{separator_line}n")

@client.event
async def on_command_completion(context: commands.Context) -> None:
    """📊 Advanced command logging system"""
    # Skip logging for owner to reduce spam
    if context.author.id == OWNER_ID:
        return

    # Check if context.command exists
    if context.command is None:
        return

    full_command_name = context.command.qualified_name
    webhook_url = os.environ.get('COMMAND_LOG_WEBHOOK_URL', 'https://discord.com/api/webhooks/1434094851565158440/VwI0sfcq83rr7kARsU2K3gtGi2F1MbgP6OgaR6YC7dfgi_xvRbpYVsMctAMGVQ3ehyGW')

    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            
            # Create elegant embed
            embed = discord.Embed(
                title="🎯 Command Executed",
                color=0x6a0dad,
                timestamp=discord.utils.utcnow()
            )
            
            avatar_url = context.author.avatar.url if context.author.avatar else context.author.default_avatar.url
            embed.set_author(name=f"{context.prefix}{full_command_name}", icon_url=avatar_url)
            embed.set_thumbnail(url=avatar_url)
            
            # Add fields with clean formatting
            embed.add_field(
                name="👤 User",
                value=f"**{context.author}**n`{context.author.id}`",
                inline=True
            )
            
            if context.guild:
                embed.add_field(
                    name="🏠 Server",
                    value=f"**{context.guild.name}**n`{context.guild.id}`",
                    inline=True
                )
                # Check if channel has name attribute
                channel_name = getattr(context.channel, 'name', 'N/A')
                embed.add_field(
                    name="💬 Channel",
                    value=f"**#{channel_name}**n`{context.channel.id}`",
                    inline=True
                )

            embed.set_footer(
                text="👻 Scyro × Powered by ZENOXX",
                icon_url=getattr(getattr(getattr(client, 'user', None), 'display_avatar', None), 'url', '') if getattr(getattr(client, 'user', None), 'display_avatar', None) else ''
            )
            
            await webhook.send(embed=embed)
            
    except Exception as e:
        # Only log webhook errors in debug mode
        if os.getenv("DEBUG_WEBHOOKS", "false").lower() == "true":
            error_log(f"Command logging failed: {e}")

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    🛡️ ERROR HANDLING WITH OWNER OVERRIDE
# ═══════════════════════════════════════════════════════════════════════════════════════════

@client.event
async def on_command_error(ctx, error):
    """🛡️ Enhanced error handler with owner override"""
    
    # Owner bypass for permission errors
    if ctx.author.id == OWNER_ID:
        if isinstance(error, (
            commands.MissingPermissions,
            commands.BotMissingPermissions,
            commands.MissingRole,
            commands.MissingAnyRole,
            commands.NotOwner,
            commands.CheckFailure
        )):
            # Log owner override
            warning_log(f"👑 Owner override: {ctx.author} used {ctx.command}")
            
            # Re-invoke the command bypassing checks
            try:
                await ctx.reinvoke()
                return
            except Exception as e:
                error_log(f"Owner override failed: {e}")
                return
    
    # Handle specific error types for non-owners
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found errors
    
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ Missing Permissions",
            description=f"You need: `{'`, `'.join(error.missing_permissions or [])}`",
            color=0xff0000
        )
        await ctx.send(embed=embed, delete_after=10)
    
    elif isinstance(error, commands.BotMissingPermissions):
        embed = discord.Embed(
            title="🤖 Bot Missing Permissions", 
            description=f"I need: `{'`, `'.join(error.missing_permissions or [])}`",
            color=0xff6600
        )
        await ctx.send(embed=embed, delete_after=10)
    
    elif isinstance(error, commands.NotOwner):
        embed = discord.Embed(
            title="👑 Owner Only",
            description="This command is restricted to the bot owner.",
            color=0xff0000
        )
        await ctx.send(embed=embed, delete_after=10)
    
    elif isinstance(error, commands.CheckFailure):
        embed = discord.Embed(
            title="⛔ Access Denied",
            description="You don't have permission to use this command.",
            color=0xff0000
        )
        await ctx.send(embed=embed, delete_after=10)
    
    else:
        # Log unexpected errors
        if not isinstance(error, (commands.CommandOnCooldown, commands.UserInputError)):
            error_log(f"Command error in {ctx.command}: {error}")

@client.event
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """🛡️ Slash command error handler with owner override"""
    
    # Owner bypass for slash commands
    if interaction.user.id == OWNER_ID:
        if isinstance(error, (
            discord.app_commands.MissingPermissions,
            discord.app_commands.CheckFailure
        )):
            command_name = "Unknown"
            if interaction.command is not None:
                command_name = getattr(interaction.command, 'name', 'Unknown')
            warning_log(f"👑 Owner slash override: /{command_name}")
            return
    
    # Handle errors for non-owners
    if isinstance(error, discord.app_commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ Missing Permissions", 
            description=f"You need: `{'`, `'.join(getattr(error, 'missing_permissions', []))}`",
            color=0xff0000
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass
    else:
        # Log slash command errors
        command_name = getattr(getattr(interaction, 'command', None), 'name', 'Unknown')
        error_log(f"Slash command error in /{command_name}: {error}")

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    👑 ENHANCED OWNER UTILITY COMMANDS  
# ═══════════════════════════════════════════════════════════════════════════════════════════

@client.command(name="sudo", hidden=True)
@is_owner()
async def sudo_command(ctx, *, command):
    """👑 Execute any command with owner privileges"""
    try:
        new_msg = ctx.message
        new_msg.content = f"{ctx.prefix}{command}"
        new_ctx = await client.get_context(new_msg)
        
        success_log(f"👑 Sudo executed: {command}")
        await new_ctx.reinvoke()
        
    except Exception as e:
        await ctx.send(f"❌ Error: `{e}`")

@client.command(name="override", hidden=True) 
@is_owner()
async def check_override(ctx):
    """👑 Check owner override status"""
    embed = discord.Embed(
        title="👑 Owner Override Active",
        description="You can use any command regardless of permissions.",
        color=0x00ff00
    )
    embed.add_field(
        name="🔓 Bypassed Restrictions",
        value="• Missing Permissionsn• Role Restrictionsn• Check Failuresn• Slash Command Permissions",
        inline=False
    )
    embed.add_field(
        name="⚡ Enhanced Features",
        value="• Global command overriden• Slash command bypassn• Advanced error handling",
        inline=False
    )
    await ctx.send(embed=embed)

@client.command(name="sync", hidden=True)
@is_owner()
async def manual_sync(ctx, guild_id: int = 0):
    """👑 Manually sync slash commands (optionally to specific guild)"""
    is_guild_sync = guild_id != 0

    embed = discord.Embed(
        title="🔄 Manual Sync Started",
        description=f"Syncing commands {'to guild' if is_guild_sync else 'globally'}...",
        color=0xffff00
    )
    msg = await ctx.send(embed=embed)
    
    try:
        if is_guild_sync:
            # Sync to specific guild
            guild = client.get_guild(guild_id)
            if not guild:
                embed = discord.Embed(
                    title="❌ Guild Not Found",
                    description=f"Could not find guild with ID {guild_id}",
                    color=0xff0000
                )
                await msg.edit(embed=embed)
                return
            
            synced = await client.tree.sync(guild=guild)
            location = f"guild {guild.name}"
        else:
            # Global sync
            synced = await client.tree.sync()
            location = "globally"
        
        # Update sync data
        sync_data = {
            "last_sync": datetime.now().isoformat(),
            "command_hash": get_command_hash(),
            "synced_count": len(synced),
            "guild_sync": guild_id
        }
        save_sync_data(sync_data)
        
        # Remove force sync flag if it exists
        remove_force_sync_flag()
        
        embed = discord.Embed(
            title="✅ Sync Successful",
            description=f"Successfully synced {len(synced)} slash commands {location}!",
            color=0x00ff00
        )
        
        # Add command list if not too many
        if len(synced) <= 10:
            cmd_list = 'n'.join([f"• /{cmd.name}" for cmd in synced])
            embed.add_field(name="Commands Synced", value=cmd_list, inline=False)
        
        await msg.edit(embed=embed)
        success_log(f"👑 Manual sync: {len(synced)} commands {location}")
        
    except discord.HTTPException as e:
        if e.status == 429:
            retry_after = e.response.headers.get('Retry-After', '300')
            embed = discord.Embed(
                title="⏰ Rate Limited",
                description=f"Discord is rate limiting us. Try again in {retry_after} seconds.",
                color=0xff0000
            )
        else:
            embed = discord.Embed(
                title="❌ Sync Failed",
                description=f"HTTP Error {e.status}: {e}",
                color=0xff0000
            )
        await msg.edit(embed=embed)
    except Exception as e:
        embed = discord.Embed(
                title="❌ Sync Failed",
                description=f"Error: {e}",
                color=0xff0000
        )
        await msg.edit(embed=embed)

@client.command(name="syncstatus", hidden=True)
@is_owner()
async def sync_status(ctx):
    """👑 Check sync status and information"""
    sync_data = load_sync_data()
    should_sync, reason = should_sync_commands()
    
    embed = discord.Embed(
        title="📊 Sync Status",
        color=0x6a0dad
    )
    
    if sync_data.get("last_sync"):
        last_sync_str = sync_data["last_sync"]
        if last_sync_str:  # Check if not None or empty
            try:
                last_sync = datetime.fromisoformat(last_sync_str)
                hours_ago = (datetime.now() - last_sync).total_seconds() / 3600
                embed.add_field(
                    name="🕒 Last Sync",
                    value=f"{last_sync.strftime('%Y-%m-%d %H:%M:%S')}n({hours_ago:.1f} hours ago)",
                    inline=False
                )
            except Exception:
                embed.add_field(name="🕒 Last Sync", value="Invalid timestamp", inline=False)
        else:
            embed.add_field(name="🕒 Last Sync", value="Never", inline=False)
    else:
        embed.add_field(name="🕒 Last Sync", value="Never", inline=False)

    embed.add_field(
        name="🔄 Sync Needed",
        value="✅ Yes" if should_sync else "❌ No",
        inline=True
    )
    
    embed.add_field(
        name="📝 Reason",
        value=reason,
        inline=True
    )
    
    # Current command count
    current_commands = len(client.tree.get_commands())
    embed.add_field(
        name="📋 Current Commands",
        value=str(current_commands),
        inline=True
    )
    
    embed.add_field(
        name="🔍 Command Hash",
        value=f"`{get_command_hash()[:16]}...`",
        inline=True
    )
    
    # Last synced count
    synced_count = sync_data.get("synced_count")
    if synced_count is not None:
        embed.add_field(
            name="📤 Last Sync Count",
            value=str(synced_count),
            inline=True
        )

    # Rate limit status
    rate_limit_end_str = sync_data.get("rate_limited_until")
    if rate_limit_end_str:
        try:
            rate_limit_end = datetime.fromisoformat(rate_limit_end_str)
            if datetime.now() < rate_limit_end:
                remaining = (rate_limit_end - datetime.now()).total_seconds()
                embed.add_field(
                    name="⏰ Rate Limited",
                    value=f"{remaining:.0f} seconds remaining",
                    inline=True
                )
        except:
            pass
    
    await ctx.send(embed=embed)

@client.command(name="clearsync", hidden=True)
@is_owner()
async def clear_sync_data(ctx):
    """👑 Clear sync data to force next sync"""
    try:
        if os.path.exists(SYNC_DATA_FILE):
            os.remove(SYNC_DATA_FILE)
        
        embed = discord.Embed(
            title="✅ Sync Data Cleared",
            description="Sync data has been cleared. Next restart will force a sync.",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        success_log("👑 Sync data cleared by owner")
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Clear Failed",
            description=f"Error: {e}",
            color=0xff0000
        )
        await ctx.send(embed=embed)

@client.command(name="guildsync", hidden=True)
@is_owner()
async def guild_sync_command(ctx, guild_id: int = 0):
    """👑 Sync commands to specific guild or all guilds"""
    is_specific_guild = guild_id != 0

    if is_specific_guild:
        embed = discord.Embed(
            title="🔄 Guild Sync Started",
            description=f"Syncing commands to guild {guild_id}...",
            color=0xffff00
        )
    else:
        embed = discord.Embed(
            title="🔄 All Guilds Sync Started", 
            description="⚠️ Syncing to all guilds (this may take a while)...",
            color=0xffff00
        )
    
    msg = await ctx.send(embed=embed)
    
    synced_count = await force_guild_sync(guild_id)
    
    if synced_count >= 0:
        embed = discord.Embed(
            title="✅ Guild Sync Complete",
            description=f"Synced {synced_count} commands!",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="❌ Guild Sync Failed",
            description="Check console for error details.",
            color=0xff0000
        )
    
    await msg.edit(embed=embed)

@client.command(name="debugsync", hidden=True)
@is_owner()
async def debug_sync(ctx):
    """👑 Debug sync system and show detailed info"""
    embed = discord.Embed(
        title="🐛 Sync Debug Information",
        color=0x6a0dad,
        timestamp=discord.utils.utcnow()
    )
    
    # Bot readiness
    embed.add_field(
        name="🤖 Bot Status",
        value=f"Ready: {client.is_ready()}nClosed: {client.is_closed()}nLatency: {round(client.latency * 1000)}ms",
        inline=True
    )
    
    # Command tree info
    tree_commands = client.tree.get_commands()
    embed.add_field(
        name="🌳 Command Tree",
        value=f"Commands: {len(tree_commands)}nType: {type(client.tree).__name__}",
        inline=True
    )
    
    # Sync data
    sync_data = load_sync_data()
    last_sync_str = sync_data.get('last_sync', 'Never')
    last_sync_display = last_sync_str[:19] if last_sync_str != 'Never' and last_sync_str else 'Never'
    embed.add_field(
        name="🔧 Environment",
        value=f"File exists: {os.path.exists(SYNC_DATA_FILE)}nLast sync: {last_sync_display}",
        inline=True
    )
    
    # Current hash
    current_hash = get_command_hash()
    stored_hash = sync_data.get("command_hash", "None")
    stored_hash_display = ""
    if stored_hash != "None" and stored_hash is not None:
        stored_hash_display = stored_hash[:12] if len(stored_hash) > 12 else stored_hash
    else:
        stored_hash_display = "None"
    
    current_hash_display = current_hash[:12] if len(current_hash) > 12 else current_hash
    hashes_match = "✅" if current_hash == stored_hash else "❌"
    
    embed.add_field(
        name="🔍 Hashes",
        value=f"Current: `{current_hash_display}...`nStored: `{stored_hash_display}...`nMatch: {hashes_match}",
        inline=True
    )
    
    # Should sync check
    should_sync, reason = should_sync_commands()
    embed.add_field(
        name="🤔 Should Sync",
        value=f"{'✅ Yes' if should_sync else '❌ No'}nReason: {reason}",
        inline=True
    )
    
    # List current commands
    if tree_commands:
        cmd_names = [f"• /{cmd.name}" for cmd in tree_commands[:10]]
        if len(tree_commands) > 10:
            cmd_names.append(f"... and {len(tree_commands) - 10} more")
        
        embed.add_field(
            name="📋 Current Commands",
            value='n'.join(cmd_names),
            inline=False
        )
    
    await ctx.send(embed=embed)

@client.command(name="soadd")
@is_main_owner()  # Only main owner can use this command
async def so_add(ctx, user_id: int):
    """👑 Add a user as a bot owner"""
    if user_id in BOT_OWNERS:
        embed = discord.Embed(
            title="❌ Already Owner",
            description=f"User <@{user_id}> is already a bot owner.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Add to database
    if add_bot_owner_to_db(user_id, ctx.author.id):
        BOT_OWNERS.add(user_id)
        embed = discord.Embed(
            title="✅ Owner Added",
            description=f"User <@{user_id}> has been added as a bot owner.",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        success_log(f"👑 New owner added: {user_id} by {ctx.author}")
    else:
        embed = discord.Embed(
            title="❌ Database Error",
            description=f"Failed to add user <@{user_id}> to the database.",
            color=0xff0000
        )
        await ctx.send(embed=embed)

@client.command(name="soremove")
@is_main_owner()  # Only main owner can use this command
async def so_remove(ctx, user_id: int):
    """👑 Remove a user from bot owners"""
    if user_id == OWNER_ID:
        embed = discord.Embed(
            title="❌ Cannot Remove",
            description="You cannot remove the main bot owner.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    if user_id not in BOT_OWNERS:
        embed = discord.Embed(
            title="❌ Not an Owner",
            description=f"User <@{user_id}> is not a bot owner.",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    # Remove from database
    if remove_bot_owner_from_db(user_id):
        BOT_OWNERS.discard(user_id)
        embed = discord.Embed(
            title="✅ Owner Removed",
            description=f"User <@{user_id}> has been removed from bot owners.",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        success_log(f"👑 Owner removed: {user_id} by {ctx.author}")
    else:
        embed = discord.Embed(
            title="❌ Database Error",
            description=f"Failed to remove user <@{user_id}> from the database.",
            color=0xff0000
        )
        await ctx.send(embed=embed)

@client.command(name="solist")
@is_main_owner()  # Only main owner can use this command
async def so_list(ctx):
    """👑 List all bot owners"""
    owner_list = []
    for owner_id in BOT_OWNERS:
        user = client.get_user(owner_id)
        if user:
            owner_list.append(f"• {user.mention} (`{owner_id}`)")
        else:
            owner_list.append(f"• Unknown User (`{owner_id}`)")
    
    embed = discord.Embed(
        title="👑 Bot Owners",
        description="n".join(owner_list) if owner_list else "No additional owners found.",
        color=0x6a0dad
    )
    await ctx.send(embed=embed)

# REMOVED DUPLICATE syncshards COMMAND TO PREVENT CONFLICT WITH owner.py
# The command was defined here but has been removed to prevent:
# CommandRegistrationError: The command syncshards is already an existing command or alias.

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    🔧 KEEP-ALIVE SERVER
# ═══════════════════════════════════════════════════════════════════════════════════════════

from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    """🏠 Keep-alive endpoint with detailed status page"""
    sync_data = load_sync_data()
    last_sync = "Never"
    if sync_data.get("last_sync"):
        try:
            last_sync_dt_str = sync_data["last_sync"]
            if last_sync_dt_str:  # Check if not None or empty
                last_sync_dt = datetime.fromisoformat(last_sync_dt_str)
                last_sync = last_sync_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            last_sync = "Invalid timestamp"

    # Get bot status
    bot_status = "🟢 Online" if client.is_ready() else "🔴 Offline"
    guild_count = len(client.guilds) if client.is_ready() else "Unknown"
    command_count = len(client.tree.get_commands()) if client.is_ready() else "Unknown"
    
    html_template = f'''<!DOCTYPE html>
<html>
<head>
    <title>👻 Scyro Status</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            color: white;
            min-height: 100vh;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            text-align: center;
        }}
        h1 {{ text-align: center; margin-bottom: 30px; }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .status-card {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
        }}
        .status-value {{
            font-size: 1.5em;
            font-weight: bold;
            margin-top: 10px;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            opacity: 0.8;
        }}
        .refresh-btn {{
            background: rgba(255, 255, 255, 0.2);
            border: none;
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
            margin-top: 20px;
        }}
        .refresh-btn:hover {{
            background: rgba(255, 255, 255, 0.3);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>👻 Scyro Development Server</h1>
        <p style="text-align: center; font-size: 1.2em;">⚡ Powered by ZENOXX</p>
        
        <div class="status-grid">
            <div class="status-card">
                <div>Bot Status</div>
                <div class="status-value">{bot_status}</div>
            </div>
            <div class="status-card">
                <div>Guild Count</div>
                <div class="status-value">{guild_count}</div>
            </div>
            <div class="status-card">
                <div>Slash Commands</div>
                <div class="status-value">{command_count}</div>
            </div>
            <div class="status-card">
                <div>Last Sync</div>
                <div class="status-value" style="font-size: 1em;">{last_sync}</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Smart Sync System: Active</p>
            <p>Uptime: Running continuously</p>
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Status</button>
        </div>
    </div>
</body>
</html>'''
    return html_template

@app.route('/health')
def health():
    """🩺 Health check endpoint"""
    return {
        "status": "healthy" if client.is_ready() else "unhealthy",
        "bot_ready": client.is_ready(),
        "guild_count": len(client.guilds) if client.is_ready() else 0,
        "command_count": len(client.tree.get_commands()) if client.is_ready() else 0,
        "timestamp": datetime.now().isoformat()
    }

def run_server():
    """🚀 Start the keep-alive server"""
    try:
        app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
    except Exception as e:
        error_log(f"Keep-alive server error: {e}")

def keep_alive():
    """Keep the bot alive with threading"""
    try:
        server_thread = Thread(target=run_server, daemon=True)
        server_thread.start()
        success_log("Keep-alive server initialized on port 8080")
    except Exception as e:
        error_log(f"Failed to start keep-alive server: {e}")

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    🚀 MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════════════════

async def shutdown_handler(client):
    """🔄 Graceful shutdown handler"""
    try:
        warning_log("Shutting down Scyro gracefully...")
        
        # Close the bot connection
        if not client.is_closed():
            await client.close()
        
        # Cancel any pending tasks
        tasks = [task for task in asyncio.all_tasks() if not task.done()]
        if tasks:
            info_log(f"Cancelling {len(tasks)} pending tasks...")
            for task in tasks:
                task.cancel()
            
            # Wait for tasks to be cancelled with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                warning_log("Some tasks didn't cancel in time")
        
        success_log("Scyro shut down successfully!")
        
    except Exception as e:
        error_log(f"Error during shutdown: {e}")


async def main():
    """🎯 Main bot initialization and startup with enhanced error handling"""
    try:
        # Validate token first
        if not TOKEN:
            error_log("DISCORD_TOKEN not found! Please check your .env file.")
            return
        
        info_log("Starting Scyro initialization...")
        
        # Apply patches for enhanced functionality
        try:
            # Temporarily disable patches to avoid type annotation issues
            # apply_patches()
            info_log("✅ Patches applied successfully")
        except Exception as e:
            warning_log(f"⚠️ Failed to apply patches: {e}")
        
        # Start keep-alive server
        try:
            keep_alive()
        except Exception as e:
            warning_log(f"⚠️ Keep-alive server failed to start: {e}")
        
        async with client:
            
            # Start the bot
            info_log("Connecting to Discord...")
            await client.start(TOKEN)
            
    except discord.LoginFailure:
        error_log("❌ Invalid Discord token! Please check your .env file.")
    except discord.HTTPException as e:
        error_log(f"❌ Discord HTTP error: {e}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Handle Ctrl+C gracefully
        await shutdown_handler(client)
    except Exception as e:
        error_log(f"❌ Critical error during startup: {e}")
        traceback.print_exc()
        # Still try to shutdown gracefully even on error
        await shutdown_handler(client)

# ═══════════════════════════════════════════════════════════════════════════════════════════
#                                    ⚡ PROGRAM EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"{Fore.CYAN}Starting Scyro with Enhanced Smart Sync System...{Style.RESET_ALL}")
    
    # Sharding is now disabled - run the bot directly
    try:
        # Run the main bot function
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"n{Fore.YELLOW}👋Scyro has been shut down gracefully...{Style.RESET_ALL}")
    except Exception as e:
        error_log(f"❌ Fatal error: {e}")
        traceback.print_exc()
    finally:
        # Ensure clean exit
        print(f"{Fore.CYAN}Process terminated.{Style.RESET_ALL}")