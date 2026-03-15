import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
import uuid
from typing import List, Optional, Dict, Any
import motor.motor_asyncio

# ══════════════════════════════════════════════════════════════
# CONFIGURATION & CONSTANTS
# ══════════════════════════════════════════════════════════════

# GLOBAL REGISTRY TO PREVENT MEMORY LEAKS
# Stores strings in format "guild_id:embed_name"
VIEW_REGISTRY = set()

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

# ══════════════════════════════════════════════════════════════
# DATABASE SYSTEM
# ══════════════════════════════════════════════════════════════

def get_database():
    mongo_url = os.getenv("MONGO_URI")
    if not mongo_url:
        print("CRITICAL: MONGO_URI not found in environment!")
        return None
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    return client.get_default_database()

# ══════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════

async def safe_reply(ctx, **kwargs):
    """Helper to handle prefix vs slash command responses safely."""
    if ctx.interaction:
        kwargs["ephemeral"] = True
        if ctx.interaction.response.is_done():
            return await ctx.send(**kwargs)
            
    return await ctx.reply(**kwargs)

# ... (omitted lines)

    @embed_group.command(name="list", description="List all embeds created in this server")
    @commands.has_permissions(administrator=True)
    async def embed_list(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT embed_name FROM embeds WHERE guild_id = ?", (ctx.guild.id,))

def parse_embed_color(input_str: Optional[str]) -> discord.Color:
    if not input_str:
        return discord.Color(COLOR_NAME_MAP["grey"])
    
    input_str = input_str.lower().strip()
    
    if input_str in COLOR_NAME_MAP:
        return discord.Color(COLOR_NAME_MAP[input_str])
    
    if input_str.startswith("#"):
        input_str = input_str[1:]
    elif input_str.startswith("0x"):
        input_str = input_str[2:]
        
    try:
        return discord.Color(int(input_str, 16))
    except ValueError:
        return discord.Color(COLOR_NAME_MAP["grey"])

def create_system_embed(type: str, title: str, description: str) -> discord.Embed:
    color_map = {
        "success": discord.Color.green(),
        "error": discord.Color.red(),
        "warning": discord.Color.orange(),
        "info": discord.Color.blurple()
    }
    color = color_map.get(type, discord.Color.blurple())
    embed = discord.Embed(title=title, description=description, color=color)
    return embed

def apply_variables(text: str, user: discord.User, guild: discord.Guild) -> str:
    """Minimal variable parser."""
    if not text or not str(text).strip(): return None
    replacements = {
        "{user}": user.mention,
        "{user.name}": user.name,
        "{guild.name}": guild.name if guild else "DM",
        "{guild.count}": str(guild.member_count) if guild else "0"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def register_view_safely(bot: commands.Bot, view: discord.ui.View, unique_key: str):
    """
    Registers a persistent view only if it hasn't been registered 
    in the current runtime session.
    """
    if unique_key in VIEW_REGISTRY:
        return False # Already listening
    
    bot.add_view(view)
    VIEW_REGISTRY.add(unique_key)
    return True # Newly registered

# ══════════════════════════════════════════════════════════════
# MODALS & INTERACTION FLOW
# ══════════════════════════════════════════════════════════════

class GenericInputModal(discord.ui.Modal):
    def __init__(self, title, label, current_val, parent_view, field_key, max_len=4000):
        super().__init__(title=title)
        self.parent_view = parent_view
        self.field_key = field_key
        
        self.field = discord.ui.TextInput(
            label=label,
            default=current_val,
            style=discord.TextStyle.paragraph if max_len > 100 else discord.TextStyle.short,
            max_length=max_len,
            required=False
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user_id:
            if not interaction.response.is_done():
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        self.parent_view.data[self.field_key] = self.field.value
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        if self.parent_view.message:
            try:
                await self.parent_view.message.edit(embed=self.parent_view.build_embed_object(), view=self.parent_view)
            except discord.NotFound:
                pass

class ComponentActionModal(discord.ui.Modal):
    def __init__(self, mode, parent_view):
        super().__init__(title=f"Configure {mode}")
        self.mode = mode
        self.parent_view = parent_view
        
        self.c_label = discord.ui.TextInput(label="Label", max_length=100 if mode == "Select" else 80, required=True)
        self.add_item(self.c_label)
        
        if mode == "Select":
            self.c_desc = discord.ui.TextInput(label="Description", max_length=100, required=False)
            self.add_item(self.c_desc)
            
        self.c_emoji = discord.ui.TextInput(label="Emoji (Optional)", max_length=32, required=False)
        self.add_item(self.c_emoji)

        if mode == "Button":
            self.c_color = discord.ui.TextInput(
                label="Color (blue, grey, red, green)", 
                placeholder="blue", 
                max_length=10, 
                required=False
            )
            self.add_item(self.c_color)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user_id:
            if not interaction.response.is_done():
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        data = {
            "label": self.c_label.value,
            "emoji": self.c_emoji.value.strip() if self.c_emoji.value else None
        }
        
        if self.mode == "Select":
            data["description"] = self.c_desc.value
        else:
            raw_color = self.c_color.value.lower() if self.c_color.value else "blue"
            style_map = {
                "blue": discord.ButtonStyle.primary,
                "grey": discord.ButtonStyle.secondary,
                "gray": discord.ButtonStyle.secondary,
                "red": discord.ButtonStyle.danger,
                "green": discord.ButtonStyle.success
            }
            data["style"] = style_map.get(raw_color, discord.ButtonStyle.primary).value

        view = ActionTypeView(self.parent_view, data)
        embed = create_system_embed("info", "Action Required", "What should this component do?")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class ActionTypeView(discord.ui.View):
    def __init__(self, parent_view, component_data):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        self.data = component_data

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent_view.user_id:
            await interaction.response.send_message("You don't own this menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Send Message", style=discord.ButtonStyle.blurple)
    async def send_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActionContentModal("message", self.parent_view, self.data))

    @discord.ui.button(label="Send Embed", style=discord.ButtonStyle.green)
    async def send_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActionContentModal("embed", self.parent_view, self.data))

class ActionContentModal(discord.ui.Modal):
    def __init__(self, action_type, parent_view, component_data):
        super().__init__(title=f"Configure {action_type.capitalize()}")
        self.action_type = action_type
        self.parent_view = parent_view
        self.data = component_data
        
        label = "Message Content" if action_type == "message" else "Embed Name"
        self.content = discord.ui.TextInput(
            label=label, 
            style=discord.TextStyle.paragraph if action_type == "message" else discord.TextStyle.short,
            max_length=2000 if action_type == "message" else 100
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user_id:
            if not interaction.response.is_done():
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if self.action_type == "embed":
            embed_name = self.content.value
            db = get_database()
            doc = await db.embeds.find_one({"guild_id": interaction.guild.id, "name": embed_name})
            
            if not doc:
                await interaction.followup.send(
                    embed=create_system_embed("error", "Not Found", "This server does not have this embed. Create it first."),
                    ephemeral=True
                )
                return
            
            await interaction.followup.send(
                embed=create_system_embed("success", "Action Configured", f"Setted **{embed_name}** to the response."),
                ephemeral=True
            )

        self.data["action_type"] = self.action_type
        self.data["payload"] = self.content.value
        
        c_type = "select_option" if "description" in self.data else "button"
        
        component_entry = {
            "type": c_type,
            "id": str(uuid.uuid4()), 
            "label": self.data["label"],
            "emoji": self.data.get("emoji"),
            "action_type": self.data["action_type"],
            "payload": self.data["payload"]
        }
        
        if c_type == "select_option":
            component_entry["description"] = self.data.get("description")
            component_entry["description"] = self.data.get("description")
            
            # Anti-Duplicate / Edit Mode: If label exists, update it
            existing_idx = next((i for i, c in enumerate(self.parent_view.select_options) if c['label'] == self.data["label"]), None)
            
            if existing_idx is not None:
                # Update existing (keep ID if possible, but we generated a new one. It's fine to replace)
                # Actually, better to keep the ID if we are strictly editing? 
                # But component_entry has new ID. Does not matter for DB overwrite (deleted anyway).
                # But for remove_flow, it matters.
                component_entry['id'] = self.parent_view.select_options[existing_idx]['id'] 
                self.parent_view.select_options[existing_idx] = component_entry
            else:
                self.parent_view.select_options.append(component_entry)
        else:
            component_entry["style"] = self.data.get("style")
            
            # Anti-Duplicate / Edit Mode for Buttons
            existing_idx = next((i for i, c in enumerate(self.parent_view.buttons) if c['label'] == self.data["label"]), None)
            
            if existing_idx is not None:
                component_entry['id'] = self.parent_view.buttons[existing_idx]['id']
                self.parent_view.buttons[existing_idx] = component_entry
            else:
                self.parent_view.buttons.append(component_entry)

        if self.parent_view.message:
             self.parent_view.setup_ui()
             await self.parent_view.message.edit(embed=self.parent_view.build_embed_object(), view=self.parent_view)

# ══════════════════════════════════════════════════════════════
# BUILDER VIEW (EDITING INTERFACE)
# ══════════════════════════════════════════════════════════════

class EmbedBuilderView(discord.ui.View):
    def __init__(self, guild_id, embed_name, user_id, initial_data=None, initial_components=None):
        super().__init__(timeout=None) 
        self.guild_id = guild_id
        self.embed_name = embed_name
        self.user_id = int(user_id)
        self.message: Optional[discord.Message] = None
        
        self.data = initial_data or {
            "content": "",
            "title": "New Embed",
            "description": "Description here...",
            "color": "grey",
            "image": None,
            "thumbnail": None,
            "footer_text": None,
            "footer_icon": None
        }
        
        self.buttons = []
        self.select_options = []
        
        if initial_components:
            seen_button_labels = set()
            seen_option_labels = set()
            
            for c in initial_components:
                if c['type'] == 'button':
                    lbl = c.get('label', '').strip()
                    if lbl and lbl in seen_button_labels:
                        continue
                    if lbl: seen_button_labels.add(lbl)
                    self.buttons.append(c)
                    
                elif c['type'] == 'select_option':
                    lbl = c.get('label', '').strip()
                    if lbl and lbl in seen_option_labels:
                        continue
                    if lbl: seen_option_labels.add(lbl)
                    self.select_options.append(c)
        
        self.setup_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=create_system_embed("error", "Access Denied", "You do not own this editing session."),
                ephemeral=True
            )
            return False
        return True

    def setup_ui(self):
        self.clear_items()
        
        select = discord.ui.Select(
            placeholder="Edit a field...",
            options=[
                discord.SelectOption(label="Message Content", value="content"),
                discord.SelectOption(label="Title", value="title"),
                discord.SelectOption(label="Description", value="description"),
                discord.SelectOption(label="Color", value="color"),
                discord.SelectOption(label="Small Image (Thumbnail)", value="thumbnail"),
                discord.SelectOption(label="Large Image", value="image"),
                discord.SelectOption(label="Footer Text", value="footer_text"),
                discord.SelectOption(label="Footer Image", value="footer_icon"),
            ],
            row=0
        )
        select.callback = self.field_select_callback
        self.add_item(select)

        self.add_item(self.create_button("Add Selection", discord.ButtonStyle.secondary, self.add_selection, 1))
        self.add_item(self.create_button("Remove Selection", discord.ButtonStyle.secondary, self.remove_selection, 1))
        self.add_item(self.create_button("Add Button", discord.ButtonStyle.secondary, self.add_button, 1))
        self.add_item(self.create_button("Remove Button", discord.ButtonStyle.secondary, self.remove_button, 1))

        self.add_item(self.create_button("Finish", discord.ButtonStyle.success, self.finish_callback, 2))
        self.add_item(self.create_button("Cancel", discord.ButtonStyle.danger, self.cancel_callback, 2))

    def create_button(self, label, style, callback, row):
        btn = discord.ui.Button(label=label, style=style, row=row)
        btn.callback = callback
        return btn

    def build_embed_object(self):
        e = discord.Embed(
            title=self.data.get("title") or None,
            description=self.data.get("description") or None,
            color=parse_embed_color(self.data.get("color"))
        )
        if self.data.get("image"): e.set_image(url=self.data.get("image"))
        if self.data.get("thumbnail"): e.set_thumbnail(url=self.data.get("thumbnail"))
        
        footer_text = self.data.get("footer_text")
        footer_icon = self.data.get("footer_icon")
        
        if footer_text or footer_icon:
            e.set_footer(text=footer_text, icon_url=footer_icon)
            
        return e

    async def field_select_callback(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        sel_val = interaction.data['values'][0]
        modal = GenericInputModal(
            title=f"Edit {sel_val}", 
            label="Value", 
            current_val=self.data.get(sel_val, ""),
            parent_view=self,
            field_key=sel_val,
            max_len=2000 if sel_val == "content" else 256
        )
        await interaction.response.send_modal(modal)

    async def add_selection(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        if len(self.select_options) >= 25:
             await interaction.response.send_message(embed=create_system_embed("error", "Limit Reached", "Max 25 selections allowed."), ephemeral=True)
             return
        await interaction.response.send_modal(ComponentActionModal("Select", self))

    async def add_button(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        await interaction.response.send_modal(ComponentActionModal("Button", self))

    async def remove_selection(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        await self._remove_component_flow(interaction, "select_option", self.select_options)

    async def remove_button(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        await self._remove_component_flow(interaction, "button", self.buttons)

    async def _remove_component_flow(self, interaction: discord.Interaction, c_type, target_list):
        if not target_list:
            await interaction.response.send_message(embed=create_system_embed("warning", "Empty", f"No {c_type.replace('_', ' ')}s to remove."), ephemeral=True)
            return

        options = [discord.SelectOption(label=c['label'], value=c['id']) for c in target_list[:25]]
        
        view = discord.ui.View()
        select = discord.ui.Select(placeholder=f"Select item to delete", options=options)
        
        async def delete_cb(inter):
            if inter.user.id != self.user_id:
                if not inter.response.is_done():
                    await inter.response.send_message("You don't own this menu.", ephemeral=True)
                return

            val = select.values[0]
            if c_type == "button":
                self.buttons = [c for c in self.buttons if c['id'] != val]
            else:
                self.select_options = [c for c in self.select_options if c['id'] != val]
                
            if not inter.response.is_done():
                await inter.response.defer(ephemeral=True)
            if self.message:
                try:
                    await self.message.edit(embed=self.build_embed_object(), view=self)
                except discord.NotFound:
                    pass
            try:
                await inter.delete_original_response()
            except discord.NotFound:
                pass

        select.callback = delete_cb
        view.add_item(select)
        await interaction.response.send_message(embed=create_system_embed("info", "Remove Item", "Select one to remove:"), view=view, ephemeral=True)

    async def finish_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        db = get_database()
        
        # AGGRESSIVE DEDUPLICATION
        unique_options = []
        seen_opt = set()
        for comp in self.select_options:
            label_key = comp['label'].strip()
            if label_key not in seen_opt:
                seen_opt.add(label_key)
                unique_options.append(comp)
        
        unique_buttons = []
        seen_btn = set()
        for comp in self.buttons:
            label_key = comp.get('label', '').strip()
            if label_key and label_key not in seen_btn:
                seen_btn.add(label_key)
                unique_buttons.append(comp)
            elif not label_key: 
                unique_buttons.append(comp)

        # Update IDs and Collect
        final_components = []
        
        for i, comp in enumerate(unique_options):
            comp_id = f"embed:{self.guild_id}:{self.embed_name}:select_option:{i}"
            comp['id'] = comp_id 
            comp['component_type'] = 'select_option'
            # Store JSON string as per old logic? Or raw dict?
            # Let's store raw dict in 'component_json' to keep compatibility with View reader logic which expects 'component_json' key wrapper
            # Actually, to make migration smoother, let's keep the structure the View expects:
            # View expects: { 'component_id': ..., 'component_type': ..., 'component_json': json_str }
            wrapper = {
                'component_id': comp_id,
                'component_type': 'select_option',
                'component_json': json.dumps(comp)
            }
            final_components.append(wrapper)
            
        for i, comp in enumerate(unique_buttons):
            comp_id = f"embed:{self.guild_id}:{self.embed_name}:button:{i}"
            comp['id'] = comp_id
            comp['component_type'] = 'button'
            wrapper = {
                'component_id': comp_id,
                'component_type': 'button',
                'component_json': json.dumps(comp)
            }
            final_components.append(wrapper)
        
        # Save to MongoDB
        await db.embeds.update_one(
            {"guild_id": self.guild_id, "name": self.embed_name},
            {"$set": {
                "data": self.data,
                "components": final_components
            }},
            upsert=True
        )

        for child in self.children:
            child.disabled = True
        try:
            if interaction.message:
                await interaction.message.edit(view=self)
        except discord.NotFound:
            pass
        
        await interaction.followup.send(embed=create_system_embed("success", "Saved", f"Embed **{self.embed_name}** updated successfully."), ephemeral=True)

    async def cancel_callback(self, interaction: discord.Interaction):
        try:
            await interaction.message.delete()
        except discord.NotFound:
            # Message already deleted, only try to edit if response not done
            if not interaction.response.is_done():
                try:
                    await interaction.response.edit_message(view=discord.ui.View())
                except discord.NotFound:
                    pass
            
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=create_system_embed("warning", "Cancelled", "Edit session cancelled."), ephemeral=True)
        else:
            try:
                await interaction.followup.send(embed=create_system_embed("warning", "Cancelled", "Edit session cancelled."), ephemeral=True)
            except:
                pass

# ══════════════════════════════════════════════════════════════
# PERSISTENT RUNNER VIEW
# ══════════════════════════════════════════════════════════════

class DynamicEmbedView(discord.ui.View):
    def __init__(self, components_data: List[Dict]):
        super().__init__(timeout=None) 
        self.option_map = {} 
        self.interaction_lock = asyncio.Lock()
        
        # Identify the embed this view belongs to using the first component
        # Format: embed:guild_id:embed_name:type:index
        self.unique_key = None
        if components_data:
            first_id = components_data[0].get('component_id', '')
            parts = first_id.split(':')
            if len(parts) >= 3:
                self.unique_key = f"{parts[1]}:{parts[2]}"

        self.build_view(components_data)

    def build_view(self, components):
        select_options_data = [c for c in components if c['component_type'] == 'select_option']
        buttons_data = [c for c in components if c['component_type'] == 'button']
        
        # AUTO-LAYOUT: Select Menu
        current_row = 0
        if select_options_data:
            discord_options = []
            # Deterministic ID for the Select Menu itself.
            first_id_parts = select_options_data[0]['component_id'].split(':')
            if len(first_id_parts) >= 3:
                menu_id = f"embed:{first_id_parts[1]}:{first_id_parts[2]}:select_menu"
            else:
                menu_id = f"select_auto_{uuid.uuid4()}" 

            seen_labels = set()
            for comp in select_options_data:
                c_data = json.loads(comp['component_json'])
                c_id = comp['component_id']
                
                # MASKING FIX: Skip duplicates from display even if DB is dirty
                lbl = c_data.get('label', '').strip()
                if lbl and lbl in seen_labels:
                    continue
                if lbl: seen_labels.add(lbl)

                self.option_map[c_id] = c_data
                
                discord_options.append(discord.SelectOption(
                    label=c_data.get('label'),
                    description=c_data.get('description'),
                    emoji=c_data.get('emoji') if c_data.get('emoji') else None,
                    value=c_id
                ))
            
            if discord_options:
                sel = discord.ui.Select(
                    custom_id=menu_id,
                    placeholder="Make a selection...",
                    min_values=1,
                    max_values=1,
                    row=current_row,
                    options=discord_options[:25]
                )
                sel.callback = self.select_callback
                self.add_item(sel)
                current_row += 1

        # AUTO-LAYOUT: Buttons
        btn_count_row = 0
        for comp in buttons_data:
            c_data = json.loads(comp['component_json'])
            c_id = comp['component_id']
            
            if btn_count_row >= 5:
                current_row += 1
                btn_count_row = 0
            
            emoji_val = c_data.get('emoji')
            emoji_obj = None
            if emoji_val:
                try:
                    # Attempt to parse as PartialEmoji (works for custom <:name:id> and unicode)
                    emoji_obj = discord.PartialEmoji.from_str(emoji_val)
                except:
                    # If parsing fails, it might be a raw string. 
                    # If it's a valid unicode char, Button(emoji=str) works.
                    # BUT if it's "garbage" string, it causes 400.
                    # Safety check: if it looks like a custom emoji but failed parse, drop it.
                    if "<:" in emoji_val or ">" in emoji_val:
                        print(f"[WARNING] Invalid custom emoji format: {emoji_val}. Dropping emoji.")
                        emoji_obj = None
                    else:
                        # Assume unicode string. If this is still invalid, it might crash, 
                        # but we can't easily validate unicode without a library.
                        # Let's hope it's valid unicode.
                        emoji_obj = emoji_val 

            btn = discord.ui.Button(
                custom_id=c_id,
                label=c_data.get('label'),
                style=discord.ButtonStyle(c_data.get('style', 1)),
                emoji=emoji_obj,
                row=current_row
            )
            btn.callback = self.create_button_callback(c_data)
            self.add_item(btn)
            btn_count_row += 1

    async def select_callback(self, interaction: discord.Interaction):
        if self.interaction_lock.locked():
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            return
        
        async with self.interaction_lock:
            selected_value = interaction.data['values'][0]
            data = self.option_map.get(selected_value)
            if data:
                await self.execute_action(interaction, data)
            else:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Option configuration not found.", ephemeral=True)

    def create_button_callback(self, data):
        async def callback(interaction: discord.Interaction):
            if self.interaction_lock.locked():
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                return

            async with self.interaction_lock:
                await self.execute_action(interaction, data)
        return callback

    async def execute_action(self, interaction: discord.Interaction, data):
        action = data.get('action_type')
        payload = data.get('payload')
        
        if action == 'message':
            content = apply_variables(payload, interaction.user, interaction.guild)
            if not interaction.response.is_done():
                await interaction.response.send_message(content, ephemeral=True)
        elif action == 'embed':
            embed_name = payload
            db = get_database()
            doc = await db.embeds.find_one({"guild_id": interaction.guild.id, "name": embed_name})
            
            if not doc:
                await interaction.response.send_message(embed=create_system_embed("error", "Error", "Linked embed not found."), ephemeral=True)
                return

            embed_data = doc.get('data', {})
            # Schema: doc['components'] is list of wrappers
            
            e = discord.Embed(
                title=apply_variables(embed_data.get("title"), interaction.user, interaction.guild), 
                description=apply_variables(embed_data.get("description"), interaction.user, interaction.guild), 
                color=parse_embed_color(embed_data.get("color"))
            )
            if embed_data.get("image"): e.set_image(url=embed_data.get("image"))
            if embed_data.get("thumbnail"): e.set_thumbnail(url=embed_data.get("thumbnail"))
            
            if embed_data.get("footer_text"): 
                e.set_footer(
                    text=apply_variables(embed_data.get("footer_text"), interaction.user, interaction.guild), 
                    icon_url=embed_data.get("footer_icon")
                )
            
            view = None
            components = doc.get('components', [])
            if components:
                # The components in DB are already in the format expected by DynamicEmbedView list
                # Wrapper format: {'component_type': ..., 'component_id': ..., 'component_json': ...}
                # So we can pass them directly
                
                # CRITICAL MEMORY FIX: Only register if not already listening
                target_key = f"{interaction.guild.id}:{embed_name}"
                view = DynamicEmbedView(components)
                
                # Safe registration ensures we don't add duplicate listeners
                register_view_safely(interaction.client, view, target_key)

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    content=apply_variables(embed_data.get("content", ""), interaction.user, interaction.guild) or None, 
                    embed=e, 
                    view=view, 
                    ephemeral=True
                )

# ══════════════════════════════════════════════════════════════
# MAIN COG
# ══════════════════════════════════════════════════════════════

class Embed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Database Schema is now managed by MongoDB (No schema fix needed)
        
        db = get_database()
        if db is None:
            print("[Embed] MongoDB connection failed. Persistent views not restored.")
            return

        count = 0
        try:
            # Efficiently fetch only necessary fields
            cursor = db.embeds.find({}, {"guild_id": 1, "name": 1, "components": 1})
            
            async for doc in cursor:
                components = doc.get("components", [])
                if not components:
                    continue
                
                guild_id = doc.get("guild_id")
                embed_name = doc.get("name")
                
                if not guild_id or not embed_name:
                    continue
                    
                unique_key = f"{guild_id}:{embed_name}"
                
                # Components are already stored in the wrapper format required by DynamicEmbedView
                view = DynamicEmbedView(components)
                
                # MEMORY FIX: Use the safe register function
                if register_view_safely(self.bot, view, unique_key):
                    count += 1
                    
        except Exception as e:
            print(f"[Embed] Failed to restore views: {e}")
            import traceback
            traceback.print_exc()
            
        print(f"[Embed] Restored {count} persistent embed views from MongoDB.")

    # Autocomplete Callback - Defined as instance method
    async def embed_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        
        db = get_database()
        if db is None:
            return []
            
        params = {"guild_id": interaction.guild.id}
        if current:
            # Use case-insensitive regex for searching
            params["name"] = {"$regex": current, "$options": "i"}
            
        cursor = db.embeds.find(params).limit(25)
        
        choices = []
        async for doc in cursor:
            name = doc.get("name")
            if name:
                choices.append(app_commands.Choice(name=name, value=name))
                
        return choices

    @commands.hybrid_group(name="embed", fallback="help", description="Advanced Embed Builder System")
    @commands.has_permissions(administrator=True)
    async def embed_group(self, ctx: commands.Context):
        embed = create_system_embed("info", "Embed Help", "Use `/embed create`, `/embed edit`, `/embed send` etc.")
        await safe_reply(ctx, embed=embed)

    @embed_group.command(name="create", description="Create a new embed from scratch")
    @app_commands.describe(name="Unique name for the new embed")
    @commands.has_permissions(administrator=True)
    async def embed_create(self, ctx: commands.Context, name: str):
        await ctx.defer(ephemeral=True)
        name = name.strip()
        db = get_database()
        
        existing = await db.embeds.find_one({"guild_id": ctx.guild.id, "name": name})
        if existing:
            await safe_reply(ctx, embed=create_system_embed("error", "Exists", f"Embed `{name}` already exists."))
            return
        
        initial_data = {
            "title": "New Embed",
            "description": "Edit me!",
            "color": "grey"
        }
        
        view = EmbedBuilderView(ctx.guild.id, name, ctx.author.id, initial_data=initial_data)
        embed = view.build_embed_object()
        
        message = await safe_reply(ctx, embed=embed, view=view)
        # safe_reply returns Message for both prefix and slash commands
        if hasattr(message, 'edit'):
            view.message = message

    @embed_group.command(name="edit", description="Edit an existing embed's content and components")
    @app_commands.describe(name="Select the embed you want to edit")
    @app_commands.autocomplete(name=embed_name_autocomplete)
    @commands.has_permissions(administrator=True)
    async def embed_edit(self, ctx: commands.Context, name: str):
        embed = discord.Embed(
            title="You found a broken command 🛠️",
            description=(
                "The embed edit feature through the bot isn't working right now and we are working on it. "
                "It will be fixed soon.\n\n"
                "Till then you can use dashboard to edit your embeds.\n"
                "**Dashboard Link:** https://scyro.xyz/dashboard"
            ),
            color=discord.Color.orange()
        )
        await safe_reply(ctx, embed=embed)

    @embed_group.command(name="delete", description="Permanently delete an embed and its components")
    @app_commands.describe(name="Select the embed to delete")
    @app_commands.autocomplete(name=embed_name_autocomplete)
    @commands.has_permissions(administrator=True)
    async def embed_delete(self, ctx: commands.Context, name: str):
        await ctx.defer(ephemeral=True)
        name = name.strip()
        db = get_database()
        
        result = await db.embeds.delete_one({"guild_id": ctx.guild.id, "name": name})
        
        if result.deleted_count == 0:
            await safe_reply(ctx, embed=create_system_embed("error", "Not Found", f"Embed `{name}` not found."))
            return
            
        # NOTE: We do not remove from VIEW_REGISTRY here because removing a view from the bot
        # is complex without the instance. The registry prevents re-addition, which is sufficient.
        
        await safe_reply(ctx, embed=create_system_embed("success", "Deleted", f"Embed `{name}` has been deleted."))

    @embed_group.command(name="list", description="List all embeds created in this server")
    @commands.has_permissions(administrator=True)
    async def embed_list(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        db = get_database()
        if db is None:
            return await safe_reply(ctx, embed=create_system_embed("error", "Database Error", "Could not connect to database."))
            
        cursor = db.embeds.find({"guild_id": ctx.guild.id})
        embed_names = [doc['name'] for doc in await cursor.to_list(length=100)]
        
        if not embed_names:
            await safe_reply(ctx, embed=create_system_embed("info", "Empty", "No embeds created yet."))
            return
            
        names = [f"`{name}`" for name in embed_names]
        desc = ", ".join(names)
        await safe_reply(ctx, embed=create_system_embed("info", "Server Embeds", desc))

    @embed_group.command(name="send", description="Send a saved embed to a specific channel")
    @app_commands.describe(name="Select the embed to send", channel="Channel to send the embed to (defaults to current)")
    @app_commands.autocomplete(name=embed_name_autocomplete)
    @commands.has_permissions(administrator=True)
    async def embed_send(self, ctx: commands.Context, name: str, channel: Optional[discord.TextChannel] = None):
        await ctx.defer(ephemeral=True)
        name = name.strip()
        target = channel or ctx.channel
        
        db = get_database()
        doc = await db.embeds.find_one({"guild_id": ctx.guild.id, "name": name})
        
        if not doc:
            await safe_reply(ctx, embed=create_system_embed("error", "Not Found", f"Embed `{name}` not found."))
            return
            
        embed_data = doc.get('data', {})
        components = doc.get('components', [])
        
        embed_obj = discord.Embed(
            title=apply_variables(embed_data.get("title"), ctx.author, ctx.guild),
            description=apply_variables(embed_data.get("description"), ctx.author, ctx.guild),
            color=parse_embed_color(embed_data.get("color"))
        )
        if embed_data.get("image"): embed_obj.set_image(url=embed_data.get("image"))
        if embed_data.get("thumbnail"): embed_obj.set_thumbnail(url=embed_data.get("thumbnail"))
        
        if embed_data.get("footer_text"):
             embed_obj.set_footer(
                 text=apply_variables(embed_data.get("footer_text"), ctx.author, ctx.guild),
                 icon_url=embed_data.get("footer_icon")
             )
            
        view = None
        if components:
            # MEMORY FIX: Check registry before adding
            unique_key = f"{ctx.guild.id}:{name}"
            view = DynamicEmbedView(components)
            register_view_safely(self.bot, view, unique_key)

        try:
            content = apply_variables(embed_data.get("content", ""), ctx.author, ctx.guild) or None
            await target.send(content=content, embed=embed_obj, view=view)
            await safe_reply(ctx, embed=create_system_embed("success", "Sent", f"Embed sent to {target.mention}."))
        except discord.Forbidden:
            await safe_reply(ctx, embed=create_system_embed("error", "Permission Denied", f"I cannot send messages in {target.mention}."))
        except Exception as e:
            await safe_reply(ctx, embed=create_system_embed("error", "Failed", f"Error: {str(e)}"))

    @embed_group.command(name="reset", description="Delete ALL embeds in this server (Irreversible)")
    @commands.has_permissions(administrator=True)
    async def embed_reset(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        view = discord.ui.View()
        
        async def confirm(inter):
            db = get_database()
            await db.embeds.delete_many({"guild_id": ctx.guild.id})
            await inter.response.edit_message(embed=create_system_embed("success", "Reset", "All embeds deleted."), view=None)

        async def cancel(inter):
            await inter.response.edit_message(embed=create_system_embed("info", "Cancelled", "Reset cancelled."), view=None)

        btn_confirm = discord.ui.Button(label="Confirm Reset", style=discord.ButtonStyle.danger)
        btn_confirm.callback = confirm
        btn_cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        btn_cancel.callback = cancel
        
        view.add_item(btn_confirm)
        view.add_item(btn_cancel)
        
        await safe_reply(ctx, embed=create_system_embed("warning", "Confirm Reset", "Are you sure? This deletes ALL embeds."), view=view)

async def setup(bot):
    await bot.add_cog(Embed(bot))