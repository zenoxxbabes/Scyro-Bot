import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import re
from typing import *
from utils.Tools import *
from discord.ui import Button, View
from typing import Union, Optional
from io import BytesIO
import requests
import aiohttp
import time
from datetime import datetime, timezone, timedelta


time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d))+?")
time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400}


def convert(argument):
  args = argument.lower()
  matches = re.findall(time_regex, args)
  time = 0
  for key, value in matches:
    try:
      time += time_dict[value] * float(key)
    except KeyError:
      raise commands.BadArgument(
        f"{value} is an invalid time key! h|m|s|d are valid arguments")
    except ValueError:
      raise commands.BadArgument(f"{key} is not a number!")
  return round(time)


class Role(commands.Cog):

  def __init__(self, bot):
    self.bot = bot
    self.color = 0x2b2d31  # Professional purple theme

  def create_embed(self, title: str, description: str, embed_type: str = "default", user=None, role=None, member_count=None):
    """Create standardized embeds with consistent professional branding"""
    
    color_map = {
        "success": 0x10b981,    # Emerald green
        "error": 0xef4444,      # Red  
        "warning": 0xf59e0b,    # Amber
        "info": 0x3b82f6,       # Blue
        "default": self.color    # Purple
    }
    
    icon_map = {
        "success": "https://cdn.discordapp.com/emojis/1222750301233090600.png",
        "error": "https://cdn.discordapp.com/emojis/1204106928675102770.png",
        "warning": "https://cdn.discordapp.com/emojis/1204106928675102770.png",
        "info": "https://cdn.discordapp.com/emojis/1222750301233090600.png",
        "default": "https://cdn.discordapp.com/emojis/1222750301233090600.png"
    }

    embed = discord.Embed(
        description=description,
        color=color_map.get(embed_type, self.color),
        timestamp=datetime.now()
    )
    
    embed.set_author(
        name=title,
        icon_url=icon_map.get(embed_type, icon_map["default"])
    )
    
    if user:
        embed.set_footer(
            text=f"Executed by {user}",
            icon_url=user.avatar.url if user.avatar else user.default_avatar.url
        )
        
    if role and member_count is not None:
        embed.add_field(
            name="📊 Statistics",
            value=f"**Role:** {role.mention}\n**Members:** {member_count}\n**Color:** {role.color}",
            inline=False
        )
        
    return embed

  async def check_role_permissions(self, ctx, role: discord.Role, member: Optional[discord.Member] = None):
    """Enhanced permission checking with detailed error messages"""
    
    # Check bot permissions
    if not ctx.guild.me.guild_permissions.manage_roles:
        embed = self.create_embed(
            "Permission Error",
            f"<a:alert:1396429026842644584> I don't have the **Manage Roles** permission!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
        return False

    # Check role hierarchy for bot
    if role >= ctx.guild.me.top_role:
        embed = self.create_embed(
            "Hierarchy Error",
            f"<a:alert:1396429026842644584> I cannot manage **{role.name}** because it's higher than or equal to my highest role!\n\n**Solution:** Move my role above **{role.name}** in Server Settings → Roles",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
        return False

    # Check user permissions for role management
    if ctx.author != ctx.guild.owner and ctx.author.top_role <= role:
        embed = self.create_embed(
            "Insufficient Permissions",
            f"<a:alert:1396429026842644584> You cannot manage **{role.name}** because it's higher than or equal to your highest role!\n\n**Your highest role:** {ctx.author.top_role.mention}\n**Target role:** {role.mention}",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
        return False
        
    # Check if trying to manage a member with higher role
    if member and ctx.author != ctx.guild.owner and ctx.author.top_role <= member.top_role:
        embed = self.create_embed(
            "Insufficient Permissions", 
            f"<a:alert:1396429026842644584> You cannot manage roles for **{member.display_name}** because they have a higher or equal role than yours!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
        return False
        
    return True

  # MAIN ROLE COMMAND GROUP

  @commands.hybrid_group(name="role", invoke_without_command=True, fallback="toggle")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  @top_check()
  async def role(self, ctx, member: discord.Member, *, role: discord.Role):
    """Add or remove a role from a member (toggles the role)"""
    
    if not await self.check_role_permissions(ctx, role, member):
        return

    try:
        if role not in member.roles:
            await member.add_roles(role, reason=f"Role added by {ctx.author} (ID: {ctx.author.id})")
            embed = self.create_embed(
                "Role Added",
                f"<:yes:1396838746862784582> Successfully **added** {role.mention} to {member.mention}",
                "success",
                ctx.author,
                role,
                len(role.members)
            )
        else:
            await member.remove_roles(role, reason=f"Role removed by {ctx.author} (ID: {ctx.author.id})")
            embed = self.create_embed(
                "Role Removed",
                f"<:yes:1396838746862784582> Successfully **removed** {role.mention} from {member.mention}",
                "success",
                ctx.author,
                role,
                len(role.members)
            )
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = self.create_embed(
            "Permission Error",
            "<a:alert:1396429026842644584> I don't have permission to manage roles for this user!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = self.create_embed(
            "Unexpected Error",
            f"<a:alert:1396429026842644584> An unexpected error occurred: {str(e)}",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)

  @role.command(name="add", help="Add a specific role to a member")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  async def role_add(self, ctx, member: discord.Member, *, role: discord.Role):
    """Add a specific role to a member"""
    
    if not await self.check_role_permissions(ctx, role, member):
        return
        
    if role in member.roles:
        embed = self.create_embed(
            "Role Already Assigned",
            f"<a:alert:1396429026842644584> **{member.display_name}** already has the {role.mention} role!",
            "warning",
            ctx.author
        )
        await ctx.send(embed=embed)
        return
        
    try:
        await member.add_roles(role, reason=f"Role added by {ctx.author} (ID: {ctx.author.id})")
        
        embed = self.create_embed(
            "Role Added",
            f"<:yes:1396838746862784582> Successfully added {role.mention} to {member.mention}",
            "success",
            ctx.author,
            role,
            len(role.members)
        )
        await ctx.send(embed=embed)
        
    except discord.Forbidden:
        embed = self.create_embed(
            "Permission Error",
            f"<a:alert:1396429026842644584> I don't have permission to add roles to **{member.display_name}**!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)

  @role.command(name="remove", help="Remove a specific role from a member")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 3, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  async def role_remove(self, ctx, member: discord.Member, *, role: discord.Role):
    """Remove a specific role from a member"""
    
    if not await self.check_role_permissions(ctx, role, member):
        return
        
    if role not in member.roles:
        embed = self.create_embed(
            "Role Not Found",
            f"<a:alert:1396429026842644584> **{member.display_name}** doesn't have the {role.mention} role!",
            "warning",
            ctx.author
        )
        await ctx.send(embed=embed)
        return
        
    try:
        await member.remove_roles(role, reason=f"Role removed by {ctx.author} (ID: {ctx.author.id})")
        
        embed = self.create_embed(
            "Role Removed",
            f"<:yes:1396838746862784582> Successfully removed {role.mention} from {member.mention}",
            "success",
            ctx.author,
            role,
            len(role.members)
        )
        await ctx.send(embed=embed)
        
    except discord.Forbidden:
        embed = self.create_embed(
            "Permission Error", 
            f"<a:alert:1396429026842644584> I don't have permission to remove roles from **{member.display_name}**!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)

  @role.command(name="temp", help="Give role to member for particular time")
  @commands.bot_has_permissions(manage_roles=True)
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 7, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  async def role_temp(self, ctx, role: discord.Role, time, *, user: discord.Member):
    """Give a role to a member temporarily"""
    
    if not await self.check_role_permissions(ctx, role, user):
        return
          
    seconds = convert(time)
    await user.add_roles(role, reason=f"Temporary role by {ctx.author}")
    
    embed = self.create_embed(
        "Temporary Role Added",
        f"<:yes:1396838746862784582> Successfully added {role.mention} to {user.mention} for **{time}**\n\n⏰ Role will be automatically removed after the specified duration.",
        "success",
        ctx.author,
        role,
        len(role.members)
    )
    await ctx.send(embed=embed)
    await asyncio.sleep(seconds)
    
    try:
        await user.remove_roles(role, reason="Temporary role expired")
        embed = self.create_embed(
            "Temporary Role Expired",
            f"⏰ Temporary role {role.mention} has been removed from {user.mention}",
            "info",
            ctx.author
        )
        await ctx.send(embed=embed)
    except:
        pass

  @role.command(name="delete", help="Delete a role in the guild")
  @blacklist_check()
  @ignore_check()
  @top_check()
  @commands.cooldown(1, 7, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  async def role_delete(self, ctx, *, role: discord.Role):
    """Delete a role from the server"""
    
    if not await self.check_role_permissions(ctx, role):
        return

    # Confirm deletion for roles with members
    if len(role.members) > 0:
        embed = self.create_embed(
            "Confirmation Required",
            f"⚠️ **{role.name}** has **{len(role.members)}** member(s). Are you sure you want to delete it?\n\n**This action cannot be undone!**",
            "warning",
            ctx.author
        )
        
        view = ConfirmationView(ctx.author, timeout=30)
        message = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        if not view.value:
            embed = self.create_embed(
                "Deletion Cancelled",
                "<a:alert:1396429026842644584> Role deletion cancelled.",
                "info",
                ctx.author
            )
            await message.edit(embed=embed, view=None)
            return

    try:
        role_name = role.name
        role_members = len(role.members)
        await role.delete(reason=f"Role deleted by {ctx.author} (ID: {ctx.author.id})")
        
        embed = self.create_embed(
            "Role Deleted",
            f"<:yes:1396838746862784582> Successfully deleted role **{role_name}**",
            "success",
            ctx.author
        )
        embed.add_field(
            name="📋 Deletion Summary",
            value=f"**Members affected:** {role_members}",
            inline=False
        )
        await ctx.send(embed=embed)
        
    except discord.Forbidden:
        embed = self.create_embed(
            "Permission Error",
            "<a:alert:1396429026842644584> I don't have permission to delete this role!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
      
  @role.command(name="create", help="Create a role in the guild")
  @blacklist_check()
  @ignore_check()
  @top_check()
  @commands.cooldown(1, 7, commands.BucketType.user)
  @commands.has_permissions(administrator=True)
  @commands.bot_has_permissions(manage_roles=True)
  async def role_create(self, ctx, *, name):
    """Create a new role in the server"""
    
    if len(name) > 100:
        embed = self.create_embed(
            "Invalid Role Name",
            "<a:alert:1396429026842644584> Role name cannot exceed 100 characters!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
        return
        
    # Check if role already exists
    existing_role = discord.utils.get(ctx.guild.roles, name=name)
    if existing_role:
        embed = self.create_embed(
            "Role Already Exists",
            f"<a:alert:1396429026842644584> A role named **{name}** already exists!",
            "warning",
            ctx.author
        )
        await ctx.send(embed=embed)
        return
        
    try:
        new_role = await ctx.guild.create_role(
            name=name, 
            color=discord.Color.default(), 
            reason=f"Role created by {ctx.author} (ID: {ctx.author.id})"
        )
        embed = self.create_embed(
            "Role Created",
            f"<:yes:1396838746862784582> Successfully created role **{new_role.name}**!",
            "success",
            ctx.author
        )
        embed.add_field(
            name="📋 Role Details",
            value=f"**Name:** {new_role.mention}\n**ID:** `{new_role.id}`\n**Position:** {new_role.position}\n**Color:** {new_role.color}",
            inline=False
        )
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = self.create_embed(
            "Permission Error",
            "<a:alert:1396429026842644584> I don't have permission to create roles!",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = self.create_embed(
            "Creation Error",
            f"<a:alert:1396429026842644584> Failed to create role: `{str(e)}`",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)

  @role.command(name="rename", help="Renames a role in the server.")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.has_permissions(administrator=True)
  @commands.bot_has_permissions(manage_roles=True)
  async def role_rename(self, ctx, role: discord.Role, *, newname):
    """Rename an existing role"""
    
    if not await self.check_role_permissions(ctx, role):
        return

    old_name = role.name
    await role.edit(name=newname, reason=f"Role renamed by {ctx.author}")
    embed = self.create_embed(
        "Role Renamed",
        f"<:yes:1396838746862784582> Role **{old_name}** has been renamed to **{newname}**",
        "success",
        ctx.author
    )
    await ctx.send(embed=embed)

  @role.command(name="list", help="List all roles of a member or show server roles")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  async def role_list(self, ctx, *, member: Optional[discord.Member] = None):
    """List all roles of a member or show server roles"""
    
    if member is None:
        member = ctx.author
        
    roles = [role for role in member.roles if role != ctx.guild.default_role]
    roles.sort(key=lambda r: r.position, reverse=True)
    
    if not roles:
        embed = self.create_embed(
            "No Roles Found",
            f"<a:alert:1396429026842644584> **{member.display_name}** has no special roles!",
            "info",
            ctx.author
        )
    else:
        role_list = []
        for i, role in enumerate(roles[:20], 1):  # Limit to 20 roles
            role_list.append(f"`{i:02d}.` {role.mention} - {len(role.members)} members")
            
        embed = self.create_embed(
            f"Roles for {member.display_name}",
            f"👤 **{member.display_name}** has **{len(roles)}** role(s):\n\n" + "\n".join(role_list),
            "info",
            ctx.author
        )
        
        if len(roles) > 20:
            embed.add_field(
                name="⚠️ Note",
                value=f"Only showing first 20 roles. Total roles: **{len(roles)}**",
                inline=False
            )
            
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    await ctx.send(embed=embed)

  @role.command(name="info", help="Get detailed information about a role")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  async def role_info(self, ctx, *, role: discord.Role):
    """Get detailed information about a role"""
    
    embed = self.create_embed(
        f"Role Information: {role.name}",
        f"Comprehensive details about {role.mention}",
        "info",
        ctx.author
    )
    
    # Basic info
    embed.add_field(
        name="📋 Basic Information",
        value=f"**Name:** {role.name}\n**ID:** `{role.id}`\n**Mention:** {role.mention}\n**Created:** <t:{int(role.created_at.timestamp())}:F>",
        inline=False
    )
    
    # Permissions and settings
    embed.add_field(
        name="⚙️ Settings",
        value=f"**Color:** {role.color}\n**Position:** {role.position}\n**Hoisted:** {'Yes' if role.hoist else 'No'}\n**Mentionable:** {'Yes' if role.mentionable else 'No'}",
        inline=True
    )
    
    # Member statistics
    embed.add_field(
        name="👥 Members",
        value=f"**Total:** {len(role.members)}\n**Humans:** {len([m for m in role.members if not m.bot])}\n**Bots:** {len([m for m in role.members if m.bot])}",
        inline=True
    )
    
    # Show key permissions if any
    key_perms = []
    if role.permissions.administrator:
        key_perms.append("Administrator")
    if role.permissions.manage_guild:
        key_perms.append("Manage Server")
    if role.permissions.manage_roles:
        key_perms.append("Manage Roles")
    if role.permissions.manage_channels:
        key_perms.append("Manage Channels")
        
    if key_perms:
        embed.add_field(
            name="🔐 Key Permissions",
            value=", ".join(key_perms[:5]) + ("..." if len(key_perms) > 5 else ""),
            inline=False
        )
        
    # Set role color as embed color if it's not default
    if role.color != discord.Color.default():
        embed.color = role.color
        
    await ctx.send(embed=embed)

  # BULK ROLE OPERATIONS WITH ENHANCED CONFIRMATIONS

  async def bulk_role_operation(self, ctx, role: discord.Role, target_members: list, operation: str, reason: str):
    """Helper method for bulk role operations with progress tracking"""
    
    if not target_members:
        embed = self.create_embed(
            "No Target Members",
            "<a:alert:1396429026842644584> No members found matching the criteria!",
            "warning",
            ctx.author
        )
        await ctx.send(embed=embed)
        return
        
    # Show confirmation with member count
    embed = self.create_embed(
        "Confirmation Required",
        f"⚠️ Are you sure you want to **{operation}** {role.mention} {'to' if operation == 'add' else 'from'} **{len(target_members)}** member(s)?\n\n**This action will affect a large number of users!**",
        "warning",
        ctx.author
    )
    
    view = ConfirmationView(ctx.author, timeout=30)
    message = await ctx.send(embed=embed, view=view)
    
    await view.wait()
    if not view.value:
        embed = self.create_embed(
            "Operation Cancelled",
            "<a:alert:1396429026842644584> Bulk role operation cancelled.",
            "info",
            ctx.author
        )
        await message.edit(embed=embed, view=None)
        return
        
    # Show progress message
    progress_embed = self.create_embed(
        f"Processing {operation.title()} Operation",
        f"⏳ {operation.title()}ing {role.mention} {'to' if operation == 'add' else 'from'} {len(target_members)} members...\n\n**Please wait, this may take a while.**",
        "info",
        ctx.author
    )
    await message.edit(embed=progress_embed, view=None)
    
    success_count = 0
    failed_count = 0
    
    # Process members with rate limiting
    for i, member in enumerate(target_members):
        try:
            if operation == "add" and role not in member.roles:
                await member.add_roles(role, reason=reason)
                success_count += 1
            elif operation == "remove" and role in member.roles:
                await member.remove_roles(role, reason=reason)
                success_count += 1
                
            # Update progress every 10 members
            if (i + 1) % 10 == 0:
                progress_embed.description = f"⏳ Processed **{i + 1}**/{len(target_members)} members...\n\n**Progress: {((i + 1) / len(target_members)) * 100:.1f}%**"
                await message.edit(embed=progress_embed)
                await asyncio.sleep(0.5)  # Rate limiting
                
        except Exception as e:
            failed_count += 1
            print(f"Failed to {operation} role for {member}: {e}")
            
    # Final result
    embed = self.create_embed(
        f"Bulk {operation.title()} Complete",
        f"<:yes:1396838746862784582> Successfully **{operation}ed** {role.mention} {'to' if operation == 'add' else 'from'} **{success_count}** member(s)!",
        "success" if failed_count == 0 else "warning",
        ctx.author,
        role,
        success_count
    )
    
    if failed_count > 0:
        embed.add_field(
            name="⚠️ Errors",
            value=f"**{failed_count}** operation(s) failed due to permissions or other issues.",
            inline=False
        )
        
    await message.edit(embed=embed)

  @role.command(name="humans", help="Gives role to all humans in the guild")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 15, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  @commands.has_permissions(administrator=True)
  async def role_humans(self, ctx, *, role: discord.Role):
    """Add a role to all human members (non-bots)"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if not member.bot and role not in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "add", 
        f"Role humans command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  @role.command(name="bots", help="Gives role to all the bots in the guild")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  @commands.has_permissions(administrator=True)
  async def role_bots(self, ctx, *, role: discord.Role):
    """Add a role to all bot members"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if member.bot and role not in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "add",
        f"Role bots command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  @role.command(name="unverified", help="Gives role to all the unverified members in the guild")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  @commands.has_permissions(administrator=True)
  async def role_unverified(self, ctx, *, role: discord.Role):
    """Add a role to all unverified members"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if member.avatar is None and role not in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "add",
        f"Role unverified command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  @role.command(name="all", help="Gives role to all the members in the guild")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 15, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  @commands.has_permissions(administrator=True)
  async def role_all(self, ctx, *, role: discord.Role):
    """Add a role to all members in the server"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if role not in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "add",
        f"Role all command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  # REMOVE ROLE COMMAND GROUP

  @commands.hybrid_group(name="removerole", invoke_without_command=True,
                 aliases=['rrole'], help="Remove a role from all members")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
  @commands.guild_only()
  @commands.has_permissions(administrator=True)
  async def rrole(self, ctx):
    """Remove role command group"""
    if ctx.subcommand_passed is None:
      await ctx.send_help(ctx.command)
      ctx.command.reset_cooldown(ctx)

  @rrole.command(name="humans", help="Removes a role from all the humans in the server.")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.has_permissions(administrator=True)
  async def rrole_humans(self, ctx, *, role: discord.Role):
    """Remove a role from all human members"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if not member.bot and role in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "remove",
        f"Remove role humans command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  @rrole.command(name="bots", help="Removes a role from all the bots in the server.")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.has_permissions(administrator=True)
  async def rrole_bots(self, ctx, *, role: discord.Role):
    """Remove a role from all bot members"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if member.bot and role in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "remove",
        f"Remove role bots command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  @rrole.command(name="all", help="Removes a role from all members in the server.")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.has_permissions(administrator=True)
  async def rrole_all(self, ctx, *, role: discord.Role):
    """Remove a role from all members"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if role in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "remove",
        f"Remove role all command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  @rrole.command(name="unverified", help="Removes a role from all the unverified members in the server.")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  @commands.has_permissions(administrator=True)
  async def rrole_unverified(self, ctx, *, role: discord.Role):
    """Remove a role from all unverified members"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    target_members = [member for member in ctx.guild.members if member.avatar is None and role in member.roles]
    await self.bulk_role_operation(
        ctx, role, target_members, "remove",
        f"Remove role unverified command executed by {ctx.author} (ID: {ctx.author.id})"
    )

  # ADDITIONAL UTILITY COMMANDS

  @commands.hybrid_command(name="rolelist", aliases=["roles"])
  @blacklist_check()  
  @ignore_check()
  @commands.cooldown(1, 10, commands.BucketType.user)
  async def rolelist(self, ctx):
    """Display all roles in the server with member counts"""
    
    roles = [role for role in ctx.guild.roles if role != ctx.guild.default_role]
    roles.sort(key=lambda r: r.position, reverse=True)
    
    if not roles:
        embed = self.create_embed(
            "No Roles Found",
            "<a:alert:1396429026842644584> This server has no custom roles!",
            "info",
            ctx.author
        )
        await ctx.send(embed=embed)
        return
        
    # Paginate roles (15 per page)
    page_size = 15
    pages = [roles[i:i + page_size] for i in range(0, len(roles), page_size)]
    
    embed = self.create_embed(
        f"Server Roles ({len(roles)} total)",
        f"Showing roles for **{ctx.guild.name}**",
        "info",
        ctx.author
    )
    
    # Show first page
    role_list = []
    for i, role in enumerate(pages[0], 1):
        member_count = len(role.members)
        role_list.append(f"`{role.position:02d}.` {role.mention} - **{member_count}** member{'s' if member_count != 1 else ''}")
        
    embed.add_field(
        name="📋 Role List",
        value="\n".join(role_list),
        inline=False
    )
    
    if len(pages) > 1:
        embed.set_footer(text=f"Page 1 of {len(pages)} • Use reactions to navigate")
        
    await ctx.send(embed=embed)

  @commands.hybrid_command(name="rolecolor", help="Change the color of a role")
  @blacklist_check()
  @ignore_check()
  @commands.cooldown(1, 5, commands.BucketType.user)
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  async def rolecolor(self, ctx, role: discord.Role, color: str):
    """Change the color of a role"""
    
    if not await self.check_role_permissions(ctx, role):
        return
        
    try:
        # Convert color string to discord.Color
        if color.startswith('#'):
            color = color[1:]
        color_value = int(color, 16)
        new_color = discord.Color(color_value)
        
        old_color = role.color
        await role.edit(color=new_color, reason=f"Color changed by {ctx.author}")
        
        embed = self.create_embed(
            "Role Color Changed",
            f"<:yes:1396838746862784582> Successfully changed {role.mention} color from `{old_color}` to `{new_color}`",
            "success",
            ctx.author
        )
        embed.color = new_color
        await ctx.send(embed=embed)
        
    except ValueError:
        embed = self.create_embed(
            "Invalid Color",
            "<a:alert:1396429026842644584> Invalid color format! Use hex format like `#FF0000` or `FF0000`",
            "error",
            ctx.author
        )
        await ctx.send(embed=embed)


class ConfirmationView(discord.ui.View):
    """Enhanced confirmation view with professional styling"""
    
    def __init__(self, user: discord.Member, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.user = user
        self.value = None
        
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This confirmation is not for you!", ephemeral=True)
            return
            
        self.value = True
        self.stop()
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This confirmation is not for you!", ephemeral=True)
            return
            
        self.value = False
        self.stop()


async def setup(bot):
    await bot.add_cog(Role(bot))
