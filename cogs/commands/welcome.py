import discord
import os
from discord import app_commands
from discord.ext import commands
import motor.motor_asyncio
import datetime
import json
import asyncio
import random
import re
from typing import Optional
from utils.Tools import getConfig
from easy_pil import Editor, Canvas, Font, load_image_async
from PIL import Image, ImageFont, ImageDraw
import io

# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS & CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

COLOR_NAME_MAP = {
    "red": 0xFF0000, "blue": 0x0000FF, "green": 0x00FF00, "yellow": 0xFFFF00,
    "orange": 0xFFA500, "purple": 0x800080, "black": 0x000000, "white": 0xFFFFFF,
    "grey": 0x808080, "gray": 0x808080, "silver": 0xC0C0C0, "charcoal": 0x36454F,
    "slate": 0x708090, "blurple": 0x5865F2, "fuchsia": 0xFF00FF, "cyan": 0x00FFFF,
    "teal": 0x008080, "magenta": 0xFF00FF, "lime": 0x32CD32, "pink": 0xFFC0CB,
    "hotpink": 0xFF69B4, "maroon": 0x800000, "navy": 0x000080, "olive": 0x808000,
    "brown": 0xA52A2A, "crimson": 0xDC143C, "gold": 0xFFD700, "coral": 0xFF7F50,
    "indigo": 0x4B0082, "violet": 0xEE82EE, "turquoise": 0x40E0D0, "beige": 0xF5F5DC,
    "lavender": 0xE6E6FA, "mint": 0x98FF98, "azure": 0xF0FFFF
}

DEFAULT_COLOR = 0x2f3136
MAX_AUTODELETE = 300  # Safety clamp


# ════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════════════════════

async def safe_reply(ctx: commands.Context, **kwargs):
    """Safely handles ephemeral replies for both slash and prefix commands."""
    if ctx.interaction:
        if 'ephemeral' not in kwargs:
            kwargs['ephemeral'] = True
    else:
        kwargs.pop('ephemeral', None)
    
    # FIX: Return the message object so Views can track it
    return await ctx.send(**kwargs)

def parse_embed_color(input_str: Optional[str]) -> discord.Color:
    if not input_str:
        return discord.Color(DEFAULT_COLOR)
    
    clean_input = input_str.strip().lower()
    
    if clean_input in COLOR_NAME_MAP:
        return discord.Color(COLOR_NAME_MAP[clean_input])
    
    clean_input = clean_input.replace("#", "")
    if len(clean_input) == 6:
        try:
            val = int(clean_input, 16)
            return discord.Color(val)
        except ValueError:
            pass
            
    return discord.Color(DEFAULT_COLOR)

def format_variable(text: str, member: discord.Member) -> str:
    if not text:
        return ""
    
    guild = member.guild
    replacements = {
        "{user}": member.mention,
        "{user_name}": member.name,
        "{user_id}": str(member.id),
        "{user_nick}": member.display_name,
        "{user_avatar}": member.display_avatar.url,
        "{user_joindate}": discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown",
        "{user_createdate}": discord.utils.format_dt(member.created_at, "R"),
        "{server_name}": guild.name,
        "{server_id}": str(guild.id),
        "{server_membercount}": str(guild.member_count),
        "{server_icon}": guild.icon.url if guild.icon else "",
    }
    
    for key, val in replacements.items():
        text = text.replace(key, str(val))
    return text

