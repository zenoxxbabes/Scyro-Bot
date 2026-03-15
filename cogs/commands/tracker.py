import discord
from discord.ext import commands
import os
import time
import io
import aiohttp
import math
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import motor.motor_asyncio
from typing import Optional
from discord import app_commands

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & COLORS
# ════════════════════════════════════════════════════════════════════════════

# --- CUSTOM FONT PATHS ---
FONT_HEADING_PATH = os.path.join("data", "tracker", "heading.ttf")
FONT_BODY_PATH = os.path.join("data", "tracker", "other.ttf")

# --- COLORS ---
COLOR_BG = "#23272A"       
COLOR_CARD = "#2C2F33"     
COLOR_EMBED = 0x2B2D31     
COLOR_ACCENT = "#9b59b6" # Updated to Purple (Amethyst)
COLOR_TEXT_MAIN = "#FFFFFF"
COLOR_TEXT_SUB = "#B9BBBE"
DEFAULT_COLOR = 0x2B2D31 # Assuming this is the same as COLOR_EMBED

# --- HELPER FUNCTIONS ---

def get_level(xp):
    return int(math.sqrt(xp / 50))

def create_progress_bar(xp, level, length=10):
    # Match leveling.py formula: xp for level L = 50 * L^2
    current_lvl_xp = 50 * (level ** 2)
    next_lvl_xp = 50 * ((level + 1) ** 2)
    needed = next_lvl_xp - current_lvl_xp
    current = xp - current_lvl_xp
    
    progress = current / needed if needed > 0 else 0
    filled = int(length * progress)
    return "■" * filled + "□" * (length - filled)

async def get_avatar_image(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).convert("RGBA")
    except: return None
    return None

def draw_rounded_rect(draw, xy, corner_radius, fill=None, outline=None):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1, y1, x2, y2), radius=corner_radius, fill=fill, outline=outline, width=2)

def create_circular_mask(h):
    mask = Image.new('L', (h, h), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, h, h), fill=255)
    return mask

def draw_centered_text(draw, xy, text, font, fill):
    length = font.getlength(text)
    draw.text((xy[0] - (length / 2), xy[1]), text, font=font, fill=fill)

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()

# --- IMAGE GENERATION ---

async def generate_pro_leaderboard(bot, guild, sorted_rows, title_text):
    width, row_height, header_height, padding = 900, 120, 130, 20
    total_height = header_height + (len(sorted_rows) * (row_height + padding)) + padding
    
    # Run image gen in executor to avoid blocking
    def make_image():
        img = Image.new("RGBA", (width, total_height), COLOR_BG)
        draw = ImageDraw.Draw(img)
        
        font_header = load_font(FONT_HEADING_PATH, 60)
        font_rank = load_font(FONT_HEADING_PATH, 50)
        font_name = load_font(FONT_BODY_PATH, 35)
        font_sub = load_font(FONT_BODY_PATH, 24)

        draw.text((40, 30), title_text.upper(), font=font_header, fill=COLOR_ACCENT)
        draw.line([(40, 100), (width - 40, 100)], fill=COLOR_CARD, width=3)
        return img, draw, font_rank, font_name, font_sub, row_height, header_height, padding

    # Create base
    img, draw, font_rank, font_name, font_sub, row_height, header_height, padding = await bot.loop.run_in_executor(None, make_image)


    for idx, row in enumerate(sorted_rows):
        user_id, xp, msg_count, voice_time, level = row
        user = guild.get_member(int(user_id))
        username = user.display_name if user else "Unknown User"
        y_pos = header_height + (idx * (row_height + padding))
        
        rank_c = ["#FFD700", "#C0C0C0", "#CD7F32"][idx] if idx < 3 else "#5d5d5d"
        
        def draw_row(current_img, current_draw, u_name):
            draw_rounded_rect(current_draw, (30, y_pos, 900 - 30, y_pos + row_height), 25, fill=COLOR_CARD, outline=rank_c if idx == 0 else None)
            current_draw.text((60, y_pos + 30), f"#{idx + 1}", font=font_rank, fill=rank_c)
            current_draw.text((300, y_pos + 25), u_name, font=font_name, fill=COLOR_TEXT_MAIN)
            current_draw.text((300, y_pos + 70), f"LVL: {get_level(xp)}  |  XP: {int(xp)}", font=font_sub, fill=COLOR_TEXT_SUB)
        
        await bot.loop.run_in_executor(None, draw_row, img, draw, username)

        
        if user:
            asset = user.avatar.url if user.avatar else user.default_avatar.url
            avatar_img = await get_avatar_image(asset)
            if avatar_img:
                def paste_avatar():
                    img.paste(avatar_img.resize((90, 90)), (180, y_pos + 15), create_circular_mask(90))
                await bot.loop.run_in_executor(None, paste_avatar)


    buffer = io.BytesIO()
    await bot.loop.run_in_executor(None, img.save, buffer, "PNG")

    buffer.seek(0)
    return buffer

