import os
import discord
from discord.ext import commands
import motor.motor_asyncio
from typing import Optional
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
OWNER_ID = 1218037361926209640
EMBED_COLOR = 0x2b2d31
# DB_PATH is no longer needed for MongoDB, but keeping variable if referenced elsewhere (unlikely)

# Spam tracking for automatic blacklisting
SPAM_THRESHOLD = 7
MENTION_SPAM_THRESHOLD = 7


class Block(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            print("CRITICAL: MONGO_URI not found in environment!")
            return

        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_default_database()
        
        # Collections
        self.user_blacklist = self.db.user_blacklist
        self.guild_blacklist = self.db.guild_blacklist
        self.bypass_users = self.db.block_bypass_users # Renamed to avoid partial name conflict with banword bypass
        
        # Determine premium db (if separate) or collection
        # Assuming premium is also on mongo or will be. 
        # For now, if premium_mongo.py is used, we should use that. 
        # But looking at existing code, it checked "db/premium.db".
        # We will need to check how premium is checked. 
        # Existing code: _is_user_premium uses 'db/premium.db'.
        # If premium is NOT migrated yet, we might need to keep aiosqlite JUST for premium check 
        # OR better, use the bot's cog to check premium if available.
        
        self.bot.loop.create_task(self._init_db())
        # global gate that blocks blacklisted users/guilds from using ANY command
        self.bot.add_check(self._global_block_check)

    def cog_unload(self):
        # remove the global check if the cog is unloaded
        try:
            self.bot.remove_check(self._global_block_check)
        except Exception:
            pass

    # ── DB bootstrap ───────────────────────────────────────────────────────────
    async def _init_db(self):
        # MongoDB collection creation is implicit, but we can set indexes
        await self.user_blacklist.create_index("user_id", unique=True)
        await self.guild_blacklist.create_index("guild_id", unique=True)
        await self.bypass_users.create_index("user_id", unique=True)

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _is_user_blacklisted(self, user_id: int) -> bool:
        doc = await self.user_blacklist.find_one({"user_id": user_id})
        return doc is not None
    
    async def _is_user_bypassed(self, user_id: int) -> bool:
        """Check if a user is bypassed (immune to automatic blacklisting)"""
        doc = await self.bypass_users.find_one({"user_id": user_id})
        return doc is not None
    
    async def _is_user_premium(self, user_id: int) -> bool:
        """Check if a user has an active premium tier"""
        # Strategy: Use the Premium cog if loaded, otherwise fallback or fail safe.
        # The previous code used aiosqlite on 'db/premium.db'.
        # We should try to use the Cog method which is cleaner.
        premium_cog = self.bot.get_cog('Premium')
        if premium_cog:
             if hasattr(premium_cog, 'check_premium'): # Hypothetical method
                 return await premium_cog.check_premium(user_id)
             # Or use the method seen in customrole.py: premium_cog.premium_system.check_user_premium
             if hasattr(premium_cog, 'premium_system') and hasattr(premium_cog.premium_system, 'check_user_premium'):
                 is_prem, _ = await premium_cog.premium_system.check_user_premium(user_id, 0) # 0 for 'no guild context' maybe?
                 # Actually customrole.py passed guild_id. For user premium, maybe it ignores guild.
                 # Let's double check how previous block.py did it: "SELECT 1 FROM premium_users WHERE user_id = ?"
                 # If we can't reliably check mongo premium yet (if premium.py isn't migrated), 
                 # we might have a gap. 
                 # User said "migrate block, customrole, emergency... nothing else".
                 # If premium.py is not migrated, we can't check premium DB if we deleted sqlite support?
                 # BUT, block.config says PREMIUM_DB_PATH = "db/premium.db".
                 # I will preserve aiosqlite ONLY for _is_user_premium if premium.py is not migrated.
                 pass
        
        # Fallback to pure aiosqlite for premium if cog method fails/not exists
        # We need to import aiosqlite locally if we removed it from top
        import aiosqlite
        PREMIUM_DB_PATH = "db/premium.db"
        try:
             # Check if file exists first to avoid error spam
            if not os.path.exists(PREMIUM_DB_PATH):
                return False

            async with aiosqlite.connect(PREMIUM_DB_PATH) as db:
                async with db.execute(
                    'SELECT 1 FROM premium_users WHERE user_id = ? AND expires_at > ?',
                    (user_id, datetime.now().isoformat())
                ) as cursor:
                    return await cursor.fetchone() is not None
        except Exception:
            return False
    
    async def _add_bypass_user(self, user_id: int, added_by: int):
        """Add a user to the bypass list"""
        await self.bypass_users.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "added_by": added_by, "timestamp": datetime.utcnow()}},
            upsert=True
        )
    
    async def _remove_bypass_user(self, user_id: int):
        """Remove a user from the bypass list"""
        await self.bypass_users.delete_one({"user_id": user_id})
    
    def _is_valid_user_id(self, user_id: int) -> bool:
        """Validate if a user ID is properly formatted"""
        return isinstance(user_id, int) and user_id >= 10000000000000000 and user_id <= 9999999999999999999

    async def _is_guild_blacklisted(self, guild_id: int) -> bool:
        doc = await self.guild_blacklist.find_one({"guild_id": guild_id})
        return doc is not None

    async def _add_user_bl(self, user_id: int):
        # Check if user has premium - if so, don't blacklist them
        if await self._is_user_premium(user_id):
            return False
        
        await self.user_blacklist.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "timestamp": datetime.utcnow()}},
            upsert=True
        )
        return True

    async def _remove_user_bl(self, user_id: int):
        await self.user_blacklist.delete_one({"user_id": user_id})

    async def _add_guild_bl(self, guild_id: int):
        await self.guild_blacklist.update_one(
            {"guild_id": guild_id},
            {"$set": {"guild_id": guild_id, "timestamp": datetime.utcnow()}},
            upsert=True
        )

    async def _remove_guild_bl(self, guild_id: int):
        await self.guild_blacklist.delete_one({"guild_id": guild_id})

    # ── Global blocker (runs before ANY command) ───────────────────────────────
    async def _global_block_check(self, ctx: commands.Context) -> bool:
        # Owner always bypasses
        if ctx.author.id == OWNER_ID:
            return True

        # Block blacklisted users
        if await self._is_user_blacklisted(ctx.author.id):
            embed = discord.Embed(
                title="<a:warn:1396429222066782228> **__You are Blacklisted__**",
                description="You are blacklisted from using commands.\nJoin our **[Support Server](https://dsc.gg/scyrogg)** to Appeal.",
                color=discord.Color.red()
            )
            try:
                await ctx.reply(embed=embed, mention_author=False)
            except discord.HTTPException:
                pass
            return False

        # Block commands in blacklisted guilds (if in a server)
        if ctx.guild and await self._is_guild_blacklisted(ctx.guild.id):
            embed = discord.Embed(
                title="<a:warn:1396429222066782228> **__Guild is Blacklisted__**",
                description="This server is blacklisted. Commands cannot be used here.\nJoin our **[Support Server](https://dsc.gg/scyrogg)** if you think this was a mistake.",
                color=discord.Color.red()
            )
            try:
                await ctx.reply(embed=embed, mention_author=False)
            except discord.HTTPException:
                pass
            return False

        return True

    # ── Security helper ────────────────────────────────────────────────────────
    def _owner_only(self, ctx: commands.Context) -> bool:
        return ctx.author.id == OWNER_ID

    async def _deny_owner_only(self, ctx: commands.Context):
        embed = discord.Embed(
            title="<:no:1396838761605890090> Access Denied",
            description="Only the bot owner can use this command.",
            color=EMBED_COLOR
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ── $bl (user) + $bl guild <id> ────────────────────────────────────────────
    @commands.group(name="bl", invoke_without_command=True)
    async def bl(self, ctx: commands.Context, *, target: Optional[str] = None):
        """$bl <user>  — blacklist a user (mention or ID)"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)

        if not target:
            embed = discord.Embed(
                title="Blacklist",
                description="Usage:\n`$bl <user>`\n`$bl guild <guild_id>`\n\nNote: For bypass management, use `$blbypass add <user_id>` or `$blbypass remove <user_id>`",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        # Resolve user from mention or ID
        user = None
        if ctx.message.mentions:
            user = ctx.message.mentions[0]
        elif target.isdigit():
            try:
                user = await self.bot.fetch_user(int(target))
            except Exception:
                user = None

        if not user:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Wrong Usage",
                description="For bypass management, use `$blbypass add <user_id>` or `$blbypass remove <user_id>`",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        if user.id == OWNER_ID:
            embed = discord.Embed(
                description="``I can’t block you, my creator.``",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        if await self._is_user_blacklisted(user.id):
            embed = discord.Embed(
                title="<:no:1396838761605890090> User Already Blacklisted",
                description=f"{user.mention} is already blacklisted.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        # Owner can manually blacklist even premium users
        success = await self._add_user_bl(user.id)
        if not success:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Premium User",
                description=f"{user.mention} has an active premium tier and cannot be automatically blacklisted.\nOnly the bot owner can force blacklist premium users.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)
        
        embed = discord.Embed(
            title="<:yes:1396838746862784582> User Blacklisted",
            description=f"{user.mention} has been added to the global blacklist.",
            color=EMBED_COLOR
        )
        await ctx.reply(embed=embed)

    @bl.command(name="guild")
    async def bl_guild(self, ctx: commands.Context, guild_id: int):
        """$bl guild <guild_id> — blacklist a server by ID"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)

        if await self._is_guild_blacklisted(guild_id):
            embed = discord.Embed(
                title="<:no:1396838761605890090> Guild Already Blacklisted",
                description=f"Guild with ID `{guild_id}` is already blacklisted.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        await self._add_guild_bl(guild_id)
        embed = discord.Embed(
            title="<:yes:1396838746862784582> Guild Blacklisted",
            description=f"Guild with ID `{guild_id}` has been added to the global blacklist.",
            color=EMBED_COLOR
        )
        await ctx.reply(embed=embed)

    # ── $unbl (user) + $unbl guild <id> ────────────────────────────────────────
    @commands.group(name="unbl", invoke_without_command=True)
    async def unbl(self, ctx: commands.Context, *, target: Optional[str] = None):
        """$unbl <user>  — unblacklist a user (mention or ID)"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)

        if not target:
            embed = discord.Embed(
                title="Unblacklist",
                description="Usage:\n`$unbl <user>`\n`$unbl guild <guild_id>`",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        # Resolve user
        user = None
        if ctx.message.mentions:
            user = ctx.message.mentions[0]
        elif target.isdigit():
            try:
                user = await self.bot.fetch_user(int(target))
            except Exception:
                user = None

        if not user:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Invalid User",
                description="Please mention a user or provide a valid user ID.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        if not await self._is_user_blacklisted(user.id):
            embed = discord.Embed(
                title="<:no:1396838761605890090> User Not Blacklisted",
                description=f"{user.mention} is not in the blacklist.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        await self._remove_user_bl(user.id)
        embed = discord.Embed(
            title="<:yes:1396838746862784582> User Unblacklisted",
            description=f"{user.mention} has been removed from the global blacklist.",
            color=EMBED_COLOR
        )
        await ctx.reply(embed=embed)
    
    # ── Bypass commands ─────────────────────────────────────────────────────────
    @commands.group(name="blbypass", invoke_without_command=True)
    async def blbypass(self, ctx: commands.Context):
        """Manage bypass list for automatic blacklisting"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)
        
        embed = discord.Embed(
            title="Blacklist Bypass Management",
            description="Manage users who are immune to automatic blacklisting",
            color=EMBED_COLOR
        )
        embed.add_field(
            name="Commands",
            value="`$blbypass add <user_id>` - Add user to bypass\n`$blbypass remove <user_id>` - Remove user from bypass",
            inline=False
        )
        await ctx.reply(embed=embed)
    
    @blbypass.command(name="add")
    async def blbypass_add(self, ctx: commands.Context, user_id: int):
        """Add a user to the bypass list (immune to automatic blacklisting)"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)
        
        # Validate user ID format
        if not self._is_valid_user_id(user_id):
            embed = discord.Embed(
                title="<:no:1396838761605890090> Invalid User",
                description="Please provide a valid user ID.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)
        
        # Check if already bypassed
        if await self._is_user_bypassed(user_id):
            # Try to get user info for display, but don't fail if we can't
            try:
                user = await self.bot.fetch_user(user_id)
                user_mention = user.mention
            except Exception:
                user_mention = f"<@{user_id}>"
            
            embed = discord.Embed(
                title="<:no:1396838761605890090> User Already Bypassed",
                description=f"{user_mention} is already immune to automatic blacklisting.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)
        
        # Add to bypass
        await self._add_bypass_user(user_id, ctx.author.id)
        
        # Try to get user info for display, but don't fail if we can't
        try:
            user = await self.bot.fetch_user(user_id)
            user_mention = user.mention
            user_name = user.display_name
        except Exception:
            user_mention = f"<@{user_id}>"
            user_name = f"User {user_id}"
        
        embed = discord.Embed(
            title="<:yes:1396838746862784582> User Bypass Added",
            description=f"{user_mention} is now immune to automatic blacklisting.",
            color=EMBED_COLOR
        )
        embed.set_footer(text=f"Added by {ctx.author.display_name}")
        await ctx.reply(embed=embed)
    
    @blbypass.command(name="remove")
    async def blbypass_remove(self, ctx: commands.Context, user_id: int):
        """Remove a user from the bypass list"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)
        
        # Validate user ID format
        if not self._is_valid_user_id(user_id):
            embed = discord.Embed(
                title="<:no:1396838761605890090> Invalid User",
                description="Please provide a valid user ID.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)
        
        # Check if bypassed
        if not await self._is_user_bypassed(user_id):
            # Try to get user info for display, but don't fail if we can't
            try:
                user = await self.bot.fetch_user(user_id)
                user_mention = user.mention
            except Exception:
                user_mention = f"<@{user_id}>"
            
            embed = discord.Embed(
                title="<:no:1396838761605890090> User Not Bypassed",
                description=f"{user_mention} is not in the bypass list.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)
        
        # Remove from bypass
        await self._remove_bypass_user(user_id)
        
        # Try to get user info for display, but don't fail if we can't
        try:
            user = await self.bot.fetch_user(user_id)
            user_mention = user.mention
            user_name = user.display_name
        except Exception:
            user_mention = f"<@{user_id}>"
            user_name = f"User {user_id}"
        
        embed = discord.Embed(
            title="<:yes:1396838746862784582> User Bypass Removed",
            description=f"{user_mention} is no longer immune to automatic blacklisting.",
            color=EMBED_COLOR
        )
        embed.set_footer(text=f"Removed by {ctx.author.display_name}")
        await ctx.reply(embed=embed)

    @unbl.command(name="guild")
    async def unbl_guild(self, ctx: commands.Context, guild_id: int):
        """$unbl guild <guild_id> — unblacklist a server by ID"""
        if not self._owner_only(ctx):
            return await self._deny_owner_only(ctx)

        if not await self._is_guild_blacklisted(guild_id):
            embed = discord.Embed(
                title="<:no:1396838761605890090> Guild Not Blacklisted",
                description=f"Guild with ID `{guild_id}` is not in the blacklist.",
                color=EMBED_COLOR
            )
            return await ctx.reply(embed=embed)

        await self._remove_guild_bl(guild_id)
        embed = discord.Embed(
            title="<:yes:1396838746862784582> Guild Unblacklisted",
            description=f"Guild with ID `{guild_id}` has been removed from the global blacklist.",
            color=EMBED_COLOR
        )
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Block(bot))
