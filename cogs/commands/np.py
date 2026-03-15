from discord.ext import commands, tasks
from discord import *
import discord
import motor.motor_asyncio
from typing import Optional
from datetime import datetime, timedelta
from discord.ui import View, Button, Select
from utils.config import OWNER_IDS
from utils import Paginator, DescriptionEmbedPaginator
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUCCESS_EMOJI = "✅" 

# Add import for the main bot file to access BOT_OWNERS
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from main import BOT_OWNERS

def load_owner_ids():
    return OWNER_IDS


async def is_staff(user, staff_ids):
    return user.id in staff_ids


async def is_owner_or_staff(ctx):
    return await is_staff(ctx.author, ctx.cog.staff) or ctx.author.id in BOT_OWNERS


class TimeSelect(Select):
    def __init__(self, user, cog, author):
        super().__init__(placeholder="Select the duration")
        self.user = user
        self.cog = cog  # Pass cog reference instead of db_path
        self.author = author

        self.options = [
            SelectOption(label="10 Minutes", description="Trial for 10 minutes", value="10m"),
            SelectOption(label="1 Week", description="No prefix for 1 week", value="1w"),
            SelectOption(label="3 Weeks", description="No prefix for 3 weeks", value="3w"),
            SelectOption(label="1 Month", description="No prefix for 1 Month", value="1m"),
            SelectOption(label="3 Months", description="No prefix for 3 Months.", value="3m"),
            SelectOption(label="6 Months", description="No prefix for 6 Months.", value="6m"),
            SelectOption(label="1 Year", description="No prefix for 1 Year.", value="1y"),
            SelectOption(label="3 Years", description="No prefix for 3 Years.", value="3y"),
            SelectOption(label="Lifetime", description="No prefix Permanently.", value="lifetime"),
        ]

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("You can't select this option.", ephemeral=True)

        # Defer immediately to prevent timeouts
        await interaction.response.defer()

        duration_mapping = {
            "10m": timedelta(minutes=10),
            "1w": timedelta(weeks=1),
            "3w": timedelta(days=21),
            "1m": timedelta(days=30),
            "3m": timedelta(days=90),
            "6m": timedelta(days=180),
            "1y": timedelta(days=365),
            "3y": timedelta(days=365 * 3),
            "lifetime": None
        }

        selected_duration = self.values[0]
        expiry_time = None

        if selected_duration != "lifetime":
            expiry_time = datetime.utcnow() + duration_mapping[selected_duration]
            expiry_str = expiry_time.isoformat()
        else:
            expiry_str = None

        await self.cog.np_users.update_one(
            {"user_id": self.user.id},
            {"$set": {"expiry_time": expiry_str}},
            upsert=True
        )

        expiry_text = "**Lifetime**" if selected_duration == "lifetime" else (expiry_time.strftime('%Y-%m-%d %H:%M:%S') + " UTC" if expiry_time else "Unknown")
        expiry_timestamp = "None (Permanent)" if selected_duration == "lifetime" else (f"<t:{int(expiry_time.timestamp())}:f>" if expiry_time else "Unknown")

        guild = interaction.client.get_guild(699587669059174461)
        if guild:
            member = guild.get_member(self.user.id)
            if member:
                role = guild.get_role(1295883122902302771)
                if role:
                    try:
                        await member.add_roles(role, reason="No prefix added")
                    except: pass

        log_channel = interaction.client.get_channel(int(os.getenv('NO_PREFIX_ADD_LOG_CHANNEL', 1299513569766805597)))
        if log_channel and isinstance(log_channel, discord.TextChannel):
            embed = discord.Embed(
                title="User Added to No Prefix",
                description=f"👤 **User**: [{self.user}](https://discord.com/users/{self.user.id})\n⚪ **User Mention**: {self.user.mention}\n📍 **ID**: {self.user.id}\n\n🤖 **Added By**: [{self.author.display_name}](https://discord.com/users/{self.author.id})\n⏰ **Expiry Time**: {expiry_text}\n➡️ **Timestamp**: {expiry_timestamp}\n\n⭐ **Tier**: **{self.values[0].upper()}**",
                color=0x2b2d31
            )
            embed.set_thumbnail(url=self.user.avatar.url if self.user.avatar else self.user.default_avatar.url)
            try:
                await log_channel.send("No Prefix Update!",embed=embed)
            except: pass

        embed = discord.Embed(description=f"**Added Global No Prefix**:\n👤 **User**: **[{self.user}](https://discord.com/users/{self.user.id})**\n⚪ **User Mention**: {self.user.mention}\n📍 **User ID**: {self.user.id}\n\n__**Additional Info**__:\n🤖 **Added By**: **[{self.author.display_name}](https://discord.com/users/{self.author.id})**\n⏰ **Expiry Time:** {expiry_text}\n➡️ **Timestamp:** {expiry_timestamp}", color=0x2b2d31)
        embed.set_author(name="Added No Prefix", icon_url="https://cdn.discordapp.com/attachments/1409886768811085847/1412054443058266152/4da14c09ac3e7f27fb29c90535fbad14.png?ex=68b6e5ad&is=68b5942d&hm=b88a226de326e66070174a43cd6f497ede1ac3ee4b8ed0ed4e0bd1d657564de5&")
        embed.set_footer(text="DM will be sent to the user in case No prefix is expired.")
        
        # Since we deferred, we use edit_original_response or message.edit
        try:
            await interaction.message.edit(embed=embed, view=None)
        except:
            # Fallback
            await interaction.edit_original_response(embed=embed, view=None)

