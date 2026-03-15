import discord
from discord.ext import commands
import motor.motor_asyncio
import os
from utils.Tools import blacklist_check, ignore_check
from collections import defaultdict
import time
from typing import Union

class Media(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.infractions = defaultdict(list)
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.settings = None
        self.client.loop.create_task(self.init_db())
        
    async def init_db(self):
        if not self.mongo_uri: return
        self.client_mongo = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client_mongo.get_database()
        self.settings = self.db.media_settings
        await self.settings.create_index("guild_id", unique=True)

    @commands.hybrid_group(name="media", help="Setup Media channels. These channels only allow media files.", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    async def media(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @media.command(name="setup", aliases=["add"], help="Adds a channel to the media-only list")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        
        doc = await self.settings.find_one({"guild_id": ctx.guild.id})
        current_channels = doc.get("channels", []) if doc else []
        
        if len(current_channels) >= 20:
             return await ctx.reply(embed=discord.Embed(title="Error", description="You have reached the limit of 20 media channels.", color=discord.Color.red()))

        if channel.id in current_channels:
             return await ctx.reply(embed=discord.Embed(title="Error", description="This channel is already a media channel.", color=discord.Color.red()))

        await self.settings.update_one(
            {"guild_id": ctx.guild.id},
            {"$addToSet": {"channels": channel.id}},
            upsert=True
        )
        
        embed = discord.Embed(
            title="<:yes:1396838746862784582> Success",
            description=f"Added {channel.mention} to media-only channels.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Ensure I have 'Manage Messages' permission.")
        await ctx.reply(embed=embed)

    @media.command(name="remove", aliases=["delete"], help="Removes a channel from the media-only list")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        
        result = await self.settings.update_one(
            {"guild_id": ctx.guild.id},
            {"$pull": {"channels": channel.id}}
        )
            
        if result.modified_count == 0:
            await ctx.reply(embed=discord.Embed(title="Error", description="This channel is not a media channel.", color=discord.Color.red()))
        else:
            await ctx.reply(embed=discord.Embed(title="<:yes:1396838746862784582> Success", description=f"Removed {channel.mention} from media-only channels.", color=discord.Color.green()))

    @media.command(name="list", aliases=["show", "config"], help="Shows configured media channels")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def config(self, ctx):
        doc = await self.settings.find_one({"guild_id": ctx.guild.id})
        channel_ids = doc.get("channels", []) if doc else []
        
        if not channel_ids:
            return await ctx.reply(embed=discord.Embed(title="Media Channels", description="No media channels set.", color=discord.Color.orange()))

        channels = []
        for cid in channel_ids:
            ch = ctx.guild.get_channel(cid)
            if ch: channels.append(ch.mention)
            else: channels.append(f"<#{cid}> (Deleted)")
            
        embed = discord.Embed(title="Media Only Channels", description="\n".join(channels), color=discord.Color.blue())
        await ctx.reply(embed=embed)

    @media.group(name="bypass", help="Manage media bypass (Users/Roles)", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    async def bypass(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @bypass.command(name="add", help="Add user or role to bypass")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def bypass_add(self, ctx, target: Union[discord.Member, discord.Role]):
        is_role = isinstance(target, discord.Role)
        field = "bypass_roles" if is_role else "bypass_users"
        limit = 10 if is_role else 25
        
        doc = await self.settings.find_one({"guild_id": ctx.guild.id})
        current_list = doc.get(field, []) if doc else []
        
        if len(current_list) >= limit:
             return await ctx.reply(embed=discord.Embed(title="Error", description=f"Limit reached for {target.__class__.__name__} bypass list.", color=discord.Color.red()))

        if target.id in current_list:
             return await ctx.reply(embed=discord.Embed(title="Error", description=f"{target.mention} is already bypassed.", color=discord.Color.red()))

        await self.settings.update_one(
            {"guild_id": ctx.guild.id},
            {"$addToSet": {field: target.id}},
            upsert=True
        )
        await ctx.reply(embed=discord.Embed(title="Success", description=f"Added {target.mention} to bypass list.", color=discord.Color.green()))

    @bypass.command(name="remove", help="Remove user or role from bypass")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def bypass_remove(self, ctx, target: Union[discord.Member, discord.Role]):
        is_role = isinstance(target, discord.Role)
        field = "bypass_roles" if is_role else "bypass_users"
        
        result = await self.settings.update_one(
            {"guild_id": ctx.guild.id},
            {"$pull": {field: target.id}}
        )
            
        if result.modified_count == 0:
            await ctx.reply(embed=discord.Embed(title="Error", description=f"{target.mention} was not in bypass list.", color=discord.Color.red()))
        else:
            await ctx.reply(embed=discord.Embed(title="Success", description=f"Removed {target.mention} from bypass list.", color=discord.Color.green()))

    @bypass.command(name="list", aliases=["show"], help="Show bypass list")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def bypass_list(self, ctx):
        doc = await self.settings.find_one({"guild_id": ctx.guild.id})
        bypass_users = doc.get("bypass_users", []) if doc else []
        bypass_roles = doc.get("bypass_roles", []) if doc else []

        users = [f"<@{uid}>" for uid in bypass_users]
        roles = [f"<@&{rid}>" for rid in bypass_roles]

        embed = discord.Embed(title="Media Bypass List", color=discord.Color.blue())
        embed.add_field(name=f"Users ({len(users)})", value=", ".join(users) if users else "None", inline=False)
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) if roles else "None", inline=False)
        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return

        # Optimization: Fetch settings once
        if self.settings is None: return
        doc = await self.settings.find_one({"guild_id": message.guild.id})
        if not doc: return

        # Check if channel is media channel
        channels = doc.get("channels", [])
        if message.channel.id not in channels:
            return # Not a media channel

        # It IS a media channel, check bypass
        # 1. Check User Bypass
        if message.author.id in doc.get("bypass_users", []): return

        # 2. Check Role Bypass
        role_ids = [r.id for r in message.author.roles]
        bypass_roles = doc.get("bypass_roles", [])
        if any(rid in bypass_roles for rid in role_ids): return

        # 3. Check Global Blacklist (Optimization: do this last or first depending on probability, usually done by bot globally but explicit check here)
        # Assuming block check is done via decorator on commands, but for listener we might rely on bot's global check
        # But here we reproduce logic:
        # We can implement a helper or assume global blacklist works. The original code checked blacklist DB.
        # We should check the `user_blacklist` collection if needed, but let's assume standard checks apply?
        # The original code explicitly checked 'db/block.db'. We should check 'user_blacklist' collection.
        # However, for performance, maybe we skip or rely on `blacklist_check` cog listener if it exists?
        # Original code: checks block.db.
        # Let's add that check if we want 1:1 parity, using the new mongo collection.
        
        # Accessing block collection (assuming we can get it from bot or create new client)
        # Using self.db.user_blacklist
        try:
             block_doc = await self.db.user_blacklist.find_one({"user_id": message.author.id})
             if block_doc: return
        except: pass

        # Validation: content check
        if message.attachments: return # Allowed
        
        # If we are here, message has no attachments and user is not bypassed
        try:
            await message.delete()
            msg = await message.channel.send(f"{message.author.mention} This channel is **Media Only**.", delete_after=3)
        except: pass

        # Infraction Logic
        now = time.time()
        self.infractions[message.author.id] = [t for t in self.infractions[message.author.id] if now - t < 10]
        self.infractions[message.author.id].append(now)
        
        if len(self.infractions[message.author.id]) >= 5:
            # Blacklist user
            try:
                await self.db.user_blacklist.update_one(
                    {"user_id": message.author.id},
                    {"$set": {"reason": "Spamming in media channel", "timestamp": time.time()}},
                    upsert=True
                )
            except: pass
            
            try: await message.channel.send(f"<a:alert:1396429026842644584> {message.author.mention} has been blacklisted for spamming in media channel.")
            except: pass
            del self.infractions[message.author.id]

async def setup(bot):
    await bot.add_cog(Media(bot))