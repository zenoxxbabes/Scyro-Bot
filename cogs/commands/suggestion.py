import discord
from discord.ext import commands
from discord import app_commands
import motor.motor_asyncio
import datetime
import os
from utils.Tools import *
from typing import Optional
from bson import ObjectId

# Bot Owner Configuration
BOT_OWNER_ID = 1218037361926209640  # Your bot owner ID
BOT_OWNER_EMOJI = "<:90716owner:1417059807172497460>"  # Your custom bot owner emoji

# ═══════════════════════════════════════════════════════════════════════════════
#                           🎨 EMOJI CONFIGURATION - BEAUTIFUL DESIGN
# ═══════════════════════════════════════════════════════════════════════════════

# Status Emojis
SUCCESS_EMOJI = "<:yes:1396838746862784582>"        # Success messages
ERROR_EMOJI = "<:no:1396838761605890090>"          # Error messages
WARNING_EMOJI = "<a:alert:1396429026842644584>"    # Warning messages
INFO_EMOJI = "ℹ️"                                   # Info messages

# Feature Emojis
SUGGESTION_EMOJI = "💡"     # Suggestion indicator
CHANNEL_EMOJI = "📺"        # Channel indicator
SETTINGS_EMOJI = "⚙️"       # Settings
LIST_EMOJI = "📋"          # Lists
RESET_EMOJI = "🔄"         # Reset operations
USER_EMOJI = "👤"          # User indicator
TIME_EMOJI = "⏰"          # Time indicator
APPROVE_EMOJI = "✅"       # Approve
REJECT_EMOJI = "❌"        # Reject
ACCEPT_EMOJI = "🎉"        # Accept
DECLINE_EMOJI = "🚫"       # Decline

# Reaction Emojis for Voting
UPVOTE_EMOJI = "⬆️"         # Upvote reaction
DOWNVOTE_EMOJI = "⬇️"       # Downvote reaction

# Response Emojis
THANKS_EMOJI = "🙏"         # Thank you message
LOADING_EMOJI = "⏳"        # Loading indicator
VIEW_EMOJI = "👁️"          # View indicator

# Database setup removed - will be handled in Cog

