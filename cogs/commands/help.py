import discord
from discord.ext import commands
from discord import app_commands, Interaction, Message
from difflib import get_close_matches
from contextlib import suppress
from core import Context
from core.Scyro import Scyro
from core.Cog import Cog
from utils.Tools import getConfig
from itertools import chain
import json
import asyncio
from utils.Tools import *
import re
from typing import Optional

color = 0x2F3136  # Dark box color

class AdvancedHelpView(discord.ui.View):
    def __init__(self, command_name, related_commands, ctx, prefix="{prefix}"):
        super().__init__(timeout=300)
        self.command_name = command_name
        self.related_commands = related_commands
        self.ctx = ctx
        self.prefix = prefix
        self.current_page = 0
        self.max_pages = len(related_commands) if related_commands else 1
        self.message: Optional[Message] = None 
        
        if self.max_pages > 1:
            self.add_navigation_buttons()

    def add_navigation_buttons(self):
        prev_button = discord.ui.Button(
            label="◀️ Previous", 
            style=discord.ButtonStyle.secondary,
            disabled=self.current_page == 0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        page_button = discord.ui.Button(
            label=f"Page {self.current_page + 1}/{self.max_pages}",
            style=discord.ButtonStyle.primary,
            disabled=True
        )
        self.add_item(page_button)
        
        next_button = discord.ui.Button(
            label="Next ▶️", 
            style=discord.ButtonStyle.secondary,
            disabled=self.current_page >= self.max_pages - 1
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

    async def previous_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            embed = self.create_command_embed()
            self.clear_items()
            if self.max_pages > 1:
                self.add_navigation_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
        
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            embed = self.create_command_embed()
            self.clear_items()
            if self.max_pages > 1:
                self.add_navigation_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

    def create_command_embed(self):
        if not self.related_commands:
            embed = discord.Embed(
                title="❌ Command Not Found",
                description=f"No command found matching `{self.command_name}`",
                color=0xFF6B6B
            )
            return embed

        command_data = self.related_commands[self.current_page]
        embed = discord.Embed(color=0x2F3136)
        
        embed.title = f" {command_data['name']} Command Help"
        embed.description = f"**Description:** {command_data['description']}\n\n"
        embed.description += f"**Usage:** `{self.prefix}{command_data['usage']}`\n\n"
        
        if command_data['aliases']:
            aliases = ", ".join([f"`{alias}`" for alias in command_data['aliases']])
            embed.description += f"**Aliases:** {aliases}\n\n"
        
        # Show ALL related commands with no limit
        if command_data['related']:
            related_cmds = []
            for cmd, desc in command_data['related']:
                related_cmds.append(f"`{cmd}` - {desc}")
            
            # Split into multiple fields if too long for one field
            if len("\n".join(related_cmds)) > 1024:
                # Split into chunks of 15 commands each
                chunk_size = 15
                for i in range(0, len(related_cmds), chunk_size):
                    chunk = related_cmds[i:i + chunk_size]
                    field_name = "🔗 Related Commands" if i == 0 else f"🔗 Related Commands (Part {i//chunk_size + 1})"
                    embed.add_field(
                        name=field_name,
                        value="\n".join(chunk),
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🔗 Related Commands",
                    value="\n".join(related_cmds),
                    inline=False
                )
        
        if command_data['examples']:
            examples = []
            for example in command_data['examples'][:5]:
                examples.append(f"`{self.prefix}{example}`")
            
            embed.add_field(
                name="💡 Examples",
                value="\n".join(examples),
                inline=False
            )
        
        # Add permissions and category info
        if command_data.get('permissions'):
            embed.add_field(
                name="<:syperms:1445414179279343740> Permissions",
                value=", ".join(command_data['permissions']),
                inline=True
            )
        
        if command_data.get('category'):
            embed.add_field(
                name="<:syfolder:1445413611609788428> Category",
                value=command_data['category'],
                inline=True
            )
        
        if command_data.get('cooldown'):
            embed.add_field(
                name="<:sycooldown:1445413901675266088> Cooldown",
                value=command_data['cooldown'],
                inline=True
            )
        
        current_time = discord.utils.utcnow()
        embed.set_footer(
            text=f"Requested by {self.ctx.author.display_name} • {current_time.strftime('%H:%M')}",
            icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None
        )
        
        return embed

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        try:
            # Safely access message attribute with proper type checking
            if self.message is not None:
                await self.message.edit(view=self)
        except:
            pass

class StructuredHelpView(discord.ui.View):
    def __init__(self, module_config, ctx, homeembed, core_utilities, essential_utilities, prefix="{prefix}"):
        super().__init__(timeout=300)
        self.module_config = module_config
        self.core_utilities = core_utilities
        self.essential_utilities = essential_utilities
        self.ctx = ctx
        self.homeembed = homeembed
        self.prefix = prefix
        self.current_module = None
        self.current_page = 0
        self.max_pages = 1
        self.message: Optional[Message] = None
        
        self.add_module_dropdowns()

    def validate_and_get_emoji(self, emoji_str, module_key, bot):
        """Validate custom emoji and return usable emoji or fallback"""
        # Unicode emoji fallbacks that ALWAYS work
        emoji_fallbacks = {
            'general': '<:sygeneral:1445408317576052910>',
            'moderation': '<:symoderation:1445408640549916842>', 
            'security': '<:sysecurity:1445409068108877885>',
            'automod': '<:syautomod:1445409419511730239>',
            'extra': '<:syextra:1445410337787740160>',
            'fun': '<:syfun:1445410830354088141>',
            'giveaways': '<:sygifts:1445411264087199794>',
            'welcome': '<:sygreet:1445411663275888772>',
            'ticket': '<:syticket:1445412067300479027>',
            'management': '<:symanagement:1445412747259936860>',
            'logging': '<:sylogging:1445412355314815198>',
            'tempvc': '<:sytempc:1445413019336183808>',
            'vc': '<:syvoicechat:1445413220394340402>',
            'music': '<:symusic:1447245745559310446>',
            'verification': '<:syverify:1454404002094649375>',
            'nightmode': '<:synightmode:1454403977990111283>',
            'embeds': '<:embeds:1454403990010724506>',
            'automation': '<:ar:1456972164644343868>',
            'tracker': '<:tracker:1456972153189695735>',
        }
        
        # If it's not a custom emoji format, return as-is (Unicode emoji)
        if not emoji_str.startswith('<:') or not emoji_str.endswith('>'):
            return emoji_str
        
        try:
            # Extract emoji ID from custom emoji format <:name:id>
            parts = emoji_str.split(':')
            if len(parts) != 3:
                print(f"⚠️ Invalid emoji format: {emoji_str}, using fallback")
                return emoji_fallbacks.get(module_key, '⚙️')
            
            emoji_name = parts[1]
            emoji_id_str = parts[2][:-1]  # Remove the closing >
            
            # Check if it's a valid number
            try:
                emoji_id = int(emoji_id_str)
            except ValueError:
                print(f"⚠️ Invalid emoji ID: {emoji_id_str}, using fallback")
                return emoji_fallbacks.get(module_key, '⚙️')
            
            # Try to get the emoji object
            emoji_obj = bot.get_emoji(emoji_id)
            if emoji_obj and emoji_obj.is_usable():
                return emoji_str  # Return original custom emoji
            else:
                return emoji_fallbacks.get(module_key, '⚙️')
        
        except (ValueError, IndexError, AttributeError) as e:
            print(f"⚠️ Error with emoji {emoji_str}: {e}, using fallback")
            return emoji_fallbacks.get(module_key, '⚙️')

    def add_module_dropdowns(self):
        """Add two dropdowns: Core Utilities and Essential Utilities"""
        # Core Utilities Dropdown
        core_options = [
            discord.SelectOption(
                label="Index",
                description="Home menu",
                emoji="<:mainmenu:1445406899658035332>",
                value="home_core"
            )
        ]
        
        for module_key in self.core_utilities:
            module_data = self.module_config.get(module_key)
            if module_data and isinstance(module_data, dict):
                command_count = sum(len(cmds) for cmds in module_data.get('commands', {}).values())
                
                original_emoji = module_data.get('emoji', '⚙️')
                safe_emoji = self.validate_and_get_emoji(original_emoji, module_key, self.ctx.bot)
                
                try:
                    core_options.append(
                        discord.SelectOption(
                            label=module_data['name'],
                            description=f"See {module_data['name']} Commands",
                            emoji=safe_emoji,
                            value=module_key
                        )
                    )
                except Exception as e:
                    print(f"❌ Failed to add option for {module_key} with emoji {safe_emoji}: {e}")
                    core_options.append(
                        discord.SelectOption(
                            label=module_data['name'],
                            description=f"See {module_data['name']} Commands",
                            value=module_key
                        )
                    )
        
        core_dropdown = discord.ui.Select(
            placeholder="Core Utilities...",
            options=core_options[:25],
            row=2
        )
        core_dropdown.callback = self.dropdown_callback
        self.add_item(core_dropdown)
        
        # Essential Utilities Dropdown
        essential_options = [
            discord.SelectOption(
                label="Index",
                description="Home menu",
                emoji="<:mainmenu:1445406899658035332>",
                value="home_essential"
            )
        ]
        
        for module_key in self.essential_utilities:
            module_data = self.module_config.get(module_key)
            if module_data and isinstance(module_data, dict):
                command_count = sum(len(cmds) for cmds in module_data.get('commands', {}).values())
                
                original_emoji = module_data.get('emoji', '⚙️')
                safe_emoji = self.validate_and_get_emoji(original_emoji, module_key, self.ctx.bot)
                
                try:
                    essential_options.append(
                        discord.SelectOption(
                            label=module_data['name'],
                            description=f"See {module_data['name']} Commands",
                            emoji=safe_emoji,
                            value=module_key
                        )
                    )
                except Exception as e:
                    print(f"❌ Failed to add option for {module_key} with emoji {safe_emoji}: {e}")
                    essential_options.append(
                        discord.SelectOption(
                            label=module_data['name'],
                            description=f"See {module_data['name']} Commands",
                            value=module_key
                        )
                    )
        
        essential_dropdown = discord.ui.Select(
            placeholder="Essential Utilities...",
            options=essential_options[:25],
            row=3
        )
        essential_dropdown.callback = self.dropdown_callback
        self.add_item(essential_dropdown)

    def add_pagination_buttons(self):
        """Add pagination buttons: Previous, Home, Next"""
        # Previous Button
        prev_button = discord.ui.Button(
            emoji="<:syarr1:1460627377783705661>",
            style=discord.ButtonStyle.secondary,
            disabled=self.current_page == 0,
            row=0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Home Button
        home_button = discord.ui.Button(
            emoji="<:mainmenu:1445406899658035332>",
            style=discord.ButtonStyle.secondary,
            row=0
        )
        home_button.callback = self.home_page
        self.add_item(home_button)
        
        # Next Button
        next_button = discord.ui.Button(
            emoji="<:syarr2:1460627388500279358>",
            style=discord.ButtonStyle.secondary,
            disabled=self.current_page >= self.max_pages - 1,
            row=0
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

    async def previous_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
            
        if self.current_module and self.current_page > 0:
            self.current_page -= 1
            module_data = self.module_config.get(self.current_module)
            if module_data:
                embed, total_pages = await self.create_module_embed(self.current_module, module_data, page=self.current_page)
                self.max_pages = total_pages
                
                self.clear_items()
                self.add_module_dropdowns()
                self.add_pagination_buttons()
                
                await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
            
        if self.current_module and self.current_page < self.max_pages - 1:
            self.current_page += 1
            module_data = self.module_config.get(self.current_module)
            if module_data:
                embed, total_pages = await self.create_module_embed(self.current_module, module_data, page=self.current_page)
                self.max_pages = total_pages
                
                self.clear_items()
                self.add_module_dropdowns()
                self.add_pagination_buttons()
                
                await interaction.response.edit_message(embed=embed, view=self)

    async def home_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
        
        self.current_module = None
        self.current_page = 0
        self.max_pages = 1
        
        self.clear_items()
        self.add_module_dropdowns()
        # No pagination buttons on home page
        
        await interaction.response.edit_message(embed=self.homeembed, view=self)

    async def dropdown_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
        
        # Safely extract selected value from interaction data
        if interaction.data and 'values' in interaction.data and interaction.data['values']:
            selected_value = interaction.data['values'][0]
        else:
            return  # Invalid interaction data
        
        if selected_value == "home_core" or selected_value == "home_essential" or selected_value == "home":
            self.current_module = None
            self.current_page = 0
            self.clear_items()
            self.add_module_dropdowns()
            await interaction.response.edit_message(embed=self.homeembed, view=self)
        else:
            module_data = self.module_config.get(selected_value)
            if module_data:
                self.current_module = selected_value
                self.current_page = 0
                
                embed, total_pages = await self.create_module_embed(selected_value, module_data, page=0)
                self.max_pages = total_pages
                
                self.clear_items()
                self.add_module_dropdowns()
                self.add_pagination_buttons()
                
                await interaction.response.edit_message(embed=embed, view=self)


    def get_all_commands_from_module(self, commands_dict):
        """Get ALL commands from a module, preserving compound commands"""
        all_commands = []
        seen = set()
        
        for category_name, category_commands in commands_dict.items():
            for cmd, desc in category_commands:
                # Remove parameter brackets but keep the full command structure
                cmd_clean = re.sub(r'<[^>]*>', '', cmd)  # Remove <@user>, <#channel>, etc.
                cmd_clean = re.sub(r'\[[^\]]*\]', '', cmd_clean)  # Remove [optional] parts
                cmd_clean = cmd_clean.strip()
                
                # Only add if we haven't seen this exact command before
                if cmd_clean and cmd_clean not in seen:
                    seen.add(cmd_clean)
                    all_commands.append((cmd_clean, desc))
        
        return all_commands

    async def create_module_embed(self, module_key, module_data, page=0):
        embed = discord.Embed(color=0x2F3136)
        
        # Get safe emoji for embed (Unicode fallback)
        original_emoji = module_data.get('emoji', '⚙️')
        safe_emoji = self.validate_and_get_emoji(original_emoji, module_key, self.ctx.bot)
        
        embed.title = f"{safe_emoji} __**{module_data['name']}**__"
        
        # Get ALL commands from the module
        commands = module_data.get('commands', {})
        all_commands = self.get_all_commands_from_module(commands)
        
        # Pagination Logic
        items_per_page = 10
        total_pages = (len(all_commands) + items_per_page - 1) // items_per_page
        if total_pages < 1:
            total_pages = 1
            
        # Adjust page if out of bounds
        if page >= total_pages:
            page = total_pages - 1
        elif page < 0:
            page = 0
            
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        current_commands = all_commands[start_idx:end_idx]
        
        # Format:
        # **`command`**
        # Description
        
        # Chunking Logic to prevent Overflow (still useful for long descriptions)
        chunks = []
        current_chunk = ""
        
        for cmd, desc in current_commands:
            entry = f"**`{self.prefix}{cmd}`**\n{desc}\n\n"
            
            # Discord limit is 4096 for description, 1024 for fields
            # We use a safe limit of 3800 for description and 1000 for fields
            limit = 3800 if len(chunks) == 0 else 1000
            
            if len(current_chunk) + len(entry) > limit:
                chunks.append(current_chunk)
                current_chunk = entry
            else:
                current_chunk += entry
                
        if current_chunk:
            chunks.append(current_chunk)

        # Add to embed
        if chunks:
            embed.description = chunks[0]
            for i in range(1, len(chunks)):
                embed.add_field(name="​", value=chunks[i], inline=False) # Zero width space name
        else:
             embed.description = "No commands found in this module."
        
        current_time = discord.utils.utcnow()
        embed.set_thumbnail(url=self.ctx.bot.user.display_avatar.url)
        embed.set_footer(
            text=f"Page {page + 1}/{total_pages} • {self.ctx.author.display_name} • {current_time.strftime('%H:%M')}",
            icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None
        )
        
        return embed, total_pages

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        
        try:
            # Safely access message attribute with proper type checking
            if self.message is not None:
                await self.message.edit(view=self)
        except:
            pass

class CustomHelpCommand(commands.HelpCommand):
    def __init__(self, **options):
        super().__init__(**options)
        self.command_database = self.build_command_database()

    def build_command_database(self):
        """Advanced command database with ALL commands present in the bot"""
        # Existing database + NEW MUSIC COMMANDS
        base_db = {
            # ... [Previous commands like ship, antinuke, etc. remain unchanged] ...
            # I am adding the music commands here:
            # --- CUSTOM PROFILE COMMANDS ---
            "customprofile": {
                "name": "<:sygeneral:1445408317576052910> Custom Profile",
                "description": "Manage per-server bot profile customizations",
                "usage": "customprofile <subcommand>",
                "aliases": ["c"],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "3 seconds",
                "examples": ["customprofile bot avatar <url>", "customprofile config"],
                "related": [("customprofile bot", "Bot settings"), ("customprofile config", "View config")]
            },
            "customprofile bot": {
                "name": "<:sygeneral:1445408317576052910> Bot Profile",
                "description": "Customize the bot's appearance for this server",
                "usage": "customprofile bot <subcommand>",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "3 seconds",
                "examples": ["customprofile bot avatar <url>", "customprofile bot name <name>"],
                "related": [("customprofile bot avatar", "Set Avatar"), ("customprofile bot bio", "Set Bio")]
            },
            "customprofile bot avatar": {
                "name": "<:sygeneral:1445408317576052910> Bot Avatar",
                "description": "Set the bot's avatar for this server",
                "usage": "customprofile bot avatar <url>",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "5 seconds",
                "examples": ["customprofile bot avatar https://imgur.com/..."],
                "related": [("customprofile bot banner", "Set Banner"), ("customprofile reset", "Reset Profile")]
            },
            "customprofile bot banner": {
                "name": "<:sygeneral:1445408317576052910> Bot Banner",
                "description": "Set the bot's banner for this server",
                "usage": "customprofile bot banner <url>",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "5 seconds",
                "examples": ["customprofile bot banner https://imgur.com/..."],
                "related": [("customprofile bot avatar", "Set Avatar")]
            },
            "customprofile bot bio": {
                "name": "<:sygeneral:1445408317576052910> Bot Bio",
                "description": "Set the bot's bio for this server (Popup)",
                "usage": "customprofile bot bio",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "3 seconds",
                "examples": ["customprofile bot bio"],
                "related": [("customprofile bot name", "Set Name")]
            },
            "customprofile bot name": {
                "name": "<:sygeneral:1445408317576052910> Bot Name",
                "description": "Set the bot's nickname for this server",
                "usage": "customprofile bot name <nickname>",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "3 seconds",
                "examples": ["customprofile bot name MyCoolBot"],
                "related": [("customprofile bot bio", "Set Bio")]
            },
            "customprofile config": {
                "name": "<:sygeneral:1445408317576052910> Profile Config",
                "description": "View current custom profile settings",
                "usage": "customprofile config",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only"],
                "cooldown": "3 seconds",
                "examples": ["customprofile config"],
                "related": [("customprofile reset", "Reset Profile")]
            },
            "customprofile reset": {
                "name": "<:sygeneral:1445408317576052910> Profile Reset",
                "description": "Reset all custom profile settings",
                "usage": "customprofile reset",
                "aliases": [],
                "category": "General",
                "permissions": ["Premium Only", "Admin"],
                "cooldown": "10 seconds",
                "examples": ["customprofile reset"],
                "related": [("customprofile config", "View config")]
            },
            "play": {
                "name": "<:symusic:1447245745559310446> Play",
                "description": "Play a song from a link or search query",
                "usage": "play <query>",
                "aliases": ["p"],
                "category": "Music",
                "permissions": ["Connect", "Speak"],
                "cooldown": "3 seconds",
                "examples": ["play Lo-fi", "play https://youtube.com/..."],
                "related": [("stop", "Stop music"), ("pause", "Pause music"), ("skip", "Skip song")]
            },
            "stop": {
                "name": "<:symusic:1447245745559310446> Stop",
                "description": "Stop the music and clear the queue",
                "usage": "stop",
                "aliases": [],
                "category": "Music",
                "permissions": ["Requestor Only"],
                "cooldown": "3 seconds",
                "examples": ["stop"],
                "related": [("play", "Play music"), ("leave", "Leave channel")]
            },
            "pause": {
                "name": "<:symusic:1447245745559310446> Pause",
                "description": "Pause or resume the current track",
                "usage": "pause",
                "aliases": [],
                "category": "Music",
                "permissions": ["Requestor Only"],
                "cooldown": "3 seconds",
                "examples": ["pause"],
                "related": [("play", "Play music"), ("stop", "Stop music")]
            },
            "skip": {
                "name": "<:symusic:1447245745559310446> Skip",
                "description": "Skip the current song",
                "usage": "skip",
                "aliases": [],
                "category": "Music",
                "permissions": ["Requestor Only"],
                "cooldown": "3 seconds",
                "examples": ["skip"],
                "related": [("stop", "Stop music"), ("play", "Play music")]
            },
            "volume": {
                "name": "<:symusic:1447245745559310446> Volume",
                "description": "Adjust the player volume",
                "usage": "volume <0-100>",
                "aliases": ["vol"],
                "category": "Music",
                "permissions": ["Requestor Only"],
                "cooldown": "3 seconds",
                "examples": ["volume 50", "vol 100"],
                "related": [("play", "Play music")]
            },
            "shuffle": {
                "name": "<:symusic:1447245745559310446> Shuffle",
                "description": "Shuffle the current queue",
                "usage": "shuffle",
                "aliases": [],
                "category": "Music",
                "permissions": ["Administrator"],
                "cooldown": "3 seconds",
                "examples": ["shuffle"],
                "related": [("showqueue", "Show queue"), ("clearqueue", "Clear queue")]
            },
            "clearqueue": {
                "name": "<:symusic:1447245745559310446> Clear Queue",
                "description": "Clear all songs in the queue",
                "usage": "clearqueue",
                "aliases": ["cq"],
                "category": "Music",
                "permissions": ["Administrator"],
                "cooldown": "3 seconds",
                "examples": ["clearqueue", "cq"],
                "related": [("shuffle", "Shuffle queue"), ("stop", "Stop music")]
            },
            "showqueue": {
                "name": "<:symusic:1447245745559310446> Show Queue",
                "description": "Display the next 10 songs in the queue",
                "usage": "showqueue",
                "aliases": ["queue", "q"],
                "category": "Music",
                "permissions": ["Send Messages"],
                "cooldown": "3 seconds",
                "examples": ["showqueue", "q"],
                "related": [("play", "Play music"), ("nowplaying", "Current song")]
            },
            "nowplaying": {
                "name": "<:symusic:1447245745559310446> Now Playing",
                "description": "Show the currently playing song",
                "usage": "nowplaying",
                "aliases": ["np"],
                "category": "Music",
                "permissions": ["Send Messages"],
                "cooldown": "3 seconds",
                "examples": ["nowplaying", "np"],
                "related": [("showqueue", "Show queue"), ("play", "Play music")]
            },
            "filter": {
                "name": "<:symusic:1447245745559310446> Filter",
                "description": "Apply audio filters like Nightcore or Vaporwave",
                "usage": "filter [enable/disable] [type]",
                "aliases": [],
                "category": "Music",
                "permissions": ["Requestor Only"],
                "cooldown": "3 seconds",
                "examples": ["filter enable nightcore", "filter disable"],
                "related": [("play", "Play music")]
            },
            "autoplay": {
                "name": "<:symusic:1447245745559310446> Autoplay",
                "description": "Toggle automatic playback of related songs",
                "usage": "autoplay",
                "aliases": [],
                "category": "Music",
                "permissions": ["Requestor Only"],
                "cooldown": "3 seconds",
                "examples": ["autoplay"],
                "related": [("play", "Play music")]
            },
            # --- Tracker Commands ---
            "leaderboard": {
                "name": "<:tracker:1456972153189695735> Leaderboard",
                "description": "View the server leaderboard for messages or voice",
                "usage": "leaderboard",
                "aliases": ["lb"],
                "category": "Tracker",
                "permissions": ["Send Messages"],
                "cooldown": "5 seconds",
                "examples": ["leaderboard", "lb"],
                "related": [("userstats", "Check user stats"), ("serverstats", "Check server stats")]
            },
            "userstats": {
                "name": "<:tracker:1456972153189695735> User Stats",
                "description": "View detailed statistics for a user",
                "usage": "userstats [@user]",
                "aliases": ["us"],
                "category": "Tracker",
                "permissions": ["Send Messages"],
                "cooldown": "5 seconds",
                "examples": ["userstats", "userstats @user", "us @user"],
                "related": [("leaderboard", "Check leaderboard"), ("serverstats", "Check server stats")]
            },
            "serverstats": {
                "name": "<:tracker:1456972153189695735> Server Stats",
                "description": "View comprehensive server statistics",
                "usage": "serverstats",
                "aliases": ["ss"],
                "category": "Tracker",
                "permissions": ["Send Messages"],
                "cooldown": "10 seconds",
                "examples": ["serverstats", "ss"],
                "related": [("leaderboard", "Check leaderboard"), ("userstats", "Check user stats")]
            },
            "level": {
                "name": "<:tracker:1456972153189695735> Level/Rank",
                "description": "Check your current level, rank, and XP progress",
                "usage": "level [@user]",
                "aliases": ["rank", "xp"],
                "category": "Tracker",
                "permissions": ["Send Messages"],
                "cooldown": "3 seconds",
                "examples": ["level", "rank @user", "xp"],
                "related": [("userstats", "Check stats"), ("leaderboard", "Check leaderboard")]
            },
            "leveling": {
                "name": "<:tracker:1456972153189695735> Leveling",
                "description": "Base command for leveling system configuration",
                "usage": "leveling <subcommand>",
                "aliases": [],
                "category": "Tracker",
                "permissions": ["Manage Guild"],
                "cooldown": "3 seconds",
                "examples": ["leveling config", "leveling setup", "leveling reset"],
                "related": [("leveling setup", "Setup leveling"), ("leveling config", "View config")]
            },
            "leveling setup": {
                "name": "<:tracker:1456972153189695735> Leveling Setup",
                "description": "Quick setup link for the leveling system",
                "usage": "leveling setup",
                "aliases": [],
                "category": "Tracker",
                "permissions": ["Manage Guild"],
                "cooldown": "3 seconds",
                "examples": ["leveling setup"],
                "related": [("leveling config", "View config")]
            },
            "leveling config": {
                "name": "<:tracker:1456972153189695735> Leveling Config",
                "description": "View the current leveling configuration",
                "usage": "leveling config",
                "aliases": [],
                "category": "Tracker",
                "permissions": ["Manage Guild"],
                "cooldown": "3 seconds",
                "examples": ["leveling config"],
                "related": [("leveling setup", "Setup leveling")]
            },
            "leveling reset": {
                "name": "<:tracker:1456972153189695735> Leveling Reset",
                "description": "Reset all leveling data for this server (Irreversible)",
                "usage": "leveling reset",
                "aliases": [],
                "category": "Tracker",
                "permissions": ["Administrator"],
                "cooldown": "10 seconds",
                "examples": ["leveling reset"],
                "related": [("leveling config", "View config")]
            },
            # --- Previous Commands ---
            "ship": {
                "name": "<:syfun:1445410830354088141> Ship/Love",
                "description": "Calculate love compatibility percentage between two users with fun messages and images",
                "usage": "ship [@user1] [@user2]",
                "aliases": ["love"],
                "category": "Fun",
                "permissions": ["Send Messages"],
                "cooldown": "5 seconds",
                "examples": ["ship", "ship @user1", "ship @user1 @user2", "love @user1 @user2"],
                "related": [("ship", "Calculate love compatibility"), ("love", "Alias for ship command")]
            },
            "love": {
                "name": "<:syfun:1445410830354088141> Ship/Love",
                "description": "Alias for ship command - Calculate love compatibility percentage between two users",
                "usage": "love [@user1] [@user2]",
                "aliases": ["ship"],
                "category": "Fun",
                "permissions": ["Send Messages"],
                "cooldown": "5 seconds",
                "examples": ["love", "love @user1", "love @user1 @user2"],
                "related": [("ship", "Calculate love compatibility")]
            },
            "antinuke": {
                "name": "<:sysecurity:1445409068108877885> Antinuke",
                "description": "Main antinuke protection system to prevent server raids and malicious actions",
                "usage": "antinuke [subcommand]",
                "aliases": ["an", "anti"],
                "category": "Security",
                "permissions": ["Administrator"],
                "cooldown": "5 seconds",
                "examples": ["antinuke enable", "antinuke disable", "antinuke config", "antinuke setup", "antinuke log"],
                "related": [("antinuke enable", "Enable antinuke"), ("whitelist", "Manage whitelist")]
            },
            "automod": {
                "name": "<:syautomod:1445409419511730239> Automod",
                "description": "Advanced automated moderation system that automatically detects and punishes rule violations",
                "usage": "automod [subcommand]",
                "aliases": ["am", "auto"],
                "category": "Automod",
                "permissions": ["Administrator", "Manage Messages"],
                "cooldown": "3 seconds",
                "examples": ["automod enable", "automod disable", "automod config", "automod punishment ban"],
                "related": [("automod enable", "Enable automod"), ("banword", "Manage banned words")]
            },
            "banword": {
                "name": "<:blacklisted3:1418851196319305848> Banword",
                "description": "Manage banned words that trigger automod actions",
                "usage": "banword [subcommand]",
                "aliases": ["baw", "badwords"],
                "category": "Automod",
                "permissions": ["Administrator", "Manage Messages"],
                "cooldown": "3 seconds",
                "examples": ["banword add badword", "banword remove badword", "banword reset"],
                "related": [("banword add", "Add word"), ("automod enable", "Enable automod")]
            },
            "ban": {
                "name": "<:symoderation:1445408640549916842> Ban",
                "description": "Ban a user from the server permanently",
                "usage": "ban <@user> [reason]",
                "aliases": ["b"],
                "category": "Moderation",
                "permissions": ["Ban Members"],
                "cooldown": "2 seconds",
                "examples": ["ban @user spamming", "ban 123456789012345678 raiding"],
                "related": [("kick", "Kick user"), ("mute", "Mute user")]
            },
            "tempvc": {
                "name": "<:sytempc:1445413019336183808> Temp Voice Channel",
                "description": "Create a temporary voice channel for a user",
                "usage": "tempvc setup | logs | reset",
                "aliases": ["tempvc"],
                "category": "TempVC",
                "permissions": ["Administrator"],
                "cooldown": "3 seconds",
                "examples": ["tempvc setup", "tempvc logs", "tempvc reset"],
                "related": [("tempvc setup", "Set up temp voice"), ("tempvc logs", "set logs")]
            },
            "kick": {
                "name": "<:symoderation:1445408640549916842> Kick",
                "description": "Remove a user from the server (they can rejoin)",
                "usage": "kick <@user> [reason]",
                "aliases": ["k"],
                "category": "Moderation",
                "permissions": ["Kick Members"],
                "cooldown": "2 seconds",
                "examples": ["kick @user spamming"],
                "related": [("ban", "Ban user"), ("mute", "Mute user")]
            },
            "list": {
                "name": "<:list3:1418851206503075920> List",
                "description": "List various server information and members",
                "usage": "list <type>",
                "aliases": ["list"],
                "category": "Utility",
                "permissions": ["Send Messages"],
                "cooldown": "3 seconds",
                "examples": ["list admins", "list mods", "list roles", "list emojis"],
                "related": [("boosters", "List boosters"), ("list admins", "List admins")]
            },
            "role": {
                "name": "<:role3:1418851215441395793> Role",
                "description": "Manage server roles and role assignments",
                "usage": "role <subcommand>",
                "aliases": ["r"],
                "category": "Moderation",
                "permissions": ["Manage Roles"],
                "cooldown": "3 seconds",
                "examples": ["role add @user @role", "role remove @user @role"],
                "related": [("role add", "Add role"), ("role remove", "Remove role")]
            },
            "mute": {
                "name": "<:symoderation:1445408640549916842> Mute", 
                "description": "Temporarily mute a user to prevent them from speaking",
                "usage": "mute <@user> [time] [reason]",
                "aliases": ["m"],
                "category": "Moderation",
                "permissions": ["Manage Messages"],
                "cooldown": "2 seconds",
                "examples": ["mute @user 10m spamming"],
                "related": [("unmute", "Unmute user"), ("timeout", "Timeout user")]
            },
            "embed": {
                "name": "<:embed3:1418851225947869234> Embed",
                "description": "Create and manage custom embeds for your server",
                "usage": "embed <subcommand>",
                "aliases": ["emb"],
                "category": "Utility",
                "permissions": ["Manage Messages"],
                "cooldown": "3 seconds",
                "examples": ["embed create welcome", "embed edit welcome"],
                "related": [("embed create", "Create embed"), ("embed send", "Send embed")]
            },
            "ticket": {
                "name": "<:syticket:1445412067300479027> Ticket",
                "description": "Manage support ticket system for user assistance",
                "usage": "ticket <subcommand>",
                "aliases": ["tickets"],
                "category": "Management",
                "permissions": ["Manage Channels"],
                "cooldown": "3 seconds",
                "examples": ["ticket panel create <#tickets>", "ticket staff @support"],
                "related": [("ticket panel create"), ("ticket close", "Close ticket")]
            },
            "welcome": {
                "name": "<:sygreet:1445411663275888772> Welcome",
                "description": "Manage welcome messages and greeting system for new members",
                "usage": "welcome <subcommand>",
                "aliases": ["greet"],
                "category": "Welcome",
                "permissions": ["Manage Messages"],
                "cooldown": "3 seconds",
                "examples": ["welcome setup #welcome", "welcome edit Welcome {user}!"],
                "related": [("welcome setup", "Setup welcome"), ("welcome test", "Test welcome")]
            },
            "giveaway": {
                "name": "<:sygifts:1445411264087199794> Giveaway",
                "description": "Manage server giveaways and contests",
                "usage": "giveaway <subcommand>",
                "aliases": ["gw"],
                "category": "Giveaways",
                "permissions": ["Manage Messages"],
                "cooldown": "5 seconds",
                "examples": ["giveaway start 1h Discord Nitro", "giveaway list"],
                "related": [("giveaway start", "Start giveaway"), ("giveaway reroll", "Reroll winner")]
            },
            "vcrole": {
                "name": "<:syvoicechat:1445413220394340402> VCRole",
                "description": "Manage voice channel roles and automatic role assignment",
                "usage": "vcrole <subcommand>",
                "aliases": ["vcr", "voicerole"],
                "category": "Voice",
                "permissions": ["Manage Roles"],
                "cooldown": "3 seconds",
                "examples": ["vcrole add @role", "vcrole config"],
                "related": [("vcrole add", "Add voice role"), ("vcrole status", "Check status")]
            },
            "reactionrole": {
                "name": "<:role3:1418851215441395793> Reaction Role",
                "description": "Manage reaction roles for automatic role assignment",
                "usage": "reactionrole <subcommand>",
                "aliases": ["rr"],
                "category": "Management",
                "permissions": ["Manage Roles"],
                "cooldown": "5 seconds",
                "examples": ["reactionrole add 123456789012345678 🎉 @Member"],
                "related": [("reactionrole add", "Add reaction role"), ("autorole setup", "Setup autorole")]
            },
            "verification": {
                "name": "✅ Verification",
                "description": "Manage server member verification system",
                "usage": "verification <subcommand>",
                "aliases": ["verify", "verif"],
                "category": "Security",
                "permissions": ["Administrator"],
                "cooldown": "3 seconds",
                "examples": ["verification setup #verify @Member", "verification config", "verification reset"],
                "related": [("verification setup", "Setup verification"), ("verification edit", "Edit verification")]
            },
            "autoresponder": {
                "name": "<:ar:1456972164644343868> Auto Responder",
                "description": "Automatically respond to specific triggers in chat",
                "usage": "autoresponder <subcommand>",
                "aliases": ["ar"],
                "category": "Automation",
                "permissions": ["Manage Guild"],
                "cooldown": "3 seconds",
                "examples": ["autoresponder create hello hi", "autoresponder list", "autoresponder delete hello"],
                "related": [("autoresponder create", "Create response"), ("autoreact", "Auto reactions")]
            },
            "autoreact": {
                "name": "<:ar:1456972164644343868> Auto React",
                "description": "Automatically react with emojis to specific triggers",
                "usage": "autoreact <subcommand>",
                "aliases": ["atr"],
                "category": "Automation",
                "permissions": ["Manage Guild"],
                "cooldown": "3 seconds",
                "examples": ["autoreact create hello 👋", "autoreact list", "autoreact delete hello"],
                "related": [("autoreact create", "Create reaction"), ("autoresponder", "Auto responders")]
            }
        }
        return base_db

    def get_module_config(self):
        """Complete configuration with ALL commands - Using Unicode emojis for reliability"""
        return {
            "music": {
                "emoji": "<:symusic:1447245745559310446>", 
                "name": "Music",
                "description": "High quality music playback",
                "commands": {
                    "Playback": [
                        ("play <query>", "Play a song"),
                        ("stop", "Stop music and disconnect"),
                        ("pause", "Pause/Resume music"),
                        ("skip", "Skip current song"),
                        ("volume <0-100>", "Set volume"),
                        ("autoplay", "Toggle autoplay")
                    ],
                    "Queue Management": [
                        ("showqueue", "Show current queue"),
                        ("shuffle", "Shuffle queue (Admin)"),
                        ("clearqueue", "Clear queue (Admin)"),
                        ("nowplaying", "Show current song info")
                    ],
                    "Effects": [
                        ("filter enable <type>", "Enable effects (Nightcore, etc.)"),
                        ("filter disable", "Disable all effects")
                    ]
                }
            },
            "general": {
                "emoji": "<:sygeneral:1445408317576052910>", 
                "name": "General",
                "description": "Core bot functionality and utilities",
                "commands": {
                    "Status & Profile": [
                        ("customprofile bot avatar <url>", "Customize bot avatar"),
                        ("customprofile bot bio", "Customize bot bio"),
                        ("customprofile bot banner <url>", "Customize bot banner"),
                        ("customprofile bot name <name>", "Customize bot name"),
                        ("customprofile config", "See the custom profile config"),
                        ("customprofile reset", "Reset custom profile"),
                        ("status", "Check anyone's status"),
                        ("stats", "Check Scyros Performance"),
                        ("afk <reason>", "Set AFK status"),
                        ("avatar <@user>", "Get user avatar"),
                        ("banner <@user>", "Get user banner"),
                        ("servericon", "Get server icon"),
                        ("membercount", "Get server member count"),
                        ("hash <text>", "Generate hash"),
                        ("snipe", "Snipe deleted messages")
                    ],
                    "Utility": [
                        ("poll <question>", "Create a poll"),
                        ("hack <@user>", "Fun hack command"),
                        ("token <@user>", "Fun token command"),
                        ("users", "List users"),
                        ("wizz <@user>", "Wizz command"),
                        ("urban <term>", "Urban dictionary lookup"),
                        ("rickroll <url>", "Check if a link contains a rickroll")
                    ],
                    "List Commands": [
                        ("boosters", "List server boosters"),
                        ("list inrole", "List users in role"),  
                        ("list emojis", "List server emojis"),
                        ("botlist", "List server bots"),
                        ("list admins", "List server admins"),
                        ("list join date", "List members join dates"),
                        ("list mods", "List server moderators"),
                        ("list invoice", "List invoices"),
                        ("list early", "List early supporters"),
                        ("list roles", "List server roles"),
                        ("users", "List all users"),
                        ("serverinfo", "Get server information"),
                        ("membercount", "Get member count"),
                        ("boostcount", "Get boost count")
                    ]
                }
            },
            "moderation": {
                "emoji": "<:symoderation:1445408640549916842>", 
                "name": "Moderation",
                "description": "Server moderation & management",
                "commands": {
                    "User Management": [
                        ("audit <@user>", "Audit user actions"),
                        ("warn <@user> [reason]", "Warn a user"),
                        ("warn add <@user> [reason]", "Add a warning"),
                        ("warn list <@user>", "Show warnings"),
                        ("warn clear <@user>", "Clear warnings"),
                        ("clearwarns <@user>", "Clear all warnings"),
                        ("ban <@user> [reason]", "Ban a user"),
                        ("unbanall", "Unban all users"),
                        ("kick <@user> [reason]", "Kick a user"),
                        ("mute <@user> [time] [reason]", "Mute a user"),
                        ("unmute <@user>", "Unmute a user"),
                        ("unban <@user>", "Unban a user"),
                        ("nick <@user> [nickname]", "Change nickname"),
                        ("nickname <@user> [nickname]", "Change nickname"),
                        ("slowmode <#channel> <time>", "Set slowmode"),
                        ("unslowmode <#channel>", "Remove slowmode"),
                        ("timeout <@user> <time> [reason]", "Timeout a user"),
                        ("untimeout <@user>", "Remove timeout")
                    ],
                    "Channel Management": [
                        ("lock <#channel>", "Lock a channel"),
                        ("unlock <#channel>", "Unlock a channel"),
                        ("lockall", "Lock all channels"),
                        ("unlockall", "Unlock all channels"),
                        ("hide <#channel>", "Hide a channel"),
                        ("unhide <#channel>", "Unhide a channel"),
                        ("hideall", "Hide all channels"),
                        ("unhideall", "Unhide all channels"),
                        ("nuke <#channel>", "Nuke a channel"),
                        ("clone <#channel>", "Clone a channel")
                    ],
                    "Role Management": [
                        ("autorole setup", "Setup autorole system"),
                        ("autorole config", "Show autorole configuration"),
                        ("autorole reset", "Reset autorole system"),
                        ("role add <@user> <@role>", "Add role to user"),
                        ("role remove <@user> <@role>", "Remove role from user"),
                        ("role all <@role>", "Give role to all users"),
                        ("role bots <@role>", "Give role to all bots"),
                        ("role humans <@role>", "Give role to all humans"),
                        ("role create <name>", "Create new role"),
                        ("role delete <@role>", "Delete role"),
                        ("role rename <@role> <new_name>", "Rename role"),
                        ("sticky add <channel>", "set a sticky message"),
                        ("sticky remove <channel>", "remove a sticky message"),
                        ("sticky list", "list all sticky messages"),
                        ("sticky reset", "reset sticky messages"),
                    ]
                }
            },
            "security": {
                "emoji": "<:sysecurity:1445409068108877885>", 
                "name": "Security",
                "description": "Server protection & anti-nuke",
                "commands": {
                    "Basic Commands": [
                        ("antinuke", "Show all antinuke commands"),
                        ("antinuke enable", "Enable protection"),
                        ("antinuke disable", "Disable protection"),
                        ("whitelist", "Manage whitelist"),
                        ("whitelist <@user>", "Add to whitelist"),
                        ("unwhitelist <@user>", "Remove from whitelist"),
                        ("whitelisted", "View whitelist"),
                        ("whitelist reset", "Reset whitelist"),
                        ("extraowner", "Manage extra owners"),
                        ("extraowner set <@user>", "Add extra owner"),
                        ("extraowner view", "View extra owners"),
                        ("extraowner reset", "Reset extra owners")
                    ],
                    "Emergency Situation": [
                        ("emergency", "Show emergency commands"),
                        ("emergency enable", "Enable emergency mode"),
                        ("emergency disable", "Disable emergency mode"),
                        ("emergency role", "Manage emergency roles"),
                        ("emergency role add <@role>", "Add role"),
                        ("emergency role remove <@role>", "Remove role"),
                        ("emergency role list", "List roles"),
                        ("emergency authorise", "Manage emergency auth"),
                        ("emergency authorise add <@user>", "Add auth"),
                        ("emergency authorise remove <@user>", "Remove auth"),
                        ("emergency authorise list", "List auths"),
                        ("emergency-situation", "Quick emergency command")
                    ]
                }
            },
            "verification": {
                "emoji": "<:syverify:1454404002094649375>",
                "name": "Verification",
                "description": "Member verification system",
                "commands": {
                    "Setup & Configuration": [
                        ("verification setup <#channel> <@role>", "Setup verification system"),
                        ("verification edit <#channel> <@role>", "Edit verification settings"),
                        ("verification config", "Show verification configuration"),
                        ("verification reset", "Reset verification system")
                    ]
                }
            },
            "nightmode": {
                "emoji": "<:synightmode:1454403977990111283>",
                "name": "Nightmode",
                "description": "Night mode protection system",
                "commands": {
                    "Nightmode Management": [
                        ("nightmode", "Show all nightmode commands"),
                        ("nightmode enable", "Enable night mode"),
                        ("nightmode disable", "Disable night mode"),
                        ("nightmode config", "Show nightmode config"),
                        ("nightmode reset", "Reset nightmode system")
                    ]
                }
            },
            "automod": {
                "emoji": "<:syautomod:1445409419511730239>", 
                "name": "Automod",
                "description": "Automated moderation",
                "commands": {
                    "Core Commands": [
                        ("automod enable", "Enable automod"),
                        ("automod disable", "Disable automod"),
                        ("automod punishment <type>", "Set punishment"),
                        ("automod config", "Configure automod"),
                        ("automod logging <#channel>", "Setup logging"),
                        ("automod ignore", "Manage ignores"),
                        ("automod ignore channel <#channel>", "Ignore channel"),
                        ("automod ignore role <@role>", "Ignore role"),
                        ("automod ignore show", "Show ignored items"),
                        ("automod ignore reset", "Reset ignores"),
                        ("automod unignore channel <#channel>", "Remove ignore"),
                        ("automod unignore role <@role>", "Remove ignore")
                    ],
                    "Ban Words": [
                        ("Banword", "Shows all banword commands"),
                        ("Banword add <word>", "Add word"),
                        ("Banword remove <word>", "Remove word"),
                        ("Banword reset", "Reset list"),
                        ("Banword config", "Configure banword Punishment"),
                        ("Banword bypass add <@user/@role>", "Add bypass"),
                        ("Banword bypass remove <@user/@role>", "Remove bypass"),
                        ("Banword bypass reset", "Reset all bypassers"),
                        ("Banword bypass list", "Show bypass list")
                    ]
                }
            },
            "extra": {
                "emoji": "<:syextra:1445410337787740160>", 
                "name": "Extra",
                "description": "Information & utilities",
                "commands": {
                    "Information": [
                        ("botinfo", "Bot information"),
                        ("invite", "Bot invite link"),
                        ("serverinfo", "Server info"),
                        ("userinfo <@user>", "User info"),
                        ("roleinfo <@role>", "Role info"),
                        ("boostcount", "Server boost count"),
                        ("joined-at <@user>", "User join date"),
                        ("ping", "Bot latency"),
                        ("github", "GitHub repository"),
                        ("vcinfo <voice_channel>", "Voice channel info"),
                        ("channelinfo <#channel>", "Channel info"),
                        ("badges <@user>", "User badges"),
                        ("banner user <@user>", "User banner"),
                        ("banner server", "Server banner")
                    ],
                    "Utilities": [
                        ("emote steal/add <emoji/sticker url> [name]", "Steal an emoji or sticker"),
                        ("emote rename <name> <new_name>", "rename an emoji"),
                        ("emote delete <emoji>", "delete an emoji"),
                    ]
                }
            },
            "fun": {
                "emoji": "<:syfun:1445410830354088141>", 
                "name": "Fun",
                "description": "Entertainment commands",
                "commands": {
                    "Fun Commands": [
                        ("nitro", "Generate a fake nitro"),
                        ("meme", "Get a random dog meme"),
                        ("joke", "Get a random joke"),
                        ("ship <@user1> <@user2>", "Calculate love compatibility between two users"),
                        ("love <@user1> <@user2>", "Alias for ship command")
                    ]
                }
            },
            "giveaways": {
                "emoji": "<:sygifts:1445411264087199794>", 
                "name": "Giveaways",
                "description": "Giveaway management system",
                "commands": {
                    "Giveaway Management": [
                        ("giveaway start <duration> <prize>", "Start a giveaway"),
                        ("giveaway end <message_id>", "End a giveaway"),
                        ("giveaway reroll <message_id>", "Reroll a giveaway"),
                        ("giveaway list", "List active giveaways"),
                        ("giveaway delete <message_id>", "Delete a giveaway"),
                        ("drop start <duration> <prize>", "Start a drop"),
                        ("drop end <message_id>", "End a drop"),
                        ("drop reroll <message_id>", "Reroll a drop")
                    ]
                }
            },
            "welcome": {
                "emoji": "<:sygreet:1445411663275888772>", 
                "name": "Welcomer",
                "description": "Welcome message system",
                "commands": {
                    "Welcome Setup": [
                        ("welcome setup <#channel>", "Setup welcome channel"),
                        ("welcome edit <message>", "Edit welcome message"),
                        ("welcome test", "Test welcome message"),
                        ("welcome config", "Show welcome config"),
                        ("welcome reset", "Reset welcome system"),
                        ("welcome channel <#channel>", "Set welcome channel"),
                        ("welcome role <@role>", "Set welcome role"),
                        ("welcome autodelete <seconds>", "Auto-delete welcome messages")
                    ]
                }
            },
            "ticket": {
                "emoji": "<:syticket:1445412067300479027>", 
                "name": "Ticket",
                "description": "Ticket support system",
                "commands": {
                    "Ticket Management": [
                        ("ticket panel create <name> <#channel> <category>", "create an ticket panel"),
                        ("ticket panel edit <name> <#channel> <category>", "edit existing ticket panel"),
                        ("ticket panel delete <name>", "delete an existing ticket panel"),
                        ("ticket panel list", "list's all ticket panels"),
                        ("ticket staff <@role>", "Set ticket staff role"),
                        ("ticket add <@user>", "Add user to ticket"),
                        ("ticket remove <@user>", "Remove user from ticket"),
                        ("ticket rename <name>", "Rename ticket"),
                        ("ticket close", "Close ticket"),
                        ("ticket transcript", "Get ticket transcript"),
                        ("ticket logs <#channel>", "Set ticket logs"),
                        ("ticket panel reset", "Reset all ticket panels")
                    ],
                    "Ticket Blacklist": [
                        ("ticket blacklist add <@user>", "Blacklist user"),
                        ("ticket blacklist remove <@user>", "Unblacklist user"),
                        ("ticket blacklist show", "Show blacklisted users"),
                        ("ticket blacklist reset", "Reset blacklist")
                    ]
                }
            },
            "embeds": {
                "emoji": "<:embeds:1454403990010724506>",
                "name": "Embeds",
                "description": "Custom embed creation and management",
                "commands": {
                    "Embed Management": [
                        ("embed create <name>", "Create a new embed"),
                        ("embed delete <name>", "Delete an embed"),
                        ("embed edit <name>", "Edit an existing embed"),
                        ("embed send <name> <#channel>", "Send embed to a channel"),
                        ("embed list", "List all embeds"),
                        ("embed reset", "Reset all embeds")
                    ]
                }
            },
            "logging": {
                "emoji": "<:sylogging:1445412355314815198>", 
                "name": "Logging",
                "description": "Server logging system",
                "commands": {
                    "Logging Setup": [
                        ("logging setup <#channel>", "Setup logging channel"),
                        ("logging config", "Show logging config"),
                        ("logging reset", "Reset logging system"),
                        ("logging toggle <event>", "Toggle specific event logging"),
                        ("logging ignore channel <#channel>", "Ignore channel"),
                        ("logging ignore role <@role>", "Ignore role"),
                        ("logging unignore channel <#channel>", "Unignore channel"),
                        ("logging unignore role <@role>", "Unignore role")
                    ]
                }
            },
            "management": {
                "emoji": "<:symanagement:1445412747259936860>", 
                "name": "Management",
                "description": "Server management tools",
                "commands": {
                    "Role Management": [
                        ("autorole setup", "Setup autorole"),
                        ("autorole config", "Show autorole config"),
                        ("autorole reset", "Reset autorole"),
                        ("customrole setup", "Setup custom role"),
                        ("customrole config", "Show custom role config"),
                        ("customrole reset", "Reset custom role"),
                        ("reactionrole add <message_id> <emoji> <@role>", "Add reaction role"),
                        ("reactionrole remove <message_id>", "Remove reaction role"),
                        ("reactionrole reset <message_id>", "Reset reaction roles"),
                        ("reactionrole edit <message_id> <emoji> <@role>", "Edit reaction role")
                    ],
                    "Channel Management": [
                        ("tempvc setup", "Setup temporary VC"),
                        ("tempvc config", "Show temp VC config"),
                        ("tempvc reset", "Reset temp VC system"),
                        ("tempvc logs <#channel>", "Set temp VC logs")
                    ]
                }
            },
            "tempvc": {
                "emoji": "<:sytempc:1445413019336183808>", 
                "name": "TempVC",
                "description": "Temporary voice channel system",
                "commands": {
                    "TempVC Management": [
                        ("tempvc setup", "Setup temp VC system"),
                        ("tempvc logs <#channel>", "Set temp VC logs"),
                        ("tempvc reset", "Reset temp VC system"),
                        ("tempvc config", "Show temp VC config")
                    ]
                }
            },
            "automation": {
                "emoji": "<:ar:1456972164644343868>", 
                "name": "Automation",
                "description": "Automated response systems",
                "commands": {
                    "Auto Responders": [
                        ("autoresponder create <trigger> <response>", "Create response"),
                        ("autoresponder list", "List responses"),
                        ("autoresponder delete <trigger>", "Delete response"),
                        ("autoresponder reset", "Reset all responses")
                    ],
                    "Auto Reactors": [
                        ("autoreact create <trigger> <emoji>", "Create reaction"),
                        ("autoreact list", "List reactions"),
                        ("autoreact delete <trigger>", "Delete reaction"),
                        ("autoreact reset", "Reset all reactions")
                    ]
                }
            },
            "vc": {
                "emoji": "<:syvoicechat:1445413220394340402>", 
                "name": "VC Management",
                "description": "Voice channel management commands",
                "commands": {
                    "Voice Controls": [
                        ("vcmute", "Mute user in voice channel"),
                        ("vcunmute", "Unmute user in voice channel"),
                        ("vckick", "Kick user from voice channel"),
                        ("vcdeafen", "Deafen user in voice channel"),
                        ("vcundeafen", "Undeafen user in voice channel"),
                        ("vclist", "List users in voice channel")
                    ],
                    "Voice Role Management": [
                        ("vcrole add", "Add VC role"),
                        ("vcrole remove", "Remove VC role"),
                        ("vcrole status", "VC role status"),
                        ("vcroletest", "Test VC role"),
                        ("vcroleconfig", "VC role configuration"),
                        ("vcrole reset", "Reset VC roles")
                    ]
                }
            },
            "tracker": {
                "emoji": "<:tracker:1456972153189695735>",
                "name": "Tracker",
                "description": "Statistics and tracking system",
                "commands": {
                    "Stats & Leaderboards": [
                        ("leaderboard", "Server leaderboard"),
                        ("userstats <@user>", "User statistics"),
                        ("serverstats", "Server statistics"),
                        ("leveling setup", "setup Leveling system"),
                        ("leveling config", "configure Leveling system"),
                        ("leveling reset", "reset Leveling system"),
                        ("level", "check the xp of a user")
                    ]
                }
            },
        }

    async def send_bot_help(self, mapping):
        ctx = self.context
        try:
            check_ignore = await ignore_check().predicate(ctx)
            check_blacklist = await blacklist_check().predicate(ctx)
            if not check_blacklist:
                return
            if not check_ignore:
                return
        except:
            pass

        try:
            try:
                data = await getConfig(ctx.guild.id if ctx.guild else 0, ctx.bot)
                prefix = data.get("prefix", "{prefix}")
            except:
                prefix = "{prefix}"
            
            module_config = self.get_module_config()
            
            embed = discord.Embed(color=0x2F3136, timestamp=discord.utils.utcnow())
            
            bot_name = ctx.bot.user.display_name if ctx.bot.user else "Scyro"
            bot_avatar = ctx.bot.user.avatar.url if ctx.bot.user and ctx.bot.user.avatar else None
            
            embed.set_author(name=f"{bot_name}", icon_url=bot_avatar)
            
            embed.title = "  __Scyro Your Discord Agent__ always ready to help."
            
            embed.description = ""
            embed.description += "## <:ques:1445406983543848972> **Usage**\n\n"
            embed.description += f"To Use **Scyro™,** type `{prefix}help`.\nAnd for a Specific command use `{prefix}sh <command>`.\n\n"
            embed.description += "## <:hash:1445406962727522373> **Categories**\n\n"
            embed.description += "Commands are grouped in different **categories,** click on the dropdown below to interact.Select the category you want to explore and view all related commands.\n\n"
            embed.description += "## <:moneybag:1445406945405178019> **Premium**\n\n"
            embed.description += "**Premium** gives you access to more epic features of **Scyro™** and supports the developement of bot. **[Buy Premium](https://scyro.xyz/premium)**.\n\n"
            embed.description += "## <:linkz:1445407559199756439> **Links**\n"
            embed.description += "**[Website](https://scyro.xyz/)︙[Dashboard](https://scyro.xyz/dashboard)︙[Support](https://dsc.gg/scyrogg)︙[Invite](https://discord.com/oauth2/authorize?client_id=1387046835322880050&scope=bot%20applications.commands&permissions=30030655231&redirect_uri=https%3A%2F%2Fdsc.gg%2Fscyrogg)**\n\n"            
            total_commands = sum(sum(len(cmds) for cmds in module_data.get('commands', {}).values()) for module_data in module_config.values())
            current_time = discord.utils.utcnow()
            
            embed.set_footer(
                text=f"Requested by {ctx.author.display_name} • {current_time.strftime('%H:%M')}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else None
            )
            
            # Define the two dropdown categories
            # Define the two dropdown categories
            core_utilities = [
                "security",
                "automod",
                "management",
                "verification",
                "nightmode",
                "moderation",
                "logging",
                "music"
            ]
            
            essential_utilities = [
                "general",
                "tracker",
                "ticket",
                "welcome",
                "tempvc",
                "embeds",
                "vc",
                "fun",
                "automation",
                "giveaways"
            ]
            
            view = StructuredHelpView(
                module_config=module_config,
                ctx=ctx, 
                homeembed=embed,
                core_utilities=core_utilities,
                essential_utilities=essential_utilities,
                prefix=prefix
            )
            
            message = await ctx.reply(embed=embed, view=view)
            view.message = message  # This should work now with proper typing
            
        except Exception as e:
            print(f"❌ Error in send_bot_help: {e}")
            simple_embed = discord.Embed(
                title="❌ This feature is currently unavailable.",
                description="You can use `/help or .help` to get a list of available commands.\nAnd for a specific command use `.help <command>`",
                color=discord.Color.red()
            )
            await ctx.reply(embed=simple_embed)

    def find_related_commands(self, command_name):
        """Find related commands based on command name"""
        command_name = command_name.lower()
        related_commands = []
        
        # First check for exact match
        if command_name in self.command_database:
            related_commands.append(self.command_database[command_name])
        
        # Then check for partial matches
        for cmd_key, cmd_data in self.command_database.items():
            if (command_name in cmd_key.lower() or 
                command_name in cmd_data.get('name', '').lower() or
                any(command_name in alias.lower() for alias in cmd_data.get('aliases', []))):
                if cmd_data not in related_commands:
                    related_commands.append(cmd_data)
        
        # If no matches found, try to find similar command names
        if not related_commands:
            all_commands = list(self.command_database.keys())
            similar_commands = get_close_matches(command_name, all_commands, n=3, cutoff=0.3)
            for cmd in similar_commands:
                related_commands.append(self.command_database[cmd])
        
        return related_commands

    async def send_command_help(self, command):
        ctx = self.context
        help_text = command.help if command.help else "No description provided."
        
        embed = discord.Embed(
            title=f"{command.qualified_name.title()} Command",
            description=help_text,
            color=color
        )
        
        current_time = discord.utils.utcnow()
        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • {current_time.strftime('%H:%M')}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )
        
        await ctx.reply(embed=embed, mention_author=False)

class Help(Cog, name="help"):
    def __init__(self, client: Scyro):
        self.client = client
        self._original_help_command = client.help_command
        attributes = {
            'name': "help",
            'aliases': ['h'],
            'cooldown': commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.user),
            'help': 'Shows help about bot, a command or a category'
        }
        
        help_cmd = CustomHelpCommand(command_attrs=attributes)
        help_cmd.cog = self
        client.help_command = help_cmd

    async def cog_unload(self):
        self.client.help_command = self._original_help_command

    async def _syhelp_logic(self, ctx_or_interaction, command_name: str = None, is_slash: bool = False):
        """Shared logic for both prefix and slash syhelp commands"""
        if is_slash:
            class FakeContext:
                def __init__(self, interaction):
                    self.author = interaction.user
                    self.guild = interaction.guild
                    self.channel = interaction.channel
                    self.bot = interaction.client
                    try:
                        self.prefix = "{prefix}"
                    except:
                        self.prefix = "{prefix}"
                
                async def reply(self, *args, **kwargs):
                    if ctx_or_interaction.response.is_done():
                        return await ctx_or_interaction.followup.send(*args, **kwargs)
                    else:
                        return await ctx_or_interaction.response.send_message(*args, **kwargs)
            
            ctx = FakeContext(ctx_or_interaction)
            prefix = "{prefix}"
        else:
            ctx = ctx_or_interaction
            try:
                check_ignore = await ignore_check().predicate(ctx)
                check_blacklist = await blacklist_check().predicate(ctx)
                if not check_blacklist:
                    return
                if not check_ignore:
                    await ctx.reply("This channel is ignored.", mention_author=False)
                    return
            except:
                pass
            prefix = ctx.prefix

        if not command_name:
            embed = discord.Embed(
                title="🔍 Advanced Help System",
                description=f"Use `{prefix}syhelp <command>` to get detailed information about any command.\n\n"
                            f"**Available Commands:**\n"
                            f"• `{prefix}syhelp automod` - Automod system help\n"
                            f"• `{prefix}syhelp antinuke` - Antinuke system help\n"
                            f"• `{prefix}syhelp ban` - Ban command help\n"
                            f"• `{prefix}syhelp list` - List commands help\n"
                            f"• `{prefix}syhelp role` - Role management help\n"
                            f"• `{prefix}syhelp ticket` - Ticket system help\n"
                            f"• `{prefix}syhelp welcome` - Welcome system help\n"
                            f"• And many more...",
                color=0x2F3136
            )
            current_time = discord.utils.utcnow()
            embed.set_footer(
                text=f"Requested by {ctx.author.display_name} • {current_time.strftime('%H:%M')}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else None
            )
            await ctx.reply(embed=embed)
            return

        related_commands = self.client.help_command.find_related_commands(command_name)
        
        if not related_commands:
            embed = discord.Embed(
                title="❌ Command Not Found",
                description=f"No command found matching `{command_name}`.\n\n"
                            f"Try using `{prefix}syhelp` to see available commands.",
                color=0xFF6B6B
            )
            current_time = discord.utils.utcnow()
            embed.set_footer(
                text=f"Requested by {ctx.author.display_name} • {current_time.strftime('%H:%M')}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else None
            )
            await ctx.reply(embed=embed)
            return

        view = AdvancedHelpView(
            command_name=command_name,
            related_commands=related_commands,
            ctx=ctx,
            prefix=prefix
        )
        
        embed = view.create_command_embed()
        message = await ctx.reply(embed=embed, view=view)
        view.message = message

    async def _help_slash_logic(self, interaction: Interaction, command: str = None):
        """Shared logic for slash help command"""
        try:
            class FakeContext:
                def __init__(self, interaction, bot):
                    self.author = interaction.user
                    self.guild = interaction.guild
                    self.channel = interaction.channel
                    self.bot = bot
                    self.command = None
                    self.prefix = "{prefix}"
                    
                async def reply(self, *args, **kwargs):
                    if interaction.response.is_done():
                        return await interaction.followup.send(*args, **kwargs)
                    else:
                        return await interaction.response.send_message(*args, **kwargs)
            
            ctx = FakeContext(interaction, self.client)
            
            old_context = self.client.help_command.context
            self.client.help_command.context = ctx
            
            if not command:
                await self.client.help_command.send_bot_help({})
            else:
                cmd = self.client.get_command(command)
                if cmd:
                    await self.client.help_command.send_command_help(cmd)
                else:
                    error_embed = discord.Embed(
                        title="❌ Command Not Found",
                        description=f"No command found matching `{command}`.",
                        color=0xFF6B6B
                    )
                    current_time = discord.utils.utcnow()
                    error_embed.set_footer(
                        text=f"Requested by {ctx.author.display_name} • {current_time.strftime('%H:%M')}",
                        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
                    )
                    await ctx.reply(embed=error_embed)
            
            self.client.help_command.context = old_context
                    
        except Exception as e:
            print(f"❌ Error in help slash command: {e}")
            try:
                error_embed = discord.Embed(
                    title="❌ Help System Error",
                    description="There was an error loading the help system. Please try again.",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=error_embed)
                else:
                    await interaction.response.send_message(embed=error_embed)
            except:
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Help system error. Please try again.")
                else:
                    await interaction.response.send_message("❌ Help system error. Please try again.")

    @commands.command(name="syhelp", aliases=["sh", "syshelp"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def syhelp_prefix(self, ctx, *, command_name: str = None):
        """Advanced help system - Shows detailed information about commands (Prefix version)"""
        await self._syhelp_logic(ctx, command_name, is_slash=False)



    @app_commands.command(name="help", description="Shows Scyro's help menu")
    @app_commands.describe(command="The specific command to get help for (optional)")
    async def help_slash(self, interaction: Interaction, command: str = None):
        """Main help command - Shows help menu (Slash version)"""
        await self._help_slash_logic(interaction, command)

async def setup(client: Scyro):
    await client.add_cog(Help(client))
    # Removed automatic sync to prevent rate limiting
    # Command syncing is now handled globally in main.py