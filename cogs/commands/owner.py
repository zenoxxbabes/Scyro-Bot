from __future__ import annotations
from discord.ext import commands
from discord import *
from PIL import Image, ImageDraw, ImageFont
import discord
import json
import datetime
import asyncio
import motor.motor_asyncio
from typing import Optional
from utils import Paginator, DescriptionEmbedPaginator, FieldPagePaginator, TextPaginator
from utils.Tools import *
from core import Cog, Scyro, Context
import os
import requests
from io import BytesIO
from discord.errors import Forbidden
from discord import Embed
from discord.ui import Button, View

# Add import for the main bot file to access BOT_OWNERS
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from main import BOT_OWNERS

BADGE_URLS = {
    "owner": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "staff": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "partner": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "sponsor": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "friend": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "early": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "vip": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512",
    "bug": "https://cdn.discordapp.com/banners/1387046835322880050/4477c55b490619e3f0c9336db8ab1a4f.png?size=512"
}

BADGE_NAMES = {
    "owner": "Owner",
    "staff": "Staff",
    "partner": "Partner",
    "sponsor": "Sponsor",
    "friend": "Owner's Friend",
    "early": "Early Supporter",
    "vip": "VIP",
    "bug": "Bug Hunter"
}

FONT_PATH = os.path.join('utils', 'arial.ttf')

# Removed global SQLite connection

def convert_time_to_seconds(time_str):
    time_units = {
        "h": "hours",
        "d": "days",
        "m": "months"
    }
    num = int(time_str[:-1])
    unit = time_units.get(time_str[-1])
    return datetime.timedelta(**{unit: num})


async def do_removal(ctx, limit, predicate, *, before=None, after=None):
  if limit > 2000:
      return await ctx.error(f"Too many messages to search given ({limit}/2000)")

  if before is None:
      before = ctx.message
  else:
      before = discord.Object(id=before)

  if after is not None:
      after = discord.Object(id=after)

  try:
      deleted = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate)
  except discord.Forbidden as e:
      return await ctx.error("I do not have permissions to delete messages.")
  except discord.HTTPException as e:
      return await ctx.error(f"Error: {e} (try a smaller search?)")

  spammers = Counter(m.author.display_name for m in deleted)
  deleted = len(deleted)
  messages = [f'<:yes:1396838746862784582> | {deleted} message{" was" if deleted == 1 else "s were"} removed.']
  if deleted:
      messages.append("")
      spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
      messages.extend(f"**{name}**: {count}" for name, count in spammers)

  to_send = "\n".join(messages)

  if len(to_send) > 2000:
      await ctx.send(f"<:yes:1396838746862784582> | Successfully removed {deleted} messages.", delete_after=3)
  else:
      await ctx.send(to_send, delete_after=3)

def load_owner_ids():
    return OWNER_IDS


async def is_staff(user, staff_ids):
    return user.id in staff_ids


async def is_owner_or_staff(ctx):
    return await is_staff(ctx.author, ctx.cog.staff) or ctx.author.id in BOT_OWNERS


