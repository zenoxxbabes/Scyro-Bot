import discord
from discord.ext import commands
import motor.motor_asyncio
from utils.Tools import *
from datetime import datetime, timedelta
from collections import defaultdict
import os

# ═══════════════════════════════════════════════════════════════════════════════
#                           🎨 IMPROVED EMOJI CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Status Emojis
ENABLED_EMOJI = "<:enabled:1396473501447098368>"
DISABLED_EMOJI = "<:disabled:1396473518962507866>"
SUCCESS_EMOJI = "<:yes:1396838746862784582>"
ERROR_EMOJI = "<:no:1396838761605890090>"
WARNING_EMOJI = "<a:alert:1396429026842644584>"
SECURITY_EMOJI = "<:security:1396477817000034385>"

# Feature Emojis
AUTOMOD_EMOJI = "<:security:1396477817000034385>"
SHIELD_EMOJI = "<:security:1396477817000034385>"
SETTINGS_EMOJI = "<:gear:1409149841082155078>"
LIST_EMOJI = "<:26500tasks:1459854656980390072>"
CHANNEL_EMOJI = "<:46419discordchannelfromvega:1409183750557929634>"
ROLE_EMOJI = "<:rolez:1459854739595591863>"
PUNISHMENT_EMOJI = "<:punishment:1459854728581087403>"
LOGGING_EMOJI = "<:26500tasks:1459854656980390072>"

# Rule Type Emojis - ALL REPLACED WITH DOT EMOJI
ANTI_SPAM_EMOJI = "<a:dot:1396429135588626442>"
ANTI_CAPS_EMOJI = "<a:dot:1396429135588626442>"
ANTI_LINK_EMOJI = "<a:dot:1396429135588626442>"
ANTI_INVITE_EMOJI = "<a:dot:1396429135588626442>"
ANTI_MENTION_EMOJI = "<a:dot:1396429135588626442>"
ANTI_EMOJI_EMOJI = "<a:dot:1396429135588626442>"
ANTI_NSFW_EMOJI = "<a:dot:1396429135588626442>"

# Action Emojis
MUTE_EMOJI = "<:mutetgds:1459854718443716700>"
KICK_EMOJI = "<:qwdkick:1459854645613826132>"
BAN_EMOJI = "<:banhammer:1409414586704199840>"
BLOCK_EMOJI = "<:no:1396838761605890090>"
WHITELIST_EMOJI = "<:yes:1396838746862784582>"
RESET_EMOJI = "<:reroll:1457368810184249567>"

