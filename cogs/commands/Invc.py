import discord
from discord.ext import commands
from discord import app_commands
import motor.motor_asyncio
import asyncio
from utils.Tools import *
from typing import Optional
import logging
import datetime
import json
import os

# ═══════════════════════════════════════════════════════════════════════════════
#                           🎨 UNIVERSAL EMOJI CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Success/Error Emojis
SUCCESS_EMOJI = "✅"        # Success operations
ERROR_EMOJI = "❌"          # Error messages  
WARNING_EMOJI = "⚠️"        # Warning messages
INFO_EMOJI = "ℹ️"           # Information messages

# Feature Emojis
VOICE_EMOJI = "🎙️"         # Voice channel related
ROLE_EMOJI = "🏷️"          # Role related operations
SETTINGS_EMOJI = "⚙️"      # Configuration/settings
LIST_EMOJI = "📋"          # Lists and displays
SECURITY_EMOJI = "🔐"      # Security/permissions
STATS_EMOJI = "📊"         # Statistics
TIME_EMOJI = "⏰"          # Time/duration related
USER_EMOJI = "👤"          # User related
BOT_EMOJI = "🤖"           # Bot related
CHANNEL_EMOJI = "📺"       # Channel related

# Action Emojis  
ADD_EMOJI = "➕"           # Add operations
REMOVE_EMOJI = "➖"        # Remove operations
RESET_EMOJI = "🔄"         # Reset operations
VIEW_EMOJI = "👁️"          # View/show operations
EDIT_EMOJI = "✏️"          # Edit operations
DELETE_EMOJI = "🗑️"        # Delete operations

# Status Emojis
ONLINE_EMOJI = "🟢"        # Online/active status
OFFLINE_EMOJI = "🔴"       # Offline/inactive status
LOADING_EMOJI = "⏳"       # Loading status
TEST_EMOJI = "🧪"          # Test operations


