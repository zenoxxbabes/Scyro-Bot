import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
import motor.motor_asyncio
import asyncio
from utils.Tools import *
from typing import List, Tuple
import os

class Customrole(commands.Cog):
    """<:ogstar:1420709631663013928> Premium-only Custom Role Management System
    
    This cog provides advanced role management features including:
    - Predefined role types (staff, girl, vip, guest, friend)
    - Custom role commands with dynamic creation
    - Role assignment/removal with toggle functionality
    - Advanced permission management
    
    <:premium:1409162823862325248> Premium Feature - Requires active premium subscription\n Purchase it from [here](https://dsc.gg/scyrogg)!
    """

    def __init__(self, bot):
        self.bot = bot
        self.cooldown = {}
        self.rate_limit = {}
        self.rate_limit_timeout = 5
        
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_default_database()
        self.config_collection = self.db.customrole_config
        self.commands_collection = self.db.customrole_commands
        
        self.bot.loop.create_task(self.create_indexes())
    
    async def create_indexes(self):
        await self.config_collection.create_index("guild_id", unique=True)
        await self.commands_collection.create_index([("guild_id", 1), ("name", 1)], unique=True)

    async def premium_check(self, ctx):
        """Check if user has premium access for this guild"""
        # Bot owner bypasses premium checks
        if ctx.author.id in BOT_OWNERS:
            return True
        
        # Try to get the premium cog
        premium_cog = self.bot.get_cog('Premium')
        if not premium_cog:
            # If premium cog not loaded, allow access for now
            return True
        
        # Check premium access
        try:
            has_premium, tier = await premium_cog.premium_system.check_user_premium(ctx.author.id, ctx.guild.id)
            return has_premium
        except:
            # If error checking premium, deny access
            return False
    
    # Premium access is handled by the global check in Premium cog

    def flatten_prefixes(self, prefixes):
        """Flatten nested prefix lists into a single list of strings"""
        if not prefixes:
            return []
        
        flat_list = []
        for prefix in prefixes:
            if isinstance(prefix, list):
                flat_list.extend(self.flatten_prefixes(prefix))
            elif isinstance(prefix, str):
                flat_list.append(prefix)
        return flat_list

    async def reset_rate_limit(self, user_id):
        await asyncio.sleep(self.rate_limit_timeout)
        self.rate_limit.pop(user_id, None)

    async def add_role(self, *, role_id: int, member: discord.Member):
        if member.guild.me.guild_permissions.manage_roles:
            role = discord.Object(id=role_id)
            await member.add_roles(role, reason="Scyro Customrole | Role Added")
        else:
            raise discord.Forbidden("Bot does not have permission to manage roles.")

    async def remove_role(self, *, role_id: int, member: discord.Member):
        if member.guild.me.guild_permissions.manage_roles:
            role = discord.Object(id=role_id)
            await member.remove_roles(role, reason="Scyro Customrole | Role Removed")
        else:
            raise discord.Forbidden("Bot does not have permission to manage roles.")
            
    async def add_role2(self, *, role: int, member: discord.Member):
        if member.guild.me.guild_permissions.manage_roles:
            role = discord.Object(id=int(role))
            await member.add_roles(role, reason="Scyro Customrole | Role Added")

    async def remove_role2(self, *, role: int, member: discord.Member):
        if member.guild.me.guild_permissions.manage_roles:
            role = discord.Object(id=int(role))
            await member.remove_roles(role, reason="Scyro Customrole | Role Removed")

    async def handle_role_command(self, context: Context, member: discord.Member, role_type: str):
        data = await self.config_collection.find_one({"guild_id": context.guild.id})
        
        if data and data.get(role_type) and data.get("reqrole"):
            reqrole_id = data["reqrole"]
            role_id = data[role_type]
            
            reqrole = context.guild.get_role(reqrole_id)
            role = context.guild.get_role(role_id)

            if reqrole:
                if context.author == context.guild.owner or reqrole in context.author.roles:
                    if role:
                        if role not in member.roles:
                            await self.add_role2(role=role_id, member=member)
                            embed = discord.Embed(
                                title="✅ Success",
                                description=f"> 🎯 **Successfully Added** <@&{role.id}> To {member.mention}",
                                color=0x9b59b6
                            )
                        else:
                            await self.remove_role2(role=role_id, member=member)
                            embed = discord.Embed(
                                title="✅ Success",
                                description=f"> 🗑️ **Successfully Removed** <@&{role.id}> From {member.mention}",
                                color=0x9b59b6
                            )
                        await context.reply(embed=embed)
                    else:
                        embed = discord.Embed(
                            title="❌ Error",
                            description=f"> ⚠️ **{role_type.capitalize()} role** is not configured in **{context.guild.name}**\n> 🔧 **Please set it up first**",
                            color=0x9b59b6
                        )
                        await context.reply(embed=embed)
                else:
                    embed = discord.Embed(
                        title="🚫 Access Denied",
                        description=f"> 🔒 **Permission Required:** {reqrole.mention}\n> 💡 **You need this role to run this command**",
                        color=0x9b59b6
                    )
                    await context.reply(embed=embed)
            else:
                embed = discord.Embed(
                    title="🚫 Access Denied",
                    description=f"> ⚠️ **Required role** is not configured in **{context.guild.name}**\n> 🔧 **Use `customrole reqrole` to set it up**",
                    color=0x9b59b6
                )
                await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Configuration Error",
                description=f"> 📋 **Custom roles** are not configured in **{context.guild.name}**\n> 🚀 **Use `customrole` commands to set them up**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    # create_tables replaced by create_indexes

    @commands.hybrid_group(
        name="customrole",
        description="Manage custom roles for the server.",
        help="Manage custom roles for the server."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def customrole(self, context: Context):
        if context.subcommand_passed is None:
            await context.send_help(context.command)
            context.command.reset_cooldown(context)

    async def fetch_role_data(self, guild_id):
        data = await self.config_collection.find_one({"guild_id": guild_id})
        if data:
            # Return tuple to match existing logic: (staff, girl, vip, guest, frnd, reqrole)
            return (
                data.get("staff"),
                data.get("girl"),
                data.get("vip"),
                data.get("guest"),
                data.get("frnd"),
                data.get("reqrole")
            )
        return None

    async def update_role_data(self, guild_id, column, value):
        try:
            await self.config_collection.update_one(
                {"guild_id": guild_id},
                {"$set": {column: value}},
                upsert=True
            )
        except Exception as e:
            print(f"Error updating role data: {e}")
            
    async def fetch_custom_role_data(self, guild_id):
        cursor = self.commands_collection.find({"guild_id": guild_id})
        results = await cursor.to_list(length=None)
        # Return list of tuples to match existing logic: [(name, role_id), ...]
        return [(doc["name"], doc["role_id"]) for doc in results]

    @customrole.command(
        name="staff",
        description="Setup staff role in guild",
        help="Setup staff role in Guild"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role to be added")
    async def staff(self, context: Context, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            await self.update_role_data(context.guild.id, 'staff', role.id)
            embed = discord.Embed(
                title="✅ Staff Role Configured",
                description=f"> 👮‍♂️ **Successfully Added** {role.mention} as **Staff Role**\n\n__**Usage Instructions:**__\n> 🎯 Use `$staff <user>` to **assign** {role.mention}\n> 🔄 Use the same command again to **remove** the role",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="girl",
        description="Setup girl role in the Guild",
        help="Setup girl role in the Guild"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role to be added")
    async def girl(self, context: Context, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            await self.update_role_data(context.guild.id, 'girl', role.id)
            embed = discord.Embed(
                title="✅ Girl Role Configured",
                description=f"> 👩 **Successfully Added** {role.mention} as **Girl Role**\n\n__**Usage Instructions:**__\n> 🎯 Use `$girl <user>` to **assign** {role.mention}\n> 🔄 Use the same command again to **remove** the role",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="vip",
        description="Setups vip role in the Guild",
        help="Setups vip role in the Guild"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role to be added")
    async def vip(self, context: Context, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            await self.update_role_data(context.guild.id, 'vip', role.id)
            embed = discord.Embed(
                title="✅ VIP Role Configured",
                description=f"> 💎 **Successfully Added** {role.mention} as **VIP Role**\n\n__**Usage Instructions:**__\n> 🎯 Use `$vip <user>` to **assign** {role.mention}\n> 🔄 Use the same command again to **remove** the role",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="guest",
        description="Setup guest role in the Guild",
        help="Setup guest role in the Guild"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role to be added")
    async def guest(self, context: Context, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            await self.update_role_data(context.guild.id, 'guest', role.id)
            embed = discord.Embed(
                title="✅ Guest Role Configured",
                description=f"> 🏠 **Successfully Added** {role.mention} as **Guest Role**\n\n__**Usage Instructions:**__\n> 🎯 Use `$guest <user>` to **assign** {role.mention}\n> 🔄 Use the same command again to **remove** the role",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="friend",
        description="Setup friend role in the Guild",
        help="Setup friend role in the Guild"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role to be added")
    async def friend(self, context: Context, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            await self.update_role_data(context.guild.id, 'frnd', role.id)
            embed = discord.Embed(
                title="✅ Friend Role Configured",
                description=f"> 👫 **Successfully Added** {role.mention} as **Friend Role**\n\n__**Usage Instructions:**__\n> 🎯 Use `$friend <user>` to **assign** {role.mention}\n> 🔄 Use the same command again to **remove** the role",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="reqrole",
        description="Setup required role for custom role commands",
        help="Setup required role for custom role commands"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(role="Role to be added")
    async def req_role(self, context: Context, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            await self.update_role_data(context.guild.id, 'reqrole', role.id)
            embed = discord.Embed(
                title="✅ Required Role Configured",
                color=0x9b59b6,
                description=f"> 🔑 **Successfully Set** {role.mention} as **Required Role**\n> 💡 **Members with this role** can use custom role commands in **{context.guild.name}**"
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="config",
        description="Shows the current custom role configuration in the Guild.",
        help="Shows the current custom role configuration in the Guild."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def config(self, context: Context) -> None:
        role_data = await self.fetch_role_data(context.guild.id)
        if role_data:
            embed = discord.Embed(
                title="⚙️ Custom Role Configuration",
                color=0x9b59b6
            )
            
            role_info = [
                ("👮‍♂️ **Staff Role:**", role_data[0]),
                ("👩 **Girl Role:**", role_data[1]),
                ("💎 **VIP Role:**", role_data[2]),
                ("🏠 **Guest Role:**", role_data[3]),
                ("👫 **Friend Role:**", role_data[4]),
                ("🔑 **Required Role:**", role_data[5])
            ]
            
            for emoji_name, role_id in role_info:
                role = context.guild.get_role(role_id) if role_id else None
                value = f"> {role.mention}" if role else "> ❌ **Not Configured**"
                embed.add_field(name=emoji_name, value=value, inline=False)
            
            embed.set_footer(text="💡 Use role commands to assign/remove roles. Use the same command twice to toggle roles.")
            await context.reply(embed=embed)
            
        else:
            embed = discord.Embed(
                title="❌ Configuration Not Found",
                description="> 📋 **No custom role configuration** found in this server\n> 🚀 **Get started** by using `customrole` commands",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="create",
        description="Creates a custom role command.",
        help="Creates a custom role command"
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(name="Command name", role="Role to be assigned")
    async def create(self, context: Context, name: str, role: discord.Role) -> None:
        count = await self.commands_collection.count_documents({"guild_id": context.guild.id})
        if count >= 56:
            embed = discord.Embed(
                title="🚫 Limit Reached",
                description="> ⚠️ **Maximum limit reached:** 56 custom role commands per server\n> 🗑️ **Delete some commands** before creating new ones",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
            return

        name_exists = await self.commands_collection.find_one({"guild_id": context.guild.id, "name": name})
        if name_exists:
            embed = discord.Embed(
                title="❌ Command Already Exists",
                description=f"> 🔄 **Command `{name}` already exists** in this server\n> 🗑️ **Remove it first** before creating a new one with the same name",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
            return

        await self.commands_collection.insert_one({"guild_id": context.guild.id, "name": name, "role_id": role.id})

        embed = discord.Embed(
            title="✅ Custom Command Created",
            description=f"> 🎯 **Successfully Created** custom command: `{name}`\n> 🎭 **Assigns Role:** {role.mention}\n\n__**Usage Instructions:**__\n> 💡 Use `${name} <user>` to **assign/remove** {role.mention}\n> 🔑 **Only works** for users with the required role",
            color=0x9b59b6
        )
        await context.reply(embed=embed)
        
    @customrole.command(
        name="delete", 
        aliases=["remove"],
        description="Deletes a custom role command.",
        help="Deletes a custom role command."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(name="Command name to be deleted")
    async def delete(self, context: Context, name: str) -> None:
        result = await self.commands_collection.delete_one({"guild_id": context.guild.id, "name": name})

        if result.deleted_count == 0:
            embed = discord.Embed(
                title="❌ Command Not Found",
                description=f"> 🔍 **No custom command** named `{name}` found in this server\n> 📝 **Check spelling** or use `customrole list` to see available commands",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
            return

        embed = discord.Embed(
            title="✅ Command Deleted",
            description=f"> 🗑️ **Successfully Deleted** custom command: `{name}`",
            color=0x9b59b6
        )
        await context.reply(embed=embed)
        
    @customrole.command(
        name="edit",
        description="Edit the role assigned to a custom role command.",
        help="Edit the role assigned to a custom role command."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(name="Command name to edit", role="New role to be assigned")
    async def edit(self, context: Context, name: str, role: discord.Role) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            existing_role = await self.commands_collection.find_one({"guild_id": context.guild.id, "name": name})

            if not existing_role:
                embed = discord.Embed(
                    title="❌ Command Not Found",
                    description=f"> 🔍 **No custom command** named `{name}` found in this server\n> 📝 **Check spelling** or use `customrole list` to see available commands",
                    color=0x9b59b6
                )
                await context.reply(embed=embed)
                return

            old_role_id = existing_role["role_id"]
            old_role = context.guild.get_role(old_role_id)
            
            await self.commands_collection.update_one(
                {"guild_id": context.guild.id, "name": name},
                {"$set": {"role_id": role.id}}
            )

            embed = discord.Embed(
                title="✅ Command Updated",
                description=f"> 🔄 **Successfully Edited** command: `{name}`\n> 🎭 **Previous Role:** {old_role.mention if old_role else '`Deleted Role`'}\n> 🎯 **New Role:** {role.mention}\n\n__**Usage Instructions:**__\n> 💡 Use `{name} <user>` to **assign/remove** {role.mention}",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @customrole.command(
        name="rename",
        description="Rename a custom role command.",
        help="Rename a custom role command."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @app_commands.describe(old_name="Current command name", new_name="New command name")
    async def rename(self, context: Context, old_name: str, new_name: str) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            existing_role = await self.commands_collection.find_one({"guild_id": context.guild.id, "name": old_name})

            if not existing_role:
                embed = discord.Embed(
                    title="❌ Command Not Found",
                    description=f"> 🔍 **No custom command** named `{old_name}` found in this server\n> 📝 **Check spelling** or use `customrole list` to see available commands",
                    color=0x9b59b6
                )
                await context.reply(embed=embed)
                return

            # Check if new name already exists
            name_exists = await self.commands_collection.find_one({"guild_id": context.guild.id, "name": new_name})

            if name_exists:
                embed = discord.Embed(
                    title="❌ Name Already Exists",
                    description=f"> 🔄 **Command `{new_name}` already exists** in this server\n> 💡 **Choose a different name** or delete the existing command first",
                    color=0x9b59b6
                )
                await context.reply(embed=embed)
                return

            role_id = existing_role['role_id']
            role = context.guild.get_role(role_id)

            # Update the command name
            await self.commands_collection.update_one(
                {"guild_id": context.guild.id, "name": old_name},
                {"$set": {"name": new_name}}
            )

            embed = discord.Embed(
                title="✅ Command Renamed",
                description=f"> 🔄 **Successfully Renamed** command\n> 📝 **Old Name:** `{old_name}`\n> 🆕 **New Name:** `{new_name}`\n> 🎭 **Assigned Role:** {role.mention if role else '`Deleted Role`'}\n\n__**Usage Instructions:**__\n> 💡 Use `{new_name} <user>` to **assign/remove** the role",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
        
    @customrole.command(
        name="list",
        description="List all the custom roles setup for the server.",
        help="List all the custom roles setup for the server."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def list(self, context: Context) -> None:
        custom_roles = await self.fetch_custom_role_data(context.guild.id)

        if not custom_roles:
            embed = discord.Embed(
                title="❌ No Custom Commands",
                description="> 📝 **No custom role commands** have been created for this server\n> 🚀 **Get started** with `customrole create <name> <role>`",
                color=0x9b59b6
            )
            await context.reply(embed=embed)
            return

        def chunk_list(data: List[Tuple[str, int]], chunk_size: int):
            """Yield successive chunks of `chunk_size` from `data`."""
            for i in range(0, len(data), chunk_size):
                yield data[i:i + chunk_size]

        chunks = list(chunk_list(custom_roles, 7))

        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title="📋 Custom Role Commands",
                color=0x9b59b6
            )
            for name, role_id in chunk:
                role = context.guild.get_role(role_id)
                if role:
                    embed.add_field(
                        name=f"🎯 **Command:** `{name}`", 
                        value=f"> 🎭 **Role:** {role.mention}", 
                        inline=False
                    )

            embed.set_footer(text=f"📄 Page {i+1}/{len(chunks)} | 🔑 These commands require the configured required role to use")
            await context.reply(embed=embed)

    @customrole.command(
        name="reset",
        description="Resets custom role configuration for the server.",
        help="Resets custom role configuration for the server."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def reset(self, context: Context) -> None:
        if context.author == context.guild.owner or context.author.top_role.position > context.guild.me.top_role.position:
            removed_roles = []
            role_data = await self.fetch_role_data(context.guild.id)
            if role_data and any(role_data): # Check if any data exists
                role_names = ["👮‍♂️ **Staff**", "👩 **Girl**", "💎 **VIP**", "🏠 **Guest**", "👫 **Friend**", "🔑 **Required Role**"]
                
                # Fetch role objects for reporting
                for i, role_name in enumerate(role_names):
                    role_id = role_data[i]
                    if role_id:
                        role = context.guild.get_role(role_id)
                        if role:
                            removed_roles.append(f"> {role_name}: {role.mention}")
                
                # Setup collections to clear
                await self.config_collection.delete_one({"guild_id": context.guild.id})
                await self.commands_collection.delete_many({"guild_id": context.guild.id})
                
                embed = discord.Embed(
                    title="🔄 Configuration Reset Complete",
                    description=f"✅ **All custom role commands deleted**\n\n__**Removed Roles:**__\n" + "\n".join(removed_roles) if removed_roles else "> ❌ **No roles were previously configured**",
                    color=0x9b59b6
                )
                await context.reply(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ No Configuration Found", 
                    description="> 📋 **No configuration** found for this server\n> 🚀 **Nothing to reset**", 
                    color=0x9b59b6
                )
                await context.reply(embed=embed)
        else:
            embed = discord.Embed(
                title="🚫 Access Denied",
                description="> 🔒 **Permission Error:** Your role must be above my highest role\n> 👑 **Or you must be the server owner**",
                color=0x9b59b6
            )
            await context.reply(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.content or not message.guild:
            return

        # Get prefixes and flatten them properly
        try:
            prefixes = await self.bot.get_prefix(message)
            if not prefixes:
                return
            
            # Flatten nested prefix lists
            flat_prefixes = self.flatten_prefixes(prefixes)
            if not flat_prefixes:
                return
                
        except Exception as e:
            print(f"Error getting prefixes: {e}")
            return

        # Check if message starts with any prefix
        if not any(message.content.startswith(prefix) for prefix in flat_prefixes):
            return

        # Extract command name
        command_name = None
        used_prefix = None
        for prefix in flat_prefixes:
            if message.content.startswith(prefix):
                remaining = message.content[len(prefix):].strip()
                if remaining:
                    command_name = remaining.split()[0]
                    used_prefix = prefix
                    break
        
        if not command_name:
            return

        guild_id = message.guild.id

        # Check if command exists in custom roles
        result = await self.commands_collection.find_one({"guild_id": guild_id, "name": command_name})

        if result:
            role_id = result["role_id"]
            role = message.guild.get_role(role_id)

            # Get required role
            config_data = await self.config_collection.find_one({"guild_id": guild_id})
            reqrole_id = config_data.get("reqrole") if config_data else None
            reqrole = message.guild.get_role(reqrole_id) if reqrole_id else None

            # Check if required role is set up
            if reqrole is None:
                embed = discord.Embed(
                    title="🚫 Access Denied",
                    description="> ⚠️ **Required role** is not configured in this server\n> 🔧 **Set it up** using `customrole reqrole <role>`",
                    color=0x9b59b6
                )
                await message.channel.send(embed=embed)
                return

            # Check if user has required role (owner bypass)
            if message.author != message.guild.owner and reqrole not in message.author.roles:
                embed = discord.Embed(
                    title="🚫 Access Denied",
                    description=f"> 🔒 **Permission Required:** {reqrole.mention}\n> 💡 **You need this role** to use this command",
                    color=0x9b59b6
                )
                await message.channel.send(embed=embed)
                return

            # Check for mentioned user
            member = message.mentions[0] if message.mentions else None
            if not member:
                embed = discord.Embed(
                    title="❌ Missing User",
                    description=f"> 👤 **Please mention a user** to assign the role to\n> 💡 **Example:** `{command_name} @user`",
                    color=0x9b59b6
                )
                await message.channel.send(embed=embed)
                return

            # Cooldown check
            now = asyncio.get_event_loop().time()
            if guild_id not in self.cooldown or now - self.cooldown[guild_id] >= 5:
                self.cooldown[guild_id] = now
            else:
                embed = discord.Embed(
                    title="⏰ Cooldown Active",
                    description="> ⏳ **Please wait 5 seconds** before using another command\n> 🔄 **Cooldown prevents spam**",
                    color=0x9b59b6
                )
                await message.channel.send(embed=embed, delete_after=5)
                return

            # Check if role exists
            if not role:
                embed = discord.Embed(
                    title="❌ Role Not Found",
                    description="> 🔍 **The configured role** no longer exists in this server\n> 🔧 **Please reconfigure** the custom command",
                    color=0x9b59b6
                )
                await message.channel.send(embed=embed)
                return

            try:
                if role in member.roles:
                    await self.remove_role(role_id=role_id, member=member)
                    embed = discord.Embed(
                        title="✅ Role Removed",
                        description=f"> 🗑️ **Successfully Removed** {role.mention} from {member.mention}",
                        color=0x9b59b6
                    )
                    await message.channel.send(embed=embed)
                else:
                    await self.add_role(role_id=role_id, member=member)
                    embed = discord.Embed(
                        title="✅ Role Added",
                        description=f"> 🎯 **Successfully Added** {role.mention} to {member.mention}",
                        color=0x9b59b6
                    )
                    await message.channel.send(embed=embed)

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Permission Error",
                    description="> 🔒 **I cannot manage this role**\n> 💡 **Check my role hierarchy** and permissions",
                    color=0x9b59b6
                )
                await message.channel.send(embed=embed)
            except Exception as e:
                print(f"Error managing role: {e}")
                embed = discord.Embed(
                    title="❌ Error",
                    description="> ⚠️ **An unexpected error occurred** while managing the role",
                    color=0x9b59b6
                )


    @commands.hybrid_command(
        name="staff",
        description="Gives the staff role to the user.",
        aliases=['official'],
        help="Gives the staff role to the user."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(member="The member to give/remove the staff role")
    async def _staff(self, context: Context, member: discord.Member) -> None:
        await self.handle_role_command(context, member, 'staff')

    @commands.hybrid_command(
        name="girl",
        description="Gives the girl role to the user.",
        aliases=['qt'],
        help="Gives the girl role to the user."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(member="The member to give/remove the girl role")
    async def _girl(self, context: Context, member: discord.Member) -> None:
        await self.handle_role_command(context, member, 'girl')

    @commands.hybrid_command(
        name="vip",
        description="Gives the VIP role to the user.",
        help="Gives the VIP role to the user."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(member="The member to give/remove the VIP role")
    async def _vip(self, context: Context, member: discord.Member) -> None:
        await self.handle_role_command(context, member, 'vip')

    @commands.hybrid_command(
        name="guest",
        description="Gives the guest role to the user.",
        help="Gives the guest role to the user."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(member="The member to give/remove the guest role")
    async def _guest(self, context: Context, member: discord.Member) -> None:
        await self.handle_role_command(context, member, 'guest')

    @commands.hybrid_command(
        name="friend",
        description="Gives the friend role to the user.",
        aliases=['frnd'],
        help="Gives the friend role to the user."
    )
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(member="The member to give/remove the friend role")
    async def _friend(self, context: Context, member: discord.Member) -> None:
        await self.handle_role_command(context, member, 'frnd')


async def setup(bot):
    await bot.add_cog(Customrole(bot))