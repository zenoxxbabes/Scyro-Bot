import discord
from discord.ext import commands
from discord import app_commands, ui
import motor.motor_asyncio
import os
import json
import asyncio
import io
import datetime
from typing import Optional, List

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & COLORS
# ════════════════════════════════════════════════════════════════════════════

# Global Locks for Concurrency Safety
CREATION_LOCK = asyncio.Lock()
ACTION_LOCK = asyncio.Lock()

DEFAULT_COLOR = 0x2B2D31 

COLORS = {
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

def parse_color(color_input: str) -> int:
    if not color_input: return DEFAULT_COLOR
    color_input = color_input.lower().strip().replace(" ", "")
    if color_input in COLORS: return COLORS[color_input]
    if color_input.startswith("0x"):
        try: return int(color_input, 16)
        except: pass
    elif color_input.startswith("#"):
        try: return int(color_input[1:], 16)
        except: pass
    return DEFAULT_COLOR

# ════════════════════════════════════════════════════════════════════════════
# UTILS & NOTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════

async def generate_transcript(channel: discord.TextChannel) -> discord.File:
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    output = io.StringIO()
    output.write(f"TRANSCRIPT | Channel: {channel.name}\nServer: {channel.guild.name} | Date: {datetime.datetime.now()}\n{'='*60}\n\n")
    for msg in messages:
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        output.write(f"[{ts}] {msg.author}: {msg.content} {'[ATTACHMENT]' if msg.attachments else ''}\n")
    output.seek(0)
    return discord.File(fp=io.BytesIO(output.getvalue().encode('utf-8')), filename=f"transcript-{channel.name}.txt")

# ════════════════════════════════════════════════════════════════════════════
# VIEWS
# ════════════════════════════════════════════════════════════════════════════

class TicketPanelView(discord.ui.View):
    def __init__(self, cog, panel_id: str, component_data: dict):
        super().__init__(timeout=None)
        self.cog = cog
        print(f"[DEBUG] TicketPanelView init for {panel_id}")
        self.panel_id = panel_id
        if component_data.get("type") == "BUTTON":
            for btn in component_data.get("options", []):
                self.add_item(TicketLauncherButton(cog, panel_id, btn))
        elif component_data.get("type") == "SELECT":
            self.add_item(TicketLauncherSelect(cog, panel_id, component_data.get("options", [])))

class TicketLauncherButton(discord.ui.Button):
    def __init__(self, cog, panel_id, data):
        color_map = {"blue": discord.ButtonStyle.primary, "red": discord.ButtonStyle.danger, "green": discord.ButtonStyle.success, "grey": discord.ButtonStyle.secondary}
        cid = f"tkt_btn:{panel_id}:{data['category']}".replace(" ", "_")
        emoji = data.get('emoji') or None
        super().__init__(style=color_map.get(data.get('color', 'blue'), discord.ButtonStyle.primary), label=data['label'], emoji=emoji, custom_id=cid)
        self.cog = cog
        self.panel_id, self.category = panel_id, data['category']
    
    async def callback(self, interaction): 
        if interaction.response.is_done(): return
        await self.cog.create_ticket(interaction, self.panel_id, self.category)

class TicketLauncherSelect(discord.ui.Select):
    def __init__(self, cog, panel_id, options_data):
        options = []
        for o in options_data:
            emoji = o.get('emoji') or None
            options.append(discord.SelectOption(label=o['label'], description=o.get('description'), value=o['category'], emoji=emoji))
        super().__init__(placeholder="Select category...", custom_id=f"tkt_sel:{panel_id}", options=options)
        self.cog = cog
        self.panel_id = panel_id
    
    async def callback(self, interaction): 
        if interaction.response.is_done(): return
        self.placeholder = "Select category..."
        await self.cog.create_ticket(interaction, self.panel_id, self.values[0])

class TicketManagementView(discord.ui.View):
    def __init__(self, cog): 
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.select(custom_id="tkt_manage", placeholder="Ticket Actions", options=[
        discord.SelectOption(label="Claim", value="claim", emoji="<:syclaim:1460595792707321991>"),
        discord.SelectOption(label="Add User", value="add", emoji="<:syaddtkt:1460595774067839029>"),
        discord.SelectOption(label="Remove User", value="rem", emoji="<:syremovetkt:1460595765855522896>"),
        discord.SelectOption(label="Close", value="close", emoji="<:sylocktkt:1460595783933100053>"),
        discord.SelectOption(label="Transcript", value="transcript", emoji="<:sytranscript:1460595812613488762>"),
        discord.SelectOption(label="Delete", value="delete", emoji="<:sybin:1460595803633614848>")
    ])
    async def callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        # 1. Immediate Safety Check
        if interaction.response.is_done(): return

        if not await self.cog.is_staff_or_admin(interaction): 
            return await interaction.response.send_message(embed=discord.Embed(description="<:no:1396838761605890090> Only Staff can manage tickets.", color=discord.Color.red()), ephemeral=True)
        
        act = select.values[0]

        # 2. Handle Modals (Must be sent BEFORE defer)
        if act == "add":
            return await interaction.response.send_modal(UserModal(self.cog, "add"))
        if act == "rem":
            return await interaction.response.send_modal(UserModal(self.cog, "remove"))
        
        # 3. Defer Interaction (Acknowledges the event)
        await interaction.response.defer()

        # 4. Immediate UI Feedback + Disable
        select.placeholder = "Processing..."
        select.disabled = True
        
        try:
            await interaction.message.edit(view=self)
        except discord.NotFound:
            return 
        
        # 5. Logic Execution with Lock
        async with ACTION_LOCK:
            try:
                if act == "claim": await self.cog.handle_claim(interaction)
                elif act == "close": await self.cog.handle_close(interaction)
                elif act == "delete": await self.cog.handle_delete(interaction)
                elif act == "transcript": await self.cog.handle_transcript(interaction)
            except Exception as e:
                # Fallback error logger (Safe Pattern: Direct Channel Message)
                try: 
                    await interaction.channel.send(content=f"Error: {e}")
                except: 
                    pass
            finally:
                # 6. Restore View State
                try:
                    if act != "delete":
                        select.disabled = False
                        select.placeholder = "Ticket Actions"
                        # Use edit directly on message for reliability
                        await interaction.message.edit(view=self)
                except:
                    pass

class ConfirmationView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60); self.value = None
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self.value = True
        self.stop()
        if not interaction.response.is_done(): await interaction.response.defer()
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.value = False
        self.stop()
        if not interaction.response.is_done(): await interaction.response.defer()

