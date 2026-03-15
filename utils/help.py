# utils/help.py
import discord
from discord.ext import commands


class Dropdown(discord.ui.Select):
    def __init__(self, ctx, options):
        super().__init__(
            placeholder="Select a module to view commands",
            min_values=1,
            max_values=1,
            options=options
        )
        self.invoker = ctx.author

    async def callback(self, interaction: discord.Interaction):
        if self.invoker == interaction.user:
            index = self.view.find_index_from_select(self.values[0])
            if index is None:
                index = 0
            await self.view.set_page(index, interaction)
        else:
            await interaction.response.send_message(
                "This help menu doesn't belong to you. Run the command yourself to interact with it.", 
                ephemeral=True
            )


class HelpView(discord.ui.View):
    def __init__(self, ctx=None, home_embed=None, homeembed=None, prefix="!", mapping=None, ui=1, **kwargs):
        super().__init__(timeout=300)
        self.ctx = ctx
        # Handle both parameter names for compatibility
        self.home = home_embed or homeembed
        self.index = 0
        self.prefix = prefix
        self.ui = ui
        
        # Handle the mapping parameter that Discord.py passes
        self.mapping = mapping or kwargs.get('mapping', None)
        
        self.options, self.embeds, self.total_pages = self.generate_embeds()
        if self.options:  # Only add dropdown if we have options
            self.add_item(Dropdown(ctx=self.ctx, options=self.options))

    def find_index_from_select(self, value):
        for i, option in enumerate(self.options):
            if option.value == value:
                return i
        return 0

    def get_custom_emoji(self, emoji_string):
        """Helper method to safely get custom emoji"""
        try:
            if emoji_string.startswith('<') and emoji_string.endswith('>'):
                # Extract emoji ID from string like <:name:id>
                emoji_id = emoji_string.split(':')[-1].rstrip('>')
                if emoji_id.isdigit():
                    # Try to get emoji from bot
                    if self.ctx and hasattr(self.ctx, 'bot'):
                        emoji = self.ctx.bot.get_emoji(int(emoji_id))
                        if emoji:
                            return emoji
                # Return the string as fallback
                return emoji_string
            return emoji_string
        except:
            # Fallback to default emoji if custom emoji fails
            return "📁"

    def get_allowed_modules(self):
        """Module configurations with commands and descriptions"""
        return {
            "general": {
                "emoji": "<:general:1412365030435061831>", 
                "name": "General",
                "description": "Core bot functionality and utilities",
                "commands": {
                    "Status & Profile": [
                        ("status", "Check bot status"),
                        ("afk <reason>", "Set AFK status"),
                        ("avatar <@user>", "Get user avatar"),
                        ("banner <@user>", "Get user banner"),
                        ("servericon", "Get server icon"),
                        ("membercount/mc", "Get server member count"),
                        ("hash <text>", "Generate hash"),
                        ("snipe <#channel>", "Snipe deleted messages")
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
                        ("list boosters", "List server boosters"),
                        ("list inrole <@role>", "List users in role"),
                        ("list emojis", "List server emojis"),
                        ("list bots", "List server bots"),
                        ("list admins", "List server admins"),
                        ("list invoice", "List invoices"),
                        ("list mods", "List server moderators"),
                        ("list early", "List early supporters"),
                        ("list activedeveloper", "List active developers"),
                        ("list createpos", "List creation positions"),
                        ("list roles", "List server roles")
                    ]
                }
            },
            "moderation": {
                "emoji": "<:moderation:1412365003570413568>", 
                "name": "Moderation",
                "description": "Server moderation and management tools",
                "commands": {
                    "User Management": [
                        ("audit <@user>", "Audit user actions"),
                        ("warn <@user> [reason]", "Warn a user"),
                        ("warn add <@user> [reason]", "Warn a user"),
                        ("warn list <@user>", "Check user warnings"),
                        ("warn clear <@user>", "Clear user warnings"),
                        ("clearwarns <@user>", "Clear user warnings"),
                        ("ban <@user> [reason]", "Ban a user"),
                        ("unbanall", "Unban all banned users"),
                        ("kick <@user> [reason]", "Kick a user"),
                        ("mute <@user> [time] [reason]", "Mute a user"),
                        ("unmute <@user>", "Unmute a user"),
                        ("unban <@user>", "Unban a user"),
                        ("nick <@user> [nickname]", "Change user nickname"),
                        ("nickname <@user> [nick]", "Change user nickname"),
                        ("slowmode <#channel> <time>", "Set slowmode in channel"),
                        ("unslowmode <#channel>", "Remove slowmode from channel"),
                        ("timeout <@user> <time> [reason]", "Timeout a user"),
                        ("untimeout <@user>", "Remove timeout from user")
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
                        ("autorole config", "See autorole configration"),
                        ("autorole reset", "Reset autrole system"),
                        ("role add<@user> <@role>", "Add user roles"),
                        ("role remove <@user> <@role>", "Remove user role"),
                        ("role all <@role>", "Give role to all users"),
                        ("role bots <@role>", "Give role to all bots"),
                        ("role create <name>", "Create new role"),
                        ("role delete <@role>", "Delete a role"),
                        ("role humans <@role>", "Give role to all humans"),
                        ("role rename <@role> <new_name>", "Rename a role")
                    ]
                }
            },
            "security": {
                "emoji": "<:security22:1412364975325839512>", 
                "name": "Security",
                "description": "Protect your server from nuking attempts",
                "commands": {
                    "Basic Commands": [
                        ("antinuke", "Shows all antinuke commands"),
                        ("antinuke enable", "Enable antinuke protection"),
                        ("antinuke disable", "Disable antinuke protection"),
                        ("whitelist", "Manage whitelist settings"),
                        ("whitelist <@user>", "Add user to whitelist"),
                        ("unwhitelist <@user>", "Remove user from whitelist"),
                        ("whitelisted", "View whitelisted users"),
                        ("whitelist reset", "Reset whitelist"),
                        ("extraowner", "Manage extra owners"),
                        ("extraowner set <@user>", "Set extra owner"),
                        ("extraowner view", "View extra owners"),
                        ("extraowner reset", "Reset extra owners"),
                        ("nightmode", "Manage night mode"),
                        ("nightmode enable", "Enable night mode"),
                        ("nightmode disable", "Disable night mode")
                    ],
                    "Emergency Situation": [
                        ("emergency", "Emergency mode commands"),
                        ("emergency enable", "Enable emergency mode"),
                        ("emergency disable", "Disable emergency mode"),
                        ("emergency role", "Manage emergency roles"),
                        ("emergency role add <@role>", "Add emergency role"),
                        ("emergency role remove <@role>", "Remove emergency role"),
                        ("emergency role list", "List emergency roles"),
                        ("emergency authorise", "Manage emergency authorization"),
                        ("emergency authorise add <@user>", "Add emergency auth"),
                        ("emergency authorise remove <@user>", "Remove emergency auth"),
                        ("emergency authorise list", "List emergency auth"),
                        ("emergency-situation", "Quick emergency command")
                    ]
                }
            },
            "automod": {
                "emoji": "<:automod:1412364991142563860>", 
                "name": "Automod",
                "description": "Automated moderation for your server",
                "commands": {
                    "Core Commands": [
                        ("automod", "Shows all automod commands"),
                        ("automod enable", "Enable automod on server"),
                        ("automod disable", "Disable automod on server"),
                        ("automod punishment <type>", "Set punishment for automod events"),
                        ("automod config", "Configure automod settings"),
                        ("automod logging <#channel>", "Setup automod logging"),
                        ("automod ignore", "Manage ignored channels/roles"),
                        ("automod ignore channel <#channel>", "Ignore specific channel"),
                        ("automod ignore role <@role>", "Ignore specific role"),
                        ("automod ignore show", "Show ignored items"),
                        ("automod ignore reset", "Reset ignored items"),
                        ("automod unignore", "Remove from ignore list"),
                        ("automod unignore channel <#channel>", "Unignore channel"),
                        ("automod unignore role <@role>", "Unignore role")
                    ],
                    "Blacklist Words": [
                        ("blacklistword", "Manage blacklisted words"),
                        ("blacklistword add <word>", "Add word to blacklist"),
                        ("blacklistword remove <word>", "Remove word from blacklist"),
                        ("blacklistword reset", "Reset blacklist"),
                        ("blacklistword config", "Configure blacklist settings"),
                        ("blacklistword bypass add <@user/@role>", "Add bypass permission"),
                        ("blacklistword bypass remove <@user/@role>", "Remove bypass permission"),
                        ("blacklistword bypass show", "Show bypass list")
                    ]
                }
            },
            "extra": {
                "emoji": "<:extra:1412365912723427410>", 
                "name": "Extra",
                "description": "Additional utility commands",
                "commands": {
                    "Information": [
                        ("botinfo", "Get information about the bot"),
                        ("stats", "View bot statistics"),
                        ("invite", "Get bot invite link"),
                        ("serverinfo", "Get server information"),
                        ("userinfo <@user>", "Get user information"),
                        ("roleinfo <@role>", "Get role information"),
                        ("boostcount", "View server boost count"),
                        ("joined-at <@user>", "Check when user joined"),
                        ("ping", "Check bot latency"),
                        ("github", "Get GitHub repository link"),
                        ("vcinfo <voice_channel>", "Get voice channel info"),
                        ("channelinfo <#channel>", "Get channel information"),
                        ("badges <@user>", "View user badges"),
                        ("banner user <@user>", "Get user banner"),
                        ("banner server", "Get server banner")
                    ],
                    "Utilities": [
                        ("embed create <name> ", "Create custom embed"),
                        ("embed delete <name>", "Delete a embed"),
                        ("embed edit <name> ", "Edit a embed"),
                        ("embed send <name> <channel> ", "Send Embed to a channel"),
                        ("embed list", "List all Embeds"),
                        ("embed reset", "Reset all embeds"),
                        ("perms <@user>", "Check user permissions")
                       
                    ],
                    "Media Commands": [
                        ("media", "Media command settings"),
                        ("media setup <#channel>", "Setup media commands"),
                        ("media remove", "Remove media setup"),
                        ("media config", "Configure media settings"),
                        ("media bypass", "Manage media bypass"),
                        ("media bypass add <@user/@role>", "Add media bypass"),
                        ("media bypass remove <@user/@role>", "Remove media bypass"),
                        ("media bypass show", "Show media bypass list")
                    ]
                }
            },
            "fun": {
                "emoji": "<:fun:1412365924178067499>", 
                "name": "Fun",
                "description": "Entertainment and interactive commands",
                "commands": {
                    "Interactive": [
                        ("mydog", "Get a random dog image"),
                        ("translate <text>", "Translate text"),
                        ("howgay <@user>", "Check gay percentage"),
                        ("lesbian <@user>", "Check lesbian percentage"),
                        ("cute <@user>", "Check cuteness level"),
                        ("iq <@user>", "Check intelligence level"),
                        ("chutiya <@user>", "Fun insult command"),
                        ("horny <@user>", "Check horny level"),
                        ("tharki <@user>", "Fun personality check"),
                        ("ship <@user1> <@user2>", "Calculate love compatibility between two users"),
                        ("love <@user1> <@user2>", "Alias for ship command")
                    ],
                    "Actions": [
                        ("gif", "Get random GIF"),
                        ("ngif", "Get NSFW GIF"),
                        ("hug <@user>", "Hug someone"),
                        ("kiss <@user>", "Kiss someone"),
                        ("pat <@user>", "Pat someone"),
                        ("cuddle <@user>", "Cuddle with someone"),
                        ("slap <@user>", "Slap someone"),
                        ("tickle <@user>", "Tickle someone"),
                        ("spank <@user>", "Spank someone")
                    ],
                    "Games & Tools": [
                        ("8ball <question>", "Ask the magic 8ball"),
                        ("truth", "Get a truth question"),
                        ("dare", "Get a dare"),
                        ("iplookup <ip_address>", "Look up IP information"),
                        ("weather <location>", "Get weather information")
                    ]
                }
            },
            "welcomer": {
                "emoji": "<:welcome:1412366884254257233>", 
                "name": "Welcomer",
                "description": "Welcome and greeting system",
                "commands": {
                    "Greet System": [
                        ("greet", "Main greet command"),
                        ("greet setup <#channel>", "Setup welcome messages"),
                        ("greet reset", "Reset greet configuration"),
                        ("greet channel <#channel>", "Set greet channel"),
                        ("greet edit <message>", "Edit greet message"),
                        ("greet test", "Test greet message"),
                        ("greet config", "View greet configuration"),
                        ("greet autodeleted <time>", "Auto-delete greet messages")
                    ]
                }
            },
            "giveaways": {
                "emoji": "<:gwy:1412365936262123532>", 
                "name": "Giveaways",
                "description": "Manage server giveaways",
                "commands": {
                    "Giveaway Management": [
                        ("gstart <time> <prize>", "Start a new giveaway"),
                        ("gend <giveaway_id>", "End a giveaway early"),
                        ("greroll <giveaway_id>", "Reroll giveaway winner"),
                        ("glist", "List active giveaways")
                    ]
                }
            },
            "management": {
                "emoji": "<:manag:1412365960064798720>", 
                "name": "Management",
                "description": "Server management and utility commands",
                "commands": {
                    "Ignore System": [
                        ("ignore channel add <#channel>", "Add channel to ignore"),
                        ("ignore channel remove <#channel>", "Remove channel from ignore"),
                        ("ignore channel list", "Show ignored channels"),
                        ("ignore channel reset", "reset ignored channels"),
                        ("ignore bypass add <@user>", "Add ignore bypass"),
                        ("ignore bypass list", "Show ignore bypass"),
                        ("ignore bypass remove <@user>", "Remove ignore bypass"),
                        ("ignore bypass reset ", "Reset ignore bypass")
                    ],
                    "Customrole System": [
                        ("customerole", "Main customerole command"),
                        ("customerole create <name>", "Create new customerole"),
                        ("customerole delete <name>", "Delete customerole"),
                        ("customerole list", "List all customeroles"),
                        ("customerole staff <@role>", "customerole staff role"),
                        ("customerole girl <@role>", "customerole girl role"),
                        ("customerole friend <@role>", "customerole friend role"),
                        ("customerole vip <@role>", "customerole VIP role"),
                        ("customerole guest <@role>", "customerole guest role"),
                        ("customerole config", "Configure customerole"),
                        ("customerole reset", "Reset customerole")
                    ],
                    "Role Assignment": [
                        ("staff <@user>", "Assign staff role"),
                        ("girl <@user>", "Assign girl role"),
                        ("friend <@user>", "Assign friend role"),
                        ("vip <@user>", "Assign VIP role"),
                        ("guest <@user>", "Assign guest role")
                    ]
                }
            },
            "logging": {
                "emoji": "<:logging:1412365947263782942>", 
                "name": "Logging",
                "description": "Server logging and audit system",
                "commands": {
                    "Log Management": [
                        ("logs setup", "Setup server logging"),
                        ("logs settings", "See logging settings"),
                        ("logs stats", "See logging stats"),
                        ("logs enable <type>", "Enable specific log type"),
                        ("logs disable <type>", "Disable Specific log type"),
                        ("logs test", "Test all logs or specific log"),
                        ("logs reset", "Reset logging configuration")
                    ]
                }
            },
            "ticket": {
                "emoji": "<:ticket:1412365017038454855>", 
                "name": "Ticket",
                "description": "Support ticket system",
                "commands": {
                    "Ticket System": [
                        ("ticket setup <#channel>", "Setup ticket panel"),
                        ("ticket staff <role>", "Set ticket staff role"),
                        ("ticket category <#category>", "Set ticket category"),
                        ("ticket add <@user>", "Add user to ticket"),
                        ("ticket remove <@user>", "Remove user from ticket"),
                        ("ticket rename <name>", "Rename a ticket"),
                        ("ticket logs <#channel>", "Set tickets logs channel"),
                        ("ticket transcript <#channel>", "Get ticket's transcript"),
                        ("ticket blacklist add <@user>", "Blacklist user from creating ticket"),
                        ("ticket blacklist remove <@user>", "Unblacklist user from creating ticket"),
                        ("ticket show ", "See all ticket blacklisted users"),
                        ("ticket reset", "Reset al ticket blacklisted urers")
                  
                    ]
                }
            }
        }

    def generate_embeds(self):
        options = []
        embeds = []
        allowed_modules = self.get_allowed_modules()

        # Safe bot name handling
        bot_name = "Scyro"
        if self.ctx and hasattr(self.ctx, 'bot') and self.ctx.bot and hasattr(self.ctx.bot, 'user') and self.ctx.bot.user:
            bot_name = getattr(self.ctx.bot.user, 'display_name', 'Scyro')

        # Add home option first
        options.append(
            discord.SelectOption(
                label="Home",
                value="home",
                description=f"View {bot_name} overview and modules",
                emoji="<:home:1412369462488731658>"
            )
        )
        embeds.append(self.home)

        # Process each module
        for module_key, module_info in allowed_modules.items():
            try:
                emoji_string = module_info.get("emoji", "<:folder:1412381834695671868>")
                emoji = self.get_custom_emoji(emoji_string)
                module_name = module_info.get("name", module_key.title())
                module_desc = module_info.get("description", f"Commands for {module_name}")
                commands_dict = module_info.get("commands", {})
                
                embed = discord.Embed(
                    title=f"{emoji} {module_name} Commands",
                    description=module_desc,
                    color=0x9b59b6
                )
                
                if commands_dict:
                    total_commands = 0
                    for section_name, commands_list in commands_dict.items():
                        if commands_list:
                            formatted_commands = []
                            for cmd_info in commands_list:
                                if isinstance(cmd_info, (list, tuple)) and len(cmd_info) >= 2:
                                    cmd_name, cmd_desc = cmd_info[0], cmd_info[1]
                                    # Clean formatting - use backticks properly
                                    formatted_commands.append(f"`{cmd_name}` - {cmd_desc}")
                                    total_commands += 1
                            
                            if formatted_commands:
                                commands_text = "\n".join(formatted_commands)
                                
                                # Handle long field content by splitting if needed
                                if len(commands_text) > 1024:
                                    chunks = []
                                    current_chunk = []
                                    current_length = 0
                                    
                                    for cmd in formatted_commands:
                                        if current_length + len(cmd) + 1 > 1024:
                                            if current_chunk:
                                                chunks.append("\n".join(current_chunk))
                                                current_chunk = [cmd]
                                                current_length = len(cmd)
                                            else:
                                                # Single command too long, truncate
                                                chunks.append(cmd[:1020] + "...")
                                        else:
                                            current_chunk.append(cmd)
                                            current_length += len(cmd) + 1
                                    
                                    if current_chunk:
                                        chunks.append("\n".join(current_chunk))
                                    
                                    for i, chunk in enumerate(chunks):
                                        field_name = section_name if i == 0 else f"{section_name} (cont.)"
                                        embed.add_field(
                                            name=field_name,
                                            value=chunk,
                                            inline=False
                                        )
                                else:
                                    embed.add_field(
                                        name=section_name,
                                        value=commands_text,
                                        inline=False
                                    )
                    
                    # Safe footer handling
                    footer_text = f"Total commands: {total_commands}"
                    footer_icon = None
                    if self.ctx and hasattr(self.ctx, 'author'):
                        footer_text += f" • Requested by {self.ctx.author.display_name}"
                        if hasattr(self.ctx.author, 'display_avatar'):
                            footer_icon = self.ctx.author.display_avatar.url
                    
                    embed.set_footer(text=footer_text, icon_url=footer_icon)
                else:
                    embed.add_field(
                        name="Commands",
                        value="No commands configured",
                        inline=False
                    )
                
                cmd_count = sum(len(cmds) for cmds in commands_dict.values()) if commands_dict else 0
                
                # For dropdown options, use string representation for emoji
                options.append(
                    discord.SelectOption(
                        label=f"{module_name}",
                        value=module_key,
                        description=f"{cmd_count} commands available.",
                        emoji=emoji if isinstance(emoji, (discord.Emoji, discord.PartialEmoji, str)) else None
                    )
                )
                embeds.append(embed)
                
            except Exception as e:
                print(f"Error processing module {module_key}: {e}")
                continue

        return options, embeds, len(embeds)

    async def set_page(self, page: int, interaction: discord.Interaction):
        try:
            if 0 <= page < len(self.embeds):
                self.index = page
                await interaction.response.edit_message(embed=self.embeds[page], view=self)
            else:
                await interaction.response.defer()
        except discord.InteractionResponse.errors.InteractionResponded:
            # Interaction already responded to
            pass
        except Exception as e:
            print(f"Error setting page: {e}")
            try:
                await interaction.response.defer()
            except:
                pass

    async def on_timeout(self):
        try:
            self.clear_items()
        except:
            pass