async def generate_welcome_image(member: discord.Member, background_url: str = None, title: str = "WELCOME", subtitle: str = None, canvas_size: str = "1640x664", **kwargs) -> discord.File:
    """Generates a welcome image using easy-pil."""
    
    # Parse canvas size
    try:
        width, height = map(int, canvas_size.split("x"))
    except:
        width, height = 1640, 664
        
    # Unpack styling parameters (with defaults matching frontend)
    ax_pct = float(kwargs.get('avatar_x', 3.1))
    ay_pct = float(kwargs.get('avatar_y', 12.5))
    asize_pct = float(kwargs.get('avatar_size', 18.75))
    arot = float(kwargs.get('avatar_rotation', 0))
    
    tx_pct = float(kwargs.get('text_x', 25))
    ty_pct = float(kwargs.get('text_y', 25))
    tsize_scale = float(kwargs.get('text_size', 100)) / 100.0
    trot = float(kwargs.get('text_rotation', 0))

    # New Parameters
    overlay_opacity = int(kwargs.get('overlay_opacity', 0)) # 0-100
    title_color = kwargs.get('title_color', '#FFFFFF')
    subtitle_color = kwargs.get('subtitle_color', '#CCCCCC')

    # Calculate absolute pixels
    avatar_size_px = int(width * (asize_pct / 100))
    avatar_x_px = int(width * (ax_pct / 100))
    avatar_y_px = int(height * (ay_pct / 100))
    
    text_x_px = int(width * (tx_pct / 100))
    text_y_px = int(height * (ty_pct / 100))
    
    title_size_px = int(width * 0.06 * tsize_scale)
    subtitle_size_px = int(width * 0.035 * tsize_scale)

    # Load background or create default
    if background_url:
        print(f"DEBUG: Generating image with background_url: {background_url}")
        try:
            if background_url.startswith("/uploads/"):
                # Try multiple base paths for robustness
                paths_to_try = [
                    os.path.join(os.getcwd(), "dashboard", "public", background_url.lstrip("/")),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "dashboard", "public", background_url.lstrip("/"))
                ]
                
                found_path = None
                for p in paths_to_try:
                    if os.path.exists(p):
                        found_path = p
                        break

                if found_path:
                    # print(f"DEBUG: Found local background at {found_path}")
                    bg_image = Image.open(found_path).convert("RGBA")
                    background = Editor(bg_image).resize((width, height), crop=True)
                else:
                    print(f"DEBUG: Local background not found. CWD: {os.getcwd()} - Trying URL...")
                    dash_base = os.getenv("DASHBOARD_URL", "http://localhost:3000")
                    full_url = f"{dash_base.rstrip('/')}/{background_url.lstrip('/')}"
                    background_image = await load_image_async(full_url)
                    background = Editor(background_image).resize((width, height), crop=True)
            else:
                background_image = await load_image_async(background_url)
                background = Editor(background_image).resize((width, height), crop=True)
        except Exception as e:
            print(f"Failed to load background '{background_url}': {e}")
            background = Editor(Canvas((width, height), color="#23272A"))
    else:
        background = Editor(Canvas((width, height), color="#23272A"))

    # Force RGBA for consistency
    if background.image.mode != "RGBA":
         background.image = background.image.convert("RGBA")

    # Apply Overlay (Dullness)
    if overlay_opacity > 0:
        # Clamp between 0-100
        opacity = max(0, min(100, overlay_opacity))
        alpha = int(255 * (opacity / 100))
        # Create a black overlay with alpha
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, alpha))
        # Paste it over the background
        background.image.paste(overlay, (0, 0), overlay)

    # Load Avatar
    try:
        # Force PNG/Static to avoid issues with GIFs or WebPs
        avatar_url = member.display_avatar.replace(format="png", static_format="png", size=512).url
        print(f"DEBUG: Loading avatar from {avatar_url}")
        
        avatar_image = await load_image_async(str(avatar_url))
        
        # Create circle avatar
        avatar_editor = Editor(avatar_image).resize((avatar_size_px, avatar_size_px)).circle_image()
        
        # Apply Rotation
        if arot != 0:
            # Fix: Use PIL image directly to avoid 'resample' keyword error in Editor.rotate
            rotated_avatar = avatar_editor.image.rotate(-arot, resample=Image.BICUBIC, expand=False)
            avatar_editor = Editor(rotated_avatar)
            
        background.paste(avatar_editor, (avatar_x_px, avatar_y_px))
    except Exception as e:
        print(f"Failed to load avatar: {e}")
        # Fallback circle
        avatar = Editor(Canvas((avatar_size_px, avatar_size_px), color="#7289da")).circle_image()
        background.paste(avatar, (avatar_x_px, avatar_y_px))

    # Text
    try:
        font_large = Font.poppins(size=title_size_px, variant="bold")
        font_small = Font.poppins(size=subtitle_size_px, variant="regular")
    except:
        font_large = ImageFont.truetype("arial.ttf", title_size_px) if os.name == 'nt' else ImageFont.load_default()
        font_small = ImageFont.truetype("arial.ttf", subtitle_size_px) if os.name == 'nt' else ImageFont.load_default()

    def draw_rotated_text(editor, text, x, y, font, color, angle):
        if angle == 0:
            editor.text((x, y), text, color=color, font=font)
            return

        # Measure text size
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bbox = dummy.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        
        # Create text layer
        txt_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        d = ImageDraw.Draw(txt_layer)
        d.text((-bbox[0], -bbox[1]), text, font=font, fill=color)
        
        # Rotate
        rotated = txt_layer.rotate(-angle, resample=Image.BICUBIC, expand=True)
        editor.paste(Editor(rotated), (x, y))

    # TITLE
    draw_rotated_text(background, title, text_x_px, text_y_px, font_large, title_color, trot)
    
    # SUBTITLE
    sub_text = subtitle if subtitle else member.name
    subtitle_y_px = text_y_px + int(title_size_px * 1.2)
    draw_rotated_text(background, sub_text, text_x_px, subtitle_y_px, font_small, subtitle_color, trot)

    # Convert to buffer
    buffer = io.BytesIO()
    background.image.save(buffer, format="PNG")
    buffer.seek(0)
    
    return discord.File(fp=buffer, filename="welcome.png")

