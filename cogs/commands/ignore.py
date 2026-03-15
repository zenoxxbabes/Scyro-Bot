from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
from core import *
from utils.Tools import *
from typing import Optional
import motor.motor_asyncio
import asyncio
import os



# ================= UNIVERSAL EMOJI CONFIGURATION =================
EMOJIS = {
    "error": "<:no:1396838761605890090>",
    "success": "<:yes:1396838746862784582>",
    "alert": "<a:alert:1396429026842644584>",
    "info": "<:info:1409161358733213716>",
    "warning": "<a:warn:1396429222066782228>",
    "trash": "<:bin:1409169036285313155>"
}



class Ignore(commands.Cog):
    """Advanced Ignore System - Blocks bot responses in ignored channels and for ignored commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_default_database()
        
        # Collections
        self.ignored_channels = self.db.ignored_channels
        self.ignored_commands = self.db.ignored_commands
        self.ignored_users = self.db.ignored_users
        self.bypass_users = self.db.bypass_users
        
         # Map for dynamic access
        self.collections_map = {
            "ignored_channels": self.ignored_channels,
            "ignored_commands": self.ignored_commands,
            "ignored_users": self.ignored_users,
            "bypass_users": self.bypass_users
        }
        
        self.color = 0x9B59B6  # Purple color
        self.emojis = EMOJIS
        # Initialize database on startup
        bot.loop.create_task(self.setup_database())


    async def setup_database(self):
        """Initialize the ignore database with all required indexes"""
        try:
             # Create unique indexes
            await self.ignored_channels.create_index([("guild_id", 1), ("channel_id", 1)], unique=True)
            await self.ignored_commands.create_index([("guild_id", 1), ("command_name", 1)], unique=True)
            await self.ignored_users.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
            await self.bypass_users.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
            
            print("✅ [Ignore System] MongoDB indexes initialized successfully!")
        except Exception as e:
            print(f"❌ [Ignore System] Database initialization failed: {e}")


    # ================= CORE BLOCKING LOGIC =================
    async def is_channel_ignored(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is ignored"""
        try:
            doc = await self.ignored_channels.find_one({"guild_id": guild_id, "channel_id": channel_id})
            return doc is not None
        except:
            return False


    async def is_command_ignored(self, guild_id: int, command_name: str) -> bool:
        """Check if a command is ignored"""
        try:
            doc = await self.ignored_commands.find_one({"guild_id": guild_id, "command_name": command_name.lower()})
            return doc is not None
        except:
            return False


    async def is_user_ignored(self, guild_id: int, user_id: int) -> bool:
        """Check if a user is ignored"""
        try:
            doc = await self.ignored_users.find_one({"guild_id": guild_id, "user_id": user_id})
            return doc is not None
        except:
            return False


    async def is_user_bypassed(self, guild_id: int, user_id: int) -> bool:
        """Check if a user bypasses ignore system"""
        try:
            doc = await self.bypass_users.find_one({"guild_id": guild_id, "user_id": user_id})
            return doc is not None
        except:
            return False


    def extract_command_name(self, message_content: str, prefixes: list) -> str:
        """Extract command name from message content"""
        # Handle no prefix case (empty string prefix)
        if '' in prefixes:
            content_stripped = message_content.strip()
            if not content_stripped:
                return ""
            parts = content_stripped.split()
            if not parts:
                return ""
            return parts[0].lower()
        
        # Handle regular prefixes
        for prefix in prefixes:
            if prefix and message_content.startswith(prefix):
                # Remove prefix and get first word (command name)
                content_without_prefix = message_content[len(prefix):].strip()
                if not content_without_prefix:
                    return ""
                parts = content_without_prefix.split()
                if not parts:
                    return ""
                return parts[0].lower()
        return ""

    async def should_block_message(self, message: discord.Message) -> tuple[bool, str]:
        """Determine if bot should ignore this message"""
        if not message.guild or message.author.bot:
            return False, ""

        # Check if user is admin (admins bypass everything)
        if message.author.guild_permissions.administrator:
            return False, ""

        # Check if user is in bypass list
        if await self.is_user_bypassed(message.guild.id, message.author.id):
            return False, ""

        # Get bot prefixes
        try:
            prefixes = await self.bot.get_prefix(message)
            if isinstance(prefixes, str):
                prefixes = [prefixes]
        except:
            prefixes = [',', '!', '?']  # Default prefixes

        # Check if user has no prefix access (empty string prefix)
        has_no_prefix = '' in prefixes if isinstance(prefixes, list) else False
        
        # If user has no prefix access, all messages could potentially be commands
        # But we should only block actual commands, not random text
        if has_no_prefix:
            # For no prefix users, we need to check if this is actually a command
            # by trying to match it against registered commands
            content = message.content.strip().lower()
            if content:  # Non-empty message
                # Check if this matches any registered command
                ctx = await self.bot.get_context(message)
                if ctx.command is not None:
                    # This is a valid command, check ignore conditions
                    pass
                else:
                    # Not a valid command, don't block
                    return False, ""
            else:
                # Empty message, don't block
                return False, ""

        # For regular users, check if message starts with any prefix
        starts_with_prefix = any(message.content.startswith(prefix) for prefix in prefixes if prefix)
        if not starts_with_prefix and not has_no_prefix:
            return False, ""

        # Extract command name
        command_name = self.extract_command_name(message.content, prefixes)
        if not command_name:
            # For no prefix users, if we couldn't extract a command but content exists,
            # check if it's a valid command by getting context
            if has_no_prefix and message.content.strip():
                ctx = await self.bot.get_context(message)
                if ctx.command is None:
                    return False, ""
                # If it's a valid command, fall through to check ignore conditions
            else:
                return False, ""

        # Don't block ignore system commands
        if command_name.startswith('ignore') or command_name in ['igca', 'igcr', 'igcl', 'igcres', 'igcmda', 'igcmdr', 'igcmdl', 'igcmdres', 'igua', 'igur', 'iguL', 'igures', 'igba', 'igbr', 'igbl', 'igbres']:
            return False, ""

        # Check ignore conditions in priority order
        # 1. User ignore (highest priority after bypass)
        if await self.is_user_ignored(message.guild.id, message.author.id):
            return True, "user"

        # 2. Channel ignore
        if await self.is_channel_ignored(message.guild.id, message.channel.id):
            return True, "channel"

        # 3. Command ignore
        if await self.is_command_ignored(message.guild.id, command_name):
            return True, "command"

        return False, ""


    async def should_block_interaction(self, interaction: discord.Interaction) -> tuple[bool, str]:
        """Determine if bot should ignore this slash command"""
        if not interaction.guild or not interaction.command:
            return False, ""

        # Check if user is admin
        if interaction.user.guild_permissions.administrator:
            return False, ""

        # Check if user is in bypass list
        if await self.is_user_bypassed(interaction.guild.id, interaction.user.id):
            return False, ""

        # Don't block ignore system commands
        if hasattr(interaction.command, 'qualified_name') and interaction.command.qualified_name.startswith('ignore'):
            return False, ""

        # Check ignore conditions
        if await self.is_user_ignored(interaction.guild.id, interaction.user.id):
            return True, "user"
        elif await self.is_channel_ignored(interaction.guild.id, interaction.channel.id):
            return True, "channel"
        elif hasattr(interaction.command, 'name') and await self.is_command_ignored(interaction.guild.id, interaction.command.name):
            return True, "command"

        return False, ""


    async def send_ignore_message(self, channel, user_mention: str, ignore_type: str):
        """Send ignore notification and delete after 3 seconds"""
        try:
            messages = {
                "channel": f"{user_mention} Commands are ignored in this channel.",
                "command": f"{user_mention} This command is ignored in this guild.",
                "user": f"{user_mention} You are ignored in this guild."
            }
            
            message_content = messages.get(ignore_type, f"{user_mention} This command is ignored in this guild.")
            msg = await channel.send(message_content)
            
            # Delete after 3 seconds
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except discord.NotFound:
                pass
        except Exception:
            pass


    # ================= EVENT LISTENERS FOR BLOCKING =================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Block prefix commands in ignored channels/commands"""
        should_block, ignore_type = await self.should_block_message(message)
        
        if should_block:
            # Send ignore notification
            await self.send_ignore_message(message.channel, message.author.mention, ignore_type)
            # Don't process the command by returning early
            return


    @commands.Cog.listener()  
    async def on_interaction(self, interaction: discord.Interaction):
        """Block slash commands in ignored channels/commands"""
        if interaction.type != discord.InteractionType.application_command:
            return
            
        should_block, ignore_type = await self.should_block_interaction(interaction)
        
        if should_block:
            try:
                message_content = {
                    "channel": f"{interaction.user.mention} Commands are ignored in this channel.",
                    "command": f"{interaction.user.mention} This command is ignored in this guild.",
                    "user": f"{interaction.user.mention} You are ignored in this guild."
                }.get(ignore_type, f"{interaction.user.mention} This command is ignored in this guild.")
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(message_content, ephemeral=False)
                    msg = await interaction.original_response()
                else:
                    msg = await interaction.followup.send(message_content, ephemeral=False)
                
                # Delete after 3 seconds
                await asyncio.sleep(3)
                try:
                    await msg.delete()
                except discord.NotFound:
                    pass
            except Exception:
                pass


    # ================= UTILITY FUNCTIONS =================
    def create_embed(self, title: str, description: str, emoji_type: str = "info"):
        """Create standardized embed with emoji"""
        emoji = self.emojis.get(emoji_type, "")
        embed_title = f"{emoji} {title}" if emoji else title
        embed = discord.Embed(title=embed_title, description=description, color=self.color)
        return embed


    async def get_count(self, table: str, guild_id: int) -> int:
        """Get count of items in database table"""
        try:
            collection = self.collections_map.get(table)
            if not collection:
                return 0
            
            return await collection.count_documents({"guild_id": guild_id})
        except:
            return 0


    async def item_exists(self, table: str, guild_id: int, item_id: int = None, item_name: str = None) -> bool:
        """Check if item exists in database table"""
        try:
            collection = self.collections_map.get(table)
            if not collection:
                return False

            if item_name:
                doc = await collection.find_one({"guild_id": guild_id, "command_name": item_name.lower()})
            else:
                 # Check logic based on table name for ID field
                if "channel" in table:
                    doc = await collection.find_one({"guild_id": guild_id, "channel_id": item_id})
                else:
                    doc = await collection.find_one({"guild_id": guild_id, "user_id": item_id})
            
            return doc is not None
        except:
            return False


    # ================= MAIN IGNORE COMMAND GROUP =================
    @commands.hybrid_group(name="ignore", with_app_command=True, fallback="help")
    @blacklist_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ignore(self, ctx: commands.Context):
        """Advanced Ignore System - Manage ignored channels, commands, users and bypasses"""
        embed = discord.Embed(
            title="🚫 **Advanced Ignore System**",
            description="Comprehensive bot response blocking system for better server control",
            color=self.color,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📺 **Channel Management**",
            value=(
                "`/ignore channel add <channel>` - Block all commands in channel\n"
                "`/ignore channel remove <channel>` - Unblock channel\n"
                "`/ignore channel list` - View ignored channels\n"
                "`/ignore channel reset` - Clear all ignored channels"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🤖 **Command Management**", 
            value=(
                "`/ignore command add <command>` - Block specific command (e.g. `gif`)\n"
                "`/ignore command remove <command>` - Unblock command\n"
                "`/ignore command list` - View ignored commands\n"
                "`/ignore command reset` - Clear all ignored commands"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👤 **User Management**",
            value=(
                "`/ignore user add <user>` - Block all commands from user\n"
                "`/ignore user remove <user>` - Unblock user\n"
                "`/ignore user list` - View ignored users\n"
                "`/ignore user reset` - Clear all ignored users"
            ),
            inline=False
        )
        
        embed.add_field(
            name="✅ **Bypass Management**",
            value=(
                "`/ignore bypass add <user>` - Allow user to bypass ignores\n"
                "`/ignore bypass remove <user>` - Remove bypass access\n"
                "`/ignore bypass list` - View bypass users\n"
                "`/ignore bypass reset` - Clear all bypass users"
            ),
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ **System Information**",
            value=(
                "• **Administrators** automatically bypass all ignores\n"
                "• **Bypass users** can use commands anywhere\n"
                "• Works with **both prefix** (`,gif`) **and slash** (`/gif`) commands\n"
                "• Ignore notifications auto-delete after 3 seconds\n"
                "• **Priority**: User Ignore > Channel Ignore > Command Ignore"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)


    # ================= CHANNEL MANAGEMENT =================
    @ignore.group(name="channel", with_app_command=True, fallback="help")
    @blacklist_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def channel(self, ctx: commands.Context):
        """Manage ignored channels - Bot won't respond to ANY commands in ignored channels"""
        embed = self.create_embed(
            "Channel Ignore Management",
            "**Commands:**\n"
            "`add <channel>` - Block all commands in channel\n"
            "`remove <channel>` - Unblock channel\n"
            "`list` - View all ignored channels\n"
            "`reset` - Clear all ignored channels\n\n"
            "**Effect:** Bot will completely ignore ALL commands in blocked channels (except from bypass users)."
        )
        await ctx.send(embed=embed)


    @channel.command(name="add", with_app_command=True)
    @app_commands.describe(channel="Channel to ignore all commands in")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def channel_add(self, ctx: commands.Context, channel: discord.TextChannel):
        """Add a channel to ignore list"""
        try:
            # Check limits
            count = await self.get_count("ignored_channels", ctx.guild.id)
            if count >= 50:
                embed = self.create_embed("Limit Reached", "Maximum 50 channels can be ignored per server.", "error")
                return await ctx.send(embed=embed)

            # Check if already ignored
            if await self.item_exists("ignored_channels", ctx.guild.id, channel.id):
                embed = self.create_embed("Already Ignored", f"{channel.mention} is already ignored.", "error")
                return await ctx.send(embed=embed)

            # Add to database
            await self.ignored_channels.insert_one({"guild_id": ctx.guild.id, "channel_id": channel.id})

            embed = self.create_embed(
                "Channel Ignored Successfully", 
                f"✅ {channel.mention} has been added to ignore list.\n\n**Effect:** Bot will not respond to any commands in this channel.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to ignore channel: {str(e)}", "error")
            await ctx.send(embed=embed)


    @channel.command(name="remove", with_app_command=True)
    @app_commands.describe(channel="Channel to remove from ignore list")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def channel_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        """Remove a channel from ignore list"""
        try:
            # Check if exists
            if not await self.item_exists("ignored_channels", ctx.guild.id, channel.id):
                embed = self.create_embed("Not Found", f"{channel.mention} is not in the ignore list.", "error")
                return await ctx.send(embed=embed)

            # Remove from database
            await self.ignored_channels.delete_one({"guild_id": ctx.guild.id, "channel_id": channel.id})

            embed = self.create_embed(
                "Channel Unignored Successfully",
                f"✅ {channel.mention} has been removed from ignore list.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to unignore channel: {str(e)}", "error")
            await ctx.send(embed=embed)


    @channel.command(name="list", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def channel_list(self, ctx: commands.Context):
        """List all ignored channels"""
        try:
            cursor = self.ignored_channels.find({"guild_id": ctx.guild.id})
            channels = await cursor.to_list(length=None)

            if not channels:
                embed = self.create_embed("No Ignored Channels", "No channels are currently ignored.", "info")
                return await ctx.send(embed=embed)

            # Build channel list
            channel_mentions = []
            for doc in channels:
                channel_id = doc['channel_id']
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    channel_mentions.append(f"• {channel.mention}")
                else:
                    channel_mentions.append(f"• Deleted Channel (ID: {channel_id})")

            # Create paginated embed
            embed = discord.Embed(
                title=f"{self.emojis['info']} Ignored Channels ({len(channels)})",
                color=self.color,
                timestamp=discord.utils.utcnow()
            )

            # Add channels in chunks
            chunks = [channel_mentions[i:i+15] for i in range(0, len(channel_mentions), 15)]
            for i, chunk in enumerate(chunks[:3]):  # Show max 45 channels
                field_name = f"Channels {i*15+1}-{min((i+1)*15, len(channel_mentions))}"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

            if len(channels) > 45:
                embed.add_field(name="Note", value=f"Showing first 45 of {len(channels)} channels", inline=False)

            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to list channels: {str(e)}", "error")
            await ctx.send(embed=embed)


    @channel.command(name="reset", with_app_command=True) 
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def channel_reset(self, ctx: commands.Context):
        """Clear all ignored channels"""
        try:
            count = await self.get_count("ignored_channels", ctx.guild.id)
            if count == 0:
                embed = self.create_embed("Nothing to Clear", "No channels are ignored.", "info")
                return await ctx.send(embed=embed)

            # Confirmation
            embed = self.create_embed(
                "Confirm Channel Reset",
                f"⚠️ This will remove **{count}** ignored channels.\n**This action cannot be undone!**\n\nReact ✅ to confirm or ❌ to cancel.",
                "warning"
            )
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30, check=check)
                
                if str(reaction.emoji) == "✅":
                    await self.ignored_channels.delete_many({"guild_id": ctx.guild.id})
                    
                    embed = self.create_embed(
                        "Channels Reset Successfully",
                        f"✅ Removed all **{count}** ignored channels.",
                        "success"
                    )
                    await msg.edit(embed=embed)
                else:
                    embed = self.create_embed("Reset Cancelled", "Channel reset was cancelled.", "info")
                    await msg.edit(embed=embed)
                    
            except asyncio.TimeoutError:
                embed = self.create_embed("Timeout", "Reset confirmation timed out.", "warning")
                await msg.edit(embed=embed)
            
            try:
                await msg.clear_reactions()
            except:
                pass

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to reset channels: {str(e)}", "error")
            await ctx.send(embed=embed)


    # ================= COMMAND MANAGEMENT =================
    @ignore.group(name="command", with_app_command=True, fallback="help")
    @blacklist_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def command(self, ctx: commands.Context):
        """Manage ignored commands - Block specific commands server-wide"""
        embed = self.create_embed(
            "Command Ignore Management",
            "**Commands:**\n"
            "`add <command>` - Block specific command (e.g. `gif`, `meme`)\n"
            "`remove <command>` - Unblock command\n"
            "`list` - View all ignored commands\n"
            "`reset` - Clear all ignored commands\n\n"
            "**Effect:** Bot will not respond to blocked commands anywhere in server.\n"
            "**Examples:** `,ignore command add gif` blocks both `,gif` and `/gif`"
        )
        await ctx.send(embed=embed)


    @command.command(name="add", with_app_command=True)
    @app_commands.describe(command="Command name to ignore (without prefix, e.g. 'gif')")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def command_add(self, ctx: commands.Context, command: str):
        """Add a command to ignore list"""
        try:
            command_name = command.lower().strip()
            
            # Prevent ignoring system commands
            if command_name.startswith('ignore') or command_name in ['help', 'ping']:
                embed = self.create_embed("Cannot Block System Commands", "System commands cannot be ignored.", "error")
                return await ctx.send(embed=embed)

            # Check limits
            count = await self.get_count("ignored_commands", ctx.guild.id)
            if count >= 100:
                embed = self.create_embed("Limit Reached", "Maximum 100 commands can be ignored per server.", "error")
                return await ctx.send(embed=embed)

            # Check if already ignored
            if await self.item_exists("ignored_commands", ctx.guild.id, item_name=command_name):
                embed = self.create_embed("Already Ignored", f"Command `{command_name}` is already ignored.", "error")
                return await ctx.send(embed=embed)

            # Add to database
            await self.ignored_commands.insert_one({"guild_id": ctx.guild.id, "command_name": command_name})

            embed = self.create_embed(
                "Command Ignored Successfully",
                f"✅ Command `{command_name}` has been ignored.\n\n**Effect:** Bot will not respond to `{command_name}` commands (prefix or slash).",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to ignore command: {str(e)}", "error")
            await ctx.send(embed=embed)


    @command.command(name="remove", with_app_command=True)
    @app_commands.describe(command="Command name to remove from ignore list")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def command_remove(self, ctx: commands.Context, command: str):
        """Remove a command from ignore list"""
        try:
            command_name = command.lower().strip()
            
            # Check if exists
            if not await self.item_exists("ignored_commands", ctx.guild.id, item_name=command_name):
                embed = self.create_embed("Not Found", f"Command `{command_name}` is not in the ignore list.", "error")
                return await ctx.send(embed=embed)

            # Remove from database
            await self.ignored_commands.delete_one({"guild_id": ctx.guild.id, "command_name": command_name})

            embed = self.create_embed(
                "Command Unignored Successfully",
                f"✅ Command `{command_name}` has been removed from ignore list.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to unignore command: {str(e)}", "error")
            await ctx.send(embed=embed)


    @command.command(name="list", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def command_list(self, ctx: commands.Context):
        """List all ignored commands"""
        try:
            cursor = self.ignored_commands.find({"guild_id": ctx.guild.id})
            commands_data = await cursor.to_list(length=None)

            if not commands_data:
                embed = self.create_embed("No Ignored Commands", "No commands are currently ignored.", "info")
                return await ctx.send(embed=embed)

            # Build command list
            command_list = [f"• `{doc['command_name']}`" for doc in commands_data]

            # Create paginated embed
            embed = discord.Embed(
                title=f"{self.emojis['info']} Ignored Commands ({len(commands_data)})",
                color=self.color,
                timestamp=discord.utils.utcnow()
            )

            # Add commands in chunks
            chunks = [command_list[i:i+25] for i in range(0, len(command_list), 25)]
            for i, chunk in enumerate(chunks[:4]):  # Show max 100 commands
                field_name = f"Commands {i*25+1}-{min((i+1)*25, len(command_list))}"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=True)

            if len(commands_data) > 100:
                embed.add_field(name="Note", value=f"Showing first 100 of {len(commands_data)} commands", inline=False)

            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to list commands: {str(e)}", "error")
            await ctx.send(embed=embed)


    @command.command(name="reset", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def command_reset(self, ctx: commands.Context):
        """Clear all ignored commands"""
        try:
            count = await self.get_count("ignored_commands", ctx.guild.id)
            if count == 0:
                embed = self.create_embed("Nothing to Clear", "No commands are ignored.", "info")
                return await ctx.send(embed=embed)

            # Confirmation
            embed = self.create_embed(
                "Confirm Command Reset",
                f"⚠️ This will remove **{count}** ignored commands.\n**This action cannot be undone!**\n\nReact ✅ to confirm or ❌ to cancel.",
                "warning"
            )
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30, check=check)
                
                if str(reaction.emoji) == "✅":
                    await self.ignored_commands.delete_many({"guild_id": ctx.guild.id})
                    
                    embed = self.create_embed(
                        "Commands Reset Successfully",
                        f"✅ Removed all **{count}** ignored commands.",
                        "success"
                    )
                    await msg.edit(embed=embed)
                else:
                    embed = self.create_embed("Reset Cancelled", "Command reset was cancelled.", "info")
                    await msg.edit(embed=embed)
                    
            except asyncio.TimeoutError:
                embed = self.create_embed("Timeout", "Reset confirmation timed out.", "warning")
                await msg.edit(embed=embed)
            
            try:
                await msg.clear_reactions()
            except:
                pass

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to reset commands: {str(e)}", "error")
            await ctx.send(embed=embed)


    # ================= USER MANAGEMENT =================
    @ignore.group(name="user", with_app_command=True, fallback="help")
    @blacklist_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def user(self, ctx: commands.Context):
        """Manage ignored users - Block all commands from specific users"""
        embed = self.create_embed(
            "User Ignore Management",
            "**Commands:**\n"
            "`add <user>` - Block all commands from user\n"
            "`remove <user>` - Unblock user\n"
            "`list` - View all ignored users\n"
            "`reset` - Clear all ignored users\n\n"
            "**Effect:** Bot will ignore ALL commands from blocked users server-wide."
        )
        await ctx.send(embed=embed)


    @user.command(name="add", with_app_command=True)
    @app_commands.describe(user="User to ignore all commands from")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def user_add(self, ctx: commands.Context, user: discord.User):
        """Add a user to ignore list"""
        try:
            # Prevent self-ignore
            if user.id == ctx.author.id:
                embed = self.create_embed("Cannot Ignore Yourself", "You cannot ignore yourself!", "error")
                return await ctx.send(embed=embed)

            # Prevent ignoring admins
            if isinstance(user, discord.Member) and user.guild_permissions.administrator:
                embed = self.create_embed("Cannot Ignore Administrators", "Administrators cannot be ignored.", "error")
                return await ctx.send(embed=embed)

            # Check limits
            count = await self.get_count("ignored_users", ctx.guild.id)
            if count >= 50:
                embed = self.create_embed("Limit Reached", "Maximum 50 users can be ignored per server.", "error")
                return await ctx.send(embed=embed)

            # Check if already ignored
            if await self.item_exists("ignored_users", ctx.guild.id, user.id):
                embed = self.create_embed("Already Ignored", f"{user.mention} is already ignored.", "error")
                return await ctx.send(embed=embed)

            # Add to database
            await self.ignored_users.insert_one({"guild_id": ctx.guild.id, "user_id": user.id})

            embed = self.create_embed(
                "User Ignored Successfully",
                f"✅ {user.mention} has been ignored.\n\n**Effect:** Bot will not respond to any commands from this user.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to ignore user: {str(e)}", "error")
            await ctx.send(embed=embed)


    @user.command(name="remove", with_app_command=True)
    @app_commands.describe(user="User to remove from ignore list")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def user_remove(self, ctx: commands.Context, user: discord.User):
        """Remove a user from ignore list"""
        try:
            # Check if exists
            if not await self.item_exists("ignored_users", ctx.guild.id, user.id):
                embed = self.create_embed("Not Found", f"{user.mention} is not in the ignore list.", "error")
                return await ctx.send(embed=embed)

            # Remove from database
            await self.ignored_users.delete_one({"guild_id": ctx.guild.id, "user_id": user.id})

            embed = self.create_embed(
                "User Unignored Successfully",
                f"✅ {user.mention} has been removed from ignore list.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to unignore user: {str(e)}", "error")
            await ctx.send(embed=embed)


    @user.command(name="list", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def user_list(self, ctx: commands.Context):
        """List all ignored users"""
        try:
            cursor = self.ignored_users.find({"guild_id": ctx.guild.id})
            users = await cursor.to_list(length=None)

            if not users:
                embed = self.create_embed("No Ignored Users", "No users are currently ignored.", "info")
                return await ctx.send(embed=embed)

            # Build user list
            user_mentions = []
            for doc in users:
                user_id = doc['user_id']
                member = ctx.guild.get_member(user_id)
                if member:
                    user_mentions.append(f"• {member.mention} (`{member.display_name}`)")
                else:
                    user = self.bot.get_user(user_id)
                    if user:
                        user_mentions.append(f"• {user.mention} (`{user.display_name}` - Left server)")
                    else:
                        user_mentions.append(f"• Unknown User (ID: {user_id})")

            # Create paginated embed
            embed = discord.Embed(
                title=f"{self.emojis['info']} Ignored Users ({len(users)})",
                color=self.color,
                timestamp=discord.utils.utcnow()
            )

            # Add users in chunks
            chunks = [user_mentions[i:i+15] for i in range(0, len(user_mentions), 15)]
            for i, chunk in enumerate(chunks[:3]):  # Show max 45 users
                field_name = f"Users {i*15+1}-{min((i+1)*15, len(user_mentions))}"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

            if len(users) > 45:
                embed.add_field(name="Note", value=f"Showing first 45 of {len(users)} users", inline=False)

            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to list users: {str(e)}", "error")
            await ctx.send(embed=embed)


    @user.command(name="reset", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def user_reset(self, ctx: commands.Context):
        """Clear all ignored users"""
        try:
            count = await self.get_count("ignored_users", ctx.guild.id)
            if count == 0:
                embed = self.create_embed("Nothing to Clear", "No users are ignored.", "info")
                return await ctx.send(embed=embed)

            # Confirmation
            embed = self.create_embed(
                "Confirm User Reset",
                f"⚠️ This will remove **{count}** ignored users.\n**This action cannot be undone!**\n\nReact ✅ to confirm or ❌ to cancel.",
                "warning"
            )
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30, check=check)
                
                if str(reaction.emoji) == "✅":
                    await self.ignored_users.delete_many({"guild_id": ctx.guild.id})
                    
                    embed = self.create_embed(
                        "Users Reset Successfully",
                        f"✅ Removed all **{count}** ignored users.",
                        "success"
                    )
                    await msg.edit(embed=embed)
                else:
                    embed = self.create_embed("Reset Cancelled", "User reset was cancelled.", "info")
                    await msg.edit(embed=embed)
                    
            except asyncio.TimeoutError:
                embed = self.create_embed("Timeout", "Reset confirmation timed out.", "warning")
                await msg.edit(embed=embed)
            
            try:
                await msg.clear_reactions()
            except:
                pass

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to reset users: {str(e)}", "error")
            await ctx.send(embed=embed)


    # ================= BYPASS MANAGEMENT =================
    @ignore.group(name="bypass", with_app_command=True, fallback="help")
    @blacklist_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def bypass(self, ctx: commands.Context):
        """Manage bypass users - Allow specific users to use commands anywhere"""
        embed = self.create_embed(
            "Bypass Management",
            "**Commands:**\n"
            "`add <user>` - Allow user to bypass all ignores\n"
            "`remove <user>` - Remove bypass access\n"
            "`list` - View all bypass users\n"
            "`reset` - Clear all bypass users\n\n"
            "**Effect:** Bypass users can use commands in ignored channels and use ignored commands."
        )
        await ctx.send(embed=embed)


    @bypass.command(name="add", with_app_command=True)
    @app_commands.describe(user="User to give bypass access to")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def bypass_add(self, ctx: commands.Context, user: discord.User):
        """Add a user to bypass list"""
        try:
            # Check limits
            count = await self.get_count("bypass_users", ctx.guild.id)
            if count >= 30:
                embed = self.create_embed("Limit Reached", "Maximum 30 users can have bypass access per server.", "error")
                return await ctx.send(embed=embed)

            # Check if already has bypass
            if await self.item_exists("bypass_users", ctx.guild.id, user.id):
                embed = self.create_embed("Already Has Bypass", f"{user.mention} already has bypass access.", "error")
                return await ctx.send(embed=embed)

            # Add to database
            await self.bypass_users.insert_one({"guild_id": ctx.guild.id, "user_id": user.id})

            embed = self.create_embed(
                "Bypass Added Successfully",
                f"✅ {user.mention} now has bypass access.\n\n**Effect:** This user can use commands in ignored channels and use ignored commands.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to add bypass: {str(e)}", "error")
            await ctx.send(embed=embed)


    @bypass.command(name="remove", with_app_command=True)
    @app_commands.describe(user="User to remove bypass access from")
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def bypass_remove(self, ctx: commands.Context, user: discord.User):
        """Remove a user from bypass list"""
        try:
            # Check if exists
            if not await self.item_exists("bypass_users", ctx.guild.id, user.id):
                embed = self.create_embed("Not Found", f"{user.mention} does not have bypass access.", "error")
                return await ctx.send(embed=embed)

            # Remove from database
            await self.bypass_users.delete_one({"guild_id": ctx.guild.id, "user_id": user.id})

            embed = self.create_embed(
                "Bypass Removed Successfully",
                f"✅ {user.mention} no longer has bypass access.",
                "success"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to remove bypass: {str(e)}", "error")
            await ctx.send(embed=embed)


    @bypass.command(name="list", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def bypass_list(self, ctx: commands.Context):
        """List all bypass users"""
        try:
            cursor = self.bypass_users.find({"guild_id": ctx.guild.id})
            users = await cursor.to_list(length=None)

            if not users:
                embed = self.create_embed("No Bypass Users", "No users have bypass access.", "info")
                return await ctx.send(embed=embed)

            # Build user list
            user_mentions = []
            for doc in users:
                user_id = doc['user_id']
                member = ctx.guild.get_member(user_id)
                if member:
                    user_mentions.append(f"• {member.mention} (`{member.display_name}`)")
                else:
                    user = self.bot.get_user(user_id)
                    if user:
                        user_mentions.append(f"• {user.mention} (`{user.display_name}` - Left server)")
                    else:
                        user_mentions.append(f"• Unknown User (ID: {user_id})")

            # Create embed
            embed = discord.Embed(
                title=f"{self.emojis['info']} Bypass Users ({len(users)})",
                color=self.color,
                timestamp=discord.utils.utcnow()
            )

            # Add users in chunks
            chunks = [user_mentions[i:i+15] for i in range(0, len(user_mentions), 15)]
            for i, chunk in enumerate(chunks[:2]):  # Show max 30 users
                field_name = f"Users {i*15+1}-{min((i+1)*15, len(user_mentions))}"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to list bypass users: {str(e)}", "error")
            await ctx.send(embed=embed)


    @bypass.command(name="reset", with_app_command=True)
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def bypass_reset(self, ctx: commands.Context):
        """Clear all bypass users"""
        try:
            count = await self.get_count("bypass_users", ctx.guild.id)
            if count == 0:
                embed = self.create_embed("Nothing to Clear", "No users have bypass access.", "info")
                return await ctx.send(embed=embed)

            # Confirmation
            embed = self.create_embed(
                "Confirm Bypass Reset",
                f"⚠️ This will remove bypass access from **{count}** users.\n**This action cannot be undone!**\n\nReact ✅ to confirm or ❌ to cancel.",
                "warning"
            )
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30, check=check)
                
                if str(reaction.emoji) == "✅":
                    await self.bypass_users.delete_many({"guild_id": ctx.guild.id})
                    
                    embed = self.create_embed(
                        "Bypass Reset Successfully",
                        f"✅ Removed bypass access from **{count}** users.",
                        "success"
                    )
                    await msg.edit(embed=embed)
                else:
                    embed = self.create_embed("Reset Cancelled", "Bypass reset was cancelled.", "info")
                    await msg.edit(embed=embed)
                    
            except asyncio.TimeoutError:
                embed = self.create_embed("Timeout", "Reset confirmation timed out.", "warning")
                await msg.edit(embed=embed)
            
            try:
                await msg.clear_reactions()
            except:
                pass

        except Exception as e:
            embed = self.create_embed("Error", f"Failed to reset bypass: {str(e)}", "error")
            await ctx.send(embed=embed)


    # ================= PREFIX COMMAND ALIASES =================
    @commands.command(name="ignorechanneladd", aliases=["igca"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_channel_add(self, ctx, channel: discord.TextChannel):
        await self.channel_add(ctx, channel)

    @commands.command(name="ignorechannelremove", aliases=["igcr"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_channel_remove(self, ctx, channel: discord.TextChannel):
        await self.channel_remove(ctx, channel)

    @commands.command(name="ignorechannellist", aliases=["igcl"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_channel_list(self, ctx):
        await self.channel_list(ctx)

    @commands.command(name="ignorechannelreset", aliases=["igcres"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_channel_reset(self, ctx):
        await self.channel_reset(ctx)

    @commands.command(name="ignorecommandadd", aliases=["igcmda"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_command_add(self, ctx, *, command: str):
        await self.command_add(ctx, command)

    @commands.command(name="ignorecommandremove", aliases=["igcmdr"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_command_remove(self, ctx, *, command: str):
        await self.command_remove(ctx, command)

    @commands.command(name="ignorecommandlist", aliases=["igcmdl"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_command_list(self, ctx):
        await self.command_list(ctx)

    @commands.command(name="ignorecommandreset", aliases=["igcmdres"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_command_reset(self, ctx):
        await self.command_reset(ctx)

    @commands.command(name="ignoreuseradd", aliases=["igua"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_user_add(self, ctx, user: discord.User):
        await self.user_add(ctx, user)

    @commands.command(name="ignoreuserremove", aliases=["igur"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_user_remove(self, ctx, user: discord.User):
        await self.user_remove(ctx, user)

    @commands.command(name="ignoreuserlist", aliases=["iguL"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_user_list(self, ctx):
        await self.user_list(ctx)

    @commands.command(name="ignoreuserreset", aliases=["igures"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_user_reset(self, ctx):
        await self.user_reset(ctx)

    @commands.command(name="ignorebypassadd", aliases=["igba"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_bypass_add(self, ctx, user: discord.User):
        await self.bypass_add(ctx, user)

    @commands.command(name="ignorebypassremove", aliases=["igbr"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_bypass_remove(self, ctx, user: discord.User):
        await self.bypass_remove(ctx, user)

    @commands.command(name="ignorebypasslist", aliases=["igbl"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_bypass_list(self, ctx):
        await self.bypass_list(ctx)

    @commands.command(name="ignorebypassreset", aliases=["igbres"])
    @blacklist_check()
    @commands.has_permissions(administrator=True)
    async def prefix_bypass_reset(self, ctx):
        await self.bypass_reset(ctx)


    # ================= ERROR HANDLING =================
    @ignore.error
    @channel.error
    @command.error
    @user.error
    @bypass.error
    async def ignore_error_handler(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = self.create_embed("Access Denied", "You need `Administrator` permission to use ignore commands.", "error")
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            embed = self.create_embed("Cooldown Active", f"Please wait {error.retry_after:.1f} seconds before using this command again.", "warning")
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = self.create_embed("Missing Argument", "Please provide all required arguments for this command.", "error")
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, (commands.ChannelNotFound, commands.UserNotFound)):
            embed = self.create_embed("Not Found", "The specified channel or user could not be found.", "error")
            await ctx.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Ignore(bot))