class TimeSelectView(View):
    def __init__(self, user, cog, author):
        super().__init__()
        self.user = user
        self.cog = cog
        self.author = author
        self.add_item(TimeSelect(user, cog, author))


class NoPrefix(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.np_users = None
        self.auto_np = None
        self.staff_coll = None
        self.staff = set()
        
        self.client.loop.create_task(self.setup_database())
        # load_staff will be called after db setup or inside setup_database if sequential 

    async def setup_database(self):
        if not self.mongo_uri:
            print("MONGO_URI not found!")
            return

        self.client_mongo = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client_mongo.get_database()
        self.np_users = self.db.no_prefix_users
        self.auto_np = self.db.auto_np_guilds
        self.staff_coll = self.db.bot_staff

        await self.np_users.create_index("user_id", unique=True)
        await self.auto_np.create_index("guild_id", unique=True)
        await self.staff_coll.create_index("user_id", unique=True)

        print(f"{SUCCESS_EMOJI} NoPrefix System MongoDB Connected")
        
        # Start tasks
        await self.load_staff()
        self.expiry_check.start()


    async def load_staff(self):
        if self.staff_coll is None:
            return

        try:
            await self.client.wait_until_ready()
        except asyncio.CancelledError:
            return
        
        cursor = self.staff_coll.find({})
        self.staff = {doc['user_id'] for doc in await cursor.to_list(length=None)}

    @tasks.loop(minutes=10)
    async def expiry_check(self):
        if self.np_users is None:
            return

        now = datetime.utcnow().isoformat()
        
        # Find expired users
        cursor = self.np_users.find({"expiry_time": {"$ne": None, "$lte": now}})
        expired_users_data = await cursor.to_list(length=None)
        expired_users = [doc['user_id'] for doc in expired_users_data]

        if expired_users:
            await self.np_users.delete_many({"user_id": {"$in": expired_users}})

            for user_id in expired_users:
                user = self.client.get_user(user_id)
                # Log removal
                if user:
                    log_channel = self.client.get_channel(int(os.getenv('NO_PREFIX_EXPIRE_LOG_CHANNEL', 1299513624477306974)))
                    if log_channel and isinstance(log_channel, discord.TextChannel):
                        embed_log = discord.Embed(
                            title="No Prefix Expired",
                            description=(
                                f"👤 **User**: [{user}](https://discord.com/users/{user.id})\n"
                                f"⚪ **User Mention**: {user.mention}\n"
                                f"📍 **ID**: {user.id}\n\n"
                                f"🤖 **Removed By**: **[Scyro](https://discord.com/users/1005088956951564358)**\n"
                            ),
                            color=0x2b2d31
                        )
                        embed_log.set_thumbnail(url=user.display_avatar.url if user.avatar else user.default_avatar.url)
                        embed_log.set_footer(text="No Prefix Removal Log")
                        try:
                            await log_channel.send("<@1005088956951564358>, <@1005088956951564358>", embed=embed_log)
                        except: pass

                    guild = self.client.get_guild(699587669059174461)
                    if guild:
                        member = guild.get_member(user.id)
                        if member:
                            role = guild.get_role(1295883122902302771)
                            if role in member.roles:
                                try:
                                    await member.remove_roles(role)
                                except: pass
                                
                    embed = discord.Embed(
                        description=f"⚠️ Your No Prefix status has **Expired**. You will now require the prefix to use commands.",
                        color=0x2b2d31
                    )
                    embed.set_author(name="No Prefix Expired", icon_url=user.avatar.url if user.avatar else user.default_avatar.url)
                    
                    embed.set_footer(text="Scyro - No Prefix, Join support to regain access.")
                    support = Button(label='Support',
                style=discord.ButtonStyle.link,
                url=f'https://discord.gg/hQge3FrtaE')
                    view = View()
                    view.add_item(support)

                    try:
                        await user.send(f"{user.mention}", embed=embed, view=view)
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException:
                        pass

    @expiry_check.before_loop
    async def before_expiry_check(self):
        try:
            await self.client.wait_until_ready()
        except asyncio.CancelledError:
            pass

    @commands.group(name="npx", help="Allows you to add someone to the no-prefix list (owner-only command)")
    @commands.check(is_owner_or_staff)
    async def _np(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @_np.command(name="list", help="List of no-prefix users")
    @commands.check(is_owner_or_staff)
    async def np_list(self, ctx):
        cursor = self.np_users.find({})
        ids = [doc['user_id'] for doc in await cursor.to_list(length=None)]
        
        if not ids:
            await ctx.reply(f"No users in the no-prefix list.", mention_author=False)
            return
        entries = [
            f"`#{no+1}`  [Profile URL](https://discord.com/users/{mem}) (ID: {mem})"
            for no, mem in enumerate(ids, start=0)
        ]
        embeds = DescriptionEmbedPaginator(
            entries=entries,
            title=f"No Prefix Users [{len(ids)}]",
            description="",
            per_page=10,
            color=0x2b2d31).get_pages()
        paginator = Paginator(ctx, embeds)
        await paginator.paginate()

    @_np.command(name="add", help="Add user to no-prefix with time options")
    @commands.check(is_owner_or_staff)
    async def np_add(self, ctx, user: discord.User):
        result = await self.np_users.find_one({"user_id": user.id})
        
        if result:
            embed = discord.Embed(description=f"**{user}** is Already in No prefix list\n\n🤖 **Requested By**: [{ctx.author.display_name}](https://discord.com/users/{ctx.author.id})\n", color=0x2b2d31)
            embed.set_author(name="Error", icon_url="https://cdn.discordapp.com/attachments/1409886768811085847/1412054443058266152/4da14c09ac3e7f27fb29c90535fbad14.png?ex=68b6e5ad&is=68b5942d&hm=b88a226de326e66070174a43cd6f497ede1ac3ee4b8ed0ed4e0bd1d657564de5&")
            await ctx.reply(embed=embed)
            return

        view = TimeSelectView(user, self, ctx.author)
        embed = discord.Embed(title="Select No Prefix Duration", description="**Choose the duration for how long no-prefix should be enabled for this user:**", color=0x2b2d31)
        await ctx.reply(embed=embed, view=view)
        

    @_np.command(name="remove", help="Remove user from no-prefix")
    @commands.check(is_owner_or_staff)
    async def np_remove(self, ctx, user: discord.User):
        result = await self.np_users.find_one({"user_id": user.id})
        
        if not result:
            embed = discord.Embed(description=f"**{user}** is Not in the No Prefix list\n\n🤖 **Requested By**: [{ctx.author.display_name}](https://discord.com/users/{ctx.author.id})\n", color=0x2b2d31)
            embed.set_author(name="Error", icon_url="https://cdn.discordapp.com/attachments/1409886768811085847/1412054443058266152/4da14c09ac3e7f27fb29c90535fbad14.png?ex=68b6e5ad&is=68b5942d&hm=b88a226de326e66070174a43cd6f497ede1ac3ee4b8ed0ed4e0bd1d657564de5&")
            await ctx.reply(embed=embed)
            return

        await self.np_users.delete_one({"user_id": user.id})

        guild = ctx.bot.get_guild(699587669059174461)
        if guild:
            member = guild.get_member(user.id)
            if member:
                role = guild.get_role(1295883122902302771)
                if role in member.roles:
                    await member.remove_roles(role)

        embed = discord.Embed(
                description=(
                    f"👤 **User**: [{user}](https://discord.com/users/{user.id})\n"
                    f"⚪ **User Mention**: {user.mention}\n"
                    f"📍 **User ID**: {user.id}\n\n"
                    f"🤖 **Removed By**: [{ctx.author.display_name}](https://discord.com/users/{ctx.author.id})\n"
                ),
            color=0x2b2d31
        )
        embed.set_author(name="Removed No Prefix", icon_url="https://cdn.discordapp.com/attachments/1409886768811085847/1412054443058266152/4da14c09ac3e7f27fb29c90535fbad14.png?ex=68b6e5ad&is=68b5942d&hm=b88a226de326e66070174a43cd6f497ede1ac3ee4b8ed0ed4e0bd1d657564de5&")
        await ctx.reply(embed=embed)

        log_channel = ctx.bot.get_channel(int(os.getenv('NO_PREFIX_EXPIRE_LOG_CHANNEL', 1299513624477306974)))
        if log_channel:
            embed_log = discord.Embed(
                title="No Prefix Removed",
                description=(
                    f"👤 **User**: [{user}](https://discord.com/users/{user.id})\n"
                    f"⚪ **User Mention**: {user.mention}\n"
                    f"📍 **ID**: {user.id}\n\n"
                    f"🤖 **Removed By**: [{ctx.author.display_name}](https://discord.com/users/{ctx.author.id})\n"
                ),
                color=0x2b2d31
            )
            embed_log.set_thumbnail(url=user.display_avatar.url if user.avatar else user.default_avatar.url)
            embed_log.set_footer(text="No Prefix Removal Log")
            await log_channel.send("No Prefix Update!", embed=embed_log)

    @_np.command(name="status", help="Check if a user is in the No Prefix list and show details.")
    @commands.check(is_owner_or_staff)
    async def np_status(self, ctx, user: discord.User):
        result = await self.np_users.find_one({"user_id": user.id})

        if not result:
            embed = discord.Embed(
                title="No Prefix Status",
                description=f"**{user}** is Not in the No Prefix list\n\n"
                            f"🤖 **Requested By**: "
                            f"[{ctx.author.display_name}](https://discord.com/users/{ctx.author.id})\n",
                color=0x2b2d31
            )
            await ctx.reply(embed=embed)
            return

        expires = result.get("expiry_time")
        user_id = result.get("user_id")

        if expires and expires != "Null": # Need to be careful with "Null" string vs None
            try:
                expire_time = datetime.fromisoformat(expires)
                expire_timestamp = f"<t:{int(expire_time.timestamp())}:F>"
            except:
                expire_time = "Unknown"
                expire_timestamp = "Unknown"
        else:
            expire_time = "Lifetime"
            expire_timestamp = "Lifetime"

        embed = discord.Embed(
            title="No Prefix Status",
            description=(
                f"👤 **User**: [{user}](https://discord.com/users/{user.id})\n"
                f"📍 **User ID**: {user_id}\n\n"
                f"⏰ **Expiry**: {expire_time} ({expire_timestamp})"
            ),
            color=0x2b2d31
        )

        embed.set_thumbnail(url=user.display_avatar.url if user.avatar else user.default_avatar.url)

        await ctx.reply(embed=embed)


    @commands.group(name="autonp", help="Manage auto no-prefix for partner guilds.")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def autonp(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autonp.group(name="guild", help="Manage partner guilds for auto no-prefix.")
    async def autonp_guild(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autonp_guild.command(name="add", help="Add a guild to auto no-prefix.")
    async def add_guild(self, ctx, guild_id: int):
        existing = await self.auto_np.find_one({"guild_id": guild_id})
        if existing:
            await ctx.reply("Guild is already added.")
            return
            
        await self.auto_np.insert_one({"guild_id": guild_id})
        await ctx.reply(f"Guild {guild_id} added to auto no-prefix.")

    @autonp_guild.command(name="remove", help="Remove a guild from auto no-prefix.")
    async def remove_guild(self, ctx, guild_id: int):
        result = await self.auto_np.delete_one({"guild_id": guild_id})
        if result.deleted_count == 0:
            await ctx.reply("Guild is not in auto no-prefix.")
        else:
            await ctx.reply(f"Guild {guild_id} removed from auto no-prefix.")

    @autonp_guild.command(name="list", help="List all guilds with auto no-prefix.")
    @commands.check(is_owner_or_staff)
    async def list_guilds(self, ctx):
        cursor = self.auto_np.find({})
        guilds = [doc['guild_id'] for doc in await cursor.to_list(length=None)]
        
        if not guilds:
            await ctx.reply("No guilds in auto no-prefix.", mention_author=False)
            return
        await ctx.reply(f"Guilds in auto no-prefix:\n" + "\n".join(str(g) for g in guilds), mention_author=False)


    async def is_user_in_np(self, user_id):
        # Optimized: return bool directly
        return await self.np_users.find_one({"user_id": user_id}) is not None
            
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if self.auto_np is None:
            return

        if before.premium_since is None and after.premium_since is not None:
            if not await self.auto_np.find_one({"guild_id": after.guild.id}):
                return
            
            if not await self.is_user_in_np(after.id):
                await self.add_np(after, timedelta(days=60))
                log_channel = self.client.get_channel(int(os.getenv('AUTO_NO_PREFIX_BOOST_LOG_CHANNEL', 1302312378578243765)))
                embed = discord.Embed(
                    title="Added No prefix due to Boosting Partner Server",
                    description=f"**User**: **[{after}](https://discord.com/users/{after.id})** (ID: {after.id})\n**Server**: {after.guild.name}",
                    color=0x00FF00
                )
                if log_channel: # Add check for log_channel before sending
                    message = await log_channel.send("<@1005088956951564358>, <@1005088956951564358>", embed=embed)
                    await message.publish()

        elif before.premium_since is not None and after.premium_since is None:  
            await self.handle_boost_removal(after)

    async def handle_boost_removal(self, user):
        if not await self.auto_np.find_one({"guild_id": user.guild.id}):
            return
            
        if await self.is_user_in_np(user.id):
            await self.remove_np(user) 
            log_channel = self.client.get_channel(int(os.getenv('AUTO_NO_PREFIX_UNBOOST_LOG_CHANNEL', 1302312616735281286)))
            embed = discord.Embed(
                title="Removed No prefix due to Unboosting Partner Server",
                description=f"**User**: **[{user}](https://discord.com/users/{user.id})** (ID: {user.id})\n**Server**: {user.guild.name}",
                color=0xFF0000
            )
            if log_channel: # Add check for log_channel before sending
                message = await log_channel.send("<@1005088956951564358>, <@1005088956951564358>", embed=embed)
                await message.publish()


    async def add_np(self, user, duration):
        expiry_time = datetime.utcnow() + duration
        
        await self.np_users.update_one(
            {"user_id": user.id}, 
            {"$set": {"expiry_time": expiry_time.isoformat()}}, 
            upsert=True
        )
            
        embed = discord.Embed(
                            title="🎉 Congratulations you got 2 months No Prefix!",
                            description=f"You've been credited 2 months of global No Prefix for boosting our Partnered Servers. You can now use my commands without prefix. If you wish to remove it, please reach out [Support Server](https://dsc.gg/scyrogg)",
                            color=0x2b2d31
                        )
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

        guild = self.client.get_guild(699587669059174461)
        if guild:
            member = guild.get_member(user.id)
            if member is not None:
                role = guild.get_role(1295883122902302771)
                if role:
                    await member.add_roles(role)


    async def remove_np(self, user):
        doc = await self.np_users.find_one({"user_id": user.id})
        if not doc or not doc.get("expiry_time"): 
            # Logic in old code: "row is None or row[0] is None: return"
            # It seems to check if it has an expiry time, or maybe if it exists at all.
            # Assuming if not in DB or expiry is None, we don't remove.
            # But "is None" in SQL usually means NULL. If row exists and expiry is NULL, it returns.
            return

        await self.np_users.delete_one({"user_id": user.id})
            
        embed= discord.Embed(title="⚠️ Global No Prefix Expired",
                        description=f"Hey {user.mention}, your global no prefix has expired!\n\n__**Reason:**__ Unboosting our partnered Server.\nIf you think this is a mistake then please reach out [Support Server](https://discord.gg/hQge3FrtaE",
                        color=0x2b2d31)
            
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

        guild = self.client.get_guild(699587669059174461)
        if guild:
            member = guild.get_member(user.id)
            if member is not None: 
                role = guild.get_role(1295883122902302771)
                if role and role in member.roles:
                    await member.remove_roles(role)

def setup(client):
    client.add_cog(NoPrefix(client))