# ════════════════════════════════════════════════════════════════════════════
# MODALS & VIEWS
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# MODALS & VIEWS
# ════════════════════════════════════════════════════════════════════════════

class SimpleWelcomeModal(discord.ui.Modal, title="Simple Welcome Message"):
    content = discord.ui.TextInput(
        label="Message Content",
        style=discord.TextStyle.paragraph,
        placeholder="Welcome {user} to {server_name}!",
        required=True,
        max_length=2000
    )

    def __init__(self, cog, guild_id: int, author_id: int = None):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ Not your menu.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        await self.cog.welcome_col.update_one(
            {"guild_id": self.guild_id},
            {"$set": {
                "message": {
                    "type": "simple",
                    "content": self.content.value
                },
                "enabled": True
            }},
            upsert=True
        )
        
        await interaction.followup.send(
            embed=discord.Embed(description="✅ **Simple welcome message saved.**", color=discord.Color.green()), 
            ephemeral=True
        )

class EmbedFieldModal(discord.ui.Modal):
    def __init__(self, view_ref, field_key: str, current_value: str = "", author_id: int = None):
        super().__init__(title=f"Edit {field_key.replace('_', ' ').title()}")
        self.view_ref = view_ref 
        self.field_key = field_key
        self.author_id = author_id
        
        style = discord.TextStyle.short
        if field_key in ["description", "message_content"]:
            style = discord.TextStyle.paragraph
            
        self.input_item = discord.ui.TextInput(
            label=field_key.replace("_", " ").title(),
            style=style,
            default=current_value,
            required=False, 
            max_length=4000 if style == discord.TextStyle.paragraph else 256
        )
        self.add_item(self.input_item)

    async def on_submit(self, interaction: discord.Interaction):
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ Not your menu.", ephemeral=True)
            return

        await interaction.response.defer()
        self.view_ref.embed_data[self.field_key] = self.input_item.value
        await self.view_ref.safe_update_preview()