# ════════════════════════════════════════════════════════════════════════════
# WIZARD UI
# ════════════════════════════════════════════════════════════════════════════

class WizardState: EMBED=1; TYPE=2; COMP=3

class PanelBuilderView(discord.ui.View):
    def __init__(self, cog, interaction, name, channel, category, data=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.name, self.target_channel, self.target_category = name, channel, category
        self.data = data or {"name": name, "message": "", "embed": {"title":"Open Ticket", "description":"Support", "color":"grey"}, "components": {"type":"BUTTON", "options":[]}}
        self.state = WizardState.EMBED
        self.setup_ui()

    def setup_ui(self):
        self.clear_items()
        if self.state == WizardState.EMBED:
            self.add_item(EmbedPropSelect())
            self.add_item(NavButton("Setup Category", "next", discord.ButtonStyle.success))
            self.add_item(NavButton("Exit", "exit", discord.ButtonStyle.danger))
        elif self.state == WizardState.TYPE:
            self.add_item(NavButton("Select Menu", "type_sel", discord.ButtonStyle.primary, "📋"))
            self.add_item(NavButton("Buttons", "type_btn", discord.ButtonStyle.primary, "🔵"))
            self.add_item(NavButton("Back", "back_embed", discord.ButtonStyle.secondary))
            self.add_item(NavButton("Exit", "exit", discord.ButtonStyle.danger))
        elif self.state == WizardState.COMP:
            t = self.data['components']['type']
            noun = "Option" if t == "SELECT" else "Button"
            self.add_item(NavButton(f"Add {noun}", "add_comp", discord.ButtonStyle.success, "➕"))
            self.add_item(NavButton(f"Remove {noun}", "rem_comp", discord.ButtonStyle.danger, "➖"))
            self.add_item(NavButton("Finish", "finish", discord.ButtonStyle.success, "<:yes:1396838746862784582>"))
            self.add_item(NavButton("Back", "back_type", discord.ButtonStyle.secondary))
            self.add_item(NavButton("Exit", "exit", discord.ButtonStyle.danger))

    async def update(self, interaction):
        self.setup_ui()
        d = self.data['embed']
        embed = discord.Embed(title=d.get("title"), description=d.get("description"), color=parse_color(d.get("color")))
        if d.get("footer"): embed.set_footer(text=d["footer"], icon_url=d.get("footer_url"))
        if d.get("image"): embed.set_image(url=d["image"])
        if d.get("thumbnail"): embed.set_thumbnail(url=d["thumbnail"])
        
        info = f"**Editing: {self.name}**"
        if self.state == WizardState.EMBED: info += "\nStep 1: Message & Embed"
        elif self.state == WizardState.TYPE: info += "\nStep 2: Panel Type"
        else: 
            ctype = self.data['components']['type']
            info += f"\nStep 3: Edit {ctype.title()}s ({len(self.data['components']['options'])})"
            if self.data['components']['options']:
                info += f"\n\n**{ctype} LIST:**"
                for opt in self.data['components']['options']:
                    info += f"\n- {opt['label']} (Cat: {opt['category']})"
        
        msg = self.data.get("message", "")
        
        if interaction.response.is_done():
            # Using message.edit (Not edit_original_response) is safe for component updates
            await interaction.message.edit(content=f"{info}\n\nPreview Msg:\n{msg}", embed=embed, view=self)
        else:
            await interaction.response.edit_message(content=f"{info}\n\nPreview Msg:\n{msg}", embed=embed, view=self)

class NavButton(discord.ui.Button):
    def __init__(self, label, cid, style, emoji=None): super().__init__(label=label, custom_id=cid, style=style, emoji=emoji)
    async def callback(self, interaction):
        if interaction.response.is_done(): return
        v = self.view
        
        if self.custom_id == "exit":
            await interaction.response.edit_message(content="<:no:1396838761605890090> Cancelled", view=None, embed=None)
        elif self.custom_id == "next": v.state = WizardState.TYPE; await v.update(interaction)
        elif self.custom_id == "back_embed": v.state = WizardState.EMBED; await v.update(interaction)
        elif self.custom_id == "back_type": v.state = WizardState.TYPE; await v.update(interaction)
        elif self.custom_id in ["type_sel", "type_btn"]:
            v.data['components']['type'] = "SELECT" if self.custom_id == "type_sel" else "BUTTON"
            v.state = WizardState.COMP; await v.update(interaction)
        elif self.custom_id == "add_comp":
            await interaction.response.send_modal(CompModal(v, v.data['components']['type']))
        elif self.custom_id == "rem_comp":
            if not v.data['components']['options']:
                return await interaction.response.send_message("Empty.", ephemeral=True)
            await interaction.response.send_message("Remove:", view=RemCompView(v), ephemeral=True)
        elif self.custom_id == "finish":
            cfg_row = await v.cog.settings.find_one({"guild_id": interaction.guild.id})
            if not cfg_row or not cfg_row.get('staff_role_id'): 
                return await interaction.response.send_message("<:no:1396838761605890090> Staff role not set. Use `/ticket staff`.", ephemeral=True)
            
            pid = f"{interaction.guild.id}-{v.name}"
            
            await v.cog.panels.update_one(
                {"panel_id": pid},
                {"$set": {
                    "guild_id": interaction.guild.id,
                    "name": v.name,
                    "channel_id": v.target_channel.id,
                    "category_id": v.target_category.id,
                    "panel_message": v.data.get("message"),
                    "embed_json": json.dumps(v.data['embed']),
                    "component_json": json.dumps(v.data['components'])
                }},
                upsert=True
            )
            
            ed = v.data['embed']
            embed = discord.Embed(title=ed.get("title"), description=ed.get("description"), color=parse_color(ed.get("color")))
            if ed.get("footer"): embed.set_footer(text=ed["footer"], icon_url=ed.get("footer_url"))
            if ed.get("image"): embed.set_image(url=ed["image"])
            if ed.get("thumbnail"): embed.set_thumbnail(url=ed["thumbnail"])
            await v.target_channel.send(content=v.data.get("message") or None, embed=embed, view=TicketPanelView(v.cog, pid, v.data['components']))
            
            await interaction.response.edit_message(content=f"<:yes:1396838746862784582> Panel deployed to {v.target_channel.mention}", view=None, embed=None)

class EmbedPropSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Configure Embed...", options=[
            discord.SelectOption(label="Message (Outside)", value="message"),
            discord.SelectOption(label="Title", value="title"),
            discord.SelectOption(label="Description", value="description"),
            discord.SelectOption(label="Color", value="color"),
            discord.SelectOption(label="Small Image", value="thumbnail"),
            discord.SelectOption(label="Large Image", value="image"),
            discord.SelectOption(label="Footer Text", value="footer"),
            discord.SelectOption(label="Footer Image", value="footer_url")
        ])
    async def callback(self, interaction):
        if not interaction.response.is_done():
            await interaction.response.send_modal(EmbedEditModal(self.view, self.values[0]))

