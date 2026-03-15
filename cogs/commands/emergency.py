import discord
from discord.ext import commands
import motor.motor_asyncio
from utils.Tools import *
import os
import datetime
import aiosqlite # Kept for Anti-Nuke DB interaction only

class EmergencyRestoreView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Only the Server Owner can use this button.", ephemeral=True)
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Only the Server Owner can use this button.", ephemeral=True)
        self.value = False
        await interaction.response.defer()
        self.stop()



class Emergency(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_default_database()
        
        # Collections
        self.auth_collection = self.db.emergency_auth
        self.roles_collection = self.db.emergency_roles
        self.restore_collection = self.db.emergency_restore
        # positions_collection is not actively used in logic but defined in schema, skipping for now as unused.

        self.bot.loop.create_task(self.create_indexes())

    async def create_indexes(self):
        await self.auth_collection.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
        await self.roles_collection.create_index([("guild_id", 1), ("role_id", 1)], unique=True)
        await self.restore_collection.create_index([("guild_id", 1), ("role_id", 1)], unique=True)

    async def is_guild_owner(self, ctx):
        return ctx.guild and ctx.author.id == ctx.guild.owner_id

    async def is_guild_owner_or_authorised(self, ctx):
        if await self.is_guild_owner(ctx):
            return True
        doc = await self.auth_collection.find_one({"guild_id": ctx.guild.id, "user_id": ctx.author.id})
        return doc is not None

    @commands.group(name="emergency", aliases=["emg"], help="Lists all the commands in the emergency group.", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def emergency(self, ctx):
        embed = discord.Embed(
            title="__Emergency Situation__",
            description="The `emergency` command group is designed to protect your server from malicious activity or accidental damage. It allows server owners and authorized users to disable dangerous permissions from roles by executing `emergencysituation` or `emgs` command and prevent potential risks.\n\n__**The command group has several subcommands**__:",
            color=0x2b2d31
        )
        embed.add_field(name=f"`{ctx.prefix}emergency enable`", value="> Enable emergency mode, it adds all roles with dangerous permissions in the emergency role list.", inline=False)
        embed.add_field(name=f"`{ctx.prefix}emergency disable`", value="> Disable emergency mode and clear the emergency role list.", inline=False)
        embed.add_field(name=f"`{ctx.prefix}emergency authorise`", value="> Manage authorized users for executing `emergencysituation` command.", inline=False)
        embed.add_field(name=f"`{ctx.prefix}emergency role`", value="> Manage roles added to the emergency list. You can add/remove/list roles by emergency role group.", inline=False)
        embed.add_field(name=f"`{ctx.prefix}emergency-situation` or `{ctx.prefix}emgs`", value="> Execute emergency situation which disables dangerous permissions from roles in the emergency list & move the role with maximum member to top position below the bot top role. Restore disabled permissions of role using `emgrestore`.", inline=False)
        embed.set_footer(text="Use \"help emergency <subcommand>\" for more information.", icon_url=self.bot.user.avatar.url)
        await ctx.reply(embed=embed)


    @emergency.command(name="enable", help="Enable emergency mode and add all roles with dangerous permissions.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def enable(self, ctx):
        Scyro = ['1005088956951564358', '1005088956951564358']
        if ctx.author.id != ctx.guild.owner_id and str(ctx.author.id) not in Scyro:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="Only the server owner can enable emergency mode.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        dangerous_permissions = ["administrator", "ban_members", "kick_members", "manage_channels", "manage_roles", "manage_guild"]
        roles_added = []
        
        # Batch DB operations could be better but let's stick to loop for simpler porting logic first
        # We can optimize to one inserts later if needed, but logic is "find if exists, then insert"
        # Mongo upsert is good here.
        
        for role in ctx.guild.roles:
            if role.managed or role.is_bot_managed():
                continue

            if role.position >= ctx.guild.me.top_role.position:
                continue
            
            if any(getattr(role.permissions, perm, False) for perm in dangerous_permissions):
                # Check if role exists
                existing = await self.roles_collection.find_one({"guild_id": ctx.guild.id, "role_id": role.id})
                if not existing:
                    await self.roles_collection.insert_one({"guild_id": ctx.guild.id, "role_id": role.id})
                    roles_added.append(role)

        if roles_added:
            description = "\n".join([f"{role.mention}" for role in roles_added])
            embed = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"The following roles with dangerous permissions have been added to the **emergency list**:\n{description}", color=0x2b2d31)
            embed.set_footer(text="Roles having greater or equal position than my top role is not added in the emergency list.", icon_url=self.bot.user.display_avatar.url)
        else:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="No new roles with dangerous permissions were found.", color=0x2b2d31)
        
        await ctx.reply(embed=embed)
        

    @emergency.command(name="disable", help="Disable emergency mode and clear the emergency role list.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def disable(self, ctx):
        Scyro = ['1005088956951564358', '1005088956951564358']
        if ctx.author.id != ctx.guild.owner_id and str(ctx.author.id) not in Scyro:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="Only the server owner can disable emergency mode.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        await self.roles_collection.delete_many({"guild_id": ctx.guild.id})

        embed = discord.Embed(title="<:yes:1396838746862784582> Success", description="Emergency mode has been disabled, and all emergency roles have been cleared.", color=0x2b2d31)
        await ctx.reply(embed=embed)


    @emergency.group(name="authorise", aliases=["ath"], help="Lists all the commands in the emergency authorise group.", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def authorise(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @authorise.command(name="add", help="Adds a user to the authorised group.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def authorise_add(self, ctx, member: discord.Member):
        if not await self.is_guild_owner(ctx):
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="Only the server owner can add authorised users for executing emergency situation.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        count = await self.auth_collection.count_documents({"guild_id": ctx.guild.id})
        if count >= 5:
            embed = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description="Only up to 5 authorised users can be added.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        existing = await self.auth_collection.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        if existing:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="This user is already authorised.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        await self.auth_collection.insert_one({"guild_id": ctx.guild.id, "user_id": member.id})

        embed = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"**{member.display_name}** has been authorised to use `emergency-situation` command.", color=0x2b2d31)
        await ctx.reply(embed=embed)

    @authorise.command(name="remove", help="Removes a user from the authorised group")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def authorise_remove(self, ctx, member: discord.Member):
        if not await self.is_guild_owner(ctx):
            embed = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description="Only the server owner can remove authorised users for emergency situation.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        result = await self.auth_collection.delete_one({"guild_id": ctx.guild.id, "user_id": member.id})
        if result.deleted_count == 0:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="This user is not authorised.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        embed = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"**{member.display_name}** has been removed from the authorised list and can no more use `emergency-situation` command.", color=0x2b2d31)
        await ctx.reply(embed=embed)

    @authorise.command(name="list", aliases=["view", "config"], help="Lists all authorised users for emergency actions.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def list_authorized(self, ctx):
        if not await self.is_guild_owner(ctx):
            embed = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description="Only the server owner can view the list of authorised users for emergency situation.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        cursor = self.auth_collection.find({"guild_id": ctx.guild.id})
        authorized_users = await cursor.to_list(length=None)
            
        if not authorized_users:
            await ctx.reply(embed=discord.Embed(
                title="Authorized Users",
                description="No authorized users found.",
                color=0x2b2d31))
            return
                
        description = "\n".join([f"{index + 1}. [{ctx.guild.get_member(user['user_id']).name if ctx.guild.get_member(user['user_id']) else 'Unknown'}](https://discord.com/users/{user['user_id']}) - {user['user_id']}" for index, user in enumerate(authorized_users)])
        await ctx.reply(embed=discord.Embed(
            title="Authorized Users",
            description=description,
            color=0x2b2d31))

    @emergency.group(name="role", help="Lists all the commands in the emergency role group.", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def role(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @role.command(name="add", help="Adds a role to the emergency role list")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def role_add(self, ctx, role: discord.Role):
        if not await self.is_guild_owner(ctx):
            embed = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description="Only the server owner can add role for emergency situation.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        count = await self.roles_collection.count_documents({"guild_id": ctx.guild.id})
        if count >= 25:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="Only up to 25 roles can be added.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        existing = await self.roles_collection.find_one({"guild_id": ctx.guild.id, "role_id": role.id})
        if existing:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="This role is already in the emergency list.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        await self.roles_collection.insert_one({"guild_id": ctx.guild.id, "role_id": role.id})

        embed = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"**{role.name}** has been **added** to the emergency list.", color=0x2b2d31)
        await ctx.reply(embed=embed)

    @role.command(name="remove", help="Removes a role from the emergency role list.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def role_remove(self, ctx, role: discord.Role):
        if not await self.is_guild_owner(ctx):
            embed = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description="Only the server owner can remove roles from emergency list.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        result = await self.roles_collection.delete_one({"guild_id": ctx.guild.id, "role_id": role.id})
        if result.deleted_count == 0:
            embed = discord.Embed(title="<:no:1396838761605890090> Error", description="This role is not in the emergency list.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        embed = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"**{role.name}** has been removed from the emergency list.", color=0x2b2d31)
        await ctx.reply(embed=embed)

    @role.command(name="list", aliases=["view", "config"], help="Lists all roles added to the emergency list.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def list_roles(self, ctx):
        if not await self.is_guild_owner_or_authorised(ctx):
            embed = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description="You are not authorised to view list of roles for emergency situation.", color=0x2b2d31)
            return await ctx.reply(embed=embed)

        cursor = self.roles_collection.find({"guild_id": ctx.guild.id})
        roles = await cursor.to_list(length=None)

        if not roles:
            await ctx.reply(embed=discord.Embed(
                title="Emergency Roles",
                description="No roles added for emergency situation.",
                color=0x2b2d31))
            return

        description = "\n".join([f"{index + 1}. <@&{role['role_id']}> - {role['role_id']}" for index, role in enumerate(roles)])

        await ctx.reply(embed=discord.Embed(
            title="Emergency Roles",
            description=description,
            color=0x2b2d31))


    @commands.command(name="emergencysituation", help="Disable dangerous permissions from roles in the emergency list.", aliases=["semgs", "emergency-situation", "emgs"])
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 40, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def emergencysituation(self, ctx):
        Scyro = ['1005088956951564358', '1005088956951564358']
        guild_id = ctx.guild.id

        if not await self.is_guild_owner_or_authorised(ctx) and str(ctx.author.id) not in Scyro:
            return await ctx.reply(embed=discord.Embed(
                title="<a:alert:1396429026842644584> Access Denied", 
                description="You are not authorised to execute the emergency situation.", 
                color=0x2b2d31))

        processing_message = await ctx.send(embed=discord.Embed(title="<a:4428ghosticonload:1409448581911416904> Processing Emergency Situation, wait for a while...", color=0x2b2d31))

        # Anti-Nuke logic kept in SQLite for compatibility
        antinuke_enabled = False
        try:
            async with aiosqlite.connect('db/anti.db') as anti:
                async with anti.execute("SELECT status FROM antinuke WHERE guild_id = ?", (guild_id,)) as cursor:
                    antinuke_status = await cursor.fetchone()
                if antinuke_status:
                    antinuke_enabled = True
                    await anti.execute('DELETE FROM antinuke WHERE guild_id = ?', (guild_id,))
                    await anti.commit()
        except Exception:
            # If anti_db doesn't exist or error, assume no anti-nuke or ignore
            pass
                
        # Clear restore data for this guild to start fresh
        await self.restore_collection.delete_many({"guild_id": ctx.guild.id})

        cursor = self.roles_collection.find({"guild_id": ctx.guild.id})
        emergency_roles = await cursor.to_list(length=None)

        if not emergency_roles:
            await processing_message.delete()
            return await ctx.reply(embed=discord.Embed(
                title="<:no:1396838761605890090> Error",
                description="No roles have been added for the emergency situation.",
                color=0x2b2d31))

        bot_highest_role = ctx.guild.me.top_role
        dangerous_permissions = [
            "administrator", "ban_members", "kick_members", 
            "manage_channels", "manage_roles", "manage_guild"
        ]

        modified_roles = []
        unchanged_roles = []

        for role_data in emergency_roles:
            role = ctx.guild.get_role(role_data['role_id'])

            if not role:
                continue

            if role.position >= bot_highest_role.position or role.managed:
                unchanged_roles.append(role)
                continue

            permissions_changed = False
            role_permissions = role.permissions
            disabled_perms = []

            for perm in dangerous_permissions:
                if getattr(role_permissions, perm, False):
                    setattr(role_permissions, perm, False)
                    permissions_changed = True
                    disabled_perms.append(perm)

            if permissions_changed:
                try:
                    await role.edit(permissions=role_permissions, reason="Emergency Situation: Disabled dangerous permissions")
                    modified_roles.append(role)

                    await self.restore_collection.insert_one({
                        "guild_id": ctx.guild.id,
                        "role_id": role.id,
                        "disabled_perms": disabled_perms # Store as list
                    })

                except discord.Forbidden:
                    unchanged_roles.append(role)

        if modified_roles:
            success_message = "\n".join([f"{role.mention}" for role in modified_roles])
        else:
            success_message = "No roles were modified."

        if unchanged_roles:
            error_message = "\n".join([f"{role.mention}" for role in unchanged_roles])
        else:
            error_message = "No roles had permission errors."

        most_mem = max(
            [role for role in ctx.guild.roles if not role.managed and role.position < bot_highest_role.position and role != ctx.guild.default_role],
            key=lambda role: len(role.members),
            default=None
        )

        if most_mem:
            target_position = bot_highest_role.position - 1 
            try:
                await most_mem.edit(position=target_position, reason="Emergency Situation: Role moved for safety")
                await ctx.reply(embed=discord.Embed(
                    title="Emergency Situation",
                    description=f"**<:yes:1396838746862784582> Roles Modified (Denied Dangerous Permissions)**:\n{success_message}\n\n**⚠️ Role Moved**: {most_mem.mention} moved to a position below the bot's highest role.\n**Move back to its previous position soon after the server is not in risk.**\n\n**<:no:1396838761605890090> Errors**:\n{error_message}",
                    color=0x2b2d31))
            except discord.Forbidden:
                await ctx.reply(embed=discord.Embed(
                    title="Emergency Situation",
                    description=f"**<:yes:1396838746862784582> Roles Modified (Denied Dangerous Permissions)**:\n{success_message}\n\n**ℹ️ Role Couldn't Moved**: Failed to move the role {most_mem.mention} below the bot's highest role due to permissions error.\n**Move back to its previous position soon after the server is not in risk.**\n\n**<:no:1396838761605890090> Errors**:\n{error_message}",
                    color=0x2b2d31))

            except Exception as e:
                await ctx.reply(embed=discord.Embed(
                    title="Emergency Situation",
                    description=f"**<:yes:1396838746862784582> Roles Modified (Denied Dangerous Permissions)**:\n{success_message}\n\n**ℹ️ Role Couldn't Moved**: An unexpected error occurred while moving the role: {str(e)}.\n**Move back to its previous position soon after the server is not in risk.**\n\n**<:no:1396838761605890090> Errors**:\n{error_message}",
                    color=0x2b2d31)) 
        else:
            await ctx.reply(embed=discord.Embed(
                title="Emergency Situation",
                description=f"**<:yes:1396838746862784582> Roles Modified (Denied Dangerous Permissions)**:\n{success_message}\n\n**<:no:1396838761605890090> Errors**:\n{error_message}",
                color=0x2b2d31))

        if antinuke_enabled:
            # Restore anti-nuke status
            try:
                async with aiosqlite.connect('db/anti.db') as anti:
                    await anti.execute("INSERT INTO antinuke (guild_id, status) VALUES (?, 1)", (guild_id,))
                    await anti.commit()
            except Exception:
                pass

        await processing_message.delete()


    
    @commands.command(name="emergencyrestore", aliases=["...", "emgrestore", "emgsrestore", "emgbackup"], help="Restore disabled permissions to roles.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def emergencyrestore(self, ctx):
        Scyro = ['1005088956951564358', '1005088956951564358']
        if ctx.author.id != ctx.guild.owner_id and str(ctx.author.id) not in Scyro:
            return await ctx.reply(embed=discord.Embed(
                title="<a:alert:1396429026842644584> Access Denied", 
                description="Only the server owner can execute the emergency restore command.", 
                color=0x2b2d31))

        cursor = self.restore_collection.find({"guild_id": ctx.guild.id})
        restore_roles = await cursor.to_list(length=None)

        if not restore_roles:
            return await ctx.reply(embed=discord.Embed(
                title="<:no:1396838761605890090> Error",
                description="No roles were found with disabled permissions for restore.",
                color=0x2b2d31))

        confirmation_embed = discord.Embed(
            title="Confirm Restoration",
            description="This will restore previously disabled permissions for emergency roles. Do you want to proceed?",
            color=0x2b2d31
        )
        view = EmergencyRestoreView(ctx)
        await ctx.send(embed=confirmation_embed, view=view)

        await view.wait()

        if view.value is None:
            return await ctx.reply(embed=discord.Embed(
                title="Restore Cancelled",
                description="The restore process timed out.",
                color=0x2b2d31))

        if view.value is False:
            return await ctx.reply(embed=discord.Embed(
                title="Restore Cancelled",
                description="Restoring permissions to roles has been cancelled.",
                color=0x2b2d31))

        modified_roles = []
        unchanged_roles = []

        for role_data in restore_roles:
            role_id = role_data['role_id']
            disabled_perms = role_data['disabled_perms'] # List
            
            role = ctx.guild.get_role(role_id)

            if not role:
                continue

            role_permissions = role.permissions
            permissions_restored = False

            for perm in disabled_perms:
                if hasattr(role_permissions, perm):
                    setattr(role_permissions, perm, True)
                    permissions_restored = True

            if permissions_restored:
                try:
                    await role.edit(permissions=role_permissions, reason="Emergency Restore: Restored permissions")
                    modified_roles.append(role)
                except discord.Forbidden:
                    unchanged_roles.append(role)

        await self.restore_collection.delete_many({"guild_id": ctx.guild.id})

        if modified_roles:
            success_message = "\n".join([f"{role.mention}" for role in modified_roles])
        else:
            success_message = "No roles were restored."

        if unchanged_roles:
            error_message = "\n".join([f"{role.mention}" for role in unchanged_roles])
        else:
            error_message = "No roles had permission errors."

        await ctx.reply(embed=discord.Embed(
            title="Emergency Restore",
            description=f"**<:yes:1396838746862784582> Permissions Restored**:\n{success_message}\n\n**<:no:1396838761605890090> Errors**:\n{error_message}\n\n<:rightarrow:1397875113138851840> Database of previously disabled permissions has been cleared.",
            color=0x2b2d31))

async def setup(bot):
    await bot.add_cog(Emergency(bot))