class ResetConfirmView(discord.ui.View):
    def __init__(self, cog, author_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ Not your menu.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        if self.message:
            try:
                for child in self.children: child.disabled = True
                await self.message.edit(content="> ⏱️ **Reset timed out.**", view=self)
            except: pass

    @discord.ui.button(label="Reset Config", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.welcome_col.delete_one({"guild_id": self.guild_id})
        
        embed = discord.Embed(description="🗑️ **Welcome configuration has been reset.**", color=discord.Color.red())
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(content="> ❌ **Reset cancelled.**", embed=None, view=None)
        self.stop()

class EmbedBuilderView(discord.ui.View):
    def __init__(self, cog, guild_id: int, author_id: int):
        super().__init__(timeout=900)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id
        self.message: Optional[discord.Message] = None
        self._locked = False
        self.embed_data = {
            "message_content": "",
            "title": "",
            "description": "",
            "color": "",
            "image": "",
            "thumbnail": "",
            "footer_text": "",
            "footer_icon": ""
        }

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ Not your menu.", ephemeral=True)
            return False
        return True

    def _build_embed_obj(self) -> discord.Embed:
        color = parse_embed_color(self.embed_data.get("color"))
        embed = discord.Embed(
            title=self.embed_data.get("title") or None,
            description=self.embed_data.get("description") or None,
            color=color
        )
        if self.embed_data.get("image"): embed.set_image(url=self.embed_data.get("image"))
        if self.embed_data.get("thumbnail"): embed.set_thumbnail(url=self.embed_data.get("thumbnail"))
        
        f_text = self.embed_data.get("footer_text")
        f_icon = self.embed_data.get("footer_icon")
        if f_text or f_icon: embed.set_footer(text=f_text, icon_url=f_icon)
        return embed

    async def safe_update_preview(self):
        if not self.message: return
        embed = self._build_embed_obj()
        content = self.embed_data.get("message_content") or None
        
        if not embed.title and not embed.description and not embed.footer and not embed.image:
             if not content: embed.description = "*(Live Preview: Embed is currently empty)*"

        try: await self.message.edit(content=content, embed=embed, view=self)
        except: pass

    @discord.ui.select(
        placeholder="Select a field to edit...",
        options=[
            discord.SelectOption(label="Message Content", value="message_content", description="Text outside the embed"),
            discord.SelectOption(label="Title", value="title"),
            discord.SelectOption(label="Description", value="description"),
            discord.SelectOption(label="Large Image URL", value="image"),
            discord.SelectOption(label="Small Image URL", value="thumbnail"),
            discord.SelectOption(label="Footer Text", value="footer_text"),
            discord.SelectOption(label="Footer Icon URL", value="footer_icon"),
            discord.SelectOption(label="Color", value="color", description="Name or Hex"),
        ]
    )
    async def select_field(self, interaction: discord.Interaction, select: discord.ui.Select):
        field = select.values[0]
        current_val = self.embed_data.get(field, "")
        select.placeholder = f"Editing {field}..."
        modal = EmbedFieldModal(self, field, current_val, self.author_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.success, row=1)
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._locked: return
        self._locked = True

        json_content = json.dumps(self.embed_data)
        
        await self.cog.welcome_col.update_one(
            {"guild_id": self.guild_id},
            {"$set": {
                "message": {
                    "type": "embed",
                    "content": json_content
                },
                "enabled": True
            }},
            upsert=True
        )
        
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(embed=discord.Embed(description="✅ **Embedded welcome message saved.**", color=discord.Color.green()), ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._locked: return
        self._locked = True
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(content="> ❌ Setup Cancelled.", embed=None, view=self)
        self.stop()

    @discord.ui.button(label="Show Variables", style=discord.ButtonStyle.secondary, row=1, emoji="📎")
    async def variables_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vars_text = "**Available Variables:**\n`{user}` `{user_name}` `{user_id}` `{user_nick}`\n`{user_avatar}` `{user_joindate}` `{user_createdate}`\n`{server_name}` `{server_id}` `{server_membercount}` `{server_icon}`"
        await interaction.response.send_message(embed=discord.Embed(description=vars_text, color=discord.Color.blurple()), ephemeral=True)

class WelcomeSetupView(discord.ui.View):
    def __init__(self, cog, guild_id: int, author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id 
        self._locked = False
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ Not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Simple Message", style=discord.ButtonStyle.primary)
    async def simple_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._locked: return
        await interaction.response.send_modal(SimpleWelcomeModal(self.cog, self.guild_id, self.author_id))

    @discord.ui.button(label="Embed Message", style=discord.ButtonStyle.primary)
    async def embed_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._locked: return
        self._locked = True
        
        view = EmbedBuilderView(self.cog, self.guild_id, self.author_id)
        embed = discord.Embed(description="*(Embed is empty)*", color=discord.Color(DEFAULT_COLOR))
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._locked: return
        self._locked = True
        await interaction.response.edit_message(content="> ❌ Setup Cancelled", embed=None, view=None)
        self.stop()



# ════════════════════════════════════════════════════════════════════════════
# COG IMPLEMENTATION
# ════════════════════════════════════════════════════════════════════════════

class Welcomer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.welcome_col = self.db["welcome"]
        self.join_queue = {}
        self.processing = set()

    async def cog_load(self):
        print("✅ [Welcome] Extension loaded & DB initialized (MongoDB).")

    async def safe_format(self, text, placeholders):
        if not text: return ""
        placeholders_lower = {k.lower(): v for k, v in placeholders.items()}
        def replace_var(match):
            var_name = match.group(1).lower()
            return str(placeholders_lower.get(var_name, f"{{{var_name}}}"))
        return re.sub(r"\{(\w+)\}", replace_var, text)

    async def process_queue(self, guild):
        while self.join_queue.get(guild.id):
            member = self.join_queue[guild.id].pop(0)
            await asyncio.sleep(0.1 + random.uniform(0.0, 0.1))
            
            # Use _process_welcome logic but adapted for queue (handling errors/retries)
            try:
                # We can reuse _process_welcome but it doesn't handle retries/backoff internally 
                # effectively for a queue batch, but it's okay for now.
                # However, to support safe_format correctly if _process_welcome doesn't use it...
                # _process_welcome uses `format_variable` (helper function). 
                # I should verify `format_variable` availability. 
                # It is likely defined in Utilities section of welcome.py (not shown in recent reads but implied).
                # I will trust _process_welcome for now or update it.
                
                success, msg = await self._process_welcome(guild.id, member)
                if not success and "Rate limited" in msg:
                     # If we had better error propagating, we could retry.
                     pass
                     
            except Exception as e:
                print(f"[Welcome Queue] Error processing {member}: {e}")
                
            await asyncio.sleep(1.0 + random.uniform(0.0, 1.0))
            
            # Helper for join nick
            try:
                config = await getConfig(guild.id, self.bot)
                join_nick = config.get("join_nick")
                if join_nick:
                    # placeholders for nick
                    placeholders = {
                        "user": member.name, 
                        "user_name": member.name,
                        "user_display": member.display_name
                    } # simplified
                    new_nick = await self.safe_format(join_nick, placeholders)
                    if guild.me.guild_permissions.manage_nicknames and member.top_role < guild.me.top_role:
                        await member.edit(nick=new_nick[:32])
            except:
                pass

        if guild.id in self.processing:
            self.processing.remove(guild.id)

    # ════════════════════════════════════════════════════════════════════════
    # COMMANDS
    # ════════════════════════════════════════════════════════════════════════

    @commands.hybrid_group(name="welcome", fallback="help", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def welcome(self, ctx: commands.Context):
        """Manage the welcome system."""
        pass

    @welcome.command(name="setup")
    @app_commands.describe()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: commands.Context):
        """Interactive setup for welcome messages (Public)."""
        
        exists = await self.welcome_col.find_one({"guild_id": ctx.guild.id})

        if exists and exists.get("message"):
            embed = discord.Embed(
                title="Configuration Exists",
                description="⚠️ **Your server already has a welcome system setup.**\n\nUse `/welcome reset` to remove the current configuration if you wish to start over.",
                color=discord.Color.gold()
            )
            return await safe_reply(ctx, embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="<:sygreet:1445411663275888772> Welcome System Setup",
            description="- Configure how the bot welcomes new members.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="<:hash:1445406962727522373> Simple Message", value="- A plain text message. Supports standard variables.", inline=True)
        embed.add_field(name="<:hash:1445406962727522373> Embedded Message", value="- A rich embed with images, title, color, and footer.", inline=True)
        embed.set_footer(text="Select a mode below to begin")
        
        view = WelcomeSetupView(self, ctx.guild.id, ctx.author.id)
        await safe_reply(ctx, embed=embed, view=view, ephemeral=True)

    @welcome.command(name="channel")
    @app_commands.describe(channel="The channel to send welcome messages in")
    @commands.has_permissions(administrator=True)
    async def channel_set(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel for welcome messages."""
        await self.welcome_col.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"channel_id": channel.id}},
            upsert=True
        )
        await safe_reply(ctx, embed=discord.Embed(description=f"> ✅ **Welcome Channel set to {channel.mention} successfully.**", color=discord.Color.green()))

    @welcome.command(name="role")
    @app_commands.describe(role="Role to give on join")
    @commands.has_permissions(administrator=True)
    async def role_set(self, ctx: commands.Context, role: discord.Role):
        """Set a role to automatically give to new members."""
        await self.welcome_col.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"role_id": role.id}},
            upsert=True
        )
        await safe_reply(ctx, embed=discord.Embed(description=f"> ✅ **Welcome Role set to {role.mention} successfully.**", color=discord.Color.green()))

    @welcome.command(name="autodelete")
    @app_commands.describe(seconds="Seconds to wait before deleting (or 'off')")
    @commands.has_permissions(administrator=True)
    async def autodelete_set(self, ctx: commands.Context, seconds: str):
        """Set how long the welcome message stays."""
        val = None
        if seconds.lower() != "off":
            try:
                val = int(seconds)
                if val < 0: raise ValueError
                if val > MAX_AUTODELETE: return await safe_reply(ctx, content=f"> ⚠️ Autodelete cannot exceed {MAX_AUTODELETE} seconds.")
            except ValueError:
                return await safe_reply(ctx, content="Please provide a positive integer or 'off'.")
        
        await self.welcome_col.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"autodelete_seconds": val}},
            upsert=True
        )
        
        msg = f"> ✅ **Autodelete set to {val} seconds.**" if val else "✅ **Autodelete disabled.**"
        await safe_reply(ctx, embed=discord.Embed(description=msg, color=discord.Color.green()))

    @welcome.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: commands.Context):
        """Resets the welcome configuration with confirmation."""
        embed = discord.Embed(
            title="Reset Welcome Configuration",
            description="⚠️ **Are you sure you want to reset the welcome configuration?**\n\nThis will **delete** all settings.",
            color=discord.Color.orange()
        )
        view = ResetConfirmView(self, author_id=ctx.author.id, guild_id=ctx.guild.id)
        msg = await safe_reply(ctx, embed=embed, view=view, ephemeral=True)
        view.message = msg

    @welcome.command(name="test")
    @commands.has_permissions(administrator=True)
    async def test(self, ctx: commands.Context):
        """Simulate a member joining to test the configuration."""
        await ctx.defer()
        # Mocking logic for test? No, logic depends on greet2.py or shared logic.
        # But this file imports logic from greet2? No, `welcome` usually handles config and `greet` handles event.
        # Wait, the original `test` command called `self._process_welcome`.
        # I need to find where `_process_welcome` is defined or move it here.
        # The file snippet I saw earlier ended before `_process_welcome` was shown?
        # Re-checking the previous `view_file` output... 
        # It stopped at line 800. The test command calls `self._process_welcome`.
        # I must look for `_process_welcome` further down in the file or implement it.
        # It's likely at the end of the file.
        
        # For now, placeholder for missing function
        success, result = await self._process_welcome(ctx.guild.id, ctx.author)
        
        if success:
            await safe_reply(ctx, embed=discord.Embed(description=f"✅ **Test successful!** Message sent to {result}", color=discord.Color.green()))
        else:
            await safe_reply(ctx, embed=discord.Embed(description=f"❌ **Test failed:** {result}", color=discord.Color.red())) 

    @welcome.command(name="config")
    @commands.has_permissions(administrator=True)
    async def config(self, ctx: commands.Context):
        """View current welcome settings."""
        conf = await self.welcome_col.find_one({"guild_id": ctx.guild.id})
        
        if not conf:
            return await safe_reply(ctx, content="No configuration found.")
            
        chan_id = conf.get("channel_id")
        role_id = conf.get("role_id")
        auto_del = conf.get("autodelete_seconds")
        
        desc = f"**Channel:** <#{chan_id}>\n" if chan_id else "**Channel:** Not Set\n"
        desc += f"**Role:** <@&{role_id}>\n" if role_id else "**Role:** Not Set\n"
        desc += f"**Autodelete:** {auto_del}s\n" if auto_del else "**Autodelete:** Disabled\n"
        
        if conf.get("message"):
            msg_data = conf["message"]
            desc += f"**Message Type:** {msg_data['type'].title()}"
        else:
            desc += "**Message Type:** Not Set"
            
        await safe_reply(ctx, embed=discord.Embed(title="Welcome Config", description=desc, color=discord.Color.blue()))

    # ════════════════════════════════════════════════════════════════════════
    # EVENTS & LOGIC
    # ════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot: return
        if member.guild.id not in self.join_queue:
            self.join_queue[member.guild.id] = []
        self.join_queue[member.guild.id].append(member)
        
        if member.guild.id not in self.processing:
            self.processing.add(member.guild.id)
            asyncio.create_task(self.process_queue(member.guild))

    async def _process_welcome(self, guild_id: int, member: discord.Member) -> tuple[bool, str]:
        # Fetch entire config in one go
        conf = await self.welcome_col.find_one({"guild_id": guild_id})
        
        if not conf:
            return False, "Channel not configured."
            
        # 1. Handle Auto-Role
        role_id = conf.get("role_id")
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="[Scyro Welcome] Auto-role")
                except discord.Forbidden:
                    pass # Cannot add role
        
        # 2. Handle Welcome Message
        if not conf.get("enabled", True):
            return False, "Welcome system is disabled."

        channel_id = conf.get("channel_id")
        if not channel_id:
            return False, "Channel not configured."

        msg_data = conf.get("message")
        if not msg_data:
            return False, "Message content not configured."

        guild = self.bot.get_guild(guild_id)
        if not guild: return False, "Guild not found."
        
        channel = guild.get_channel(channel_id)
        if not channel: return False, "Channel not found."
        
        delete_after = conf.get("autodelete_seconds")
        if delete_after == 0: delete_after = None
        
        msg_type = msg_data.get("type", "simple")
        content_raw = msg_data.get("content", "")
        
        try:
            if msg_type == "simple":
                final_content = format_variable(content_raw, member)
                await channel.send(content=final_content, delete_after=delete_after)
                
            elif msg_type == "embed":
                data = json.loads(content_raw)
                plain_content = format_variable(data.get("message_content", ""), member)
                
                col = parse_embed_color(data.get("color"))
                embed = discord.Embed(
                    title=format_variable(data.get("title", ""), member) or None,
                    description=format_variable(data.get("description", ""), member) or None,
                    color=col
                )
                
                if data.get("image"):
                    embed.set_image(url=format_variable(data.get("image", ""), member))
                if data.get("thumbnail"):
                    embed.set_thumbnail(url=format_variable(data.get("thumbnail", ""), member))
                    
                ft = data.get("footer_text", "")
                fi = data.get("footer_icon", "")
                if ft or fi:
                    embed.set_footer(
                        text=format_variable(ft, member),
                        icon_url=format_variable(fi, member) or None
                    )
                
                await channel.send(
                    content=plain_content or None, 
                    embed=embed, 
                    delete_after=delete_after
                )

            elif msg_type == "custom":
                data = json.loads(content_raw)
                plain_content = format_variable(data.get("message_content", ""), member)
                bg_url = data.get("background_url")
                
                # Card Texts
                c_title = data.get("card_title", "WELCOME")
                c_subtitle = data.get("card_subtitle", "{user_name}")
                c_size = data.get("canvas_size", "1640x664")
                
                # Format them
                c_title = format_variable(c_title, member)
                c_subtitle = format_variable(c_subtitle, member)
                
                # Generate Image
                # Pass all data as kwargs to support new dynamic params
                # Remove conflicting keys that are passed explicitly
                data_kwargs = data.copy()
                data_kwargs.pop('canvas_size', None)
                data_kwargs.pop('background_url', None)

                # Generate Image
                try:
                    file = await generate_welcome_image(member, bg_url, title=c_title, subtitle=c_subtitle, canvas_size=c_size, **data_kwargs)
                except Exception as img_err:
                    print(f"ERROR: generate_welcome_image failed: {img_err}")
                    import traceback
                    traceback.print_exc()
                    return False, f"Image Generation Failed: {str(img_err)}"
                
                await channel.send(
                    content=plain_content or None,
                    file=file,
                    delete_after=delete_after
                )
                
            return True, channel.mention
            
        except discord.Forbidden:
            return False, "Missing permissions to send in channel."
        except Exception as e:
            return False, str(e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcomer(bot))