class RemCompView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        self.p_view = parent_view
        opts = [discord.SelectOption(label=o['label'][:25], value=str(i)) for i, o in enumerate(parent_view.data['components']['options'])]
        self.add_item(RemCompSelect(parent_view, opts))

class RemCompSelect(discord.ui.Select):
    def __init__(self, parent_view, opts): 
        super().__init__(placeholder="Select to remove", options=opts)
        self.p_view = parent_view 
    async def callback(self, interaction):
        if interaction.response.is_done(): return
        del self.p_view.data['components']['options'][int(self.values[0])]
        await interaction.response.defer()
        await self.p_view.update(interaction)

# ════════════════════════════════════════════════════════════════════════════
# MODALS
# ════════════════════════════════════════════════════════════════════════════

class EmbedEditModal(discord.ui.Modal):
    def __init__(self, view, key):
        super().__init__(title=f"Edit {key}")
        self.view, self.key = view, key
        self.val = discord.ui.TextInput(label="Value", style=discord.TextStyle.paragraph if key in ["description","message"] else discord.TextStyle.short, required=False)
        self.add_item(self.val)
    async def on_submit(self, interaction):
        if self.key == "message": self.view.data['message'] = self.val.value
        else: self.view.data['embed'][self.key] = self.val.value
        # if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
        await self.view.update(interaction)