class ShowRules(discord.ui.View):
    def __init__(self, author, selected_events):
        super().__init__(timeout=60)
        self.author = author
        self.selected_events = selected_events

    @discord.ui.button(label="View Rules Details", style=discord.ButtonStyle.secondary, emoji="📖")
    async def show_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Access Denied",
                description="Only the command author can view rule details.",
                color=0x2b2d31
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        rules = {
            "Anti NSFW link": f"{ANTI_NSFW_EMOJI} **Anti NSFW Link**\n> Blocks messages containing NSFW links/words\n> **Punishment:** {BLOCK_EMOJI} Block Message *(unchangeable)*",
            "Anti Caps": f"{ANTI_CAPS_EMOJI} **Anti Caps**\n> Triggers on messages with >70% caps\n> Messages under 45 characters bypassed\n> **Default:** {MUTE_EMOJI} Mute (1 minute)",
            "Anti Link": f"{ANTI_LINK_EMOJI} **Anti Link**\n> Blocks general web links\n> Server invites, Spotify & GIFs bypassed\n> **Default:** {MUTE_EMOJI} Mute (7 minutes)",
            "Anti Invites": f"{ANTI_INVITE_EMOJI} **Anti Invites**\n> Blocks Discord server invites\n> Current server invites bypassed\n> **Default:** {MUTE_EMOJI} Mute (12 minutes)",
            "Anti Emoji Spam": f"{ANTI_EMOJI_EMOJI} **Anti Emoji Spam**\n> Triggers on 5+ emojis in message\n> **Default:** {MUTE_EMOJI} Mute (1 minute)",
            "Anti Mass Mention": f"{ANTI_MENTION_EMOJI} **Anti Mass Mention**\n> Triggers on 4+ mentions\n> **Default:** {MUTE_EMOJI} Mute (3 minutes)",
            "Anti Spam": f"{ANTI_SPAM_EMOJI} **Anti Spam**\n> Triggers on rapid message sending\n> **Default:** {MUTE_EMOJI} Mute (12 minutes)",
            "Anti repeated text": f"{ANTI_SPAM_EMOJI} **Anti Repeated Text**\n> Triggers on 3+ identical messages\n> **Default:** {MUTE_EMOJI} Mute (5 minutes)",
        }

        enabled_rules = "\n\n".join([rules[event] for event in self.selected_events if event in rules])

        embed = discord.Embed(
            title=f"{SHIELD_EMOJI} Enabled Automod Rules",
            description=enabled_rules,
            color=0x2b2d31
        )
        embed.add_field(
            name=f"{SETTINGS_EMOJI} Customization",
            value="Use 'automod punishment' to modify penalties for each event (except Anti NSFW Link).",
            inline=False
        )
        embed.set_footer(text="💡 Default Punishment is Mute.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ConfirmDisable(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.author = author
        self.value = None

    @discord.ui.button(label="Yes, Disable", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Access Denied",
                description="Only the command author can confirm this action.",
                color=0x2b2d31
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Access Denied", 
                description="Only the command author can cancel this action.",
                color=0x2b2d31
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        self.value = False
        self.stop()

class Automod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.default_punishment = "Mute"
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.settings_col = self.db["automod_settings"]
        self.rules_col = self.db["automod_rules"]
        self.ignored_col = self.db["automod_ignored"]
        
        # Anti repeated text attributes
        self.spam_threshold = 3  # Number of repeated messages to trigger action
        self.time_window = 10   # Time window in seconds to check for repeats
        self.user_message_cache = defaultdict(list)  # Cache user messages: {user_id: [(content, timestamp)]}

    async def cog_load(self):
        print("✅ [Automod] Extension loaded & DB initialized (MongoDB).")

    async def get_exempt_roles_channels(self, guild_id):
        roles_cursor = self.ignored_col.find({"guild_id": guild_id, "type": "role"})
        channels_cursor = self.ignored_col.find({"guild_id": guild_id, "type": "channel"})
        
        exempt_roles = [discord.Object(doc["target_id"]) for doc in await roles_cursor.to_list(length=None)]
        exempt_channels = [discord.Object(doc["target_id"]) for doc in await channels_cursor.to_list(length=None)]
        
        return exempt_roles, exempt_channels

    async def is_automod_enabled(self, guild_id):
        doc = await self.settings_col.find_one({"guild_id": guild_id})
        return doc is not None and doc.get("enabled", False)

    # Dictionary to map user-friendly event names to internal rule codes
    RULE_MAPPING = {
        "Anti spam": "anti_spam",
        "Anti caps": "anti_caps",
        "Anti link": "anti_link",
        "Anti invites": "anti_invites",
        "Anti mass mention": "anti_mass_mention",
        "Anti emoji spam": "anti_emoji",
        "Anti repeated text": "anti_repeated_text",
        "Anti NSFW link": "anti_nsfw"
    }

    # Reverse mapping for display
    REVERSE_RULE_MAPPING = {v: k for k, v in RULE_MAPPING.items()}

    async def update_punishments(self, guild_id, event, punishment):
        normalized_rule = self.RULE_MAPPING.get(event)
        if normalized_rule:
            await self.rules_col.update_one(
                {"guild_id": guild_id, "rule": normalized_rule},
                {"$set": {"punishment": punishment, "enabled": True}},
                upsert=True
            )

    async def get_current_punishments(self, guild_id):
        cursor = self.rules_col.find({"guild_id": guild_id})
        results = []
        for doc in await cursor.to_list(length=None):
            rule = doc.get("rule")
            if rule == "anti_nsfw": continue # Skip NSFW for general view if queried separately, but logic below excluded it. The original code excluded "Anti NSFW link".
            
            # Map back to display name
            display_name = self.REVERSE_RULE_MAPPING.get(rule, rule)
            results.append((display_name, doc.get("punishment")))
        return results

    async def is_anti_nsfw_enabled(self, guild_id):
        doc = await self.rules_col.find_one({"guild_id": guild_id, "rule": "anti_nsfw"})
        return doc is not None and doc.get("enabled", False)

    async def is_anti_repeated_text_enabled(self, guild_id):
        doc = await self.rules_col.find_one({"guild_id": guild_id, "rule": "anti_repeated_text"})
        return doc is not None and doc.get("enabled", False)

    def clean_old_messages(self, user_id):
        """Remove messages older than the time window"""
        now = datetime.utcnow()
        self.user_message_cache[user_id] = [
            (content, timestamp) for content, timestamp in self.user_message_cache[user_id]
            if (now - timestamp).total_seconds() <= self.time_window
        ]

    def count_repeated_messages(self, user_id, message_content):
        """Count how many times the same message was sent by user in time window"""
        return sum(1 for content, timestamp in self.user_message_cache[user_id] 
                  if content.lower().strip() == message_content.lower().strip())

    @commands.hybrid_group(invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def automod(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @automod.command(name="enable", help="Enable Automod on the server.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def enable(self, ctx):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied", 
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        if await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Status",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{WARNING_EMOJI} Already Active",
                value=f"Automoderation is already **{ENABLED_EMOJI} Enabled** for this server.",
                inline=False
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Management",
                value=f"Use `{ctx.prefix}automod disable` to turn off automod",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        # Event selection interface
        events = [
            "Anti spam",
            "Anti caps", 
            "Anti link",
            "Anti invites",
            "Anti mass mention",
            "Anti emoji spam",
            "Anti repeated text",
            "Anti NSFW link",
        ]

        event_emojis = {
            "Anti spam": ANTI_SPAM_EMOJI,
            "Anti caps": ANTI_CAPS_EMOJI,
            "Anti link": ANTI_LINK_EMOJI,
            "Anti invites": ANTI_INVITE_EMOJI,
            "Anti mass mention": ANTI_MENTION_EMOJI,
            "Anti emoji spam": ANTI_EMOJI_EMOJI,
            "Anti NSFW link": ANTI_NSFW_EMOJI,
        }

        # Cleaner layout
        embed = discord.Embed(
            title=f"{SHIELD_EMOJI} Automod Setup for {ctx.guild.name}",
            description=f"**Select protection features to enable:**\n\n",
            color=0x2b2d31
        )
        
        # Use simple list without excessive emojis
        event_list = ""
        for event in events:
            event_list += f"`•` **{event}**\n"
            
        embed.description += event_list + f"\n{LIST_EMOJI} **Use the dropdown below to activate modules.**"
        embed.add_field(
            name=f"{SETTINGS_EMOJI} Quick Actions:",
            value=f"{SUCCESS_EMOJI} **Enable All** - Activate all protections\n{ERROR_EMOJI} **Cancel** - Exit setup",
            inline=False
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(text="💡 Select multiple events using the dropdown menu")

        select_menu = discord.ui.Select(
            placeholder="Select events to enable...",
            min_values=1,
            max_values=len(events),
            options=[
                discord.SelectOption(
                    label=event,
                    value=event,
                    emoji=event_emojis.get(event, "<a:dot:1396429135588626442>")
                ) for event in events
            ]
        )

        async def select_callback(interaction):
            if interaction.user != ctx.author:
                embed = discord.Embed(
                    title=f"{ERROR_EMOJI} Access Denied",
                    description="Only the command author can configure automod.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            selected_events = select_menu.values
            await self.enable_automod(ctx, guild_id, selected_events, interaction)
        select_menu.callback = select_callback

        enable_all_button = discord.ui.Button(
            label="Enable All Events", 
            style=discord.ButtonStyle.success,
            emoji="⚡"
        )

        async def enable_all_callback(interaction):
            if interaction.user != ctx.author:
                embed = discord.Embed(
                    title=f"{ERROR_EMOJI} Access Denied",
                    description="Only the command author can configure automod.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            await self.enable_automod(ctx, guild_id, events, interaction)

        enable_all_button.callback = enable_all_callback

        cancel_button = discord.ui.Button(
            label="Cancel Setup",
            style=discord.ButtonStyle.danger,
            emoji="❌"
        )

        async def cancel_callback(interaction):
            if interaction.user != ctx.author:
                embed = discord.Embed(
                    title=f"{ERROR_EMOJI} Access Denied",
                    description="Only the command author can cancel setup.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            select_menu.disabled = True
            enable_all_button.disabled = True
            cancel_button.disabled = True
            
            cancel_embed = discord.Embed(
                title=f"{ERROR_EMOJI} Setup Cancelled",
                description="Automod setup has been cancelled. No changes were made.",
                color=0x2b2d31
            )
            cancel_embed.set_footer(text=f"Cancelled by {interaction.user.display_name}")
            await interaction.response.edit_message(embed=cancel_embed, view=view)

        cancel_button.callback = cancel_callback

        view = discord.ui.View()
        view.add_item(select_menu)
        view.add_item(enable_all_button)
        view.add_item(cancel_button)

        await ctx.send(embed=embed, view=view)

    async def enable_automod(self, ctx, guild_id, selected_events, interaction):
        await self.settings_col.update_one(
            {"guild_id": guild_id},
            {"$set": {"enabled": True}},
            upsert=True
        )
        
        for event in selected_events:
            normalized_rule = self.RULE_MAPPING.get(event)
            if normalized_rule:
                await self.rules_col.update_one(
                    {"guild_id": guild_id, "rule": normalized_rule},
                    {"$set": {"punishment": self.default_punishment, "enabled": True}},
                    upsert=True
                )

        # Anti NSFW setup (if selected) - COMPREHENSIVE FILTER
        if "Anti NSFW link" in selected_events:
            exempt_roles, exempt_channels = await self.get_exempt_roles_channels(guild_id)
            
            # Enhanced NSFW keywords including the new ones
            nsfw_keywords = [
                # Original NSFW keywords
                "porn", "xxx", "adult", "sex", "nsfw", "xnxx", "onlyfans", "brazzers", "xhamster", "xvideos", 
                "pornhub", "redtube", "livejasmin", "youporn", "tube8", "pornhat", "swxvid", "ixxx", 
                "tnaflix", "spankbang", "erome", "fapster", "hclips", "keezmovies", "motherless",
                
                # Adult content keywords
                "nude", "nudes", "naked", "hentai", "bdsm", "fetish", "camgirl", "camgirls", 
                "escort", "escorts", "hookup", "hookups", "titfuck", "blowjob", "handjob", 
                "dildo", "vibrator", "anal", "pussy", "feetjob", "cum", "squirt", "orgasm", 
                "threesome", "foursome", "assspanking", "bondage", "gokkun",
                
                # Hindi/Urdu abusive words
                "madarchod", "randi", "chudail", "behenchod", "bhosadiwala", "bhosadiwale", 
                "bhosdika", "bhosdike", "loda", "lund", "gand", "bkl", "chutiyapa", "mc", "bc", 
                "bcchod", "bhenchod", "lundka", "lodu", "gandu", "randiwala", "randiwale", 
                "chut", "chutiya", "chutiye", "tatti"
            ]

            try:
                await interaction.guild.create_automod_rule(
                    name="Anti NSFW Links",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=nsfw_keywords,
                    ),
                    actions=[
                        discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message),
                    ],
                    enabled=True,
                    exempt_roles=exempt_roles,
                    exempt_channels=exempt_channels,
                    reason="Automod - Comprehensive NSFW/Profanity Filter setup"
                )
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                print(f"Automod rule-create error: {e}")

        # Event emojis
        event_emojis = {
            "Anti spam": ANTI_SPAM_EMOJI,
            "Anti caps": ANTI_CAPS_EMOJI,
            "Anti link": ANTI_LINK_EMOJI,
            "Anti invites": ANTI_INVITE_EMOJI,
            "Anti mass mention": ANTI_MENTION_EMOJI,
            "Anti emoji spam": ANTI_EMOJI_EMOJI,
            "Anti repeated text": ANTI_SPAM_EMOJI,
            "Anti NSFW link": ANTI_NSFW_EMOJI,
        }

        all_events = ["Anti spam", "Anti caps", "Anti link", "Anti invites", "Anti mass mention", "Anti emoji spam", "Anti repeated text", "Anti NSFW link"]
        
        enabled_list = []
        disabled_list = []
        
        for event in all_events:
            # emoji = event_emojis.get(event, "<a:dot:1396429135588626442>") # Removed animation
            
            # Display Name conversion
            name = event.title() # Keep "Anti " -> Anti Spam
            name = name.replace("Nsfw Link", "NSFW Links") # Fix NSFW casing
            
            if event in selected_events:
                enabled_list.append(f"> <:enabled:1396473501447098368> **`{name}`**")
            else:
                disabled_list.append(f"> <:disabled:1396473518962507866> **`{name}`**")

        embed = discord.Embed(
            description=f"**Automod Settings For {ctx.guild.name} Enabled Successfully**\n\n"
                        f"**Active Protections:**\n" + "\n".join(enabled_list),
            color=0x2b2d31
        )

        if disabled_list:
             embed.description += "\n\n**Inactive Events**\n" + "\n".join(disabled_list)

        embed.add_field(
            name=f"{SETTINGS_EMOJI} Next Steps",
            value=f"• Use `{ctx.prefix}automod log` to set a logging channel.\n• Use `{ctx.prefix}automod punishment` to configure actions.",
            inline=False
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(text="Powered by Scyro.xyz", icon_url=self.bot.user.avatar.url)

        enable_logging_button = discord.ui.Button(
            label="Enable Logging", 
            style=discord.ButtonStyle.success,
            emoji=LOGGING_EMOJI
        )

        async def enable_logging_callback(interaction):
            if interaction.user != ctx.author:
                embed = discord.Embed(
                    title=f"{ERROR_EMOJI} Access Denied",
                    description="Only the command author can enable logging.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not interaction.guild.me.guild_permissions.manage_channels:
                embed = discord.Embed(
                    title=f"{WARNING_EMOJI} Missing Permissions",
                    description="I need **Manage Channels** permission to create a logging channel.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True)
            }

            try:
                for channel in interaction.guild.channels:
                    if channel.name == "automod-logs":
                        embed = discord.Embed(
                            title=f"{WARNING_EMOJI} Channel Exists",
                            description="A logging channel named **automod-logs** already exists.",
                            color=0x2b2d31
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                log_channel = await interaction.guild.create_text_channel("Scyro-automod", overwrites=overwrites)
                guild_id = interaction.guild.id

                await self.settings_col.update_one(
                    {"guild_id": guild_id},
                    {"$set": {"log_channel": log_channel.id}},
                    upsert=True
                )

                success_embed = discord.Embed(
                    title=f"{SUCCESS_EMOJI} Logging Enabled",
                    description=f"Logging channel {log_channel.mention} created successfully!\n\nAll automod actions will now be recorded.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=success_embed, ephemeral=True)

            except discord.HTTPException as e:
                error_embed = discord.Embed(
                    title=f"{ERROR_EMOJI} Setup Failed",
                    description=f"Failed to create logging channel: {e}",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)

        enable_logging_button.callback = enable_logging_callback

        view = ShowRules(ctx.author, selected_events)
        view.add_item(enable_logging_button)

        if interaction.response.is_done():
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    @automod.command(name="punishment", aliases=["punish"], help="Set the punishment for automod events.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def punishment(self, ctx):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to set up automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        # Get ALL punishments including Anti NSFW link
        cursor = self.rules_col.find({"guild_id": guild_id})
        all_punishments = []
        for doc in await cursor.to_list(length=None):
            rule = doc.get("rule")
            display_name = self.REVERSE_RULE_MAPPING.get(rule, rule)
            all_punishments.append((display_name, doc.get("punishment")))
        
        if not all_punishments:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} No Events Configured",
                description="No automod events are currently enabled.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Next Step",
                value=f"Use `{ctx.prefix}automod enable` to configure events first.",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        punishment_icons = {
            "Mute": MUTE_EMOJI,
            "Kick": KICK_EMOJI,
            "Ban": BAN_EMOJI,
            "Block Message": BLOCK_EMOJI
        }

        event_emojis = {
            "Anti spam": ANTI_SPAM_EMOJI,
            "Anti caps": ANTI_CAPS_EMOJI, 
            "Anti link": ANTI_LINK_EMOJI,
            "Anti invites": ANTI_INVITE_EMOJI,
            "Anti mass mention": ANTI_MENTION_EMOJI,
            "Anti emoji spam": ANTI_EMOJI_EMOJI,
            "Anti repeated text": ANTI_SPAM_EMOJI,
            "Anti NSFW link": ANTI_NSFW_EMOJI
        }

        embed = discord.Embed(
            title=f"{PUNISHMENT_EMOJI} Current Automod Punishments",
            description=f"**Manage penalties for {ctx.guild.name}**\n\n" +
                       f"{LIST_EMOJI} **All configured automod events and their punishments:**",
            color=0x2b2d31
        )

        # Show ALL punishments including Anti NSFW
        punishment_field = ""
        modifiable_events = []
        
        for event, punishment in all_punishments:
            event_icon = event_emojis.get(event, "<a:dot:1396429135588626442>")
            punishment_icon = punishment_icons.get(punishment, "⚖️")
            
            if event == "Anti NSFW link":
                # Show Anti NSFW as unchangeable
                punishment_field += f"{event_icon} **{event}**: {punishment_icon} Block Message *(unchangeable)*\n"
            else:
                punishment_field += f"{event_icon} **{event}**: {punishment_icon} {punishment or 'None'}\n"
                modifiable_events.append(event)

        embed.add_field(
            name=f"{SETTINGS_EMOJI} Current Settings",
            value=punishment_field,
            inline=False
        )

        if not modifiable_events:
            embed.add_field(
                name=f"{WARNING_EMOJI} No Modifiable Events",
                value="All your enabled events have fixed punishments that cannot be changed.",
                inline=False
            )
            embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
            embed.set_footer(text="💡 Anti NSFW Link punishment is permanently set to Block Message")
            await ctx.send(embed=embed)
            return

        embed.add_field(
            name=f"{SHIELD_EMOJI} Recommendation",
            value="Keep **Mute** as default to prevent server raids without permanent consequences.",
            inline=False
        )

        embed.add_field(
            name=f"💡 Note",
            value="**Anti NSFW Link** punishment cannot be changed (always Block Message)",
            inline=False
        )

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(text="💡 Select events from the dropdown to update their punishments")

        # Only show modifiable events in the dropdown
        select = discord.ui.Select(
            placeholder="⚖️ Select events to update punishment...",
            options=[
                discord.SelectOption(
                    label=event,
                    value=event,
                    emoji=event_emojis.get(event, "<a:dot:1396429135588626442>")
                ) for event in modifiable_events
            ],
            min_values=1,
            max_values=len(modifiable_events)
        )

        async def select_callback(interaction):
            if interaction.user != ctx.author:
                embed = discord.Embed(
                    title=f"{ERROR_EMOJI} Access Denied",
                    description="Only the command author can modify punishments.",
                    color=0x2b2d31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            selected_events = select.values
            
            selection_embed = discord.Embed(
                title=f"{PUNISHMENT_EMOJI} Punishment Selection",
                description=f"**Selected Events:** {', '.join(selected_events)}\n\nChoose the new punishment type:",
                color=0x2b2d31
            )
            
            punishment_buttons = discord.ui.View()
            punishments = [
                {"name": "Mute", "emoji": MUTE_EMOJI, "style": discord.ButtonStyle.primary},
                {"name": "Kick", "emoji": KICK_EMOJI, "style": discord.ButtonStyle.secondary}, 
                {"name": "Ban", "emoji": BAN_EMOJI, "style": discord.ButtonStyle.danger}
            ]

            for punishment_data in punishments:
                button = discord.ui.Button(
                    label=punishment_data["name"],
                    style=punishment_data["style"],
                    emoji=punishment_data["emoji"]
                )

                async def punishment_callback(button_interaction, selected_events=selected_events, punishment=punishment_data["name"]):
                    if button_interaction.user != ctx.author:
                        embed = discord.Embed(
                            title=f"{ERROR_EMOJI} Access Denied",
                            description="Only the command author can set punishments.",
                            color=0x2b2d31
                        )
                        await button_interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    for event in selected_events:
                        await self.update_punishments(guild_id, event, punishment)

                    # Get updated punishments including Anti NSFW
                    cursor = self.rules_col.find({"guild_id": guild_id})
                    updated_punishments = []
                    for doc in await cursor.to_list(length=None):
                        rule = doc.get("rule")
                        display_name = self.REVERSE_RULE_MAPPING.get(rule, rule)
                        updated_punishments.append((display_name, doc.get("punishment")))
                    
                    updated_embed = discord.Embed(
                        title=f"{SUCCESS_EMOJI} Punishments Updated",
                        description=f"**Successfully updated penalties for {ctx.guild.name}**",
                        color=0x2b2d31
                    )

                    updated_field = ""
                    for event, punishment in updated_punishments:
                        event_icon = event_emojis.get(event, "<a:dot:1396429135588626442>")
                        punishment_icon = punishment_icons.get(punishment, "⚖️")
                        
                        if event == "Anti NSFW link":
                            updated_field += f"{event_icon} **{event}**: {punishment_icon} Block Message *(unchangeable)*\n"
                        else:
                            updated_field += f"{event_icon} **{event}**: {punishment_icon} {punishment or 'None'}\n"

                    updated_embed.add_field(
                        name=f"{SETTINGS_EMOJI} Updated Settings",
                        value=updated_field,
                        inline=False
                    )

                    updated_embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
                    updated_embed.set_footer(text="💡 Run the command again to make further changes")

                    await button_interaction.response.edit_message(embed=updated_embed, view=None)

                button.callback = punishment_callback
                punishment_buttons.add_item(button)

            await interaction.response.send_message(embed=selection_embed, view=punishment_buttons, ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await ctx.send(embed=embed, view=view)

    @automod.group(name="ignore", aliases=["exempt", "whitelist", "wl"], help="Manage whitelisted roles and channels for Automod.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def ignore(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @ignore.command(name="channel", help="Add a channel to the whitelist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ignore_channel(self, ctx, channel: discord.TextChannel):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return

        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        if await self.ignored_col.count_documents({"guild_id": guild_id, "type": "channel", "target_id": channel.id}, limit=1) > 0:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Already Whitelisted",
                description=f"The channel {channel.mention} is already in the ignore list.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Management",
                value=f"Use `{ctx.prefix}automod unignore channel {channel.mention}` to remove it.",
                inline=False
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        count = await self.ignored_col.count_documents({"guild_id": guild_id, "type": "channel"})

        if count >= 10:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Limit Reached",
                description="You can only ignore up to **10 channels** per server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{LIST_EMOJI} Current Count",
                value=f"**{count}/10** channels ignored",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        await self.ignored_col.insert_one({"guild_id": guild_id, "type": "channel", "target_id": channel.id})
        
        if await self.is_anti_nsfw_enabled(guild_id):
            try:
                rules = await ctx.guild.fetch_automod_rules()
                for rule in rules:
                    if rule.name == "Anti NSFW Links":
                        exempt_channels = list(rule.exempt_channels)  
                        exempt_channels.append(channel) 
                        await rule.edit(
                            exempt_channels=exempt_channels,
                            reason="Channel exempted from Anti NSFW Links via automod ignore command"
                        )
                        break
            except discord.HTTPException:
                pass

        success = discord.Embed(
            title=f"{SUCCESS_EMOJI} Channel Whitelisted",
            description=f"The channel {channel.mention} has been added to the automod ignore list.",
            color=0x2b2d31
        )
        success.add_field(
            name=f"{WHITELIST_EMOJI} Protection Status", 
            value="This channel is now exempt from all automod rules.",
            inline=False
        )
        success.add_field(
            name=f"{LIST_EMOJI} View Whitelist",
            value=f"Use `{ctx.prefix}automod ignore show` to view all ignored channels and roles.",
            inline=False
        )
        success.set_thumbnail(url=self.bot.user.avatar.url)
        success.set_footer(
            text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )

        await ctx.send(embed=success)

    @ignore.command(name="role", help="Add a role to the whitelist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ignore_role(self, ctx, role: discord.Role):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return

        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        if await self.ignored_col.count_documents({"guild_id": guild_id, "type": "role", "target_id": role.id}, limit=1) > 0:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Already Whitelisted",
                description=f"The role {role.mention} is already in the ignore list.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Management",
                value=f"Use `{ctx.prefix}automod unignore role {role.mention}` to remove it.",
                inline=False
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        count = await self.ignored_col.count_documents({"guild_id": guild_id, "type": "role"})

        if count >= 10:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Limit Reached",
                description="You can only ignore up to **10 roles** per server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{LIST_EMOJI} Current Count",
                value=f"**{count}/10** roles ignored",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        await self.ignored_col.insert_one({"guild_id": guild_id, "type": "role", "target_id": role.id})
        
        if await self.is_anti_nsfw_enabled(guild_id):
            try:
                rules = await ctx.guild.fetch_automod_rules()
                for rule in rules:
                    if rule.name == "Anti NSFW Links":
                        exempt_roles = list(rule.exempt_roles)  
                        exempt_roles.append(role) 
                        await rule.edit(
                            exempt_roles=exempt_roles,
                            reason="Role exempted from Anti NSFW Links via automod ignore command"
                        )
                        break
            except discord.HTTPException:
                pass

        success = discord.Embed(
            title=f"{SUCCESS_EMOJI} Role Whitelisted",
            description=f"The role {role.mention} has been added to the automod ignore list.",
            color=0x2b2d31
        )
        success.add_field(
            name=f"{WHITELIST_EMOJI} Protection Status", 
            value="Users with this role are now exempt from all automod rules.",
            inline=False
        )
        success.add_field(
            name=f"{LIST_EMOJI} View Whitelist",
            value=f"Use `{ctx.prefix}automod ignore show` to view all ignored channels and roles.",
            inline=False
        )
        success.set_thumbnail(url=self.bot.user.avatar.url)
        success.set_footer(
            text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )

        await ctx.send(embed=success)

    @ignore.command(name="show", aliases=["view", "list", "config"], help="Show the whitelisted roles and channels.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ignore_show(self, ctx):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return

        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        cursor = self.ignored_col.find({"guild_id": guild_id})
        ignored_items = []
        for doc in await cursor.to_list(length=None):
            ignored_items.append((doc["type"], doc["target_id"]))

        if not ignored_items:
            embed = discord.Embed(
                title=f"{LIST_EMOJI} Automod Whitelist",
                description=f"**No ignored channels or roles configured**\n\n{WHITELIST_EMOJI} All channels and roles are subject to automod rules.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Add Exemptions",
                value=f"{CHANNEL_EMOJI} `{ctx.prefix}automod ignore channel #channel`\n{ROLE_EMOJI} `{ctx.prefix}automod ignore role @role`",
                inline=False
            )
            embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
            await ctx.send(embed=embed)
            return

        ignored_channels = []
        ignored_roles = []

        for item_type, item_id in ignored_items:
            if item_type == "channel":
                channel = ctx.guild.get_channel(item_id)
                if channel:
                    ignored_channels.append(f"{CHANNEL_EMOJI} {channel.mention} (ID: `{channel.id}`)")
                else:
                    ignored_channels.append(f"{ERROR_EMOJI} Deleted Channel (ID: `{item_id}`)")
            elif item_type == "role":
                role = ctx.guild.get_role(item_id)
                if role:
                    ignored_roles.append(f"{ROLE_EMOJI} {role.mention} (ID: `{role.id}`)")
                else:
                    ignored_roles.append(f"{ERROR_EMOJI} Deleted Role (ID: `{item_id}`)")

        embed = discord.Embed(
            title=f"{WHITELIST_EMOJI} Automod Whitelist for {ctx.guild.name}",
            description="**The following channels and roles are exempt from automod rules:**",
            color=0x2b2d31
        )

        if ignored_channels:
            channels_text = "\n".join(ignored_channels)
            embed.add_field(name=f"{CHANNEL_EMOJI} **Ignored Channels** ({len(ignored_channels)}/10)", value=channels_text, inline=False)
        else:
            embed.add_field(name=f"{CHANNEL_EMOJI} **Ignored Channels** (0/10)", value=f"{DISABLED_EMOJI} None configured", inline=False)

        if ignored_roles:
            roles_text = "\n".join(ignored_roles)
            embed.add_field(name=f"{ROLE_EMOJI} **Ignored Roles** ({len(ignored_roles)}/10)", value=roles_text, inline=False)
        else:
            embed.add_field(name=f"{ROLE_EMOJI} **Ignored Roles** (0/10)", value=f"{DISABLED_EMOJI} None configured", inline=False)

        embed.add_field(
            name=f"{SETTINGS_EMOJI} Management Commands",
            value=f"{RESET_EMOJI} `{ctx.prefix}automod ignore reset` - Clear all exemptions\n{ERROR_EMOJI} `{ctx.prefix}automod unignore` - Remove specific items",
            inline=False
        )

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(text="💡 Whitelisted items bypass all automod protection")

        await ctx.send(embed=embed)

    @ignore.command(name="reset", help="Reset the whitelist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def ignore_reset(self, ctx):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return

        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        async with aiosqlite.connect("db/automod.db") as db:
            await db.execute("DELETE FROM automod_ignored WHERE guild_id = ?", (guild_id,))
            await db.commit()
            
        embed = discord.Embed(
            title=f"{SUCCESS_EMOJI} Whitelist Reset Complete",
            description=f"**All ignored channels and roles have been reset for {ctx.guild.name}**",
            color=0x2b2d31
        )
        embed.add_field(
            name=f"{SHIELD_EMOJI} Protection Status",
            value="All channels and roles are now subject to automod rules again.",
            inline=False
        )
        embed.add_field(
            name=f"{SETTINGS_EMOJI} View Configuration", 
            value=f"Use `{ctx.prefix}automod config` to view current automod settings.",
            inline=False
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(
            text=f"Reset by {ctx.author.display_name} • Full protection restored",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )
        await ctx.send(embed=embed)

    @automod.group(name="unignore", aliases=["unwhitelist", "unwl"], invoke_without_command=True, help="Remove channels and roles from the whitelist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def unignore(self, ctx):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @unignore.command(name="channel", help="Remove a channel from the whitelist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def unignore_channel(self, ctx, channel: discord.TextChannel):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return

        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        if await self.is_anti_nsfw_enabled(guild_id):
            try:
                rules = await ctx.guild.fetch_automod_rules()
                for rule in rules:
                    if rule.name == "Anti NSFW Links":
                        exempt_channels = list(rule.exempt_channels)  
                        exempt_channels = [ch for ch in exempt_channels if ch.id != channel.id]
                        await rule.edit(
                            exempt_channels=exempt_channels,
                            reason="Channel removed from Anti NSFW Links exemption via automod unignore command"
                        )
                        break
            except discord.HTTPException:
                pass
        
        result = await self.ignored_col.delete_one({"guild_id": guild_id, "type": "channel", "target_id": channel.id})

        if result.deleted_count > 0:
            embed = discord.Embed(
                title=f"{SUCCESS_EMOJI} Channel Removed from Whitelist",
                description=f"{channel.mention} has been removed from the automod ignore list.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SHIELD_EMOJI} Protection Status",
                value="This channel is now subject to all automod rules again.",
                inline=False
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Channel Not Found",
                description=f"{channel.mention} is not in the automod ignore list.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{LIST_EMOJI} View Whitelist",
                value=f"Use `{ctx.prefix}automod ignore show` to see all ignored items.",
                inline=False
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)

    @unignore.command(name="role", help="Remove a role from the whitelist.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def unignore_role(self, ctx, role: discord.Role):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return

        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        if await self.is_anti_nsfw_enabled(guild_id):
            try:
                rules = await ctx.guild.fetch_automod_rules()
                for rule in rules:
                    if rule.name == "Anti NSFW Links":
                        exempt_roles = list(rule.exempt_roles)  
                        exempt_roles = [r for r in exempt_roles if r.id != role.id]
                        await rule.edit(
                            exempt_roles=exempt_roles,
                            reason="Role removed from Anti NSFW Links exemption via automod unignore command"
                        )
                        break
            except discord.HTTPException:
                pass

        result = await self.ignored_col.delete_one({"guild_id": guild_id, "type": "role", "target_id": role.id})

        if result.deleted_count > 0:
            embed = discord.Embed(
                title=f"{SUCCESS_EMOJI} Role Removed from Whitelist",
                description=f"{role.mention} has been removed from the automod ignore list.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SHIELD_EMOJI} Protection Status",
                value="Users with this role are now subject to all automod rules again.",
                inline=False
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title=f"{ERROR_EMOJI} Role Not Found",
                description=f"{role.mention} is not in the automod ignore list.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{LIST_EMOJI} View Whitelist",
                value=f"Use `{ctx.prefix}automod ignore show` to see all ignored items.",
                inline=False
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)

    @automod.command(name="disable", help="Disable Automod in the server.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Status", 
                description=f"Automoderation is already **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate protection.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        embed = discord.Embed(
            title=f"{WARNING_EMOJI} Disable Automod Confirmation",
            description="**Are you sure you want to disable Automod protection?**\n\nThis will permanently remove:",
            color=0x2b2d31
        )
        
        embed.add_field(
            name=f"{RESET_EMOJI} What will be deleted:",
            value=f"{SETTINGS_EMOJI} All event configurations\n{PUNISHMENT_EMOJI} Custom punishment settings\n{WHITELIST_EMOJI} Ignored roles and channels\n{LOGGING_EMOJI} Logging channel data\n{ANTI_NSFW_EMOJI} Anti-NSFW Discord rules",
            inline=False
        )
        
        embed.add_field(
            name=f"⚠️ Warning",
            value="This action **cannot be undone**. You'll need to reconfigure everything if you re-enable automod.",
            inline=False
        )
        
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(text="Choose carefully - this will remove all automod protection")

        view = ConfirmDisable(ctx.author)
        message = await ctx.send(embed=embed, view=view)

        await view.wait()

        if view.value is None:
            timeout_embed = discord.Embed(
                title=f"{ERROR_EMOJI} Request Timeout",
                description="You took too long to respond. Automod disable process has been cancelled.",
                color=0x2b2d31
            )
            timeout_embed.set_footer(text="Automod remains active")
            await message.edit(embed=timeout_embed, view=None)

        elif view.value:
            # Disable automod
            await self.settings_col.delete_one({"guild_id": guild_id})
            await self.rules_col.delete_many({"guild_id": guild_id})
            await self.ignored_col.delete_many({"guild_id": guild_id})

            # Remove Discord automod rules
            rules = await ctx.guild.fetch_automod_rules()
            for rule in rules:
                if rule.name == "Anti NSFW Links":
                    try:
                        await rule.delete(reason="Automod disabled - removing Anti NSFW Link rule")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            success_embed = discord.Embed(
                title=f"{SUCCESS_EMOJI} Automod Disabled",
                description=f"**Automod has been successfully disabled for {ctx.guild.name}**",
                color=0x2b2d31
            )
            
            success_embed.add_field(
                name=f"{RESET_EMOJI} Cleanup Complete",
                value="All settings, punishments, whitelist data, and logging configuration have been removed.",
                inline=False
            )
            
            success_embed.add_field(
                name=f"{SETTINGS_EMOJI} Re-enabling",
                value=f"Use `{ctx.prefix}automod enable` whenever you want to reactivate protection.",
                inline=False
            )
            
            success_embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
            success_embed.set_footer(
                text=f"Disabled by {ctx.author.display_name} • Your server is no longer protected",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await message.edit(embed=success_embed, view=None)

        else:
            cancel_embed = discord.Embed(
                title=f"{SUCCESS_EMOJI} Disable Cancelled",
                description="Automod disable process has been cancelled. Your protection remains active.",
                color=0x2b2d31
            )
            cancel_embed.set_footer(
                text=f"Cancelled by {ctx.author.display_name} • Automod is still protecting your server"
            )
            await message.edit(embed=cancel_embed, view=None)

    @automod.command(name="config", aliases=["settings", "show", "view"], help="View Automod settings.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def config(self, ctx):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Configuration",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate protection features.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return

        current_punishments = await self.get_current_punishments(guild_id)
        
        embed = discord.Embed(
            title=f"{SHIELD_EMOJI} Automod Configuration",
            description=f"**Active protection settings for {ctx.guild.name}**",
            color=0x2b2d31
        )

        if current_punishments:
            punishment_icons = {
                "Mute": MUTE_EMOJI,
                "Kick": KICK_EMOJI, 
                "Ban": BAN_EMOJI,
                "Block Message": BLOCK_EMOJI
            }

            event_emojis = {
                "Anti spam": ANTI_SPAM_EMOJI,
                "Anti caps": ANTI_CAPS_EMOJI,
                "Anti link": ANTI_LINK_EMOJI,
                "Anti invites": ANTI_INVITE_EMOJI,
                "Anti mass mention": ANTI_MENTION_EMOJI,
                "Anti emoji spam": ANTI_EMOJI_EMOJI,
                "Anti repeated text": ANTI_SPAM_EMOJI,
            }

            events_field = ""
            for event, punishment in current_punishments:
                event_icon = event_emojis.get(event, "<a:dot:1396429135588626442>")
                punishment_icon = punishment_icons.get(punishment, "⚖️")
                events_field += f"{event_icon} **{event}**\n{punishment_icon} *Punishment:* {punishment or 'None'}\n\n"

            embed.add_field(
                name=f"{ENABLED_EMOJI} Active Events",
                value=events_field,
                inline=False
            )

        if await self.is_anti_nsfw_enabled(guild_id):
            embed.add_field(
                name=f"{ANTI_NSFW_EMOJI} Anti NSFW Links",
                value=f"{BLOCK_EMOJI} *Punishment:* Block Message",
                inline=False
            )

        # Logging channel info
        settings_doc = await self.settings_col.find_one({"guild_id": guild_id})
        log_channel_id = settings_doc.get("log_channel") if settings_doc else None

        if log_channel_id:
            log_channel = ctx.guild.get_channel(log_channel_id)
            log_status = f"{LOGGING_EMOJI} {log_channel.mention}" if log_channel else f"{ERROR_EMOJI} Channel Deleted"
        else:
            log_status = f"{DISABLED_EMOJI} Not configured"

        embed.add_field(
            name=f"{LOGGING_EMOJI} Logging Channel",
            value=log_status,
            inline=False
        )

        embed.add_field(
            name=f"{SETTINGS_EMOJI} Management Commands",
            value=f"{PUNISHMENT_EMOJI} `automod punishment` - Modify penalties\n{WHITELIST_EMOJI} `automod ignore` - Manage whitelist\n{DISABLED_EMOJI} `automod disable` - Turn off automod",
            inline=False
        )

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(text="💡 Automod is actively protecting your server")

        await ctx.send(embed=embed)

    @automod.command(name="logging", help="Set the logging channel for Automod events.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def logging(self, ctx, channel: discord.TextChannel):
        guild_id = ctx.guild.id
        if ctx.author != ctx.guild.owner and ctx.author.top_role.position < ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title=f"{WARNING_EMOJI} Access Denied",
                description="Your top role must be at the **same** position or **higher** than my top role.",
                color=0x2b2d31
            )
            embed.set_footer(
                text=f"'{ctx.command.qualified_name}' Command executed by {ctx.author}",
                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        if not await self.is_automod_enabled(guild_id):
            embed = discord.Embed(
                title=f"{SECURITY_EMOJI} Automod Not Active",
                description=f"Automoderation is currently **{DISABLED_EMOJI} Disabled** for this server.",
                color=0x2b2d31
            )
            embed.add_field(
                name=f"{SETTINGS_EMOJI} Getting Started",
                value=f"Use `{ctx.prefix}automod enable` to activate automod first.",
                inline=False
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.set_footer(
                text=f"Server: {ctx.guild.name} • Requested by {ctx.author.display_name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url
            )
            await ctx.send(embed=embed)
            return
            
        await self.settings_col.update_one(
            {"guild_id": guild_id},
            {"$set": {"log_channel": channel.id}},
            upsert=True
        )
            
        embed = discord.Embed(
            title=f"{SUCCESS_EMOJI} Logging Channel Set",
            description=f"**Automod logging has been configured successfully!**",
            color=0x2b2d31
        )
        embed.add_field(
            name=f"{LOGGING_EMOJI} Channel",
            value=f"All automod actions will now be logged to {channel.mention}",
            inline=False
        )
        embed.add_field(
            name=f"{SETTINGS_EMOJI} View Configuration",
            value=f"Use `{ctx.prefix}automod config` to view all current settings.",
            inline=False
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        embed.set_footer(
            text=f"Configured by {ctx.author.display_name} • Logging is now active",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle anti-repeated text detection"""
        if message.author.bot:
            return

        # CRITICAL: Add guild check to prevent DM errors
        if not message.guild:
            return

        guild = message.guild
        user = message.author
        channel = message.channel
        guild_id = guild.id

        if not await self.is_automod_enabled(guild_id) or not await self.is_anti_repeated_text_enabled(guild_id):
            return

        if user == guild.owner or user == self.bot.user:
            return

        # Get ignored channels, roles and users
        ignored_channels_cursor = self.ignored_col.find({"guild_id": guild_id, "type": "channel"})
        ignored_roles_cursor = self.ignored_col.find({"guild_id": guild_id, "type": "role"})
        ignored_users_cursor = self.ignored_col.find({"guild_id": guild_id, "type": "user"})
        
        ignored_channels = [doc["target_id"] for doc in await ignored_channels_cursor.to_list(length=None)]
        ignored_roles = [doc["target_id"] for doc in await ignored_roles_cursor.to_list(length=None)]
        ignored_users = [doc["target_id"] for doc in await ignored_users_cursor.to_list(length=None)]

        if channel.id in ignored_channels:
            return
            
        if user.id in ignored_users:
            return

        if any(role.id in ignored_roles for role in user.roles):
            return

        # Skip empty messages or messages with only whitespace
        if not message.content.strip():
            return

        user_id = user.id
        message_content = message.content

        # Clean old messages from cache
        self.clean_old_messages(user_id)

        # Count how many times this exact message was sent recently
        repeat_count = self.count_repeated_messages(user_id, message_content)

        if repeat_count >= self.spam_threshold:
            # Get punishment for anti repeated text
            doc = await self.rules_col.find_one({"guild_id": guild_id, "rule": "anti_repeated_text"})
            punishment = doc["punishment"] if doc else "Mute"

            action_taken = None
            reason = f"Repeated Text Spam ({repeat_count + 1} identical messages)"

            try:
                if punishment == "Mute":
                    timeout_duration = discord.utils.utcnow() + timedelta(minutes=5)
                    await user.edit(timed_out_until=timeout_duration, reason=reason)
                    action_taken = "Muted for 5 minutes"
                elif punishment == "Kick":
                    await user.kick(reason=reason)
                    action_taken = "Kicked"
                elif punishment == "Ban":
                    await user.ban(reason=reason)
                    action_taken = "Banned"

                # Delete the repeated message
                await message.delete()

                # Send warning embed
                simple_embed = discord.Embed(title="Automod Anti Repeated Text", color=0x2b2d31)
                simple_embed.description = f"<:tick:1348326381611647046> | {user.mention} has been successfully **{action_taken}** for **Sending Repeated Messages.**"
                simple_embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1294125691587006525.png")
                simple_embed.set_footer(text='Use the "automod logging" command to get automod logs if it is not enabled.', icon_url=self.bot.user.avatar.url)
                
                await channel.send(embed=simple_embed, delete_after=30)

                # Clear user's message cache after punishment to prevent multiple punishments
                self.user_message_cache[user_id].clear()

                # Log the action
                await self.log_automod_action(guild, user, channel, action_taken, reason)

            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass
            except Exception:
                pass
        else:
            # Add current message to cache
            self.user_message_cache[user_id].append((message_content, datetime.utcnow()))

    async def log_automod_action(self, guild, user, channel, action, reason):
        """Log automod actions to the configured logging channel"""
        settings_doc = await self.settings_col.find_one({"guild_id": guild.id})
        log_channel_id = settings_doc.get("log_channel") if settings_doc else None

        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title="Automod Log: Anti Repeated Text", color=0x2b2d31)
                embed.add_field(name="User", value=user.mention, inline=False)
                embed.add_field(name="Action", value=action, inline=False)
                embed.add_field(name="Channel", value=channel.mention, inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.set_footer(text=f"User ID: {user.id}")
                avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
                embed.set_thumbnail(url=avatar_url)
                embed.timestamp = discord.utils.utcnow()
                await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        guild_id = guild.id

        await self.settings_col.delete_one({"guild_id": guild_id})
        await self.rules_col.delete_many({"guild_id": guild_id})
        await self.ignored_col.delete_many({"guild_id": guild_id})

async def setup(bot):
    await bot.add_cog(Automod(bot))