# Create aliases for backwards compatibility with both naming conventions
View = HelpView
Help = HelpView


# Custom Help Command Class (kept for standalone usage)
# class CustomHelpCommand(commands.HelpCommand):
#     def __init__(self):
#         super().__init__(
#             command_attrs={
#                 'help': 'Shows help about the bot, a command, or a category',
#                 'cooldown': commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.user)
#             }
#         )
#
#     def get_command_signature(self, command):
#         return f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"
#
#     def get_allowed_modules(self):
#         """Module configurations with commands and descriptions - shared method"""
#         return {
#             "general": {
#                 "emoji": "<:general:1412365030435061831>", 
#                 "name": "General",
#                 "description": "Core bot functionality and utilities",
#                 "commands": {}  # Commands dict would be populated here
#             },
#             "moderation": {
#                 "emoji": "<:moderation:1412365003570413568>", 
#                 "name": "Moderation",
#                 "description": "Server moderation and management tools",
#                 "commands": {}
#             }
#             # Add other modules as needed
#         }
#
#     async def send_bot_help(self, mapping):
#         """This method is called when !help is used without arguments"""
#         prefix = self.context.clean_prefix
#         
#         bot_name = self.context.bot.user.display_name if self.context.bot.user else "Scyro"
#         
#         home_embed = discord.Embed(
#             title=f"{bot_name} Help Menu",
#             description=f"👋 **Hey, I'm {bot_name}!**\n\nI'm here to help you explore all of my commands.\n\nUse the dropdown to jump to a category.",
#             color=0x9b59b6
#         )
#         
#         home_embed.add_field(
#             name="📊 Bot Statistics",
#             value=f"**Servers:** {len(self.context.bot.guilds)}\n**Users:** {len(self.context.bot.users)}\n**Prefix:** `{prefix}`",
#             inline=True
#         )
#         
#         home_embed.add_field(
#             name="🔗 Links",
#             value="[Invite Bot](https://discord.com/invite/yourinvite) | [Support Server](https://discord.gg/support)",
#             inline=True
#         )
#         
#         if hasattr(self.context.bot, 'user') and self.context.bot.user:
#             home_embed.set_thumbnail(url=self.context.bot.user.display_avatar.url)
#         
#         home_embed.set_footer(
#             text=f"Requested by {self.context.author.display_name}",
#             icon_url=self.context.author.display_avatar.url
#         )
#
#         view = HelpView(ctx=self.context, home_embed=home_embed, prefix=prefix, mapping=mapping)
#         await self.context.send(embed=home_embed, view=view)
#
#     async def send_command_help(self, command):
#         """This method is called when !help <command> is used"""
#         # Check if this is a command that has subcommands in our modules
#         command_name = command.qualified_name.lower()
#         subcommands = self.get_subcommands_for_command(command_name)
#         
#         if subcommands:
#             # Show subcommands like the image
#             embed = discord.Embed(
#                 title=f"Subcommands of {command_name}",
#                 description=f"All available subcommands for `{command_name}`",
#                 color=0x9b59b6
#             )
#             
#             for subcmd, desc in subcommands:
#                 embed.add_field(
#                     name=f"• {subcmd}",
#                     value=desc,
#                     inline=False
#                 )
#             
#             # Add help footer
#             embed.add_field(
#                 name="📍 Need Help?",
#                 value=f"If you find any error, please report it on our support server: [Sterix Support Server](https://discord.gg/support)",
#                 inline=False
#             )
#             
#             embed.set_footer(
#                 text=f"Requested by {self.context.author.display_name}",
#                 icon_url=self.context.author.display_avatar.url
#             )
#         else:
#             # Default single command help
#             embed = discord.Embed(
#                 title=f"Command: {command.qualified_name}",
#                 description=command.help or "No description available",
#                 color=0x9b59b6
#             )
#             
#             embed.add_field(
#                 name="Usage",
#                 value=f"`{self.get_command_signature(command)}`",
#                 inline=False
#             )
#             
#             if command.aliases:
#                 embed.add_field(
#                     name="Aliases",
#                     value=", ".join(f"`{alias}`" for alias in command.aliases),
#                     inline=False
#                 )
#         
#         await self.context.send(embed=embed)
#
#     def get_subcommands_for_command(self, command_name):
#         """Get all subcommands for a given command from our module data"""
#         allowed_modules = self.get_allowed_modules()
#         subcommands = []
#         
#         for module_key, module_info in allowed_modules.items():
#             commands_dict = module_info.get("commands", {})
#             for section_name, commands_list in commands_dict.items():
#                 for cmd_info in commands_list:
#                     if isinstance(cmd_info, (list, tuple)) and len(cmd_info) >= 2:
#                         cmd_name, cmd_desc = cmd_info[0], cmd_info[1]
#                         # Check if this command starts with our target command