class CompModal(discord.ui.Modal):
    def __init__(self, view, ctype):
        super().__init__(title=f"Add {ctype.title()}")
        self.view, self.ctype = view, ctype
        self.lbl = discord.ui.TextInput(label="Title/Label")
        self.cat = discord.ui.TextInput(label="Category (e.g. help-001)")
        self.emoji = discord.ui.TextInput(label="Emoji (Optional)", required=False)
        self.add_item(self.lbl); self.add_item(self.cat); self.add_item(self.emoji)
        if ctype == "BUTTON": self.col = discord.ui.TextInput(label="Color (red/green/blue/grey)"); self.add_item(self.col)
        else: self.desc = discord.ui.TextInput(label="Description", required=False); self.add_item(self.desc)
    async def on_submit(self, interaction):
        e_val = self.emoji.value.strip() or None
        d = {"label": self.lbl.value, "category": self.cat.value, "emoji": e_val}
        if self.ctype == "BUTTON": d['color'] = self.col.value
        else: d['description'] = self.desc.value
        self.view.data['components']['options'].append(d)
        # if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
        await self.view.update(interaction)

class UserModal(discord.ui.Modal):
    def __init__(self, cog, action): 
        super().__init__(title=f"{action} User")
        self.cog = cog
        self.action = action
        self.uid = discord.ui.TextInput(label="User ID")
        self.add_item(self.uid)
    
    async def on_submit(self, interaction):
        if interaction.response.is_done(): return
        try:
            u = await interaction.guild.fetch_member(int(self.uid.value))
            if self.action == "add": 
                await interaction.channel.set_permissions(u, read_messages=True, send_messages=True)
                msg="Added"
                await self.cog.notify_event(interaction, "User Added", f"{u.mention} added to the ticket.", discord.Color.green())
            else: 
                await interaction.channel.set_permissions(u, overwrite=None)
                msg="Removed"
                await self.cog.notify_event(interaction, "User Removed", f"{u.mention} removed from the ticket.", discord.Color.red())
            
            # Safe Pattern: No Edit Original Response
            try: await interaction.channel.send(embed=discord.Embed(description=f"<:yes:1396838746862784582> **{msg}** {u.mention}", color=DEFAULT_COLOR))
            except: pass
        except:
            # Safe Pattern
            try: await interaction.channel.send(embed=discord.Embed(description="<:no:1396838761605890090> User not found.", color=discord.Color.red()), delete_after=5)
            except: pass

class RenameModal(discord.ui.Modal, title="Rename Ticket"):
    name = discord.ui.TextInput(label="New Name")
    async def on_submit(self, interaction):
        if interaction.response.is_done(): return
        await interaction.channel.edit(name=self.name.value)
        try: await interaction.channel.send(embed=discord.Embed(description=f"<:yes:1396838746862784582> Renamed to **{self.name.value}**", color=DEFAULT_COLOR))
        except: pass

# ════════════════════════════════════════════════════════════════════════════
# SUBCOMMAND GROUPS
# ════════════════════════════════════════════════════════════════════════════