def generate_pro_graph(msg_count, voice_minutes, member_name):
    W, H = 600, 450 
    img = Image.new("RGBA", (W, H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title = load_font(FONT_HEADING_PATH, 40)
    font_val = load_font(FONT_BODY_PATH, 30)
    font_label = load_font(FONT_BODY_PATH, 25)

    draw_rounded_rect(draw, (10, 10, W-10, H-10), 25, fill=COLOR_CARD)

    draw.text((40, 40), "Activity Overview", font=font_title, fill="white")
    draw.text((40, 90), f"Stats for {member_name}", font=font_label, fill=COLOR_ACCENT)

    max_val = max(msg_count, voice_minutes, 5)
    bar_max_h, base_y, w = 200, 390, 100             

    h_msg = (msg_count / max_val) * bar_max_h
    h_vc = (voice_minutes / max_val) * bar_max_h

    # Messages
    x1 = 120
    cx1 = x1 + (w/2)
    draw_rounded_rect(draw, (x1, base_y - h_msg, x1 + w, base_y), 15, fill=COLOR_ACCENT)
    draw_centered_text(draw, (cx1, base_y - h_msg - 45), str(msg_count), font_val, "white")
    draw_centered_text(draw, (cx1, base_y + 20), "Messages", font_label, COLOR_TEXT_SUB)

    # Voice
    x2 = 380
    cx2 = x2 + (w/2)
    draw_rounded_rect(draw, (x2, base_y - h_vc, x2 + w, base_y), 15, fill="#8e44ad") # Darker Purple
    draw_centered_text(draw, (cx2, base_y - h_vc - 45), f"{int(voice_minutes)}m", font_val, "white")
    draw_centered_text(draw, (cx2, base_y + 20), "Voice", font_label, COLOR_TEXT_SUB)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

async def generate_server_banner(bot, guild):
    W, H = 800, 300
    # Run in executor
    def make_banner():
        img = Image.new("RGBA", (W, H), COLOR_BG)
        draw = ImageDraw.Draw(img)
        font_name = load_font(FONT_HEADING_PATH, 50)
        font_stat = load_font(FONT_BODY_PATH, 28)
        draw_rounded_rect(draw, (0, 0, W, H), 30, fill=COLOR_CARD)
        draw.text((230, 60), guild.name, font=font_name, fill="white")
        col1, col2 = 230, 520
        row1, row2 = 140, 190
        draw.text((col1, row1), f"Members: {guild.member_count}", font=font_stat, fill=COLOR_TEXT_SUB)
        draw.text((col1, row2), f"Boosts: {guild.premium_subscription_count}", font=font_stat, fill="#FF73FA")
        if guild.owner:
             draw.text((col2, row1), f"Owner: {guild.owner.name}", font=font_stat, fill="#F1C40F")
        draw.text((col2, row2), f"Created: {guild.created_at.strftime('%m/%y')}", font=font_stat, fill=COLOR_TEXT_SUB)
        return img

    img = await bot.loop.run_in_executor(None, make_banner)

    
    if guild.icon:
        icon_img = await get_avatar_image(guild.icon.url)
        if icon_img:
            def paste_icon():
                img.paste(icon_img.resize((150, 150)), (50, 75), create_circular_mask(150))
            await bot.loop.run_in_executor(None, paste_icon)


    buffer = io.BytesIO()
    await bot.loop.run_in_executor(None, img.save, buffer, "PNG")

    buffer.seek(0)
    return buffer

# --- VIEW CLASS ---

class LeaderboardView(discord.ui.View):
    def __init__(self, guild, bot):
        super().__init__(timeout=60)
        self.guild = guild
        self.bot = bot

    @discord.ui.select(
        placeholder="Filter Leaderboard",
        min_values=1, max_values=1,
        options=[
            discord.SelectOption(label="Top XP", value="xp", emoji="✨"),
            discord.SelectOption(label="Top Messages", value="msg", emoji="💬"),
            discord.SelectOption(label="Top Voice", value="voice", emoji="🎙️")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        
        val = select.values[0]
        if val == 'msg':
            sort_col = "msg_count" 
            title = "Top Messages"
        elif val == 'voice':
            sort_col = "voice_time"
            title = "Top Voice Time"
        else:
            sort_col = "xp"
            title = "Top XP"
        
        # This part needs to be updated to use MongoDB if this view is kept
        # raw_rows = await get_leaderboard_data(self.guild.id, sort_col, limit=50)
        # valid_rows = []
        # for row in raw_rows:
        #     if self.guild.get_member(int(row[0])):
        #         valid_rows.append(row)
        #     if len(valid_rows) >= 10: break
                
        # image_buffer = await generate_pro_leaderboard(self.bot, self.guild, valid_rows, title)

        # file = discord.File(fp=image_buffer, filename="leaderboard.png")
        # embed = discord.Embed(color=COLOR_EMBED)
        # embed.set_image(url="attachment://leaderboard.png")
        
        # await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
        await interaction.edit_original_response(content="Leaderboard filtering is not yet implemented with the new database.", view=self)


# --- COG CLASS ---

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.analytics = self.db["leveling_users"]

    async def get_user_data(self, guild_id, user_id):
        # We store guild_id as well to keep data separated per guild if needed, 
        # or globally. The original SQLite had guild_id involved.
        data = await self.analytics.find_one({"guild_id": guild_id, "user_id": user_id})
        if not data:
             data = {"guild_id": guild_id, "user_id": user_id, "msg_count": 0, "voice_time": 0, "xp": 0, "level": 0}
        
        # Map fields to match legacy expectation if needed (msg_count -> messages)
        # But let's stick to consistent naming: msg_count in original code.
        return {
            "xp": data.get("xp", 0),
            "msg_count": data.get("msg_count", 0), 
            "voice_time": data.get("voice_time", 0),
            "level": data.get("level", 0)
        }

    async def get_leaderboard_data(self, guild_id, sort_col, limit=20):
        # sort_col: xp, msg_count, voice_time
        # Map msg_count to messages in DB if we used that
        db_col = "msg_count" if sort_col == "msg_count" else sort_col
        
        cursor = self.analytics.find({"guild_id": guild_id}).sort(db_col, -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        
        # Return format similar to SQLite fetchall: list of tuples/dicts
        # Original: user_id, xp, msg_count, voice_time, level
        res = []
        for d in docs:
            res.append((
                d['user_id'], 
                d.get('xp', 0), 
                d.get('msg_count', 0), 
                d.get('voice_time', 0), 
                d.get('level', 0)
            ))
        return res

    async def get_user_rank(self, guild_id, user_id):
        user_doc = await self.analytics.find_one({"guild_id": guild_id, "user_id": user_id})
        if not user_doc: return "N/A"
        
        count = await self.analytics.count_documents({
            "guild_id": guild_id, 
            "xp": {"$gt": user_doc.get("xp", 0)}
        })
        return count + 1

    async def get_top_stat_user(self, guild, sort_col):
        db_col = "msg_count" if sort_col == "msg_count" else sort_col
        cursor = self.analytics.find({"guild_id": guild.id}).sort(db_col, -1).limit(1)
        doc = await cursor.to_list(length=1)
        if doc:
            return guild.get_member(doc[0]['user_id'])
        return None

    # --- COMMANDS ---

    @commands.hybrid_command(name='leaderboard', aliases=['lb'], description="Check the server activity leaderboard")
    @commands.cooldown(1, 10, commands.BucketType.user) 
    async def leaderboard(self, ctx):
        msg = await ctx.send("<a:loadingbro:1456977689922769080> Gathering Data...")

        # Default sort by XP
        raw_rows = await self.get_leaderboard_data(ctx.guild.id, "xp", limit=50)
        print(f"DEBUG: Leaderboard - Guild {ctx.guild.id} - Raw Rows: {len(raw_rows)}")
        
        valid_rows = []
        for row in raw_rows:
            uid = row[0]
            member = ctx.guild.get_member(int(uid))
            if member:
                valid_rows.append(row)
            else:
                print(f"DEBUG: Leaderboard - Member {uid} not found in cache.")
            
            if len(valid_rows) >= 10: break
        
        print(f"DEBUG: Leaderboard - Valid Rows: {len(valid_rows)}")

        image_buffer = await generate_pro_leaderboard(ctx.bot, ctx.guild, valid_rows, "Leaderboard")

        file = discord.File(fp=image_buffer, filename="leaderboard.png")
        
        embed = discord.Embed(title="🏆 Server Rankings", description=f"Top 10 most active members in **{ctx.guild.name}**.", color=COLOR_EMBED)
        embed.set_image(url="attachment://leaderboard.png")
        
        await msg.edit(content=None, embed=embed, attachments=[file], view=LeaderboardView(ctx.guild, ctx.bot))


    @commands.command(name='userstats', aliases=['us'])
    @commands.cooldown(1, 5, commands.BucketType.user) 
    async def userstats(self, ctx, member: discord.Member = None):
        msg = await ctx.send("<a:loadingbro:1456977689922769080> Gathering Data...")

        member = member or ctx.author
        uid = member.id
        user_data = await self.get_user_data(ctx.guild.id, uid)
        
        final_xp = user_data['xp']
        final_level = user_data['level']
        msg_count = user_data['msg_count']
        voice_time = user_data['voice_time']
        
        rank = await self.get_user_rank(ctx.guild.id, uid)
        
        graph_buffer = await self.bot.loop.run_in_executor(None, generate_pro_graph, msg_count, voice_time, member.display_name)
        file = discord.File(fp=graph_buffer, filename="stats.png")

        embed = discord.Embed(description=f"### 📊 Activity Profile: {member.mention}", color=COLOR_EMBED)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        
        joined = member.joined_at.strftime("%b %d, %Y")
        created = member.created_at.strftime("%b %d, %Y")
        embed.add_field(name="📅 Joined Server", value=f"`{joined}`", inline=True)
        embed.add_field(name="🍰 Account Created", value=f"`{created}`", inline=True)
        
        roles = len(member.roles) - 1
        embed.add_field(name="🎭 Roles", value=f"`{roles}`", inline=True)
        embed.add_field(name="🏆 Rank", value=f"`#{rank}`", inline=True)
        embed.add_field(name="⚡ Level", value=f"`{final_level}`", inline=True)
        
        bar = create_progress_bar(final_xp, final_level)
        embed.add_field(name=f"✨ XP Progress ({int(final_xp)})", value=f"`{bar}`", inline=False)
        embed.set_image(url="attachment://stats.png")
        embed.set_footer(text=f"User ID: {member.id}")
        
        await msg.edit(content=None, embed=embed, attachments=[file])

    @commands.command(name='serverstats', aliases=['ss'])
    @commands.cooldown(1, 10, commands.BucketType.user) 
    async def serverstats(self, ctx):
        msg = await ctx.send("<a:loadingbro:1456977689922769080> Gathering Data...")

        guild = ctx.guild
        banner_buffer = await generate_server_banner(ctx.bot, guild)

        file = discord.File(fp=banner_buffer, filename="server_stats.png")
        
        embed = discord.Embed(description=f"### 📈 Overview: {guild.name}", color=COLOR_EMBED)
        embed.set_image(url="attachment://server_stats.png")
        
        def format_top(member): return member.mention if member else "`None`"
        top_msg = await self.get_top_stat_user(guild, "msg_count")
        top_vc = await self.get_top_stat_user(guild, "voice_time")

        emojis = len(guild.emojis)
        roles = len(guild.roles)
        stickers = len(guild.stickers)
        embed.add_field(name="🎨 Assets", value=f"Emojis: `{emojis}`\nStickers: `{stickers}`\nRoles: `{roles}`", inline=True)
        
        txt = len(guild.text_channels)
        vc = len(guild.voice_channels)
        cats = len(guild.categories)
        embed.add_field(name="💬 Channels", value=f"Text: `{txt}`\nVoice: `{vc}`\nCats: `{cats}`", inline=True)

        embed.add_field(name="🔥 Top Chatter", value=format_top(top_msg), inline=True)
        embed.add_field(name="🎤 Top Speaker", value=format_top(top_vc), inline=True)
        embed.set_footer(text=f"Server ID: {guild.id} • Security: {guild.verification_level}")
        
        await msg.edit(content=None, embed=embed, attachments=[file])

    @leaderboard.error
    @userstats.error
    @serverstats.error
    async def on_tracker_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"<a:7596clock:1413390466979991572> Please wait **{error.retry_after:.1f}s** before using this command again.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"<:no:1396838761605890090> Could not find member **{error.argument}**.", delete_after=10)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Tracker(bot))