class Invcrole(commands.Cog):
    """Voice Channel Role Management System - Auto-assign roles when users join/leave voice channels"""
    
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.vcroles = None
        self.vcrole_stats = None
        
        # Setup logging
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        """Called when the cog is loaded - init DB and sync commands"""
        if not self.mongo_uri:
            print(f"{ERROR_EMOJI} [Invc] MONGO_URI not found in env!")
            return

        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            self.db = self.client.get_database() # Uses DB from URI
            self.vcroles = self.db.vcroles
            self.vcrole_stats = self.db.vcrole_stats
            
            # Create indexes
            await self.vcroles.create_index(
                [("guild_id", 1), ("role_id", 1)], 
                unique=True
            )
            await self.vcrole_stats.create_index("guild_id", unique=True)
            
            print(f"{SUCCESS_EMOJI} [Invc] MongoDB connected and indexes ensured.")
        except Exception as e:
            print(f"{ERROR_EMOJI} [Invc] Database connection failed: {e}")

    async def update_stats(self, guild_id: int, action: str):
        """Update statistics for voice role assignments with safe error handling"""
        try:
            current_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            
            update_op = {"$set": {"last_activity": current_time}, "$setOnInsert": {"guild_id": guild_id}}
            inc_op = {}

            if action == "assign":
                inc_op = {"total_assignments": 1}
            elif action == "remove":
                inc_op = {"total_removals": 1}
            elif action == "role_added":
                inc_op = {"total_roles": 1}
            elif action == "role_removed":
                inc_op = {"total_roles": -1}
            
            if inc_op:
                update_op["$inc"] = inc_op

            await self.vcrole_stats.update_one(
                {"guild_id": guild_id},
                update_op,
                upsert=True
            )
        except Exception as e:
            print(f"Error updating VCRole stats: {e}")

    def create_embed(self, title: str, description: str, color: int = 0x2f3136, emoji: str = INFO_EMOJI) -> discord.Embed:
        """Create a standardized embed"""
        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=description,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Scyro Voice Role System", icon_url=self.bot.user.avatar.url if self.bot.user else None)
        return embed

    async def check_role_hierarchy(self, guild: discord.Guild, role: discord.Role) -> tuple[bool, str]:
        """Check if bot can manage the specified role"""
        bot_member = guild.get_member(self.bot.user.id)
        if not bot_member:
            return False, "Bot is not in the guild"
        
        bot_top_role = bot_member.top_role
        if role >= bot_top_role:
            return False, f"Role {role.mention} is higher than or equal to my highest role ({bot_top_role.mention}). Please move my role above the target role."
        
        if not bot_member.guild_permissions.manage_roles:
            return False, "I don't have the 'Manage Roles' permission in this guild."
        
        return True, "OK"

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              🎮 PREFIX COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.group(name='vcrole', help="Voice Channel Role management commands", invoke_without_command=True, aliases=['vcr', 'voicerole'])
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def vcrole(self, ctx):
        """Voice Channel Role management system with enhanced help display"""
        if ctx.subcommand_passed is None:
            embed = self.create_embed(
                "Scyro Voice Role System Commands",
                f"{VOICE_EMOJI} **Automatic role assignment for voice channel activity**\n\nManage roles that are automatically assigned when users join voice channels and removed when they leave.",
                0x3498db,
                VOICE_EMOJI
            )

            embed.add_field(
                name=f"{SETTINGS_EMOJI} **Setup Commands**",
                value=f"""
`{ctx.prefix}vcrole add <role>` - Add a voice channel role
`{ctx.prefix}vcrole remove <role>` - Remove a voice channel role
`{ctx.prefix}vcrole reset` - Clear all voice channel roles
                """,
                inline=False
            )

            embed.add_field(
                name=f"{VIEW_EMOJI} **Management Commands**",
                value=f"""
`{ctx.prefix}vcrole config` - View current configuration
`{ctx.prefix}vcrole stats` - View assignment statistics
`{ctx.prefix}vcrole test` - Test the voice role system
                """,
                inline=False
            )

            embed.add_field(
                name=f"{INFO_EMOJI} **How Voice Roles Work**",
                value=f"""
{ADD_EMOJI} **Join Voice Channel** → User gets the role automatically
{REMOVE_EMOJI} **Leave Voice Channel** → Role is removed automatically
{VOICE_EMOJI} **Works in ALL voice channels** in your server
{SECURITY_EMOJI} **Hierarchy Safe** - Bot checks role permissions
                """,
                inline=False
            )

            embed.add_field(
                name=f"{INFO_EMOJI} **Slash Commands Available**",
                value=f"""
All commands work as slash commands with spaces:
`/vcrole add`, `/vcrole config`, `/vcrole stats`, etc.
                """,
                inline=False
            )

            embed.set_thumbnail(url=ctx.guild.me.avatar.url if ctx.guild.me.avatar else None)
            await ctx.reply(embed=embed)
            ctx.command.reset_cooldown(ctx)

    @vcrole.command(name='add', help="Add a role to the voice channel role system")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def add(self, ctx, role: discord.Role):
        """Add a role to the voice channel role system"""

        # Check user hierarchy (Prevent Privilege Escalation)
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            embed = self.create_embed(
                "Permission Error",
                f"{SECURITY_EMOJI} **Cannot manage this role:**\nThis role is higher than or equal to your highest role.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await ctx.reply(embed=embed)
        
        # Check role hierarchy
        can_manage, reason = await self.check_role_hierarchy(ctx.guild, role)
        if not can_manage:
            embed = self.create_embed(
                "Permission Error",
                f"{SECURITY_EMOJI} **Cannot manage this role:**\n{reason}",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await ctx.reply(embed=embed)

        # Check if role already exists
        existing = await self.vcroles.find_one({"guild_id": ctx.guild.id, "role_id": role.id})
        if existing:
            embed = self.create_embed(
                "Already Configured",
                f"{role.mention} is already set as a voice channel role in this guild.",
                0xe67e22,
                WARNING_EMOJI
            )
            return await ctx.reply(embed=embed)

        # Add the role
        current_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        try:
            await self.vcroles.insert_one({
                "guild_id": ctx.guild.id,
                "role_id": role.id,
                "added_by": ctx.author.id,
                "added_at": current_time
            })
        except Exception as e:
            await ctx.reply(f"{ERROR_EMOJI} Database error: {e}")
            return

        await self.update_stats(ctx.guild.id, "role_added")

        embed = self.create_embed(
            "Voice Role Added",
            f"""
{SUCCESS_EMOJI} **Successfully added voice channel role!**

{ROLE_EMOJI} **Role:** {role.mention}
{USER_EMOJI} **Added by:** {ctx.author.mention}
{TIME_EMOJI} **Added:** <t:{current_time}:F>

{VOICE_EMOJI} **How it works:**
• Users get this role when joining **any** voice channel
• Role is removed when they leave **all** voice channels
• Works automatically 24/7

{WARNING_EMOJI} **Important:** Make sure my role is positioned above {role.mention} in Server Settings → Roles!
            """,
            0x2ecc71,
            SUCCESS_EMOJI
        )
        await ctx.reply(embed=embed)

    @vcrole.command(name='remove', aliases=["delete", "del"], help="Remove a role from voice channel role system")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx, role: discord.Role):
        """Remove a role from the voice channel role system"""
        
        result = await self.vcroles.delete_one({"guild_id": ctx.guild.id, "role_id": role.id})
        
        if result.deleted_count == 0:
            embed = self.create_embed(
                "Role Not Found",
                f"{role.mention} is not configured as a voice channel role in this guild.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await ctx.reply(embed=embed)

        await self.update_stats(ctx.guild.id, "role_removed")

        embed = self.create_embed(
            "Voice Role Removed",
            f"""
{SUCCESS_EMOJI} **Successfully removed voice channel role!**

{ROLE_EMOJI} **Role:** {role.mention}
{USER_EMOJI} **Removed by:** {ctx.author.mention}
{INFO_EMOJI} **Result:** This role will no longer be automatically assigned when users join voice channels.
            """,
            0xe74c3c,
            SUCCESS_EMOJI
        )
        await ctx.reply(embed=embed)

    @vcrole.command(name='reset', aliases=['clear', 'removeall'], help="Remove all voice channel roles")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        """Remove all voice channel roles from this guild"""
        
        result = await self.vcroles.delete_many({"guild_id": ctx.guild.id})
        count = result.deleted_count
                
        if count == 0:
            embed = self.create_embed(
                "Nothing to Reset",
                "No voice channel roles are configured in this guild.",
                0xe67e22,
                WARNING_EMOJI
            )
            return await ctx.reply(embed=embed)

        embed = self.create_embed(
            "Configuration Reset",
            f"""
{SUCCESS_EMOJI} **All voice channel roles have been removed**

{STATS_EMOJI} **Removed:** {count} role(s)
{USER_EMOJI} **Reset by:** {ctx.author.mention}
{TIME_EMOJI} **Time:** <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:F>

{INFO_EMOJI} **Effect:** Voice channel role assignments are now disabled for this server.
            """,
            0x2ecc71,
            SUCCESS_EMOJI
        )
        await ctx.reply(embed=embed)

    @vcrole.command(name='config', aliases=['view', 'show', 'list'], help="View current voice channel role configuration")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def config(self, ctx):
        """Show current voice channel role configuration"""
        
        cursor = self.vcroles.find({"guild_id": ctx.guild.id})
        rows = await cursor.to_list(length=None)

        if not rows:
            embed = self.create_embed(
                "No Configuration",
                f"""
{INFO_EMOJI} No voice channel roles are currently configured in this guild.

**Get Started:**
{ADD_EMOJI} Use `{ctx.prefix}vcrole add <role>` to add a role
{VIEW_EMOJI} Use `{ctx.prefix}vcrole help` for more commands

**Example:**
`{ctx.prefix}vcrole add @Member` - Gives @Member role when joining VC
                """,
                0xe67e22,
                WARNING_EMOJI
            )
            return await ctx.reply(embed=embed)

        embed = self.create_embed(
            "Voice Channel Role Configuration",
            f"{SETTINGS_EMOJI} **Current voice roles in {ctx.guild.name}**",
            0x3498db,
            SETTINGS_EMOJI
        )

        valid_roles = []
        invalid_roles = []

        for doc in rows:
            role_id = doc['role_id']
            role = ctx.guild.get_role(role_id)
            if role:
                can_manage, reason = await self.check_role_hierarchy(ctx.guild, role)
                status = f"{ONLINE_EMOJI} Working" if can_manage else f"{OFFLINE_EMOJI} Cannot manage"
                
                valid_roles.append(f"{ROLE_EMOJI} **{role.name}** - {status}")
            else:
                invalid_roles.append(f"{ERROR_EMOJI} **Deleted Role** (ID: {role_id})")

        if valid_roles:
            embed.add_field(
                name=f"{LIST_EMOJI} Active Roles ({len(valid_roles)})",
                value="\n".join(valid_roles)[:1024],
                inline=False
            )

        if invalid_roles:
            embed.add_field(
                name=f"{ERROR_EMOJI} Invalid Roles ({len(invalid_roles)})",
                value="\n".join(invalid_roles)[:1024],
                inline=False
            )

        await ctx.reply(embed=embed)

    @vcrole.command(name='stats', help="Show voice channel role statistics")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def stats(self, ctx):
        """Show voice channel role statistics"""
        
        stats_doc = await self.vcrole_stats.find_one({"guild_id": ctx.guild.id})
        count = await self.vcroles.count_documents({"guild_id": ctx.guild.id})
        
        if not stats_doc:
            assignments, removals, last_activity, total_roles = 0, 0, 0, count
        else:
            assignments = stats_doc.get('total_assignments', 0)
            removals = stats_doc.get('total_removals', 0)
            last_activity = stats_doc.get('last_activity', 0)
            total_roles = stats_doc.get('total_roles', count)

        embed = self.create_embed(
            "Voice Role Statistics",
            f"{STATS_EMOJI} **Statistics for {ctx.guild.name}**",
            0x9b59b6,
            STATS_EMOJI
        )

        embed.add_field(
            name=f"{ROLE_EMOJI} Role Configuration",
            value=f"""
**Configured Roles:** {total_roles}
**Status:** {ONLINE_EMOJI if total_roles > 0 else OFFLINE_EMOJI} {'Active' if total_roles > 0 else 'Inactive'}
            """,
            inline=True
        )

        embed.add_field(
            name=f"{TIME_EMOJI} Activity Statistics",
            value=f"""
**Total Assignments:** {assignments:,}
**Total Removals:** {removals:,}
**Total Actions:** {assignments + removals:,}
            """,
            inline=True
        )

        embed.add_field(
            name=f"{INFO_EMOJI} System Information",
            value=f"""
**Last Activity:** {'<t:' + str(last_activity) + ':R>' if last_activity else 'Never'}
**System Status:** {ONLINE_EMOJI if total_roles > 0 else OFFLINE_EMOJI} {'Monitoring' if total_roles > 0 else 'Disabled'}
            """,
            inline=False
        )

        await ctx.reply(embed=embed)

    @vcrole.command(name='test', help="Test voice role assignment for yourself")
    @blacklist_check()
    @ignore_check()
    async def test(self, ctx):
        """Test voice role assignment"""
        
        if not ctx.author.voice:
            embed = self.create_embed(
                "Not in Voice Channel",
                f"{VOICE_EMOJI} **You must be in a voice channel to test the voice role system.**",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await ctx.reply(embed=embed)

        cursor = self.vcroles.find({"guild_id": ctx.guild.id})
        rows = await cursor.to_list(length=None)

        if not rows:
            embed = self.create_embed(
                "No Roles Configured",
                f"No voice channel roles are configured. Use `{ctx.prefix}vcrole add <role>` to add one.",
                0xe67e22,
                WARNING_EMOJI
            )
            return await ctx.reply(embed=embed)

        test_results = []
        for doc in rows:
            role_id = doc['role_id']
            role = ctx.guild.get_role(role_id)
            if not role:
                continue
                
            can_manage, reason = await self.check_role_hierarchy(ctx.guild, role)
            has_role = role in ctx.author.roles
            
            if can_manage:
                if has_role:
                    status = f"{SUCCESS_EMOJI} You have this role - System working!"
                else:
                    status = f"{INFO_EMOJI} You should receive this role"
            else:
                status = f"{ERROR_EMOJI} Cannot manage this role"
            
            test_results.append(f"{ROLE_EMOJI} **{role.name}**: {status}")

        embed = self.create_embed(
            "Voice Role Test Results",
            f"{TEST_EMOJI} **Test results for {ctx.author.mention}**\n\n{VOICE_EMOJI} **Current voice channel:** {ctx.author.voice.channel.mention}",
            0x3498db,
            TEST_EMOJI
        )

        embed.add_field(
            name=f"{LIST_EMOJI} Role Test Results",
            value="\n".join(test_results)[:1024] if test_results else "No valid roles found",
            inline=False
        )

        await ctx.reply(embed=embed)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              ⚡ WORKING SLASH COMMAND GROUP
    # ═══════════════════════════════════════════════════════════════════════════════

    vcrole_group = app_commands.Group(name="vcrole", description="Voice channel role management system")

    @vcrole_group.command(name="add", description="Add a role to the voice channel role system")
    @app_commands.describe(role="The role to assign when users join voice channels")
    async def vcrole_add_slash(self, interaction: discord.Interaction, role: discord.Role):
        """Add a role to the voice channel role system"""
        
        if not interaction.user.guild_permissions.administrator:
            embed = self.create_embed(
                "Permission Denied",
                "You need Administrator permissions to use this command.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Check user hierarchy (Prevent Privilege Escalation)
        if interaction.user.id != interaction.guild.owner_id and role >= interaction.user.top_role:
            embed = self.create_embed(
                "Permission Error",
                f"{SECURITY_EMOJI} **Cannot manage this role:**\nThis role is higher than or equal to your highest role.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Check role hierarchy
        can_manage, reason = await self.check_role_hierarchy(interaction.guild, role)
        if not can_manage:
            embed = self.create_embed(
                "Permission Error",
                f"{SECURITY_EMOJI} **Cannot manage this role:**\n{reason}",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Check if role already exists
        existing = await self.vcroles.find_one({"guild_id": interaction.guild.id, "role_id": role.id})
        if existing:
            embed = self.create_embed(
                "Already Configured",
                f"{role.mention} is already set as a voice channel role in this guild.",
                0xe67e22,
                WARNING_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
            
        # Add the role
        current_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        try:
            await self.vcroles.insert_one({
                "guild_id": interaction.guild.id,
                "role_id": role.id,
                "added_by": interaction.user.id,
                "added_at": current_time
            })
        except Exception as e:
            await interaction.response.send_message(f"{ERROR_EMOJI} Database error: {e}", ephemeral=True)
            return

        await self.update_stats(interaction.guild.id, "role_added")

        embed = self.create_embed(
            "Voice Role Added",
            f"""
{SUCCESS_EMOJI} **Successfully added voice channel role!**

{ROLE_EMOJI} **Role:** {role.mention}
{USER_EMOJI} **Added by:** {interaction.user.mention}
{TIME_EMOJI} **Added:** <t:{current_time}:F>

{VOICE_EMOJI} **How it works:**
• Users get this role when joining **any** voice channel
• Role is removed when they leave **all** voice channels
• Works automatically 24/7

{WARNING_EMOJI} **Important:** Make sure my role is positioned above {role.mention} in Server Settings!
            """,
            0x2ecc71,
            SUCCESS_EMOJI
        )
        await interaction.response.send_message(embed=embed)

    @vcrole_group.command(name="remove", description="Remove a role from voice channel role system")
    @app_commands.describe(role="The role to remove from voice channel assignment")
    async def vcrole_remove_slash(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from the voice channel role system"""
        
        if not interaction.user.guild_permissions.administrator:
            embed = self.create_embed(
                "Permission Denied",
                "You need Administrator permissions to use this command.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        result = await self.vcroles.delete_one({"guild_id": interaction.guild.id, "role_id": role.id})
        
        if result.deleted_count == 0:
            embed = self.create_embed(
                "Role Not Found",
                f"{role.mention} is not configured as a voice channel role in this guild.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await self.update_stats(interaction.guild.id, "role_removed")

        embed = self.create_embed(
            "Voice Role Removed",
            f"""
{SUCCESS_EMOJI} **Successfully removed voice channel role!**

{ROLE_EMOJI} **Role:** {role.mention}
{USER_EMOJI} **Removed by:** {interaction.user.mention}
{INFO_EMOJI} **Result:** This role will no longer be automatically assigned in voice channels.
            """,
            0xe74c3c,
            SUCCESS_EMOJI
        )
        await interaction.response.send_message(embed=embed)

    @vcrole_group.command(name="config", description="View current voice channel role configuration")
    async def vcrole_config_slash(self, interaction: discord.Interaction):
        """Show current voice channel role configuration"""
        
        if not interaction.user.guild_permissions.administrator:
            embed = self.create_embed(
                "Permission Denied", 
                "You need Administrator permissions to use this command.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        cursor = self.vcroles.find({"guild_id": interaction.guild.id})
        rows = await cursor.to_list(length=None)

        if not rows:
            embed = self.create_embed(
                "No Configuration",
                f"""
{INFO_EMOJI} No voice channel roles are currently configured in this guild.

**Get Started:**
{ADD_EMOJI} Use `/vcrole add <role>` to add a role
                """,
                0xe67e22,
                WARNING_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = self.create_embed(
            "Voice Channel Role Configuration",
            f"{SETTINGS_EMOJI} **Current voice roles in {interaction.guild.name}**",
            0x3498db,
            SETTINGS_EMOJI
        )

        valid_roles = []
        for doc in rows[:5]:
            role_id = doc['role_id']
            role = interaction.guild.get_role(role_id)
            if role:
                can_manage, reason = await self.check_role_hierarchy(interaction.guild, role)
                status = f"{ONLINE_EMOJI} Working" if can_manage else f"{OFFLINE_EMOJI} Cannot manage"
                
                valid_roles.append(f"{ROLE_EMOJI} {role.mention} - {status}")

        if valid_roles:
            embed.add_field(
                name=f"{LIST_EMOJI} Active Roles",
                value="\n".join(valid_roles),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @vcrole_group.command(name="stats", description="Show voice channel role statistics") 
    async def vcrole_stats_slash(self, interaction: discord.Interaction):
        """Show voice channel role statistics"""
        
        if not interaction.user.guild_permissions.administrator:
            embed = self.create_embed(
                "Permission Denied",
                "You need Administrator permissions to use this command.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        stats_doc = await self.vcrole_stats.find_one({"guild_id": interaction.guild.id})
        count = await self.vcroles.count_documents({"guild_id": interaction.guild.id})
        
        if not stats_doc:
            assignments, removals, last_activity, total_roles = 0, 0, 0, count
        else:
            assignments = stats_doc.get('total_assignments', 0)
            removals = stats_doc.get('total_removals', 0)
            last_activity = stats_doc.get('last_activity', 0)
            total_roles = stats_doc.get('total_roles', count)

        embed = self.create_embed(
            "Voice Role Statistics",
            f"{STATS_EMOJI} **Statistics for {interaction.guild.name}**",
            0x9b59b6,
            STATS_EMOJI
        )

        embed.add_field(
            name=f"{ROLE_EMOJI} Configuration",
            value=f"**Configured Roles:** {total_roles}",
            inline=True
        )

        embed.add_field(
            name=f"{TIME_EMOJI} Activity", 
            value=f"**Assignments:** {assignments:,}\n**Removals:** {removals:,}",
            inline=True
        )

        embed.add_field(
            name=f"{INFO_EMOJI} Status",
            value=f"**System:** {ONLINE_EMOJI if total_roles > 0 else OFFLINE_EMOJI} {'Active' if total_roles > 0 else 'Inactive'}",
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    @vcrole_group.command(name="test", description="Test voice role assignment for yourself")
    async def vcrole_test_slash(self, interaction: discord.Interaction):
        """Test voice role assignment"""
        
        if not interaction.user.voice:
            embed = self.create_embed(
                "Not in Voice Channel",
                f"{VOICE_EMOJI} You must be in a voice channel to test the voice role system.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        cursor = self.vcroles.find({"guild_id": interaction.guild.id})
        rows = await cursor.to_list(length=None)

        if not rows:
            embed = self.create_embed(
                "No Roles Configured",
                f"No voice channel roles are configured. Use `/vcrole add` to add one.",
                0xe67e22,
                WARNING_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        test_results = []
        for doc in rows:
            role_id = doc['role_id']
            role = interaction.guild.get_role(role_id)
            if not role:
                continue
                
            can_manage, reason = await self.check_role_hierarchy(interaction.guild, role)
            has_role = role in interaction.user.roles
            
            if can_manage:
                if has_role:
                    status = f"{SUCCESS_EMOJI} Working - You have this role"
                else:
                    status = f"{INFO_EMOJI} Working - You should get this role"
            else:
                status = f"{ERROR_EMOJI} Cannot manage - Check role hierarchy"
            
            test_results.append(f"{ROLE_EMOJI} **{role.name}**: {status}")

        embed = self.create_embed(
            "Voice Role Test Results",
            f"{TEST_EMOJI} **Test results for {interaction.user.mention}**\n\n{VOICE_EMOJI} **Voice channel:** {interaction.user.voice.channel.mention}",
            0x3498db,
            TEST_EMOJI
        )

        embed.add_field(
            name=f"{LIST_EMOJI} Role Test Results",
            value="\n".join(test_results)[:1024] if test_results else "No valid roles found",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    @vcrole_group.command(name="reset", description="Remove all voice channel roles")
    async def vcrole_reset_slash(self, interaction: discord.Interaction):
        """Remove all voice channel roles from this guild"""
        
        if not interaction.user.guild_permissions.administrator:
            embed = self.create_embed(
                "Permission Denied",
                "You need Administrator permissions to use this command.",
                0xe74c3c,
                ERROR_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        result = await self.vcroles.delete_many({"guild_id": interaction.guild.id})
        count = result.deleted_count
                
        if count == 0:
            embed = self.create_embed(
                "Nothing to Reset",
                "No voice channel roles are configured in this guild.",
                0xe67e22,
                WARNING_EMOJI
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = self.create_embed(
            "Configuration Reset",
            f"""
{SUCCESS_EMOJI} **All voice channel roles have been removed**

{STATS_EMOJI} **Removed:** {count} role(s)
{USER_EMOJI} **Reset by:** {interaction.user.mention}
{INFO_EMOJI} **Effect:** Voice channel role assignments are now disabled.
            """,
            0x2ecc71,
            SUCCESS_EMOJI
        )
        await interaction.response.send_message(embed=embed)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              🎧 FIXED EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes and assign/remove roles - FIXED VERSION"""
        try:
            # Skip bot users
            if member.bot:
                return
                
            cursor = self.vcroles.find({"guild_id": member.guild.id})
            rows = await cursor.to_list(length=None)
                
            if not rows:
                return

            # Process each configured role
            for doc in rows:
                role_id = doc['role_id']
                role = member.guild.get_role(role_id)
                if not role:
                    continue

                # Check if bot can manage this role
                can_manage, _ = await self.check_role_hierarchy(member.guild, role)
                if not can_manage:
                    continue

                # User joined a voice channel and doesn't have the role
                if after.channel and not before.channel and role not in member.roles:
                    success = await self.add_role_with_retry(member, role, f"Joined VC: {after.channel.name} | Scyro Voice Role")
                    if success:
                        await self.update_stats(member.guild.id, "assign")
                        print(f"✅ Added voice role {role.name} to {member} in {member.guild.name}")

                # User left voice channels entirely and has the role
                elif not after.channel and before.channel and role in member.roles:
                    success = await self.remove_role_with_retry(member, role, f"Left VC: {before.channel.name} | Scyro Voice Role")
                    if success:
                        await self.update_stats(member.guild.id, "remove")
                        print(f"❌ Removed voice role {role.name} from {member} in {member.guild.name}")

        except Exception as e:
            print(f"Error in VCRole on_voice_state_update: {e}")

    async def add_role_with_retry(self, member, role, reason, retries=3) -> bool:
        """Add role with retry logic and rate limit handling"""
        for attempt in range(retries):
            try:
                await member.add_roles(role, reason=reason)
                return True
            except discord.errors.RateLimited as e:
                retry_after = getattr(e, 'retry_after', 1)
                await asyncio.sleep(retry_after)
                continue
            except discord.Forbidden:
                print(f"❌ Missing permissions to add role {role.name} to {member}")
                return False
            except discord.HTTPException as e:
                print(f"❌ Error adding role to {member}: {e}")
                return False
            except Exception as e:
                print(f"❌ Unexpected error adding role: {e}")
                return False
        return False

    async def remove_role_with_retry(self, member, role, reason, retries=3) -> bool:
        """Remove role with retry logic and rate limit handling"""
        for attempt in range(retries):
            try:
                await member.remove_roles(role, reason=reason)
                return True
            except discord.errors.RateLimited as e:
                retry_after = getattr(e, 'retry_after', 1)
                await asyncio.sleep(retry_after)
                continue
            except discord.Forbidden:
                print(f"❌ Missing permissions to remove role {role.name} from {member}")
                return False
            except discord.HTTPException as e:
                print(f"❌ Error removing role from {member}: {e}")
                return False
            except Exception as e:
                print(f"❌ Unexpected error removing role: {e}")
                return False
        return False


async def setup(bot):
    cog = Invcrole(bot)
    # Add the slash command group to the tree
    bot.tree.add_command(cog.vcrole_group)
    await bot.add_cog(cog)
   