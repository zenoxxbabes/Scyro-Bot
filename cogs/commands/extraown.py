import discord
from discord.ext import commands
from discord.ui import View, Button
import motor.motor_asyncio
from utils.Tools import *
import os

# Bot Owner Configuration
BOT_OWNER_ID = 1218037361926209640  # Your bot owner ID
BOT_OWNER_EMOJI = "<:90716owner:1417059807172497460>"  # Your custom bot owner emoji

class Extraowner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_default_database()
        self.collection = self.db.extraowners
        
        self.bot.loop.create_task(self.create_indexes())

    async def create_indexes(self):
        await self.collection.create_index([("guild_id", 1), ("owner_id", 1)], unique=True)
        print("✅ Extraowner MongoDB indexes initialized")

    def is_bot_owner_check(self, user_id: int) -> bool:
        """Check if user is the bot owner"""
        return user_id == BOT_OWNER_ID

    async def check_permissions(self, ctx):
        """Check if user has permission to use extraowner commands"""
        # Bot owner bypass - can use commands in any guild
        if self.is_bot_owner_check(ctx.author.id):
            return True
        
        # Check if user is guild owner
        if ctx.author.id != ctx.guild.owner_id:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Access Denied",
                description="Only Server Owner or Bot Owner can run this command!",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return False
        
        return True

    # Helper for API and other cogs
    async def is_extra_owner(self, guild_id: int, user_id: int) -> bool:
        """Check if a user is an extra owner"""
        doc = await self.collection.find_one({"guild_id": guild_id, "owner_id": user_id})
        return doc is not None

    # Main extraowner group command - HYBRID SUPPORT
    @commands.hybrid_group(
        name='extraowner',
        aliases=['extrao', 'eowner', 'eo'],
        description="Manage extra owners for your server",
        invoke_without_command=True
    )
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def extraowner(self, ctx):
        """Main extraowner command group"""
        # Manual permission check that allows bot owner bypass
        if not await self.check_permissions(ctx):
            return
            
        if ctx.invoked_subcommand is None:
            # Get prefix dynamically
            if hasattr(ctx, 'prefix'):
                pre = ctx.prefix
            elif hasattr(ctx, 'clean_prefix'):
                pre = ctx.clean_prefix
            else:
                pre = '$'  # fallback prefix
            
            # Member count check (skip for bot owner)
            if not self.is_bot_owner_check(ctx.author.id) and ctx.guild.member_count < 30:
                embed = discord.Embed(
                    description="<:no:1396838761605890090> | Your Server Doesn't Meet My 30 Member Criteria",
                    color=0x2b2d31
                )
                await ctx.send(embed=embed)
                return
            
            # Special indicator if user is bot owner
            owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(ctx.author.id) else ""
            
            embed = discord.Embed(
                title=f"__**Extra Owner System**__{owner_badge}",
                description="Extraowners can adjust server antinuke settings & manage whitelist events, so careful consideration is essential before assigning it to someone.",
                color=0x2b2d31
            )
            embed.add_field(
                name="__**Available Commands**__",
                value=(
                    f'`{pre}extraowner add @user` - Add an extra owner\n'
                    f'`{pre}extraowner remove @user` - Remove an extra owner\n'
                    f'`{pre}extraowner list` - View all extra owners\n'
                    f'`{pre}extraowner reset` - Remove all extra owners\n\n'
                    f'**Slash Commands:**\n'
                    f'`/extraowner add @user` - Add an extra owner\n'
                    f'`/extraowner remove @user` - Remove an extra owner\n'
                    f'`/extraowner list` - View all extra owners\n'
                    f'`/extraowner reset` - Remove all extra owners'
                ),
                inline=False
            )
            
            if self.is_bot_owner_check(ctx.author.id):
                embed.add_field(
                    name=f'{BOT_OWNER_EMOJI} **Bot Owner Privileges**',
                    value='You have global access to extraowner commands in all servers',
                    inline=False
                )
                
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            await ctx.send(embed=embed)

    @extraowner.command(
        name='add',
        aliases=['set', 'create'],
        description="Add a user as extra owner"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    async def extraowner_add(self, ctx, user: discord.User):
        """Add an extra owner"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return
            
        # Member count check (skip for bot owner)
        if not self.is_bot_owner_check(ctx.author.id) and ctx.guild.member_count < 30:
            embed = discord.Embed(
                description="<:no:1396838761605890090> | Your Server Doesn't Meet My 30 Member Criteria",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        guild_id = ctx.guild.id

        if user.bot:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Error",
                description="You cannot set a bot as an extra owner!",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        if user.id == ctx.guild.owner_id:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Error",
                description="The server owner is already the main owner!",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        # Check limit (max 3)
        count = await self.collection.count_documents({"guild_id": guild_id})
        if count >= 3:
            embed = discord.Embed(
                 description="<:no:1396838761605890090> | You can only add up to **3** extra owners!",
                 color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        # Check if already an extra owner
        existing = await self.collection.find_one({"guild_id": guild_id, "owner_id": user.id})

        if existing:
            embed = discord.Embed(
                description=f"<:no:1396838761605890090> | {user.mention} is **already** an extra owner!",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        # Confirmation
        view = ConfirmView(ctx)
        embed = discord.Embed(
            description=f"⚠️ | **Confirm Action**\n\nAre you sure you want to add {user.mention} as an extra owner?\nThey will have nearly full control over bot settings.",
            color=0x2b2d31
        )
        message = None
        try:
            message = await ctx.send(embed=embed, view=view)
        except:
            return

        await view.wait()

        if view.value:
            await self.collection.insert_one({"guild_id": guild_id, "owner_id": user.id})
            
            success_note = f"\n*Added by {BOT_OWNER_EMOJI} Bot Owner*" if self.is_bot_owner_check(ctx.author.id) else ""
            embed = discord.Embed(
                description=f"<:yes:1396838746862784582> | Successfully **Added** {user.mention} as Extra Owner.{success_note}",
                color=0x2b2d31
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            if message:
                await message.edit(embed=embed, view=None)
            else:
                await ctx.send(embed=embed)
        else:
            cancel_embed = discord.Embed(
                description="<:no:1396838761605890090> Action cancelled.",
                color=0x2b2d31
            )
            if message:
                await message.edit(embed=cancel_embed, view=None)
            else:
                await ctx.send(embed=cancel_embed)

    @extraowner.command(
        name='remove',
        aliases=['delete'],
        description="Remove an extra owner"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    async def extraowner_remove(self, ctx, user: discord.User):
        """Remove an extra owner"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return

        guild_id = ctx.guild.id

        # Check if user is an extra owner
        existing = await self.collection.find_one({"guild_id": guild_id, "owner_id": user.id})
        
        if not existing:
            embed = discord.Embed(
                description=f"<:no:1396838761605890090> | {user.mention} is **not** an extra owner!",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        # Confirmation
        view = ConfirmView(ctx)
        embed = discord.Embed(
            description=f"⚠️ | **Confirm Action**\n\nAre you sure you want to remove {user.mention} from extra owners?",
            color=0x2b2d31
        )
        message = None
        try:
            message = await ctx.send(embed=embed, view=view)
        except:
            return
            
        await view.wait()
        
        if view.value:
            await self.collection.delete_one({"guild_id": guild_id, "owner_id": user.id})
            
            success_note = f"\n*Removed by {BOT_OWNER_EMOJI} Bot Owner*" if self.is_bot_owner_check(ctx.author.id) else ""
            embed = discord.Embed(
                description=f"<:yes:1396838746862784582> | Successfully **Removed** {user.mention} from Extra Owners.{success_note}",
                color=0x2b2d31
            )
            if message:
                await message.edit(embed=embed, view=None)
            else:
                 await ctx.send(embed=embed)
        else:
            cancel_embed = discord.Embed(
                description="<:no:1396838761605890090> Action cancelled.",
                color=0x2b2d31
            )
            if message:
                await message.edit(embed=cancel_embed, view=None)
            else:
                await ctx.send(embed=cancel_embed)

    @extraowner.command(
        name='list',
        aliases=['show', 'view', 'all'],
        description="View all extra owners"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def extraowner_list(self, ctx):
        """List all extra owners"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return

        guild_id = ctx.guild.id

        extra_owners_cursor = self.collection.find({"guild_id": guild_id})
        extra_owners = await extra_owners_cursor.to_list(length=None)

        owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(ctx.author.id) else ""
        
        if not extra_owners:
            embed = discord.Embed(
                description="<:no:1396838761605890090> | No extra owners are currently assigned for this server.",
                color=0x2b2d31
            )
            embed.set_footer(text="Powered by Scyro.xyz")
            embed.add_field(
                name="How to Add",
                value=f"Use `{ctx.prefix if hasattr(ctx, 'prefix') else '/'}extraowner add @user` to add extra owners.",
                inline=False
            )
        else:
            extra_owners_list = []
            for i, doc in enumerate(extra_owners, 1):
                owner_id = doc["owner_id"]
                user = ctx.guild.get_member(owner_id)
                if user:
                    extra_owners_list.append(f"**{i}.** {user.mention} (`{user.id}`)")
                else:
                    extra_owners_list.append(f"**{i}.** <@{owner_id}> (`{owner_id}`) *[Left Server]*")

            embed = discord.Embed(
                title=f"Extra Owners List{owner_badge}",
                description=f"**Server:** {ctx.guild.name}\n**Total Extra Owners:** {len(extra_owners)}/3\n\n" + 
                           "\n".join(extra_owners_list),
                color=0x2b2d31
            )
            
            if self.is_bot_owner_check(ctx.author.id):
                 embed.set_footer(text=f"Powered by Scyro.xyz | {BOT_OWNER_EMOJI} Bot Owner Access", icon_url=self.bot.user.avatar.url)
            else:
                 embed.set_footer(text="Powered by Scyro.xyz", icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        await ctx.send(embed=embed)

    @extraowner.command(
        name='reset',
        aliases=['clear', 'removeall'],
        description="Remove all extra owners"
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    async def extraowner_reset(self, ctx):
        """Reset all extra owners"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return

        guild_id = ctx.guild.id

        # Check if there are any extra owners
        count = await self.collection.count_documents({"guild_id": guild_id})

        if count == 0:
            embed = discord.Embed(
                description="<:no:1396838761605890090> | No extra owners are currently assigned for this server.",
                color=0x2b2d31
            )
            embed.set_footer(text="Powered by Scyro.xyz")
            await ctx.send(embed=embed)
            return

        # Confirmation
        owner_note = f" ({BOT_OWNER_EMOJI} Bot Owner Override)" if self.is_bot_owner_check(ctx.author.id) else ""
        view = ConfirmView(ctx)
        embed = discord.Embed(
            description=f"⚠️ | **Confirm Reset**{owner_note}\n\nAre you sure you want to remove ALL extra owners for this server?",
            color=0x2b2d31
        )
        embed.set_footer(text="Powered by Scyro.xyz")
        
        message = None
        try:
            message = await ctx.send(embed=embed, view=view)
        except:
             return

        await view.wait()

        if view.value:
            await self.collection.delete_many({"guild_id": guild_id})
            
            embed = discord.Embed(
                description=f"<:yes:1396838746862784582> | Successfully **Reset** all Extra Owners.",
                color=0x2b2d31
            )
            if message:
                await message.edit(embed=embed, view=None)
            else:
                await ctx.send(embed=embed)
            
        else:
            cancel_embed = discord.Embed(
                description="<:no:1396838761605890090> Reset cancelled.",
                color=0x2b2d31
            )
            if message:
                await message.edit(embed=cancel_embed, view=None)
            else:
                await ctx.send(embed=cancel_embed)

class ConfirmView(View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("You cannot interact with this confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="<:no:1396838761605890090>")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        self.value = False
        self.stop()

async def setup(bot):
    await bot.add_cog(Extraowner(bot))