class Owner(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.staff_coll = None
        self.badges_coll = None
        self.staff = set()
        self.np_cache = []
        self.stop_tour = False
        self.bot_owner_ids = [1218037361926209640, 1218037361926209640]
        self.client.loop.create_task(self.setup_database())
        # load_staff called in setup_database
        

    async def setup_database(self):
        if not self.mongo_uri:
            print("MONGO_URI not found!")
            return

        self.client_mongo = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client_mongo.get_database()
        self.staff_coll = self.db.bot_staff
        self.badges_coll = self.db.user_badges

        await self.staff_coll.create_index("user_id", unique=True)
        await self.badges_coll.create_index("user_id", unique=True)
        
        print("Owner Cog MongoDB Connected")
        await self.load_staff()

    
    async def load_staff(self):
        if self.staff_coll is None:
            return

        try:
            await self.client.wait_until_ready()
        except asyncio.CancelledError:
            # Task is being cancelled during bot shutdown
            return
        
        cursor = self.staff_coll.find({})
        self.staff = {doc['user_id'] for doc in await cursor.to_list(length=None)}

    @commands.command(name="staff_add", aliases=["staffadd", "addstaff"], help="Adds a user to the staff list.")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def staff_add(self, ctx, user: discord.User):
        if user.id in self.staff:
            Scyro = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description=f"{user} is already in the staff list.", color=0x2b2d31)
            await ctx.reply(embed=Scyro, mention_author=False)
        else:
            self.staff.add(user.id)
            await self.staff_coll.update_one(
                {"user_id": user.id},
                {"$set": {"user_id": user.id}},
                upsert=True
            )
            codex2 = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"Added {user} to the staff list.", color=0x2b2d31)
            await ctx.reply(embed=codex2, mention_author=False)

    @commands.command(name="staff_remove", aliases=["staffremove", "removestaff"], help="Removes a user from the staff list.")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def staff_remove(self, ctx, user: discord.User):
        if user.id not in self.staff:
            Scyro = discord.Embed(title="<a:alert:1396429026842644584> Access Denied", description=f"{user} is not in the staff list.", color=0x2b2d31)
            await ctx.reply(embed=Scyro, mention_author=False)
        else:
            self.staff.remove(user.id)
            await self.staff_coll.delete_one({"user_id": user.id})
            codex2 = discord.Embed(title="<:yes:1396838746862784582> Success", description=f"Removed {user} from the staff list.", color=0x2b2d31)
            await ctx.reply(embed=codex2, mention_author=False)

    @commands.command(name="staff_list", aliases=["stafflist", "liststaff", "staffs"], help="Lists all staff members.")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def staff_list(self, ctx):
        if not self.staff:
            await ctx.send("The staff list is currently empty.")
        else:
            member_list = []
            for staff_id in self.staff:
                member = await self.client.fetch_user(staff_id)
                member_list.append(f"{member.name}#{member.discriminator} (ID: {staff_id})")
            staff_display = "\n".join(member_list)
            Scyro = discord.Embed(title="<:automod:1348326413912248432> Scyro Staffs", description=f"\n{staff_display}", color=0x2b2d31)
            await ctx.send(embed=Scyro)

    @commands.command(name="zlist")
    @commands.check(is_owner_or_staff)
    async def _slist(self, ctx):
        codexop = sorted(self.client.guilds, key=lambda g: g.member_count, reverse=True)
        entries = [
            f"`#{i}` | [{g.name}](https://discord.com/guilds/{g.id}) - {g.member_count}"
            for i, g in enumerate(codexop, start=1)
        ]
        embeds = DescriptionEmbedPaginator(
            entries=entries,
            description="",
            title=f"Guild List of Scyro [{len(self.client.guilds)}]",
            color=0x2b2d31,
            per_page=10).get_pages()
        paginator = Paginator(ctx, embeds)
        await paginator.paginate()

    @commands.command(name="mutual", aliases=["mutuals"])
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def mutual_servers(self, ctx: Context, user: discord.User):
        
        if not user:
            await ctx.send("User not found.")
            return
        
        mutual_guilds = [guild for guild in self.client.guilds if user in guild.members]

        if mutual_guilds:
            entries = [
                f"`{no}` | [{guild.name}](https://discord.com/channels/{guild.id}) (ID: {guild.id})"
                for no, guild in enumerate(mutual_guilds, start=1)
            ]
            embeds = DescriptionEmbedPaginator(
                entries=entries,
                title=f"Mutual Guilds with {user.name} [{len(mutual_guilds)}]",
                description="",
                per_page=10,
                color=0x00ff00).get_pages()
            paginator = Paginator(ctx, embeds)
            await paginator.paginate()
        else:
            await ctx.send("No mutual guilds found.")

    @commands.command(name="getinvite", aliases=["gi", "getinvites"], help="Get invites for a guild or channel.")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def getinvite(self, ctx, guild_id: int = None, channel_id: int = None):
        guild = None
        channel = None

        if guild_id:
            guild = self.client.get_guild(guild_id)
            if not guild:
                await ctx.send("Invalid guild ID.")
                return
            
        elif channel_id:
            channel = self.client.get_channel(channel_id)
            if not channel:
                await ctx.send("Invalid channel ID.")
                return
            guild = channel.guild 

        else:
            await ctx.send("Please provide a guild ID or channel ID.")
            return

        can_create_invites = guild.me.guild_permissions.create_instant_invite if guild else False

        try:
            if guild_id:
                invites = await guild.invites()
                if invites:
                    embed = discord.Embed(
                        title=f"Active Invites for {guild.name}",
                        color=0xff0000
                    )
                    invites_list = [f"{invite.url} - {invite.uses} uses" for invite in invites]
                    embeds = DescriptionEmbedPaginator(
                        entries=invites_list,
                        title=f"Active Invites for {guild.name}",
                        description="",
                        per_page=10,
                        color=0xff0000).get_pages()
                    paginator = Paginator(ctx, embeds)
                    await paginator.paginate()
                elif can_create_invites:
                    
                    channel = guild.system_channel or next(
                        (ch for ch in guild.text_channels if ch.permissions_for(guild.me).create_instant_invite),
                        None
                    )
                    if channel:
                        invite = await channel.create_invite(max_age=604800, max_uses=None, reason="No active invites found, creating a new one.")
                        await ctx.send(f"Created new invite: {invite.url}")
                    else:
                        await ctx.send("No suitable channel found to create an invite.")
                else:
                    await ctx.send("Bot lacks permission to create invites for the guild.")

            
            elif channel_id:
                if channel.permissions_for(guild.me).create_instant_invite:
                    invite = await channel.create_invite(max_age=604800, max_uses=None, reason="Creating invite for the specified channel.")
                    await ctx.send(f"Created new invite for the channel: {invite.url}")
                else:
                    await ctx.send("Bot lacks permission to create invites for the specified channel.")

        except discord.Forbidden:
            await ctx.send("Bot lacks permission to access or create invites.")

    @commands.command(name="getguild")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def get_guild(self, ctx, channel_id: int):
        channel = self.client.get_channel(channel_id)

        if channel:
            guild = channel.guild
            embed = discord.Embed(
                title=f"Guild Information for {guild.name}",
                color=0x2b2d31
            )
            embed.add_field(name="Guild Name", value=guild.name)
            embed.add_field(name="Guild ID", value=guild.id)
            embed.add_field(name="Member Count", value=guild.member_count)
            embed.add_field(name="Owner", value=guild.owner)
            embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"))
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("Invalid channel ID or bot has no access to the channel.")
            
    @commands.command(name="restart", help="Restarts the client.")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def _restart(self, ctx: Context):
        await ctx.reply("Restarting Scyro...")
        restart_program()

    @commands.command(name="dsync", help="Syncs all database.")  # RENAMED FROM "sync"
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def _dbsync(self, ctx):
        await ctx.reply("Syncing...", mention_author=False)
        with open('events.json', 'r') as f:
            data = json.load(f)
        for guild in self.client.guilds:
            if str(guild.id) not in data['guild']:
                data['guilds'][str(guild.id)] = 'on'
                with open('events.json', 'w') as f:
                    json.dump(data, f, indent=4)
            else:
                pass
        with open('config.json', 'r') as f:
            data = json.load(f)
        for op in data["guilds"]:
            g = self.client.get_guild(int(op))
            if not g:
                data["guilds"].pop(str(op))
                with open('config.json', 'w') as f:
                    json.dump(data, f, indent=4)


    @commands.command(name="owners")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def own_list(self, ctx):
        nplist = OWNER_IDS
        npl = ([await self.client.fetch_user(nplu) for nplu in nplist])
        npl = sorted(npl, key=lambda nop: nop.created_at)
        entries = [
            f"`#{no}` | [{mem}](https://discord.com/users/{mem.id}) (ID: {mem.id})"
            for no, mem in enumerate(npl, start=1)
        ]
        embeds = DescriptionEmbedPaginator(
            entries=entries,
            title=f"Scyro Owners [{len(nplist)}]",
            description="",
            per_page=10,
            color=0x2b2d31).get_pages()
        paginator = Paginator(ctx, embeds)
        await paginator.paginate()





    @commands.command()
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def dm(self, ctx, user: discord.User, *, message: str):
        """ DM the user of your choice """
        try:
            await user.send(message)
            await ctx.send(f"<:yes:1396838746862784582> | Successfully Sent a DM to **{user}**")
        except discord.Forbidden:
            await ctx.send("This user might be having DMs blocked or it's a bot account...")           



    @commands.group()
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def change(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))


    @change.command(name="nickname")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def change_nickname(self, ctx, *, name: str = None):
        """ Change nickname. """
        try:
            await ctx.guild.me.edit(nick=name)
            if name:
                await ctx.send(f"<:yes:1396838746862784582> | Successfully changed nickname to **{name}**")
            else:
                await ctx.send("<:yes:1396838746862784582> | Successfully removed nickname")
        except Exception as err:
            await ctx.send(err) 


    @commands.command(name="ownerban", aliases=["forceban", "zban"])
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def _ownerban(self, ctx: Context, user_id: int, *, reason: str = "No reason provided"):
        
        member = ctx.guild.get_member(user_id)
        if member:
            try:
                await member.ban(reason=reason)
                embed = discord.Embed(
                    title="Successfully Banned",
                    description=f"<:yes:1396838746862784582> | **{member.name}** has been successfully banned from {ctx.guild.name} by the Bot Owner.",
                    color=0x2b2d31)
                await ctx.reply(embed=embed, mention_author=False, delete_after=3)
                await ctx.message.delete()
            except discord.Forbidden:
                embed = discord.Embed(
                    title="Error!",
                    description=f"<a:alert:1396429026842644584> I do not have permission to ban **{member.name}** in this guild.",
                    color=0x2b2d31
                )
                await ctx.reply(embed=embed, mention_author=False, delete_after=5)
                await ctx.message.delete()
            except discord.HTTPException:
                embed = discord.Embed(
                    title="Error!",
                    description=f"<a:alert:1396429026842644584> An error occurred while banning **{member.name}**.",
                    color=0x2b2d31
                )
                await ctx.reply(embed=embed, mention_author=False, delete_after=5)
                await ctx.message.delete()
        else:
            await ctx.reply("User not found in this guild.", mention_author=False, delete_after=3)
            await ctx.message.delete()

    @commands.command(name="ownerunban", aliases=["forceunban"])
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def _ownerunban(self, ctx: Context, user_id: int, *, reason: str = "No reason provided"):
        user = self.client.get_user(user_id)
        if user:
            try:
                await ctx.guild.unban(user, reason=reason)
                embed = discord.Embed(
                    title="Successfully Unbanned",
                    description=f"<:yes:1396838746862784582> | **{user.name}** has been successfully unbanned from {ctx.guild.name} by the Bot Owner.",
                    color=0x2b2d31
                )
                await ctx.reply(embed=embed, mention_author=False)
            except discord.Forbidden:
                embed = discord.Embed(
                    title="Error!",
                    description=f"<a:alert:1396429026842644584> I do not have permission to unban **{user.name}** in this guild.",
                    color=0x2b2d31
                )
                await ctx.reply(embed=embed, mention_author=False)
            except discord.HTTPException:
                embed = discord.Embed(
                    title="Error!",
                    description=f"<a:alert:1396429026842644584> An error occurred while unbanning **{user.name}**.",
                    color=0x2b2d31
                )
                await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.reply("User not found.", mention_author=False)



    @commands.command(name="globalunban")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def globalunban(self, ctx: Context, user: discord.User):
        success_guilds = []
        error_guilds = []

        for guild in self.client.guilds:
            bans = await guild.bans()
            if any(ban_entry.user.id == user.id for ban_entry in bans):
                try:
                    await guild.unban(user, reason="Global Unban")
                    success_guilds.append(guild.name)
                except discord.HTTPException:
                    error_guilds.append(guild.name)
                except discord.Forbidden:
                    error_guilds.append(guild.name)

        user_mention = f"{user.mention} (**{user.name}**)"

        success_message = f"Successfully unbanned {user_mention} from the following guild(s):\n{',     '.join(success_guilds)}" if success_guilds else "No guilds where the user was successfully unbanned."
        error_message = f"Failed to unban {user_mention} from the following guild(s):\n{',    '.join(error_guilds)}" if error_guilds else "No errors during unbanning."

        await ctx.reply(f"{success_message}\n{error_message}", mention_author=False)

    @commands.command(name="guildban")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def guildban(self, ctx: Context, guild_id: int, user_id: int, *, reason: str = "No reason provided"):
        guild = self.client.get_guild(guild_id)
        if not guild:
            await ctx.reply("Bot is not present in the specified guild.", mention_author=False)
            return

        member = guild.get_member(user_id)
        if member:
            try:
                await guild.ban(member, reason=reason)
                await ctx.reply(f"Successfully banned **{member.name}** from {guild.name}.", mention_author=False)
            except discord.Forbidden:
                await ctx.reply(f"Missing permissions to ban **{member.name}** in {guild.name}.", mention_author=False)
            except discord.HTTPException as e:
                await ctx.reply(f"An error occurred while banning **{member.name}** in {guild.name}: {str(e)}", mention_author=False)
        else:
            await ctx.reply(f"User not found in the specified guild {guild.name}.", mention_author=False)

    @commands.command(name="guildunban")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def guildunban(self, ctx: Context, guild_id: int, user_id: int, *, reason: str = "No reason provided"):
        guild = self.client.get_guild(guild_id)
        if not guild:
            await ctx.reply("Bot is not present in the specified guild.", mention_author=False)
            return
        #member = guild.get_member(user_id)

        try:
            user = await self.client.fetch_user(user_id)
        except discord.NotFound:
            await ctx.reply(f"User with ID {user_id} not found.", mention_author=False)
            return

        user = discord.Object(id=user_id)
        try:
            await guild.unban(user, reason=reason)
            await ctx.reply(f"Successfully unbanned user ID {user_id} from {guild.name}.", mention_author=False)
        except discord.Forbidden:
            await ctx.reply(f"Missing permissions to unban user ID {user_id} in {guild.name}.", mention_author=False)
        except discord.HTTPException as e:
            await ctx.reply(f"An error occurred while unbanning user ID {user_id} in {guild.name}: {str(e)}", mention_author=False)


    @commands.command(name="leaveguild")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def leave_guild(self, ctx, guild_id: int):
        guild = self.client.get_guild(guild_id)
        if guild is None:
            await ctx.send(f"Guild with ID {guild_id} not found.")
            return

        await guild.leave()
        await ctx.send(f"Left the guild: {guild.name} ({guild.id})")

    @commands.command(name="guildinfo")
    @commands.check(is_owner_or_staff)
    async def guild_info(self, ctx, guild_id: int):
        guild = self.client.get_guild(guild_id)
        if guild is None:
            await ctx.send(f"Guild with ID {guild_id} not found.")
            return

        embed = discord.Embed(
            title=guild.name,
            description=f"Information for guild ID {guild.id}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Owner", value=str(guild.owner), inline=True)
        embed.add_field(name="Member Count", value=str(guild.member_count), inline=True)
        embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        if guild.icon is not None:
                embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Created at: {guild.created_at}")

        await ctx.send(embed=embed)

    @commands.command()
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def servertour(self, ctx, time_in_seconds: int, member: discord.Member):
        guild = ctx.guild

        if time_in_seconds > 3600:
            await ctx.send("Time cannot be greater than 3600 seconds (1 hour).")
            return

        if not member.voice:
            await ctx.send(f"{member.display_name} is not in a voice channel.")
            return

        voice_channels = [ch for ch in guild.voice_channels if ch.permissions_for(guild.me).move_members]

        if len(voice_channels) < 2:
            await ctx.send("Not enough voice channels to move the user.")
            return

        self.stop_tour = False

        class StopButton(discord.ui.View):
            def __init__(self, outer_self):
                super().__init__(timeout=time_in_seconds)
                self.outer_self = outer_self

            @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
            async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id not in self.outer_self.bot_owner_ids:
                    await interaction.response.send_message("Only the bot owner can stop this process.", ephemeral=True)
                    return
                self.outer_self.stop_tour = True
                await interaction.response.send_message("Server tour has been stopped.", ephemeral=True)
                self.stop()

        view = StopButton(self)
        message = await ctx.send(f"Started moving {member.display_name} for {time_in_seconds} seconds. Click the button to stop.", view=view)

        end_time = asyncio.get_event_loop().time() + time_in_seconds

        while asyncio.get_event_loop().time() < end_time and not self.stop_tour:
            for ch in voice_channels:
                if self.stop_tour:
                    await ctx.send("Tour stopped.")
                    return
                if not member.voice:
                    await ctx.send(f"{member.display_name} left the voice channel.")
                    return
                try:
                    await member.move_to(ch)
                    await asyncio.sleep(1)
                except Forbidden:
                    await ctx.send(f"Missing permissions to move {member.display_name}.")
                    return
                except Exception as e:
                    await ctx.send(f"Error: {str(e)}")
                    return

        if not self.stop_tour:
            await message.edit(content=f"Finished moving {member.display_name} after {time_in_seconds} seconds.", view=None)

    @commands.command(name="sysync", help="Sync commands for the bot")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def sysync(self, ctx):
        """Sync commands for the bot"""
        embed = discord.Embed(
            title="🔄 Command Sync Started",
            description="Syncing commands for the bot...",
            color=0xffff00
        )
        msg = await ctx.send(embed=embed)
        
        try:
            # Sync commands
            synced = await self.client.tree.sync()
            
            success_embed = discord.Embed(
                title="✅ Commands Synced",
                description=f"Successfully synced {len(synced)} commands",
                color=0x00ff00
            )
            await msg.edit(embed=success_embed)
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Sync Failed",
                description=f"Failed to sync commands: {str(e)}",
                color=0xff0000
            )
            await msg.edit(embed=error_embed)

    @commands.group()
    @commands.check(is_owner_or_staff)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bdg(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(description='Invalid `bdg` command passed. Use `aad` or `remove`.', color=0x2b2d31)
            await ctx.send(embed=embed)

    @bdg.command(name="add")
    @commands.check(is_owner_or_staff)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bdg_add(self, ctx, member: discord.Member, badge: str):
        badge = badge.lower()
        user_id = member.id
        
        valid_badges = list(BADGE_URLS.keys()) + ['bug']
        if badge in valid_badges or badge == 'all':
            if badge == 'all':
                updates = {b: True for b in valid_badges}
                await self.badges_coll.update_one(
                    {"user_id": user_id},
                    {"$set": updates},
                    upsert=True
                )
                embed = discord.Embed(description=f"All badges added to {member.mention}.", color=0x2b2d31)
                await ctx.send(embed=embed)
            else:
                result = await self.badges_coll.update_one(
                    {"user_id": user_id},
                    {"$set": {badge: True}},
                    upsert=True
                )
                
                # Check if it was modified. If it was an upsert with existing true, it might not report modified.
                # Logic: We set it to True.
                embed = discord.Embed(description=f"Badge `{badge}` added to {member.mention}.", color=0x2b2d31)
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description=f"Invalid badge: `{badge}`", color=0x2b2d31)
            await ctx.send(embed=embed)

    @bdg.command(name="remove")
    @commands.check(is_owner_or_staff)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bdg_remove(self, ctx, member: discord.Member, badge: str):
        badge = badge.lower()
        user_id = member.id
        
        valid_badges = list(BADGE_URLS.keys()) + ['bug']
        if badge in valid_badges or badge == 'all':
            if badge == 'all':
                updates = {b: False for b in valid_badges}
                await self.badges_coll.update_one(
                    {"user_id": user_id},
                    {"$set": updates},
                    upsert=True
                )
                embed = discord.Embed(description=f"All badges removed from {member.mention}.", color=0x2b2d31)
                await ctx.send(embed=embed)
            else:
                # Check if they have it first to match old response logic?
                # Old logic: if result and result[0] == 1 ... else "does not have"
                doc = await self.badges_coll.find_one({"user_id": user_id})
                has_badge = doc and doc.get(badge, False)
                
                if has_badge:
                    await self.badges_coll.update_one(
                        {"user_id": user_id},
                        {"$set": {badge: False}}
                    )
                    embed = discord.Embed(description=f"Badge `{badge}` removed from {member.mention}.", color=0x2b2d31)
                else:
                    embed = discord.Embed(description=f"{member.mention} does not have the badge `{badge}`.", color=0x2b2d31)
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description=f"Invalid badge: `{badge}`", color=0x2b2d31)
            await ctx.send(embed=embed)


    @commands.command(name="forcepurgebots",
        aliases=["fpb"],
        help="Clear recently bot messages in channel (Bot owner only)")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    @commands.bot_has_permissions(manage_messages=True)
    async def _purgebot(self, ctx, prefix=None, search=100):
        
        await ctx.message.delete()
        
        def predicate(m):
            return (m.webhook_id is None and m.author.bot) or (prefix and m.content.startswith(prefix))
        
        await do_removal(ctx, search, predicate)


    @commands.command(name="forcepurgeuser",
        aliases=["fpu"],
        help="Clear recent messages of a user in channel (Bot owner only)")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    @commands.bot_has_permissions(manage_messages=True)
    async def purguser(self, ctx, member: discord.Member, search=100):
        
        await ctx.message.delete()
        
        await do_removal(ctx, search, lambda e: e.author == member)


    @commands.command(name="owner.help", aliases=['ownerhelp', 'owner-help'], hidden=True)
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)  # Use dynamic owner check
    async def _owner_help(self, ctx):
        
        embed = Embed(title="Owner Commands",
                      description="`staffadd` ,   `staffremove` ,   `stafflist` , `zlist` ,   `getinvite <guild-id>` ,   `getguild <channel-id>` ,   `mutual <user>` ,   `guildban <guild_id> <user_id>` ,   `guildunban <guild_id> <user_id>` ,   `restart` ,   `servertour` ,   `forcepurgebots` , `forcepurgeuser` ,   `zban,ownerban` , `bdg add <user> <badge>` ,   `bdg remove <user> <badge>` ,   `dsync` ,   `np <subcommand>` ,   `autonp <subcommand>`",
                      color=0x2b2d31)
        await ctx.send(embed=embed)


    @commands.group(name="dash")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def dash(self, ctx):
        if ctx.invoked_subcommand is None:
             await ctx.send_help(str(ctx.command))

    @dash.group(name="bl", aliases=["blacklist"])
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def dash_bl(self, ctx):
        if ctx.invoked_subcommand is None:
             await ctx.send_help(str(ctx.command))

    @dash_bl.command(name="add", aliases=["block"])
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def dash_bl_add(self, ctx, target: str, *, reason: str = "No reason provided"):
        """Block a User ID, Mention, or IP Address from the Dashboard."""
        
        # Determine blocked type
        blocked_type = "ip" if "." in target and not target.startswith("<@") else "user"
        valid_target = target
        
        if blocked_type == "user":
            # Clean mention
            try:
                user = await commands.UserConverter().convert(ctx, target)
                valid_target = str(user.id)
            except:
                if target.isdigit(): valid_target = target
                else: return await ctx.send("Invalid user or ID.")
        
        # Save to DB
        await self.db.dashboard_blacklist.update_one(
            {"value": valid_target},
            {"$set": {
                "type": blocked_type,
                "value": valid_target,
                "reason": reason,
                "timestamp": datetime.datetime.utcnow()
            }},
            upsert=True
        )
        
        embed = discord.Embed(
            title="<:yes:1396838746862784582> Dashboard Blocked",
            description=f"Successfully blocked **{valid_target}** ({blocked_type}) from accessing the dashboard.\nReason: {reason}",
            color=0x2b2d31
        )
        await ctx.reply(embed=embed, mention_author=False)

    @dash_bl.command(name="remove", aliases=["unblock", "unbl"])
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def dash_bl_remove(self, ctx, target: str):
        """Unblock a User ID, Mention, or IP Address."""
         # Determine blocked type cleanup
        valid_target = target
        if "." not in target: # Likely user
             try:
                user = await commands.UserConverter().convert(ctx, target)
                valid_target = str(user.id)
             except:
                if target.isdigit(): valid_target = target

        result = await self.db.dashboard_blacklist.delete_one({"value": valid_target})
        
        if result.deleted_count > 0:
             await ctx.reply(f"<:yes:1396838746862784582> Successfully unblocked **{valid_target}** from the dashboard.", mention_author=False)
        else:
             await ctx.reply(f"Target **{valid_target}** was not found in the blacklist.", mention_author=False)

    @dash_bl.command(name="list")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def dash_bl_list(self, ctx):
        cursor = self.db.dashboard_blacklist.find({})
        entries = await cursor.to_list(length=None)
        
        if not entries:
            return await ctx.send("Dashboard blacklist is empty.")
            
        lines = []
        for e in entries:
            lines.append(f"`{e['type'].upper()}`: **{e['value']}** | Reason: {e.get('reason', 'None')}")
            
        paginator = DescriptionEmbedPaginator(
            entries=lines,
            title=f"Dashboard Blacklist [{len(entries)}]",
            description="",
            per_page=10,
            color=0x2b2d31
        ).get_pages()
        await Paginator(ctx, paginator).paginate()

    @dash_bl.command(name="reset")
    @commands.check(lambda ctx: ctx.author.id in BOT_OWNERS)
    async def dash_bl_reset(self, ctx):
        view = ConfirmView(ctx.author.id)
        msg = await ctx.reply("Are you sure you want to **RESET** the entire dashboard blacklist?", view=view, mention_author=False)
        await view.wait()
        
        if view.value:
            await self.db.dashboard_blacklist.delete_many({})
            await msg.edit(content="<:yes:1396838746862784582> Dashboard blacklist has been reset.", view=None)
        else:
             await msg.edit(content="Action cancelled.", view=None)