class SuggestionView(discord.ui.View):
    """Interactive view for suggestion management"""
    def __init__(self, suggestion_id: int, cog):
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id
        self.cog = cog

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="🎉")
    async def accept_suggestion(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept a suggestion"""
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need `Manage Messages` permission to accept suggestions.", ephemeral=True)
            return

        await self.cog.update_suggestion_status(
             self.suggestion_id, interaction.guild.id, "accepted", interaction.user.id
        )

        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = 0x2ecc71
        embed.set_field_at(2, name="Status", value=f"{ACCEPT_EMOJI} **Accepted by {interaction.user.mention}**", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🚫")
    async def decline_suggestion(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline a suggestion"""
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need `Manage Messages` permission to decline suggestions.", ephemeral=True)
            return

        await self.cog.update_suggestion_status(
             self.suggestion_id, interaction.guild.id, "declined", interaction.user.id
        )

        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = 0xe74c3c
        embed.set_field_at(2, name="Status", value=f"{DECLINE_EMOJI} **Declined by {interaction.user.mention}**", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=None)

class ConfirmView(discord.ui.View):
    """Confirmation view for destructive actions"""
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.user:
            await interaction.response.send_message("You cannot interact with this confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.value = False
        self.stop()

class Suggestion(commands.Cog):
    """Advanced suggestion system with comprehensive management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.settings_coll = None
        self.suggestions_coll = None
        self.bot.loop.create_task(self.setup_db())

    def is_bot_owner_check(self, user_id: int) -> bool:
        """Check if user is the bot owner"""
        return user_id == BOT_OWNER_ID

    async def check_permissions(self, ctx_or_interaction, required_perm="administrator"):
        """Check if user has permission to use suggestion admin commands"""
        if hasattr(ctx_or_interaction, 'author'):
            user = ctx_or_interaction.author
            guild = ctx_or_interaction.guild
        else:
            user = ctx_or_interaction.user
            guild = ctx_or_interaction.guild
            
        # Bot owner bypass - can use commands in any guild
        if self.is_bot_owner_check(user.id):
            return True
        
        # Check specific permission
        if required_perm == "administrator":
            return user.guild_permissions.administrator
        elif required_perm == "manage_messages":
            return user.guild_permissions.manage_messages
        
        return False

    async def setup_db(self):
        """Initialize the database with comprehensive schema"""
        if not self.mongo_uri:
            print("MONGO_URI not found!")
            return

        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_database()
        self.settings_coll = self.db.suggestion_settings
        self.suggestions_coll = self.db.suggestions
        
        # Create indexes
        await self.settings_coll.create_index([("guild_id", 1)], unique=True)
        await self.suggestions_coll.create_index([("guild_id", 1), ("suggestion_number", 1)])
        
        print(f"{SUCCESS_EMOJI} Suggestion MongoDB initialized successfully!")

    def create_embed(self, title: str, description: str, color: int = 0x5865F2) -> discord.Embed:
        """Create a standardized embed with beautiful formatting"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text="Scyro Suggestion System", icon_url=self.bot.user.avatar.url)
        return embed

    async def get_suggestion_channel(self, guild_id: int) -> Optional[int]:
        """Get the suggestion channel for a guild"""
        settings = await self.settings_coll.find_one({"guild_id": guild_id, "enabled": True})
        return settings["channel_id"] if settings else None

    async def get_next_suggestion_number(self, guild_id: int) -> int:
        """Get the next suggestion number for a guild"""
        last_suggestion = await self.suggestions_coll.find_one(
            {"guild_id": guild_id},
            sort=[("suggestion_number", -1)]
        )
        return (last_suggestion["suggestion_number"] + 1) if last_suggestion else 1

    async def update_suggestion_status(self, suggestion_id: int, guild_id: int, status: str, reviewer_id: int):
        await self.suggestions_coll.update_one(
            {"suggestion_number": suggestion_id, "guild_id": guild_id},
            {"$set": {
                "status": status,
                "reviewed_by": reviewer_id,
                "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }}
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              🎮 PREFIX COMMAND - HELP SYSTEM
    # ═══════════════════════════════════════════════════════════════════════════════

    @commands.command(name='suggestionhelp', aliases=['suggesthelp', 'sugh'], help="Show all suggestion commands")
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def suggestion_help(self, ctx):
        """Show all suggestion commands when using prefix - RENAMED TO AVOID CONFLICTS"""
        # Check if user has admin permissions for admin commands display
        is_admin = await self.check_permissions(ctx)
        
        # Get prefix dynamically
        if hasattr(ctx, 'prefix'):
            prefix = ctx.prefix
        elif hasattr(ctx, 'clean_prefix'):
            prefix = ctx.clean_prefix
        else:
            prefix = '$'  # fallback prefix

        owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(ctx.author.id) else ""
        
        embed = self.create_embed(
            f"{SUGGESTION_EMOJI} **Suggestion System Commands**{owner_badge}",
            f"**Complete command list for {ctx.guild.name}**\n\n*Use slash commands `/suggestion` for the full experience!*",
            0x5865F2
        )

        # Basic Commands - Everyone can see
        embed.add_field(
            name=f"{USER_EMOJI} **User Commands**",
            value=f"""
{SUGGESTION_EMOJI} `/suggestion message <content>` - Submit a suggestion
{VIEW_EMOJI} `/suggestion view` - View recent suggestions
{SETTINGS_EMOJI} `/suggestion config` - View system configuration
            """,
            inline=False
        )

        # Admin Commands - Only show to admins or bot owner
        if is_admin:
            embed.add_field(
                name=f"{SETTINGS_EMOJI} **Admin Commands**",
                value=f"""
{CHANNEL_EMOJI} `/suggestion set_channel <channel>` - Set suggestion channel
{ACCEPT_EMOJI} `/suggestion accept <id>` - Accept a suggestion
{APPROVE_EMOJI} `/suggestion approve <id>` - Approve a suggestion (same as accept)
{DECLINE_EMOJI} `/suggestion decline <id>` - Decline a suggestion  
{REJECT_EMOJI} `/suggestion reject <id>` - Reject a suggestion (same as decline)
                """,
                inline=False
            )

        # How to Use
        embed.add_field(
            name=f"{INFO_EMOJI} **How to Use**",
            value=f"""
• All main functionality uses **slash commands** (`/suggestion`)
• Use `{prefix}suggestionhelp` or `{prefix}suggesthelp` to see this menu
• Suggestions get automatic voting reactions {UPVOTE_EMOJI} {DOWNVOTE_EMOJI}
• Staff can use interactive buttons or ID commands to review
            """,
            inline=False
        )

        # Bot Owner privileges
        if self.is_bot_owner_check(ctx.author.id):
            embed.add_field(
                name=f'{BOT_OWNER_EMOJI} **Bot Owner Privileges**',
                value='You have global access to all suggestion commands in every server',
                inline=False
            )

        # System Status
        channel_id = await self.get_suggestion_channel(ctx.guild.id)
        if channel_id:
            channel = ctx.guild.get_channel(channel_id)
            status_info = f"{SUCCESS_EMOJI} **Active** - Channel: {channel.mention if channel else '❌ Deleted'}"
        else:
            status_info = f"{ERROR_EMOJI} **Not Configured** - Use `/suggestion set_channel` to set up"

        embed.add_field(
            name=f"{LIST_EMOJI} **System Status**",
            value=status_info,
            inline=False
        )

        # Statistics (if system is configured)
        if channel_id:
            total_suggestions = await self.suggestions_coll.count_documents({"guild_id": ctx.guild.id})
            accepted = await self.suggestions_coll.count_documents({"guild_id": ctx.guild.id, "status": "accepted"})

            embed.add_field(
                name=f"{LIST_EMOJI} **Quick Stats**",
                value=f"**Total Suggestions:** {total_suggestions}\n**Accepted:** {accepted}",
                inline=True
            )

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.avatar.url)
        await ctx.send(embed=embed)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                              ⚡ SLASH COMMANDS
    # ═══════════════════════════════════════════════════════════════════════════════

    suggest_group = app_commands.Group(name="suggestion", description="Suggestion system management")

    @suggest_group.command(name="message", description="Submit a suggestion")
    @app_commands.describe(content="Your suggestion content")
    async def suggest_message(self, interaction: discord.Interaction, content: str):
        """Submit a suggestion - CHANGED FROM suggest to message"""
        # Get suggestion channel
        channel_id = await self.get_suggestion_channel(interaction.guild.id)
        if not channel_id:
            embed = self.create_embed(
                f"{ERROR_EMOJI} Not Configured",
                "The suggestion system hasn't been set up yet.\n\nContact an administrator to configure it using `/suggestion set_channel`.",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            embed = self.create_embed(
                f"{ERROR_EMOJI} Channel Not Found",
                "The configured suggestion channel no longer exists.\n\nContact an administrator to reconfigure it.",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Validate content
        if len(content) < 10:
            embed = self.create_embed(
                f"{WARNING_EMOJI} Too Short",
                "Your suggestion must be at least **10 characters** long.\n\nPlease provide more detail about your suggestion.",
                0xe67e22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if len(content) > 1000:
            embed = self.create_embed(
                f"{WARNING_EMOJI} Too Long",
                "Your suggestion must be less than **1000 characters**.\n\nPlease make it more concise.",
                0xe67e22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Get suggestion number
        suggestion_number = await self.get_next_suggestion_number(interaction.guild.id)

        # Create suggestion embed
        suggestion_embed = self.create_embed(
            f"{SUGGESTION_EMOJI} Suggestion #{suggestion_number:03d}",
            f"``````",
            0x5865F2
        )
        
        suggestion_embed.set_author(
            name=f"{interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        suggestion_embed.add_field(
            name=f"{USER_EMOJI} Submitted by",
            value=f"{interaction.user.mention} (`{interaction.user.id}`)",
            inline=True
        )
        
        suggestion_embed.add_field(
            name=f"{TIME_EMOJI} Submitted",
            value=f"<t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:R>",
            inline=True
        )
        
        suggestion_embed.add_field(
            name="Status",
            value=f"{LOADING_EMOJI} **Pending Review**",
            inline=True
        )

        try:
            # Send to suggestion channel with view
            view = SuggestionView(suggestion_number, self)  # Will update with actual ID
            message = await channel.send(embed=suggestion_embed, view=view)
            
            # Add voting reactions
            await message.add_reaction(UPVOTE_EMOJI)
            await message.add_reaction(DOWNVOTE_EMOJI)

            # Save to database
            current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            suggestion_doc = {
                "guild_id": interaction.guild.id,
                "user_id": interaction.user.id,
                "content": content,
                "message_id": message.id,
                "status": "pending",
                "upvotes": 0,
                "downvotes": 0,
                "created_at": current_time,
                "suggestion_number": suggestion_number
            }
            
            await self.suggestions_coll.insert_one(suggestion_doc)
            
            # Update view with correct suggestion ID (number)
            view.suggestion_id = suggestion_number

            # Send confirmation
            embed = self.create_embed(
                f"{SUCCESS_EMOJI} Suggestion Submitted!",
                f"{THANKS_EMOJI} **Thank you for your suggestion!**\n\n{CHANNEL_EMOJI} Your suggestion **#{suggestion_number:03d}** has been posted in {channel.mention} for review.\n\n{INFO_EMOJI} Community members can now vote on your suggestion, and staff will review it soon.",
                0x2ecc71
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.Forbidden:
            embed = self.create_embed(
                f"{ERROR_EMOJI} Permission Error",
                "I don't have permission to send messages in the suggestion channel.\n\nContact an administrator to fix my permissions.",
                0xe74c3c
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @suggest_group.command(name="set_channel", description="Set the channel for suggestions")
    @app_commands.describe(channel="The channel to send suggestions to")
    async def suggest_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set up the suggestion channel"""
        if not await self.check_permissions(interaction):
            embed = self.create_embed(
                f"{ERROR_EMOJI} Access Denied",
                "You need **Administrator** permission or be the Bot Owner to use this command!",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Check bot permissions
        bot_perms = channel.permissions_for(interaction.guild.me)
        if not bot_perms.send_messages or not bot_perms.add_reactions or not bot_perms.embed_links:
            embed = self.create_embed(
                f"{ERROR_EMOJI} Missing Permissions",
                f"I need the following permissions in {channel.mention}:\n• **Send Messages**\n• **Add Reactions**\n• **Embed Links**\n\nPlease grant these permissions and try again.",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Save to database
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        await self.settings_coll.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {
                "channel_id": channel.id,
                "enabled": True,
                "created_at": current_time,
                "created_by": interaction.user.id
            }},
            upsert=True
        )

        owner_note = f" | {BOT_OWNER_EMOJI} Bot Owner Override" if self.is_bot_owner_check(interaction.user.id) else ""
        embed = self.create_embed(
            f"{SUCCESS_EMOJI} Suggestion Channel Set!",
            f"""
**Suggestion system has been configured successfully!**{owner_note}

{CHANNEL_EMOJI} **Channel:** {channel.mention}
{USER_EMOJI} **Configured by:** {interaction.user.mention}
{TIME_EMOJI} **Set up:** <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:F>

{INFO_EMOJI} **Next Steps:**
• Users can now submit suggestions with `/suggestion message <content>`
• Suggestions will automatically get voting reactions {UPVOTE_EMOJI} {DOWNVOTE_EMOJI}
• Staff can accept/decline suggestions using buttons or ID commands
            """,
            0x2ecc71
        )
        await interaction.response.send_message(embed=embed)

    @suggest_group.command(name="config", description="Configure the suggestion system settings")
    async def suggest_config(self, interaction: discord.Interaction):
        """View current suggestion system configuration"""
        # Check permissions for detailed view
        is_admin = await self.check_permissions(interaction)
        
        settings = await self.settings_coll.find_one({"guild_id": interaction.guild.id})
        
        if not settings:
            embed = self.create_embed(
                f"{INFO_EMOJI} Not Configured",
                f"The suggestion system hasn't been set up yet.\n\n{SETTINGS_EMOJI} Use `/suggestion set_channel` to configure it.",
                0xe67e22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        guild_id = settings["guild_id"]
        channel_id = settings["channel_id"]
        enabled = settings["enabled"]
        created_at = settings.get("created_at")
        created_by = settings.get("created_by")
        
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        creator = interaction.guild.get_member(created_by) if created_by else None

        owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(interaction.user.id) else ""
        embed = self.create_embed(
            f"{SETTINGS_EMOJI} Suggestion System Configuration{owner_badge}",
            f"**Current settings for {interaction.guild.name}**",
            0x5865F2
        )

        # Status
        status = f"{SUCCESS_EMOJI} **Enabled**" if enabled else f"{ERROR_EMOJI} **Disabled**"
        embed.add_field(name="System Status", value=status, inline=True)

        # Channel
        channel_info = channel.mention if channel else f"❌ **Channel Deleted** (`{channel_id}`)"
        embed.add_field(name="Suggestion Channel", value=channel_info, inline=True)

        # Creator and date (only for admins)
        if is_admin:
            creator_info = creator.mention if creator else "**Unknown**"
            embed.add_field(name="Configured By", value=creator_info, inline=True)

            if created_at:
                try:
                    created_timestamp = datetime.datetime.fromisoformat(created_at)
                    embed.add_field(name="Set Up", value=f"<t:{int(created_timestamp.timestamp())}:R>", inline=True)
                except:
                    embed.add_field(name="Set Up", value="**Unknown**", inline=True)

        # Statistics
        total_suggestions = await self.suggestions_coll.count_documents({"guild_id": interaction.guild.id})
        accepted = await self.suggestions_coll.count_documents({"guild_id": interaction.guild.id, "status": "accepted"})
        declined = await self.suggestions_coll.count_documents({"guild_id": interaction.guild.id, "status": "declined"})

        embed.add_field(
            name=f"{LIST_EMOJI} Statistics",
            value=f"**Total:** {total_suggestions}\n**Accepted:** {accepted}\n**Declined:** {declined}\n**Pending:** {total_suggestions - accepted - declined}",
            inline=False
        )

        if self.is_bot_owner_check(interaction.user.id):
            embed.add_field(
                name=f"{BOT_OWNER_EMOJI} **Bot Owner Access**",
                value="You have elevated privileges in this server",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @suggest_group.command(name="accept", description="Accept a suggestion")
    @app_commands.describe(suggestion_id="The ID number of the suggestion to accept")
    async def suggest_accept(self, interaction: discord.Interaction, suggestion_id: int):
        """Accept a suggestion by ID"""
        if not await self.check_permissions(interaction, "manage_messages"):
            embed = self.create_embed(
                f"{ERROR_EMOJI} Access Denied",
                "You need **Manage Messages** permission or be the Bot Owner to use this command!",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        suggestion = await self.suggestions_coll.find_one({"suggestion_number": suggestion_id, "guild_id": interaction.guild.id})

        if not suggestion:
            embed = self.create_embed(
                f"{ERROR_EMOJI} Suggestion Not Found",
                f"No suggestion found with ID **#{suggestion_id:03d}** in this server.",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if suggestion["status"] != 'pending':  # status field
            embed = self.create_embed(
                f"{WARNING_EMOJI} Already Reviewed",
                f"Suggestion **#{suggestion_id:03d}** has already been **{suggestion['status']}**.",
                0xe67e22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Update database
        await self.update_suggestion_status(suggestion_id, interaction.guild.id, "accepted", interaction.user.id)

        # Try to update the original message
        try:
            channel_id = await self.get_suggestion_channel(interaction.guild.id)
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                message = await channel.fetch_message(suggestion[4])  # message_id
                embed = message.embeds[0]
                embed.color = 0x2ecc71
                embed.set_field_at(2, name="Status", value=f"{ACCEPT_EMOJI} **Accepted by {interaction.user.mention}**", inline=True)
                await message.edit(embed=embed, view=None)
        except:
            pass  # Message might be deleted or inaccessible

        owner_note = f" | {BOT_OWNER_EMOJI} Bot Owner Override" if self.is_bot_owner_check(interaction.user.id) else ""
        embed = self.create_embed(
            f"{ACCEPT_EMOJI} Suggestion Accepted!",
            f"Suggestion **#{suggestion_id:03d}** has been **accepted**{owner_note}.\n\n**Suggestion:** {suggestion['content'][:100]}{'...' if len(suggestion['content']) > 100 else ''}",
            0x2ecc71
        )
        await interaction.response.send_message(embed=embed)

    @suggest_group.command(name="decline", description="Decline a suggestion")
    @app_commands.describe(suggestion_id="The ID number of the suggestion to decline")
    async def suggest_decline(self, interaction: discord.Interaction, suggestion_id: int):
        """Decline a suggestion by ID"""
        if not await self.check_permissions(interaction, "manage_messages"):
            embed = self.create_embed(
                f"{ERROR_EMOJI} Access Denied",
                "You need **Manage Messages** permission or be the Bot Owner to use this command!",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        suggestion = await self.suggestions_coll.find_one({"suggestion_number": suggestion_id, "guild_id": interaction.guild.id})

        if not suggestion:
            embed = self.create_embed(
                f"{ERROR_EMOJI} Suggestion Not Found",
                f"No suggestion found with ID **#{suggestion_id:03d}** in this server.",
                0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if suggestion["status"] != 'pending':  # status field
            embed = self.create_embed(
                f"{WARNING_EMOJI} Already Reviewed",
                f"Suggestion **#{suggestion_id:03d}** has already been **{suggestion['status']}**.",
                0xe67e22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Update database
        await self.update_suggestion_status(suggestion_id, interaction.guild.id, "declined", interaction.user.id)

        # Try to update the original message
        try:
            channel_id = await self.get_suggestion_channel(interaction.guild.id)
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                message = await channel.fetch_message(suggestion[4])  # message_id
                embed = message.embeds[0]
                embed.color = 0xe74c3c
                embed.set_field_at(2, name="Status", value=f"{DECLINE_EMOJI} **Declined by {interaction.user.mention}**", inline=True)
                await message.edit(embed=embed, view=None)
        except:
            pass  # Message might be deleted or inaccessible

        owner_note = f" | {BOT_OWNER_EMOJI} Bot Owner Override" if self.is_bot_owner_check(interaction.user.id) else ""
        embed = self.create_embed(
            f"{DECLINE_EMOJI} Suggestion Declined",
            f"Suggestion **#{suggestion_id:03d}** has been **declined**{owner_note}.\n\n**Suggestion:** {suggestion['content'][:100]}{'...' if len(suggestion['content']) > 100 else ''}",
            0xe74c3c
        )
        await interaction.response.send_message(embed=embed)

    @suggest_group.command(name="approve", description="Approve a suggestion")
    @app_commands.describe(suggestion_id="The ID number of the suggestion to approve")
    async def suggest_approve(self, interaction: discord.Interaction, suggestion_id: int):
        """Approve a suggestion by ID (same as accept)"""
        # Just call the accept function
        await self.suggest_accept(interaction, suggestion_id)

    @suggest_group.command(name="reject", description="Reject a suggestion")
    @app_commands.describe(suggestion_id="The ID number of the suggestion to reject")
    async def suggest_reject(self, interaction: discord.Interaction, suggestion_id: int):
        """Reject a suggestion by ID (same as decline)"""
        # Just call the decline function
        await self.suggest_decline(interaction, suggestion_id)

    @suggest_group.command(name="view", description="View all suggestions")
    async def suggest_view(self, interaction: discord.Interaction):
        """View all suggestions with pagination"""
        cursor = self.suggestions_coll.find(
            {"guild_id": interaction.guild.id}
        ).sort("suggestion_number", -1).limit(10)
        
        suggestions = await cursor.to_list(length=10)

        if not suggestions:
            embed = self.create_embed(
                f"{INFO_EMOJI} No Suggestions",
                "No suggestions have been submitted yet in this server.\n\nUse `/suggestion message <content>` to submit the first one!",
                0xe67e22
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(interaction.user.id) else ""
        embed = self.create_embed(
            f"{VIEW_EMOJI} Recent Suggestions{owner_badge}",
            f"**Latest suggestions for {interaction.guild.name}**\n\n",
            0x5865F2
        )

        suggestion_list = []
        for doc in suggestions:
            number = doc["suggestion_number"]
            content = doc["content"]
            status = doc["status"]
            user_id = doc["user_id"]
            
            user = interaction.guild.get_member(user_id)
            username = user.display_name if user else "Unknown User"
            
            # Status emoji
            status_emoji = {
                'pending': LOADING_EMOJI,
                'accepted': ACCEPT_EMOJI,
                'declined': DECLINE_EMOJI
            }.get(status, "❓")
            
            # Truncate content
            truncated = content[:50] + "..." if len(content) > 50 else content
            
            suggestion_list.append(f"**#{number:03d}** {status_emoji} {truncated}\n*by {username}*")

        embed.description += "\n\n".join(suggestion_list)
        
        # Statistics
        total = await self.suggestions_coll.count_documents({"guild_id": interaction.guild.id})

        embed.add_field(
            name=f"{LIST_EMOJI} Statistics",
            value=f"Showing latest 10 of **{total}** total suggestions",
            inline=False
        )

        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else self.bot.user.avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    cog = Suggestion(bot)
    bot.tree.add_command(cog.suggest_group)
    await bot.add_cog(cog)
    
