import discord
from discord.ext import commands
import motor.motor_asyncio
import sys
import os
from utils.Tools import *
import time

# Database setup
# Not needed for MongoDB uri is env
# db_folder = 'db'
# db_file = 'anti.db'
# db_path = os.path.join(db_folder, db_file)

class Nightmode(commands.Cog):
    """<:ogstar:1420709631663013928> Premium-only Night Mode Protection System
    
    Night Mode provides advanced server protection by:
    - Temporarily disabling dangerous permissions (like Administrator) 
    - Preserving original role settings for seamless restoration
    - Protecting against role-based security breaches
    - Maintaining server security during vulnerable periods

    <:premium:1409162823862325248> Premium Feature - Requires active premium subscription\n Purchase it from [here](https://dsc.gg/scyrogg)!
    """

    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.coll = None
        self.extraowners = None
        self.bot.loop.create_task(self.initialize_db())
        self.ricky = [1218037361926209640, 1218037361926209640, 1218037361926209640]  # This can stay as is since it's used for other purposes
        self.color = 0x2b2d31  
    
    async def premium_check(self, ctx):
        """Check if user has premium access for this guild"""
        # Bot owner bypasses premium checks
        if ctx.author.id in self.ricky: # simplified to use self.ricky or main.BOT_OWNERS if imported
            return True
        
        # Try to get the premium cog
        premium_cog = self.bot.get_cog('Premium')
        if not premium_cog:
            # If premium cog not loaded, allow access for now or deny? 
            # Original code allowed access if cog missing? 
            # "If premium cog not loaded, allow access for now" -> okay respecting original logic
            return True
        
        # Check premium access
        try:
            has_premium, tier = await premium_cog.premium_system.check_user_premium(ctx.author.id, ctx.guild.id)
            return has_premium
        except:
            # If error checking premium, deny access
            return False

    async def initialize_db(self):
        if not self.mongo_uri: return
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client.get_database()
        self.coll = self.db.nightmode_active
        self.extraowners = self.db.extraowners
        
        await self.coll.create_index([("guild_id", 1), ("role_id", 1)], unique=True)

    async def is_extra_owner(self, user, guild):
        if not self.extraowners: return False
        doc = await self.extraowners.find_one({"guild_id": guild.id, "owner_id": user.id})
        return doc is not None

    @commands.hybrid_group(name="nightmode", aliases=[], help="Manages Nightmode feature", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    async def nightmode(self, ctx):
        nightmode_embed = discord.Embed(
            title='__**🌟 Premium Night Mode**__',
            color=self.color,
            description=(
                '🌙 **Night Mode** swiftly disables dangerous permissions for roles, like stripping `ADMINISTRATION` rights, while preserving original settings for seamless restoration.\n\n'
                '**🛡️ Security Features:**\n'
                '• Temporarily removes Administrator permissions\n'
                '• Preserves original role configurations\n'
                '• Seamless permission restoration\n'
                '• Protection against privilege escalation\n\n'
                '**⚠️ Important:** Make sure to keep my ROLE above all roles you want to protect.\n\n'
                '<:ogstar:1420709631663013928> **Premium Feature** - Requires active premium subscription'
            )
        )
        nightmode_embed.add_field(
            name="🔧 Usage Commands",
            value="<a:dot:1396429135588626442> `nightmode enable` - Activate protection\n<a:dot:1396429135588626442> `nightmode disable` - Restore permissions",
            inline=False
        )
        nightmode_embed.add_field(
            name="<:ogstar:1420709631663013928> Premium Access",
            value="This feature requires an active premium subscription.\nContact bot owner for premium access!",
            inline=False
        )
        nightmode_embed.set_thumbnail(url=self.bot.user.avatar.url)
        await ctx.send(embed=nightmode_embed)

    @nightmode.command(name="enable", help="Enable nightmode protection (Premium)")
    @commands.has_permissions(administrator=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def enable_nightmode(self, ctx):
        if ctx.guild.member_count < 50:  
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=self.color,
                description='Your Server Doesn\'t Meet My 50 Member Criteria'
            ))

        own = ctx.author.id == ctx.guild.owner_id
        check = await self.is_extra_owner(ctx.author, ctx.guild)
        if not own and not check and ctx.author.id not in self.ricky:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=self.color,
                description='Only Server Owner Or Extraowner Can Run This Command.!'
            ))

        if not own and not (
            ctx.guild.me.top_role.position <= ctx.author.top_role.position
        ) and ctx.author.id not in self.ricky:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=self.color,
                description='Only Server Owner or Extraowner Having **Higher role than me can run this command**'
            ))

        bot_highest_role = ctx.guild.me.top_role
        manageable_roles = [
            role for role in ctx.guild.roles
            if role.position < bot_highest_role.position 
            and role.name != '@everyone' 
            and role.permissions.administrator
            and not role.managed  
        ]

        if not manageable_roles:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090>  Error",
                color=self.color,
                description='No Roles Found With Admin Permissions'
            ))

        existing = await self.coll.find_one({"guild_id": ctx.guild.id})
        if existing:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090>  Error",
                color=self.color,
                description='Nightmode is already enabled.'
            ))

        count_enabled = 0
        for role in manageable_roles:
            admin_permissions = discord.Permissions(administrator=True)
            if role.permissions.administrator: # Double check
                try:
                    permissions = role.permissions
                    permissions.administrator = False

                    await role.edit(permissions=permissions, reason='Nightmode ENABLED')

                    await self.coll.update_one(
                        {"guild_id": ctx.guild.id, "role_id": role.id},
                        {"$set": {"original_admin": True}},
                        upsert=True
                    )
                    count_enabled += 1
                except Exception as e:
                    print(f"Failed to edit role {role.name}: {e}")

        if count_enabled > 0:
            await ctx.send(embed=discord.Embed(title="<:yes:1396838746862784582> Success",
                color=self.color,
                description=f'Nightmode enabled! Dangerous Permissions Disabled For {count_enabled} Roles.'
            ))
        else:
            await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Error",
                color=self.color,
                description='Could not disable permissions for any roles. Check my hierarchy.'
            ))

    @nightmode.command(name="disable", help="Disable nightmode protection (Premium)")
    @commands.has_permissions(administrator=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def disable_nightmode(self, ctx):
        if ctx.guild.member_count < 50:  
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=self.color,
                description='Your Server Doesn\'t Meet My 50 Member Criteria'
            ))

        own = ctx.author.id == ctx.guild.owner_id
        check = await self.is_extra_owner(ctx.author, ctx.guild)
        if not own and not check and ctx.author.id not in self.ricky:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=self.color,
                description='Only Server Owner Or Extraowner Can Run This Command.!'
            ))

        if not own and not (
            ctx.guild.me.top_role.position <= ctx.author.top_role.position
        ) and ctx.author.id not in self.ricky:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Access Denied",
                color=self.color,
                description='Only Server Owner or Extraowner Having **Higher role than me can run this command**'
            ))

        cursor = self.coll.find({"guild_id": ctx.guild.id})
        stored_roles = await cursor.to_list(length=None)

        if not stored_roles:
            return await ctx.send(embed=discord.Embed(title="<:no:1396838761605890090> Error",
                color=self.color,
                description='Nightmode is not enabled.'
            ))

        count_restored = 0
        for doc in stored_roles:
            role_id = doc['role_id']
            # original_admin = doc.get('original_admin', False) 
            # Logic: If it's in DB, we stripped it, so we restore it.
            
            role = ctx.guild.get_role(role_id)
            if role:
                try:
                    permissions = role.permissions
                    permissions.administrator = True # Restore admin
                    await role.edit(permissions=permissions, reason='Nightmode DISABLED')
                    count_restored += 1
                except Exception as e:
                     print(f"Failed to restore role {role.name}: {e}")
            
            await self.coll.delete_one({"_id": doc["_id"]})

        await ctx.send(embed=discord.Embed(title="<:yes:1396838746862784582> Success",
            color=self.color,
            description=f'Nightmode disabled! Restored Permissions For {count_restored} Roles.'
        ))

async def setup(bot):
    await bot.add_cog(Nightmode(bot))

 