class Badges(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.badges_coll = None
        self.bot.loop.create_task(self.setup_db())

    async def setup_db(self):
        if not self.mongo_uri: return
        self.client_mongo = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client_mongo.get_database()
        self.badges_coll = self.db.user_badges

    @commands.hybrid_command(aliases=['profile', 'pr'])
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def badges(self, ctx, member: discord.Member = None):
        processing_message = await ctx.send("⌛ Loading your profile...")
        member = member or ctx.author
        user_id = member.id
        
        # Connect to DB if not ready (safety)
        if self.badges_coll is None and self.mongo_uri:
             await self.setup_db()

        badges = {k: False for k in BADGE_URLS.keys()}
        
        if self.badges_coll is not None:
            doc = await self.badges_coll.find_one({"user_id": user_id})
            if doc:
                # Update defaults with DB values
                for k in badges.keys():
                    if doc.get(k): badges[k] = True

        
        badge_size = 120
        padding = 80
        num_columns = 4
        image_width = 960
        image_height = 540



        def calculate_text_dimensions(badge_name, font, padding=1):
            text_bbox = draw.textbbox((0, 0), badge_name, font=font)
            text_width = (text_bbox[2] - text_bbox[0]) + 2 * padding
            text_height = (text_bbox[3] - text_bbox[1]) + 2 * padding
            return text_width, text_height

        
        def draw_badges(badges, draw, img):

            
            upper_y = (image_height // 4) - (badge_size // 2)
            lower_y = (3 * image_height // 4) - (badge_size // 2)
            
            x_positions = [padding + i * ((image_width - 2 * padding) // (num_columns - 1)) for i in range(num_columns)]

            badge_positions = []
            for badge in BADGE_URLS.keys():
                if badges[badge]:
                    badge_positions.append(badge)

            for i, badge in enumerate(badge_positions):
                y = upper_y if i < num_columns else lower_y
                x = x_positions[i % num_columns]
                try:
                    response = requests.get(BADGE_URLS[badge], timeout=5)
                    response.raise_for_status()
                    badge_img = Image.open(BytesIO(response.content)).resize((badge_size, badge_size))
                    img.paste(badge_img, (x - badge_size // 2, y), badge_img)
                    text_width, text_height = calculate_text_dimensions(BADGE_NAMES[badge], font)
                    draw.text((x - text_width // 2, y + badge_size + 5), BADGE_NAMES[badge], fill=(255, 0, 0), font=font)
                except Exception as e:
                    print(f"Failed to load badge {badge} from {BADGE_URLS[badge]}: {e}")
                    # Optional: Draw a placeholder or skip
                    continue  

        
        has_badges = any(value == 1 for value in badges.values())

        if has_badges:
            
            img = Image.new('RGBA', (image_width, image_height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)
            font = ImageFont.truetype(FONT_PATH, 25)  

            
            draw_badges(badges, draw, img)

            with BytesIO() as image_binary:
                img.save(image_binary, 'PNG')
                image_binary.seek(0)
                file = discord.File(fp=image_binary, filename='badge.png')

            embed = discord.Embed(title=f"{member.display_name}'s Profile", color=0x2b2d31)

            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)
            else:
                embed.set_thumbnail(url=member.default_avatar.url)
            embed.add_field(name="__**Account Created At**__", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=True)
            embed.add_field(name="__**Joined This Guild At**__", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=True)



            # User Badges
            user_flags = member.public_flags
            user_badges = []

            badge_mapping = {
              "staff": "<:89807yellowadmingradient:1409180629542633483> Discord Employee",
              "partner": "<:49532partner:1409180501633142956> Partnered Server Owner",
              "discord_certified_moderator": "<:49548donateadmin:1409180518058168440> Moderator Programs Alumni",
              "hypesquad_balance": "<:58534hypersquadbalanceking:1409180556054495273> House Balance Member",
              "hypesquad_bravery": "<:7878iconhypesquadbravery:1409180443923976212> House Bravery Member",
              "hypesquad_brilliance": "<<:60978hypersquadbrilliance:1409180585997500498> House Brilliance Member",
              "hypesquad": "<:HypeEvent:1219284814214205531> HypeSquad Events Member",
              "early_supporter": "<:518379earlysupporterbadge:1409180652859035708> Early Supporter",
              "bug_hunter": "<:14433bughunter:1409180480116625481> Bug Hunter Level 1",
              "bug_hunter_level_2": "<:14433bughunter:1409180480116625481> Bug Hunter Level 2",
              "verified_bot": "<:9097verifiedbot:1409180467701354658> Verified Bot",
              "verified_bot_developer": "<:4323blurpleverifiedbotdeveloper:1409180433937338429> Verified Bot Developer",
              "active_developer": "<:63557discordactivedeveloper:1409180602581909667> Active Developer",
              "early_verified_bot_developer": "<:4323blurpleverifiedbotdeveloper:1409180433937338429>> Early Verified Bot Developer",
              "system": "<:7305_tabs:1409445000378454067> System User",
              "team_user": "<:21444android:1409180489863921675> User is a [Team](https://discord.com/developers/docs/topics/teams)",
              "spammer": "<:70802purplespammeralert:1409180642452967595> Marked as Spammer",
              "bot_http_interactions": "<:bot:1409157600775372941> Bot uses only [HTTP interactions](https://discord.com/developers/docs/interactions/receiving-and-responding#receiving-an-interaction) and is shown in the online member list."
            }

            for flag, value in badge_mapping.items():
              if getattr(user_flags, flag):
                user_badges.append(value)

            
            user = await self.bot.fetch_user(member.id)
            wtf = bool(user.avatar and user.avatar.is_animated())
            omg = bool(user.banner)
            if not member.bot:
                if omg or wtf:
                    user_badges.append("<:nitro:1409182140616151150> Nitro Subscriber")
                for guild in self.bot.guilds:
                    if member in guild.members:
                        if guild.premium_subscription_count > 0 and member in guild.premium_subscribers:
                            user_badges.append("<:boost:1409163194336940163> Server Booster Badge")
                            
            if user_badges:
              embed.add_field(name="__**User Badges**__", value="\n".join(user_badges), inline=False)
            else:
              embed.add_field(name="__**User Badges**__", value="None", inline=False)

            # Bot Badges
            embed.add_field(name="__**Bot Badges**__", value="Below", inline=False)
            embed.set_image(url="attachment://badge.png")
            embed.set_footer(text=f"Requested by {ctx.author} | Nitro badge if banner/animated avatar; Booster badge if boosting a mutual guild with bot.", icon_url=ctx.author.avatar.url
                               if ctx.author.avatar else ctx.author.default_avatar.url)

            await ctx.send(embed=embed, file=file)
            await processing_message.delete()
        else:
            embed = discord.Embed(title=f"{member.display_name}'s Profile", color=0x2b2d31)

            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)
            else:
                embed.set_thumbnail(url=member.default_avatar.url)
            embed.add_field(name="__**Account Created At**__", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=True)
            embed.add_field(name="__**Joined This Guild At**__", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=True)




            # User Badges
            user_flags = member.public_flags
            user_badges = []

            badge_mapping = {
              "staff": "<:89807yellowadmingradient:1409180629542633483> Discord Employee",
              "partner": "<:49532partner:1409180501633142956> Partnered Server Owner",
              "discord_certified_moderator": "<:49548donateadmin:1409180518058168440> Moderator Programs Alumni",
              "hypesquad_balance": "<:58534hypersquadbalanceking:1409180556054495273> House Balance Member",
              "hypesquad_bravery": "<:7878iconhypesquadbravery:1409180443923976212> House Bravery Member",
              "hypesquad_brilliance": "<<:60978hypersquadbrilliance:1409180585997500498> House Brilliance Member",
              "hypesquad": "<:HypeEvent:1219284814214205531> HypeSquad Events Member",
              "early_supporter": "<:518379earlysupporterbadge:1409180652859035708> Early Supporter",
              "bug_hunter": "<:14433bughunter:1409180480116625481> Bug Hunter Level 1",
              "bug_hunter_level_2": "<:14433bughunter:1409180480116625481> Bug Hunter Level 2",
              "verified_bot": "<:9097verifiedbot:1409180467701354658> Verified Bot",
              "verified_bot_developer": "<:4323blurpleverifiedbotdeveloper:1409180433937338429> Verified Bot Developer",
              "active_developer": "<:63557discordactivedeveloper:1409180602581909667> Active Developer",
              "early_verified_bot_developer": "<:4323blurpleverifiedbotdeveloper:1409180433937338429>> Early Verified Bot Developer",
              "system": "<:7305_tabs:1409445000378454067> System User",
              "team_user": "<:21444android:1409180489863921675> User is a [Team](https://discord.com/developers/docs/topics/teams)",
              "spammer": "<:70802purplespammeralert:1409180642452967595> Marked as Spammer",
              "bot_http_interactions": "<:bot:1409157600775372941> Bot uses only [HTTP interactions](https://discord.com/developers/docs/interactions/receiving-and-responding#receiving-an-interaction) and is shown in the online member list."
            }

            for flag, value in badge_mapping.items():
              if getattr(user_flags, flag):
                user_badges.append(value)

            user = await self.bot.fetch_user(member.id)
            wtf = bool(user.avatar and user.avatar.is_animated())
            omg = bool(user.banner)
            if not member.bot:
                if omg or wtf:
                    user_badges.append("<:nitro:1409182140616151150> Nitro Subscriber")
                for guild in self.bot.guilds:
                    if member in guild.members:
                        if guild.premium_subscription_count > 0 and member in guild.premium_subscribers:
                            user_badges.append("<:boost:1409163194336940163> Server Booster Badge")

            if user_badges:
              embed.add_field(name="__**User Badges**__", value="\n".join(user_badges), inline=False)
            else:
              embed.add_field(name="__**User Badges**__", value="None", inline=False)

            # Bot Badges
            embed.add_field(name="__**Bot Badges**__", value="No bot badges", inline=False)
            embed.set_footer(text=f"Requested by {ctx.author} | Nitro badge if banner/animated avatar; Booster badge if boosting a mutual guild with bot.", icon_url=ctx.author.avatar.url
                               if ctx.author.avatar else ctx.author.default_avatar.url)

            await ctx.send(embed=embed)
            await processing_message.delete()