class PanelGroup(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="panel", description="Manage Ticket Panels")
        self.cog = cog

    async def panel_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cursor = self.cog.panels.find({"guild_id": interaction.guild.id})
        panels = await cursor.to_list(length=None)
        return [app_commands.Choice(name=r['name'], value=r['name']) for r in panels if current.lower() in r['name'].lower()][:25]

    @app_commands.command(name="create", description="Create a new ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def p_create(self, interaction: discord.Interaction, name: str, channel: discord.TextChannel, category: discord.CategoryChannel):
        if await self.cog.panels.find_one({"panel_id": f"{interaction.guild.id}-{name}"}):
            return await interaction.response.send_message(embed=discord.Embed(description="<:no:1396838761605890090> Panel name exists. Use Edit.", color=discord.Color.red()), ephemeral=True)
        await interaction.response.send_message("Setup:", view=PanelBuilderView(self.cog, interaction, name, channel, category), ephemeral=True)

    @app_commands.command(name="edit", description="Edit an existing ticket panel")
    @app_commands.autocomplete(name=panel_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def p_edit(self, interaction: discord.Interaction, name: str, channel: Optional[discord.TextChannel], category: Optional[discord.CategoryChannel]):
        row = await self.cog.panels.find_one({"panel_id": f"{interaction.guild.id}-{name}"})
        if not row: return await interaction.response.send_message("Not found.", ephemeral=True)
        
        # Load Defaults
        c = channel or interaction.guild.get_channel(row['channel_id'])
        cat = category or interaction.guild.get_channel(row['category_id'])
        
        data = {
            "name": row['name'],
            "message": row['panel_message'],
            "embed": json.loads(row['embed_json']),
            "components": json.loads(row['component_json'])
        }
        await interaction.response.send_message("Editing:", view=PanelBuilderView(self.cog, interaction, name, c, cat, data), ephemeral=True)

    @app_commands.command(name="delete", description="Delete a ticket panel")
    @app_commands.autocomplete(name=panel_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def p_delete(self, interaction: discord.Interaction, name: str):
        view = ConfirmationView()
        await interaction.response.send_message(f"Delete panel **{name}**?", view=view, ephemeral=True)
        await view.wait()
        if view.value:
            await self.cog.panels.delete_one({"panel_id": f"{interaction.guild.id}-{name}"})
            embed = discord.Embed(description="<:yes:1396838746862784582> Panel Deleted.", color=DEFAULT_COLOR)
        else:
            embed = discord.Embed(description="<:no:1396838761605890090> Cancelled.", color=discord.Color.red())
            
        if not interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
             try: await interaction.edit_original_response(content=None, embed=embed, view=None)
             except: pass

    @app_commands.command(name="list", description="List all ticket panels")
    async def p_list(self, interaction: discord.Interaction):
        cursor = self.cog.panels.find({"guild_id": interaction.guild.id})
        rows = await cursor.to_list(length=None)
        names = [r.get('panel_name', r.get('name', 'Unknown')) for r in rows]
        await interaction.response.send_message(embed=discord.Embed(title="Ticket Panels", description='\n'.join(names) if names else "None", color=DEFAULT_COLOR), ephemeral=True)

    @app_commands.command(name="reset", description="Reset ALL panels")
    @app_commands.checks.has_permissions(administrator=True)
    async def p_reset(self, interaction: discord.Interaction):
        view = ConfirmationView()
        await interaction.response.send_message(embed=discord.Embed(description="<a:alert:1396429026842644584> Reset ALL panels?", color=discord.Color.red()), view=view, ephemeral=True)
        await view.wait()
        
        # Safe Edit Pattern: Using channel.send
        if view.value:
            await self.cog.panels.delete_many({"guild_id": interaction.guild.id})
            embed = discord.Embed(description="<:yes:1396838746862784582> Reset complete.", color=discord.Color.green())
        else:
            embed = discord.Embed(description="<:no:1396838761605890090> Cancelled.", color=discord.Color.red())
        
        try: await interaction.channel.send(embed=embed)
        except: pass

class BlacklistGroup(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="blacklist", description="Manage Ticket Blacklist")
        self.cog = cog

    @app_commands.command(name="add", description="Add user to blacklist")
    @app_commands.checks.has_permissions(administrator=True)
    async def b_add(self, interaction: discord.Interaction, user: discord.User):
        await self.cog.blacklist.update_one(
            {"guild_id": interaction.guild.id, "user_id": user.id},
            {"$set": {"timestamp": datetime.datetime.now()}},
            upsert=True
        )
        await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Added {user.mention} to blacklist.", color=DEFAULT_COLOR), ephemeral=True)

    @app_commands.command(name="remove", description="Remove user from blacklist")
    @app_commands.checks.has_permissions(administrator=True)
    async def b_remove(self, interaction: discord.Interaction, user: discord.User):
        res = await self.cog.blacklist.delete_one({"guild_id": interaction.guild.id, "user_id": user.id})
        if res.deleted_count > 0:
            await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Removed {user.mention} from blacklist.", color=DEFAULT_COLOR), ephemeral=True)
        else:
            await interaction.response.send_message(embed=discord.Embed(description="<:no:1396838761605890090> User not in blacklist.", color=discord.Color.red()), ephemeral=True)

    @app_commands.command(name="list", description="List blacklisted users")
    @app_commands.checks.has_permissions(administrator=True)
    async def b_list(self, interaction: discord.Interaction):
        cursor = self.cog.blacklist.find({"guild_id": interaction.guild.id})
        users = []
        async for doc in cursor:
            users.append(f"<@{doc['user_id']}>")
        
        desc = "\n".join(users) if users else "No blacklisted users."
        await interaction.response.send_message(embed=discord.Embed(title="Blacklist", description=desc, color=DEFAULT_COLOR), ephemeral=True)

    @app_commands.command(name="reset", description="Reset blacklist")
    @app_commands.checks.has_permissions(administrator=True)
    async def b_reset(self, interaction: discord.Interaction):
        await self.cog.blacklist.delete_many({"guild_id": interaction.guild.id})
        await interaction.response.send_message(embed=discord.Embed(description="<:yes:1396838746862784582> Blacklist reset.", color=DEFAULT_COLOR), ephemeral=True)

class TicketGroup(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="ticket", description="Ticket System", guild_only=True)
        self.cog = cog
    
    @app_commands.command(name="logs", description="Set log channel for tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def t_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.cog.settings.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"log_channel_id": channel.id}},
            upsert=True
        )
        await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Ticket logs set to {channel.mention}", color=DEFAULT_COLOR), ephemeral=True)

    @app_commands.command(name="staff", description="Set staff role for tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def t_staff(self, interaction: discord.Interaction, role: discord.Role):
        await self.cog.settings.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"staff_role_id": role.id}},
            upsert=True
        )
        await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Staff role set to {role.mention}", color=DEFAULT_COLOR), ephemeral=True)

    @app_commands.command(name="add", description="Add user")
    async def t_add(self, interaction: discord.Interaction, user: discord.Member):
        if await self.cog.check_ticket(interaction):
            await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
            await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Added {user.mention}", color=DEFAULT_COLOR))
            await self.cog.notify_event(interaction, "User Added", f"{user.mention} added by {interaction.user.mention}", discord.Color.green())

    @app_commands.command(name="remove", description="Remove user")
    async def t_rem(self, interaction: discord.Interaction, user: discord.Member):
        if await self.cog.check_ticket(interaction):
            await interaction.channel.set_permissions(user, overwrite=None)
            await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Removed {user.mention}", color=DEFAULT_COLOR))
            await self.cog.notify_event(interaction, "User Removed", f"{user.mention} removed by {interaction.user.mention}", discord.Color.red())

    @app_commands.command(name="rename", description="Rename ticket")
    async def t_rename(self, interaction: discord.Interaction, name: str):
        if await self.cog.check_ticket(interaction):
            await interaction.channel.edit(name=name)
            await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> Renamed to {name}", color=DEFAULT_COLOR))

    @app_commands.command(name="close", description="Close ticket")
    async def t_close(self, interaction: discord.Interaction):
        if await self.cog.check_ticket(interaction): 
            # Safe Defer
            if not interaction.response.is_done(): await interaction.response.defer()
            async with ACTION_LOCK:
                await self.cog.handle_close(interaction)

    @app_commands.command(name="transcript", description="Generate ticket transcript")
    async def t_transcript(self, interaction: discord.Interaction):
        if await self.cog.check_ticket(interaction):
            if not interaction.response.is_done(): await interaction.response.defer()
            try:
                f = await generate_transcript(interaction.channel)
                await interaction.followup.send(file=f)
            except Exception as e:
                await interaction.followup.send(f"Error generating transcript: {e}", ephemeral=True)

    @app_commands.command(name="delete", description="Delete ticket")
    async def t_del(self, interaction: discord.Interaction):
        if await self.cog.check_ticket(interaction): 
            if not interaction.response.is_done(): await interaction.response.defer()
            async with ACTION_LOCK:
                await self.cog.handle_delete(interaction)

# ════════════════════════════════════════════════════════════════════════════
# MAIN COG
# ════════════════════════════════════════════════════════════════════════════

class TicketSetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use shared database connection to prevent name mismatches
        if hasattr(bot, 'db') and bot.db is not None:
            self.db = bot.db
        else:
            self.mongo_uri = os.getenv("MONGO_URI")
            self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            self.db = self.db_client.get_default_database()

        self.settings = self.db["ticket_settings"]
        self.tickets = self.db["tickets"]
        self.panels = self.db["ticket_panels"]
        self.blacklist = self.db["ticket_blacklist"]

    async def cog_load(self):
        print("Restoring Ticket Views...")
        restored = set()
        cursor = self.panels.find({})
        async for p in cursor:
            print(f"[DEBUG] Loading panel: {p.get('panel_id')}")
            pid = p.get('panel_id')
            if pid and pid not in restored:
                try: 
                    comp_json = p.get('component_json')
                    if comp_json:
                        self.bot.add_view(TicketPanelView(self, pid, json.loads(comp_json)))
                        restored.add(pid)
                except: pass
        self.bot.add_view(TicketManagementView(self))

        # Setup Command Tree
        self.wrapper = TicketGroup(self)
        self.wrapper.add_command(PanelGroup(self))
        self.wrapper.add_command(BlacklistGroup(self))
        self.bot.tree.add_command(self.wrapper)

    async def cog_unload(self):
        self.bot.tree.remove_command("ticket")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if hasattr(channel, "id"):
            await self.tickets.delete_one({"channel_id": channel.id})

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Close all open tickets for this user
        cursor = self.tickets.find({"owner_id": member.id, "guild_id": member.guild.id})
        async for t in cursor:
             chan = member.guild.get_channel(t['channel_id'])
             if chan:
                 await chan.edit(name=f"🔒-{chan.name}"[:100])
                 await chan.set_permissions(member.guild.default_role, read_messages=False) 
                 await chan.send(embed=discord.Embed(description=f"<:sylocktkt:1460595783933100053> **User Left.** Ticket Closed.", color=DEFAULT_COLOR))
        
        await self.tickets.update_many(
            {"owner_id": member.id, "guild_id": member.guild.id}, 
            {"$set": {"status": "closed"}}
        )

    # ════════════════════════════════════════════════════════════════════════════
    # CORE LOGIC
    # ════════════════════════════════════════════════════════════════════════════

    async def check_ticket(self, interaction: discord.Interaction) -> bool:
        if await self.tickets.find_one({"channel_id": interaction.channel.id}):
            return True
        else:
            await interaction.response.send_message(embed=discord.Embed(description="<:no:1396838761605890090> This is not a ticket.", color=discord.Color.red()), ephemeral=True)
            return False

    async def is_staff_or_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator: return True
        config = await self.settings.find_one({"guild_id": interaction.guild.id})
        if config and config.get('staff_role_id'):
            role = interaction.guild.get_role(config['staff_role_id'])
            if role and role in interaction.user.roles: return True
        return False

    async def notify_event(self, interaction: discord.Interaction, title: str, description: str, color: int, file: discord.File = None):
        # 1. Fetch Ticket Owner
        row = await self.tickets.find_one({"channel_id": interaction.channel.id})
        owner_id = row['owner_id'] if row else None
        
        owner = None
        if owner_id:
            owner = interaction.guild.get_member(owner_id)
            if not owner:
                try: owner = await interaction.guild.fetch_member(owner_id)
                except: 
                    try: owner = await interaction.client.fetch_user(owner_id)
                    except: pass
        
        # 2. Build Log Embed
        log_embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now())
        log_embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
        log_embed.add_field(name="Action By", value=interaction.user.mention, inline=True)
        
        if interaction.user.display_avatar:
            log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        if owner:
            log_embed.set_footer(text=f"Ticket Owner: {owner.name} | ID: {owner.id}")
        else:
            log_embed.set_footer(text="Ticket Owner: Left or Unknown")

        # 3. Build DM Embed
        dm_embed = discord.Embed(title=f"Ticket Update: {interaction.guild.name}", color=color)
        dm_embed.add_field(name="Action", value=title, inline=False)
        dm_embed.add_field(name="Details", value=description, inline=False)
        dm_embed.add_field(name="Ticket", value=interaction.channel.name, inline=False)
        dm_embed.set_footer(text=f"Action by: {interaction.user.name}")

        # 4. Send to Log Channel
        cfg = await self.settings.find_one({"guild_id": interaction.guild.id})
        if cfg and cfg.get('log_channel_id'):
            log_chan = interaction.guild.get_channel(cfg['log_channel_id'])
            if log_chan:
                try: 
                    # Reset file pointer for log channel send if file exists
                    if file: file.fp.seek(0)
                    await log_chan.send(embed=log_embed, file=file)
                except: pass

        # 5. Send to Owner DM
        if owner:
            if owner.id != interaction.user.id:
                try: 
                    f2 = None
                    if file:
                        file.fp.seek(0) # IMPORTANT: Reset pointer before re-sending
                        f2 = discord.File(fp=file.fp, filename=file.filename)
                    
                    await owner.send(embed=dm_embed, file=f2)

                except discord.Forbidden:
                    pass
                except Exception:
                    pass

    async def create_ticket(self, interaction, panel_id, cat_prefix):
        # Acquire Lock BEFORE Deferring to prevent parallel processing of the same user click
        async with CREATION_LOCK:
            if interaction.response.is_done(): return

            # 1. Defer immediately (Ephemeral)
            await interaction.response.defer(ephemeral=True)

            # 2. Blacklist Check
            if await self.blacklist.find_one({"guild_id": interaction.guild.id, "user_id": interaction.user.id}):
                embed = discord.Embed(description="<:no:1396838761605890090> You are blacklisted.", color=discord.Color.red())
                try: await interaction.followup.send(embed=embed, ephemeral=True)
                except: pass
                return
            
            # 3. Ghost Ticket Fix
            cursor = self.tickets.find({"owner_id": interaction.user.id, "guild_id": interaction.guild.id})
            user_tickets = await cursor.to_list(length=None)
            
            active_count = 0
            for t in user_tickets:
                if interaction.guild.get_channel(t['channel_id']):
                    active_count += 1
                else:
                    await self.tickets.delete_one({"channel_id": t['channel_id']})

            if active_count >= 2:
                embed = discord.Embed(description=f"<:no:1396838761605890090> Ticket limit reached ({active_count}/2).", color=discord.Color.red())
                try: await interaction.followup.send(embed=embed, ephemeral=True)
                except: pass
                return
            
            # 4. Create Channel
            print(f"[DEBUG] create_ticket: panel_id={panel_id}, cat_prefix={cat_prefix}")
            p = await self.panels.find_one({"panel_id": panel_id})
            print(f"[DEBUG] create_ticket: panel found? {p is not None}")
            
            c = await self.settings.find_one({"guild_id": interaction.guild.id})
            staff = interaction.guild.get_role(c['staff_role_id']) if c and c.get('staff_role_id') else None
            cat = interaction.guild.get_channel(p['category_id']) if p else None
            print(f"[DEBUG] create_ticket: category={cat}, staff={staff}")
            
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            if staff: overwrites[staff] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            name = f"{cat_prefix}-{interaction.user.name}"[:100].lower().replace(" ", "-")
            try: ch = await interaction.guild.create_text_channel(name=name, category=cat, overwrites=overwrites)
            except Exception as e: 
                try: await interaction.followup.send(embed=discord.Embed(description=f"<:no:1396838761605890090> Error: {e}", color=discord.Color.red()), ephemeral=True)
                except: pass
                return
            
            await self.tickets.insert_one({
                "ticket_id": str(ch.id),
                "guild_id": interaction.guild.id,
                "owner_id": interaction.user.id,
                "channel_id": ch.id,
                "panel_id": panel_id,
                "claimed_by": None,
                "created_at": int(datetime.datetime.now().timestamp()),
                "status": "open"
            })
            
            embed = discord.Embed(title=f"<:sytkt:1460595756552552540> {cat_prefix} Ticket", description=f"<a:dot:1396429135588626442> Welcome {interaction.user.mention}. Support will be here shortly.\n<a:dot:1396429135588626442> Kindly Describe Your issue in chat and wait for staff response.\n<a:dot:1396429135588626442> You will get updates in DM.", color=DEFAULT_COLOR)
            await ch.send(content=f"{interaction.user.mention} {staff.mention if staff else ''}", embed=embed, view=TicketManagementView(self))
            
            s_embed = discord.Embed(title="<:sytkt:1460595756552552540> Ticket Created", description=f"<:yes:1396838746862784582> Your ticket has been created: {ch.mention}", color=DEFAULT_COLOR)
            s_embed.add_field(name="Ticket Slots", value=f"> {active_count + 1}/2 used")
            
            try:
                await interaction.followup.send(content=f"{interaction.user.mention}", embed=s_embed, ephemeral=True)
            except:
                pass
            
            await self.notify_event(interaction, "Ticket Created", f"Created by {interaction.user.mention}", discord.Color.green())

    async def handle_claim(self, interaction):
        row = await self.tickets.find_one({"channel_id": interaction.channel.id})
        if row and row.get('claimed_by'):
            claimer = interaction.guild.get_member(row['claimed_by'])
            text = f"Already claimed by {claimer.mention}" if claimer else "Already claimed."
            
            # Safe Fallback Pattern
            embed = discord.Embed(description=f"<:no:1396838761605890090> {text}", color=discord.Color.red())
            try: await interaction.channel.send(embed=embed, delete_after=10)
            except: pass
            return

        await self.tickets.update_one({"channel_id": interaction.channel.id}, {"$set": {"claimed_by": interaction.user.id}})
        await interaction.channel.edit(name=f"✅-{interaction.channel.name}"[:100])
        
        # Send to channel directly
        await interaction.channel.send(embed=discord.Embed(description=f"<:yes:1396838746862784582> **Claimed by** {interaction.user.mention}", color=DEFAULT_COLOR))
        await self.notify_event(interaction, "Ticket Claimed", f"Claimed by {interaction.user.mention}", discord.Color.green())

    async def handle_close(self, interaction):
        row = await self.tickets.find_one({"channel_id": interaction.channel.id})
        if row and (o := interaction.guild.get_member(row['owner_id'])): 
            await interaction.channel.set_permissions(o, send_messages=False, read_messages=True)
            
        await interaction.channel.edit(name=f"🔒-{interaction.channel.name}"[:100])
        await self.tickets.update_one({"channel_id": interaction.channel.id}, {"$set": {"status": "closed"}})
        await interaction.channel.send(embed=discord.Embed(description=f"<:sylocktkt:1460595783933100053> **Ticket Closed by** {interaction.user.mention}", color=DEFAULT_COLOR))
        await self.notify_event(interaction, "Ticket Closed", f"Closed by {interaction.user.mention}", discord.Color.orange())

    async def handle_delete(self, interaction):
        await interaction.channel.send(embed=discord.Embed(description="<:sybin:1460595803633614848> **Deleting this Ticket in 5s...**", color=DEFAULT_COLOR))
        
        f = await generate_transcript(interaction.channel)
        await self.notify_event(interaction, "Ticket Deleted", f"Deleted by {interaction.user.mention}", discord.Color.red(), file=f)
        
        await asyncio.sleep(5)
        
        if await self.tickets.find_one({"channel_id": interaction.channel.id}):
            await self.tickets.delete_one({"channel_id": interaction.channel.id})
            try: await interaction.channel.delete()
            except: pass

    async def handle_transcript(self, interaction):
        f = await generate_transcript(interaction.channel)
        try:
            await interaction.channel.send(content="**Transcript:**", file=f)
        except:
            pass # Handle file permission issues

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=discord.Embed(description="<:no:1396838761605890090> You need **Administrator** permissions.", color=discord.Color.red()), ephemeral=True)
        else:
            print(f"Error: {error}")

async def setup(bot): await bot.add_cog(TicketSetup(bot))