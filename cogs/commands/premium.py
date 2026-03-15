import discord
from discord.ext import commands, tasks
import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union
import traceback
from utils.Tools import *
from db.premium_mongo import PremiumMongoDB
import pymongo
from math import ceil




class TierSelect(discord.ui.Select):
    def __init__(self, tiers):
        self.tiers = tiers
        options = [
            discord.SelectOption(
                label="Max Tier",
                description="The ultimate premium experience",
                emoji="<:max:1420708432910221364>",
                value="max"
            ),
            discord.SelectOption(
                label="Ultra Tier",
                description="Advanced features and support",
                emoji="<:ultra:1420708446973464608>",
                value="ultra"
            ),
            discord.SelectOption(
                label="Pro Tier",
                description="Professional grade features",
                emoji="<:pro:1420708458075787385>",
                value="pro"
            ),
            discord.SelectOption(
                label="Plus Tier",
                description="Enhanced functionality",
                emoji="<:plus:1420708468561674323>",
                value="plus"
            ),
            discord.SelectOption(
                label="Free Tier",
                description="Standard features access",
                emoji="<:free:1434493668043001989>",
                value="free"
            )
        ]
        super().__init__(
            placeholder="Select a tier to view benefits...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        tier_key = self.values[0]
        tier_info = self.tiers[tier_key]
        
        embed = discord.Embed(
            title=f"{tier_info['emoji']} {tier_info['name']} Tier Benefits",
            color=0xFFD700
        )
        
        # Format perks
        if tier_info['perks']:
            perks_text = "\n".join([f"> {perk}" for perk in tier_info['perks']])
            embed.add_field(
                name="✨ Benefits",
                value=perks_text,
                inline=False
            )
        
        embed.add_field(
            name="💰 Price",
            value=tier_info['price'],
            inline=True
        )
        
        if 'servers' in tier_info:
            embed.add_field(
                name="🌐 Server Slots",
                value=str(tier_info['servers']),
                inline=True
            )
        
        embed.set_footer(text="Scyro Premium")
        
        await interaction.response.edit_message(embed=embed)


class TierView(discord.ui.View):
    def __init__(self, tiers):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.add_item(TierSelect(tiers))


# Pagination Views for Premium Guilds and Users

class PremiumGuildPaginationView(discord.ui.View):
    def __init__(self, guilds_list, bot, premium_system, page=1, per_page=5):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.guilds_list = guilds_list
        self.bot = bot
        self.premium_system = premium_system
        self.page = page
        self.per_page = per_page
        self.total_pages = ceil(len(guilds_list) / per_page)
        
        # Add navigation buttons
        if self.total_pages > 1:
            self.add_item(PremiumGuildFirstPageButton())
            self.add_item(PremiumGuildPrevPageButton())
            self.add_item(PremiumGuildNextPageButton())
            self.add_item(PremiumGuildLastPageButton())
    
    async def update_embed(self, interaction: discord.Interaction):
        # Calculate start and end indices for current page
        start_idx = (self.page - 1) * self.per_page
        end_idx = start_idx + self.per_page
        page_guilds = self.guilds_list[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="🏢 Premium Guilds",
            description=f"Showing {len(self.guilds_list)} premium guilds - Page {self.page}/{self.total_pages}",
            color=0xFFD700
        )
        
        # Add guilds for current page
        for guild_doc in page_guilds:
            guild_id = guild_doc["guild_id"]
            user_id = guild_doc["user_id"]
            tier = guild_doc.get("tier", "plus")
            activated_at = guild_doc.get("activated_at", datetime.now().isoformat())
            
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"Unknown Guild ({guild_id})"
            
            user = self.bot.get_user(user_id) if user_id != 0 and user_id != self.premium_system.bot_owner_id else None
            user_mention = user.mention if user else ("Guild-wide Access" if user_id == 0 else "Bot Owner Activated")
            
            tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
            
            embed.add_field(
                name=f"{tier_info['emoji']} {guild_name}",
                value=(
                    f"**Guild ID:** `{guild_id}`\n"
                    f"**Owner/User:** {user_mention}\n"
                    f"**Tier:** {tier_info['name']}\n"
                    f"**Activated:** <t:{int(datetime.fromisoformat(activated_at).timestamp())}:R>"
                ),
                inline=False
            )
        
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} | Total Guilds: {len(self.guilds_list)}")
        
        # Update button disabled states
        for child in self.children:
            if isinstance(child, PremiumGuildFirstPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumGuildPrevPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumGuildNextPageButton):
                child.disabled = (self.page == self.total_pages)
            elif isinstance(child, PremiumGuildLastPageButton):
                child.disabled = (self.page == self.total_pages)
        
        await interaction.response.edit_message(embed=embed, view=self)


class PremiumGuildFirstPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="<< First",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_first_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page != 1:
            view.page = 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumGuildPrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="< Prev",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_prev_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page > 1:
            view.page -= 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumGuildNextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next >",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_next_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page < view.total_pages:
            view.page += 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumGuildLastPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Last >>",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_last_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page != view.total_pages:
            view.page = view.total_pages
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserPaginationView(discord.ui.View):
    def __init__(self, users_list, bot, premium_system, page=1, per_page=5):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.users_list = users_list
        self.bot = bot
        self.premium_system = premium_system
        self.page = page
        self.per_page = per_page
        self.total_pages = ceil(len(users_list) / per_page)
        
        # Add navigation buttons
        if self.total_pages > 1:
            self.add_item(PremiumUserFirstPageButton())
            self.add_item(PremiumUserPrevPageButton())
            self.add_item(PremiumUserNextPageButton())
            self.add_item(PremiumUserLastPageButton())
    
    async def update_embed(self, interaction: discord.Interaction):
        # Calculate start and end indices for current page
        start_idx = (self.page - 1) * self.per_page
        end_idx = start_idx + self.per_page
        page_users = self.users_list[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="👥 Premium Users",
            description=f"Showing {len(self.users_list)} premium users - Page {self.page}/{self.total_pages}",
            color=0xFFD700
        )
        
        # Add users for current page
        db = await self.premium_system.mongo_db.ensure_connection()
        for user_doc in page_users:
            user_id = user_doc["user_id"]
            tier = user_doc["tier"]
            expires_at = user_doc["expires_at"]
            created_at = user_doc["created_at"]
            
            user = self.bot.get_user(user_id)
            user_mention = user.mention if user else f"Unknown User ({user_id})"
            tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
            
            # Get guild count for this user
            guild_count = await db.premium_guilds.count_documents({"user_id": user_id})
            max_servers = tier_info.get('servers', 0)
            
            embed.add_field(
                name=f"{tier_info['emoji']} {user_mention}",
                value=(
                    f"**User ID:** `{user_id}`\n"
                    f"**Tier:** {tier_info['name']}\n"
                    f"**Servers:** {guild_count}/{max_servers}\n"
                    f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>\n"
                    f"**Started:** <t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                ),
                inline=False
            )
        
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} | Total Users: {len(self.users_list)}")
        
        # Update button disabled states
        for child in self.children:
            if isinstance(child, PremiumUserFirstPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumUserPrevPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumUserNextPageButton):
                child.disabled = (self.page == self.total_pages)
            elif isinstance(child, PremiumUserLastPageButton):
                child.disabled = (self.page == self.total_pages)
        
        await interaction.response.edit_message(embed=embed, view=self)


class PremiumUserFirstPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="<< First",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_first_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page != 1:
            view.page = 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserPrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="< Prev",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_prev_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page > 1:
            view.page -= 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserNextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next >",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_next_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page < view.total_pages:
            view.page += 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserLastPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Last >>",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_last_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page != view.total_pages:
            view.page = view.total_pages
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumSystem:
    def __init__(self):
        # NOTE: Using MongoDB for centralized premium tracking
        # This ensures consistent premium tracking across all shards
        self.mongo_db = PremiumMongoDB()
        self.bot_owner_id = 1218037361926209640
        self.premium_cogs = ['customrole', 'nightmode', 'notify', 'customprofile']  # Cogs that require premium
        
        # Log channels from environment variables
        self.premium_activation_log_channel = int(os.environ.get('PREMIUM_ACTIVATION_LOG_CHANNEL', '1434547477863989418'))
        self.premium_expiration_log_channel = int(os.environ.get('PREMIUM_EXPIRATION_LOG_CHANNEL', '1434547509799162000'))
        self.premium_use_log_channel = int(os.environ.get('PREMIUM_USE_LOG_CHANNEL', '1419276599894999144'))
        # Add slot fill log channel from environment variables
        self.slot_fill_log_channel = int(os.environ.get('SLOT_FILL_LOG_CHANNEL', '1434543481182884001'))
        
        # Premium tiers configuration with updated server limits and perks
        self.tiers = {
            'max': {
                'servers': 50, 
                'emoji': '<:max:1420708432910221364>', 
                'name': 'Max',
                'price': '₹1,199 ($14.99)/month',
                'perks': [
                    '**Access to No Prefix**',
                    '**VIP Support**',
                    '**All Premium Commands in this Tier:**',
                    '**Access to Premium Commands**',
                    '**Dedicated Resources**',
                    '**Custom Features**',
                    '**50 Guild Slots**',
                    '**Advanced Antinuke**',
                    '**Advanced Automod**'
                ]
            },
            'ultra': {
                'servers': 25, 
                'emoji': '<:ultra:1420708446973464608>', 
                'name': 'Ultra',
                'price': '₹699 ($8.99)/month', 
                'perks': [
                    '**Access to No Prefix**',
                    '**VIP Support**',
                    '**All Premium Commands in this Tier:**',
                    '**Access to Premium Commands**',
                    '**25 Guild Slots**',
                    '**Better Performance**',
                    '**Advanced Antinuke**',
                    '**Advanced Automod**',
                    '**Custom bot Branding**'
                ]
            },
            'pro': {
                'servers': 10, 
                'emoji': '<:pro:1420708458075787385>', 
                'name': 'Pro',
                'price': '₹399 ($4.99)/month',
                'perks': [
                    '**Access to No Prefix**',
                    '**Priority Support**',
                    '**Low Latency**',
                    '**All Premium Commands in this Tier:**',
                    '**Access to Premium Commands**',
                    '**10 Guild Slots**',
                    '**Better Antinuke**',
                    '**Better Automod**',
                    '**Custom bot Branding**'
                ]
            },
            'plus': {
                'servers': 5, 
                'emoji': '<:plus:1420708468561674323>', 
                'name': 'Plus',
                'price': '₹249 ($2.99)/month',
                'perks': [
                    '**Access to No Prefix**',
                    '**Priority Support**',
                    '**Low Latency**',
                    '**All Premium Commands in this Tier:**',
                    '**Access to Premium Commands**',
                    '**5 Guild Slots**',
                    '**Better Antinuke**',
                    '**Better Automod**',
                    '**Custom bot Branding**'
                ]
            },
            'free': {
                'servers': 0,
                'emoji': '<:free:1434493668043001989>',
                'name': 'Free',
                'price': '₹0 ($0)/month',
                'perks': [
                    '**Access to all Standard Features and Commands of Scyro**'
                ]
            }
        }
        
        # Premium cog tiers - maps cogs to required tiers (all tiers get access to all cogs)
        self.premium_cog_tiers = {
            'max': ['customrole', 'nightmode', 'notify', 'customprofile'],  # Max gets early access to new commands
            'ultra': ['customrole', 'nightmode', 'notify', 'customprofile'],
            'pro': ['customrole', 'nightmode', 'notify', 'customprofile'], 
            'plus': ['customrole', 'nightmode', 'notify', 'customprofile']  # All cogs available at Plus level
        }
    
    async def init_db(self):
        """Initialize premium database connection"""
        # MongoDB connection is initialized on first use
        pass
    
    async def check_user_premium(self, user_id: int, guild_id: Optional[int] = None):
        """Check if user has premium and optionally if they can use it in a guild"""
        return await self.mongo_db.check_user_premium(user_id, guild_id)
    
    async def grant_premium(self, user_id: int, tier: str, days: int = 30):
        """Grant premium to a user"""
        return await self.mongo_db.grant_premium(user_id, tier, days)
    
    async def revoke_premium(self, user_id: int):
        """Remove premium from a user"""
        return await self.mongo_db.revoke_premium(user_id)
    
    async def extend_premium(self, user_id: int, days: int):
        """Extend user's premium subscription"""
        return await self.mongo_db.extend_premium(user_id, days)


class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.premium_system = PremiumSystem()
        self.bot.loop.create_task(self.initialize())
        
        # Add a global check that will block premium commands
        self.bot.add_check(self.global_premium_check)
    
    async def global_premium_check(self, ctx):
        """Global check that blocks premium commands for non-premium users"""
        # Bot owner bypasses all checks
        if ctx.author.id == self.premium_system.bot_owner_id:
            return True
            
        # Skip DM commands and premium management commands
        if not ctx.guild or not ctx.command:
            return True
            
        # Allow premium management and public commands
        if ctx.command.qualified_name.startswith(('premium', 'perks')) or ctx.command.name == 'perks':
            return True
        
        # Check if this command's cog requires premium
        if ctx.command.cog:
            cog_name = ctx.command.cog.__class__.__name__.lower()
            
            # Map cog class names to premium cog names
            cog_mapping = {
                'customrole': 'customrole',
                'nightmode': 'nightmode',
                'notify': 'notify'
            }
            
            mapped_cog = cog_mapping.get(cog_name, cog_name)
            
            if mapped_cog in self.premium_system.premium_cogs:
                # Check if user has premium access for this guild
                has_premium, tier = await self.premium_system.check_user_premium(ctx.author.id, ctx.guild.id)
                
                # If user doesn't have personal premium, check for guild-wide premium
                if not has_premium:
                    # Check if the guild has been granted premium access for all members
                    db = await self.premium_system.mongo_db.ensure_connection()
                    guild_premium = None
                    if db is not None:
                        # Using MongoDB
                        guild_premium = await self.premium_system.mongo_db.premium_guilds.find_one({
                            "guild_id": ctx.guild.id,
                            "$or": [
                                {"user_id": 0},  # Special marker for guild-wide premium
                                {"user_id": self.premium_system.bot_owner_id}  # Bot owner activated premium
                            ]
                        })
                    
                    # If guild has premium access, allow the command
                    if guild_premium:
                        return True
                
                if not has_premium:
                    # Check if user has premium but not activated in this guild
                    # Use MongoDB to check user data
                    has_premium_check, tier_name = await self.premium_system.mongo_db.check_user_premium(ctx.author.id, None)
                    if has_premium_check:
                        # User has premium but not activated in this guild
                        # Show confirmation embed
                        # Get user's actual data using the proper method
                        try:
                            db = await self.premium_system.mongo_db.ensure_connection()
                            if db is not None:
                                # Using MongoDB
                                user_info = await self.premium_system.mongo_db.premium_users.find_one({"user_id": ctx.author.id})
                            else:
                                user_info = None
                        except Exception as e:
                            traceback.print_exc()
                            user_info = None
                        
                        if user_info:
                            tier_name = user_info.get("tier", "plus")
                            expires_at = user_info.get("expires_at")
                            tier_info = self.premium_system.tiers[tier_name]
                            
                            embed = discord.Embed(
                                title="<:ogstar:1420709631663013928> Premium Slot Required",
                                description=f"You have **{tier_info['name']}** premium, but it's not activated in this server.\n\nPlease use the `.premium use` command to activate your premium slot in this server.",
                                color=0xFFD700
                            )
                            
                            embed.add_field(
                                name="📊 Your Premium Info",
                                value=(
                                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                    f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                                ),
                                inline=False
                            )
                            
                            embed.add_field(
                                name="💡 How to Activate",
                                value="Use the command: `.premium use` in this server to activate your premium slot.",
                                inline=False
                            )
                            
                            embed.set_footer(text="Premium slot required for premium commands")
                            
                            try:
                                if hasattr(ctx, 'interaction') and ctx.interaction:
                                    if not ctx.interaction.response.is_done():
                                        await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                                    else:
                                        await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                                else:
                                    await ctx.send(embed=embed)
                            except:
                                try:
                                    await ctx.send(embed=embed)
                                except:
                                    pass
                            
                            # Reset cooldown
                            if hasattr(ctx.command, 'reset_cooldown'):
                                ctx.command.reset_cooldown(ctx)
                            
                            # Block execution by returning False
                            return False
                    else:
                        # User doesn't have premium at all
                        # Send custom premium message and block execution
                        embed = discord.Embed(
                            title="<:ogstar:1420709631663013928> Premium Feature Required",
                            description="You just found a premium feature! Please consider buying a rank from https://scyro.xyz/premium",
                            color=0xFFD700
                        )
                        
                        embed.add_field(
                            name="<:premium:1409162823862325248> Premium Benefits",
                            value=(
                                "> <a:dot:1396429135588626442> Access to exclusive commands\n"
                                "> <a:dot:1396429135588626442> Advanced features\n"
                                "> <a:dot:1396429135588626442> Priority support\n"
                                "> <a:dot:1396429135588626442> No Prefix Access\n"
                                "> <a:dot:1396429135588626442> Vip Support\n"
                                "> <a:dot:1396429135588626442> Early Commands Access\n"
                                "> <a:dot:1396429135588626442> Support bot development"
                            ),
                            inline=False
                        )
                        
                        embed.set_footer(text=f"Required for: {mapped_cog}")
                        
                        try:
                            if hasattr(ctx, 'interaction') and ctx.interaction:
                                if not ctx.interaction.response.is_done():
                                    await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                                else:
                                    await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                            else:
                                await ctx.send(embed=embed)
                        except:
                            try:
                                await ctx.send(embed=embed)
                            except:
                                pass
                        
                        # Reset cooldown
                        if hasattr(ctx.command, 'reset_cooldown'):
                            ctx.command.reset_cooldown(ctx)
                        
                        # Block execution by returning False
                        return False
        
        # Allow all other commands
        return True
    
    async def initialize(self):
        """Initialize the premium system"""
        await self.premium_system.init_db()
        self.cleanup_expired.start()
        print("✅ Premium system initialized")
    
    @tasks.loop(hours=6)  # Check every 6 hours
    async def cleanup_expired(self):
        """Clean up expired premium subscriptions"""
        try:
            # Use the proper MongoDB connection
            db = await self.premium_system.mongo_db.ensure_connection()
            current_time = datetime.now().isoformat()
            
            if db is not None:
                # Using MongoDB
                # Get expired users
                expired_users = []
                async for user in self.premium_system.mongo_db.premium_users.find({"expires_at": {"$lte": current_time}}):
                    expired_users.append(user)
                
                # Remove expired premiums
                await self.premium_system.mongo_db.premium_users.delete_many({"expires_at": {"$lte": current_time}})
                # Remove guild access for expired users
                expired_user_ids = [user["user_id"] for user in expired_users]
                if expired_user_ids:
                    await self.premium_system.mongo_db.premium_guilds.delete_many({"user_id": {"$in": expired_user_ids}})
            
            # Log expired users to the expiration log channel
            if expired_users:
                log_channel = self.bot.get_channel(self.premium_system.premium_expiration_log_channel)
                if log_channel:
                    for user_data in expired_users:
                        user_id = user_data["user_id"]
                        tier = user_data.get("tier", "Unknown")
                        expires_at = user_data.get("expires_at", "Unknown")
                        tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
                        
                        # Try to get the user object
                        user = self.bot.get_user(user_id)
                        user_mention = user.mention if user else f"<@{user_id}>"
                        
                        log_embed = discord.Embed(
                            title="📝 Premium Subscription Expired",
                            description=f"User {user_mention}'s premium subscription has automatically expired",
                            color=0xFF0000
                        )
                        log_embed.add_field(
                            name="📊 Details",
                            value=(
                                f"**User:** {user_mention} (`{user_id}`)\n"
                                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                f"**Expired:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                            ),
                            inline=False
                        )
                        await log_channel.send(embed=log_embed)
                
                print(f"🧹 Cleaned up {len(expired_users)} expired premium subscriptions")
                
        except Exception as e:
            print(f"❌ Error cleaning expired premiums: {e}")
    # The global check handles premium restrictions for all cogs
    
    # The global check handles all premium restrictions
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle premium-related command errors silently"""
        if isinstance(error, commands.CheckFailure):
            if "Premium access required" in str(error) or "check functions" in str(error):
                # This is our premium check failure, handle it silently
                # The error message was already sent in the global check
                return
        
        if isinstance(error, commands.CommandNotFound):
            # Silently ignore command not found errors to reduce noise
            return
        
        # Re-raise other errors to be handled by the bot's error handler
        # Comment out the raise to completely silence all errors in this cog
        # raise error

    # Public commands
    @commands.hybrid_command(name="perks", description="View premium tier benefits")
    @blacklist_check()
    @ignore_check()
    async def premium_perks(self, ctx):
        """View all premium tier perks and benefits with interactive dropdown"""
        embed = discord.Embed(
            title="<:ogstar:1420709631663013928> Scyro Premium Perks",
            description="Explore our premium tiers and their amazing benefits! Select a tier from the dropdown below to view detailed information.",
            color=0xFFD700
        )
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        
        # Add a brief overview of all tiers
        tier_overview = []
        for tier_key, tier_info in self.premium_system.tiers.items():
            if tier_key != 'free':  # Don't show free tier in overview
                tier_overview.append(f"{tier_info['emoji']} **{tier_info['name']}** - {tier_info['price']}")
        
        embed.add_field(
            name="🌟 Available Tiers",
            value="\n".join(tier_overview),
            inline=False
        )
        
        embed.add_field(
            name="✨ Premium Benefits",
            value=(
                "> <a:dot:1396429135588626442> **Exclusive Commands Access**\n"
                "> <a:dot:1396429135588626442> **Priority Support**\n"
                "> <a:dot:1396429135588626442> **No Prefix Feature**\n"
                "> <a:dot:1396429135588626442> **Multiple Server Usage**\n"
                "> <a:dot:1396429135588626442> **Advanced Features**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="<:shopping:1397875313471655936> Get Premium",
            value="Contact the Bot Owner or Join [Support Server](https://dsc.gg/scyrogg) to purchase Premium access!",
            inline=False
        )
        
        embed.set_footer(text="Select a tier from the dropdown to view detailed benefits")
        
        view = TierView(self.premium_system.tiers, self.premium_system.premium_cogs)
        await ctx.send(embed=embed, view=view)

    # Bot owner commands
    @commands.group(name="premium", aliases=['pm'], invoke_without_command=True)
    async def premium(self, ctx):
        """Premium management system (Bot Owner Only)"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            embed = discord.Embed(
                title="Try out These!",
                description="- `/perks` or `.perks` to view premium benefits and tiers\n- `.premium guilds` - List guilds where you've used your premium slots\n- `.premium info` - Show subscription information\n- `.premium use` - Use a guild slot to activate premium in server",
                color=0xFFD700
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🌟 Premium Management System",
            description="Manage premium features and access",
            color=0xFFD700
        )
        
        embed.add_field(
            name="📊 Available Tiers",
            value="\n".join([
                f"{info['emoji']} **{info['name']}** - {info['servers']} servers ({info['price']})"
                for info in self.premium_system.tiers.values()
            ]),
            inline=False
        )
        
        embed.add_field(
            name="⚡ Commands",
            value=(
                "• `premium active <user/guild> <tier> [days]` - Grant premium\n"
                "• `premium deactive <user/guild>` - Remove premium\n" 
                "• `premium status [user/guild]` - Check premium status\n"
                "• `premium extend <user/guild> <days>` - Extend subscription\n"
                "• `premium cogs add <tier> <cog_name>` - Add cog to tier\n"
                "• `premium cogs remove <tier> <cog_name>` - Remove cog from tier\n"
                "• `premium cogs list [tier]` - List cogs by tier\n\n"
                "**Bot Owner Commands:**\n"
                "• `,fillslot <user> <slots>` - Fill premium slots for a user\n"
                "• `,slotcheck <user>` - Check all slots for a user\n"
                "• `.premiumusers` - Show all premium users with tier and expiration\n\n"
                "**User Commands:**\n"
                "• `/perks` or `.perks` - View premium tier benefits\n"
                "• `/premium guilds` - List guilds where you've used your premium slots\n"
                "• `/premium info` - Show subscription information\n"
                "• `/premium use` - Use a guild slot to activate premium in server"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔒 Premium Cogs",
            value=", ".join(self.premium_system.premium_cogs),
            inline=False
        )
        
        await ctx.send(embed=embed)

    @premium.group(name="cogs", invoke_without_command=True)
    async def premium_cogs(self, ctx):
        """Manage premium cogs and their tier assignments"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        embed = discord.Embed(
            title="🔧 Premium Cogs Management",
            description="Manage which cogs require premium access",
            color=0xFFD700
        )
        
        # Show current premium cogs
        if self.premium_system.premium_cogs:
            embed.add_field(
                name="🔒 Current Premium Cogs",
                value="\n".join([f"• {cog}" for cog in self.premium_system.premium_cogs]),
                inline=False
            )
        else:
            embed.add_field(
                name="🔒 Current Premium Cogs",
                value="No premium cogs configured",
                inline=False
            )
        
        embed.add_field(
            name="⚡ Available Commands",
            value=(
                "• `premium cogs add <tier> <cog_name>` - Add cog to premium\n"
                "• `premium cogs remove <tier> <cog_name>` - Remove cog from premium\n"
                "• `premium cogs list [tier]` - List premium cogs\n\n"
                "**Available Tiers:** plus, pro, ultra, max"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @premium_cogs.command(name="add")
    async def premium_cogs_add(self, ctx, tier: str, cog_name: str):
        """Add a cog to a premium tier"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        # Validate tier
        valid_tiers = ['plus', 'pro', 'ultra', 'max']
        if tier.lower() not in valid_tiers:
            embed = discord.Embed(
                title="❌ Invalid Tier",
                description=f"Valid tiers: {', '.join(valid_tiers)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        # Add to premium cogs list if not already there
        if cog_name.lower() not in self.premium_system.premium_cogs:
            self.premium_system.premium_cogs.append(cog_name.lower())
        
        # Add to tier mapping
        if tier.lower() not in self.premium_system.premium_cog_tiers:
            self.premium_system.premium_cog_tiers[tier.lower()] = []
        
        if cog_name.lower() not in self.premium_system.premium_cog_tiers[tier.lower()]:
            self.premium_system.premium_cog_tiers[tier.lower()].append(cog_name.lower())
        
        embed = discord.Embed(
            title="✅ Cog Added to Premium",
            description=f"Successfully added `{cog_name}` to **{tier.title()}** tier",
            color=0x00FF00
        )
        embed.add_field(
            name="📊 Current Premium Cogs",
            value="\n".join([f"• {cog}" for cog in self.premium_system.premium_cogs]),
            inline=False
        )
        await ctx.send(embed=embed)
    
    @premium_cogs.command(name="remove")
    async def premium_cogs_remove(self, ctx, tier: str, cog_name: str):
        """Remove a cog from a premium tier"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        # Remove from tier mapping
        if tier.lower() in self.premium_system.premium_cog_tiers:
            if cog_name.lower() in self.premium_system.premium_cog_tiers[tier.lower()]:
                self.premium_system.premium_cog_tiers[tier.lower()].remove(cog_name.lower())
        
        # Check if cog is in any other tiers, if not, remove from premium_cogs
        cog_in_other_tiers = any(
            cog_name.lower() in cogs 
            for tier_name, cogs in self.premium_system.premium_cog_tiers.items()
            if tier_name != tier.lower()
        )
        
        if not cog_in_other_tiers and cog_name.lower() in self.premium_system.premium_cogs:
            self.premium_system.premium_cogs.remove(cog_name.lower())
        
        embed = discord.Embed(
            title="✅ Cog Removed from Premium",
            description=f"Successfully removed `{cog_name}` from **{tier.title()}** tier",
            color=0x00FF00
        )
        embed.add_field(
            name="📊 Current Premium Cogs",
            value="\n".join([f"• {cog}" for cog in self.premium_system.premium_cogs]) if self.premium_system.premium_cogs else "No premium cogs configured",
            inline=False
        )
        await ctx.send(embed=embed)
    
    @premium_cogs.command(name="list")
    async def premium_cogs_list(self, ctx, tier: Optional[str] = None):
        """List premium cogs by tier"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        if tier:
            # Show specific tier
            if tier.lower() in self.premium_system.premium_cog_tiers:
                cogs = self.premium_system.premium_cog_tiers[tier.lower()]
                embed = discord.Embed(
                    title=f"🔒 {tier.title()} Tier Premium Cogs",
                    description="\n".join([f"• {cog}" for cog in cogs]) if cogs else "No cogs in this tier",
                    color=0xFFD700
                )
            else:
                embed = discord.Embed(
                    title="❌ Invalid Tier",
                    description="Valid tiers: plus, pro, ultra, max",
                    color=0xFF0000
                )
        else:
            # Show all tiers
            embed = discord.Embed(
                title="🔒 Premium Cogs by Tier",
                description="Premium cog assignments across all tiers",
                color=0xFFD700
            )
            
            for tier_name, cogs in self.premium_system.premium_cog_tiers.items():
                embed.add_field(
                    name=f"🏅 {tier_name.title()} Tier",
                    value="\n".join([f"• {cog}" for cog in cogs]) if cogs else "No cogs",
                    inline=True
                )
        
        await ctx.send(embed=embed)
    
    async def parse_target(self, ctx, target: Optional[str]):
        """Parse target as either user mention/ID or guild ID"""
        # Default to current guild if no target provided
        if target is None:
            if ctx.guild:
                return "guild", ctx.guild.id, ctx.guild
            else:
                return None, None, None
        
        # Try to parse as guild ID first
        if target.isdigit():
            guild_id = int(target)
            guild = self.bot.get_guild(guild_id)
            if guild:
                return "guild", guild_id, guild
        
        # Try to parse as user
        try:
            user = await commands.UserConverter().convert(ctx, target)
            return "user", user.id, user
        except:
            pass
        
        return None, None, None
    
    @premium.command(name="active")
    async def premium_active(self, ctx, target: Optional[str] = None, tier: Optional[str] = None, days: Optional[int] = 30):
        """Grant premium access to a user or guild"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        if tier is None or tier.lower() not in self.premium_system.tiers:
            valid_tiers = ", ".join([t for t in self.premium_system.tiers.keys() if t != 'free'])
            embed = discord.Embed(
                title="❌ Invalid Tier",
                description=f"Please provide a valid tier: {valid_tiers}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        tier = tier.lower()
        
        if target is None:
            target_type = "guild"
            target_id = ctx.guild.id if ctx.guild else None
            target_obj = ctx.guild
        else:
            target_type, target_id, target_obj = await self.parse_target(ctx, target)
        
        if target_type is None or target_id is None:
            embed = discord.Embed(
                title="❌ Invalid Target",
                description="Please provide a valid user mention/ID or guild ID, or use in a guild.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            embed = None  # Initialize embed variable
            if target_type == "user":
                user = target_obj
                if user is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="User not found.",
                        color=0xFF0000
                    )
                else:
                    success = await self.premium_system.grant_premium(user.id, tier, days)
                    
                    if success:
                        tier_info = self.premium_system.tiers[tier]
                        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
                        embed = discord.Embed(
                            title="✅ Premium Activated",
                            description=f"Successfully granted **{tier_info['name']}** premium to {user.mention}",
                            color=0x00FF00
                        )
                        
                        # Log to premium log channel
                        log_channel = self.bot.get_channel(self.premium_system.premium_activation_log_channel)
                        if log_channel:
                            log_embed = discord.Embed(
                                title="📝 Premium Activated",
                                description=f"Bot owner {ctx.author.mention} granted **{tier_info['name']}** premium to user {user.mention}",
                                color=0x00FF00
                            )
                            log_embed.add_field(
                                name="📊 Details",
                                value=(
                                    f"**User:** {user} (`{user.id}`)\n"
                                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                    f"**Duration:** {days} days\n"
                                    f"**Expires:** <t:{int((datetime.now() + timedelta(days=days)).timestamp())}:F>"
                                ),
                                inline=False
                            )
                            await log_channel.send(embed=log_embed)
                        
                        # Try to send DM to user
                        try:
                            dm_embed = discord.Embed(
                                title="🎉 Premium Activated!",
                                description=f"You've been granted **{tier_info['name']}** premium access!\n[Join Us](https://dsc.gg/scyrogg) if you are having any issue!",
                                color=0x00FF00
                            )
                            await user.send(embed=dm_embed)
                        except:
                            pass
                    else:
                        embed = discord.Embed(
                            title="❌ Error",
                            description="Failed to grant premium access.",
                            color=0xFF0000
                        )
            
            elif target_type == "guild":
                guild = target_obj
                if guild is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Guild not found.",
                        color=0xFF0000
                    )
                else:
                    # For guild activation, create a special guild-wide premium entry
                    # This enables ALL members in the guild to use premium features
                    
                    # First ensure the guild owner has premium access
                    success = await self.premium_system.grant_premium(self.premium_system.bot_owner_id, tier, days)
                    
                    if success:
                        # Add the guild directly to premium_guilds for guild-wide access
                        # Use proper database access with availability check
                        db_conn = await self.premium_system.mongo_db.ensure_connection()
                        if db_conn is not None and self.premium_system.mongo_db.mongo_available:
                            # Using MongoDB
                            await self.premium_system.mongo_db.premium_guilds.update_one(
                                {"user_id": 0, "guild_id": guild.id},
                                {
                                    "$set": {
                                        "user_id": 0,
                                        "guild_id": guild.id,
                                        "tier": tier,
                                        "activated_at": datetime.now().isoformat()
                                    }
                                },
                                upsert=True
                            )
                        else:
                            # Using SQLite
                            async with aiosqlite.connect(self.premium_system.mongo_db.db_path) as sqlite_db:
                                await sqlite_db.execute(
                                    '''INSERT OR REPLACE INTO premium_guilds 
                                       (user_id, guild_id, tier, activated_at) 
                                       VALUES (?, ?, ?, ?)''',
                                    (0, guild.id, tier, datetime.now().isoformat())
                                )
                                await sqlite_db.commit()
                        
                        tier_info = self.premium_system.tiers[tier]
                        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
                        embed = discord.Embed(
                            title="✅ Guild-Wide Premium Activated",
                            description=f"Successfully granted **{tier_info['name']}** premium to **{guild.name}** (all members)",
                            color=0x00FF00
                        )
                        
                        # Log to premium log channel
                        log_channel = self.bot.get_channel(self.premium_system.premium_activation_log_channel)
                        if log_channel:
                            log_embed = discord.Embed(
                                title="📝 Guild Premium Activated",
                                description=f"Bot owner {ctx.author.mention} granted **{tier_info['name']}** premium to guild **{guild.name}**",
                                color=0x00FF00
                            )
                            log_embed.add_field(
                                name="📊 Details",
                                value=(
                                    f"**Guild:** {guild.name} (`{guild.id}`)\n"
                                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                    f"**Duration:** {days} days\n"
                                    f"**Access:** Guild-wide (all members)\n"
                                    f"**Expires:** <t:{int((datetime.now() + timedelta(days=days)).timestamp())}:F>"
                                ),
                                inline=False
                            )
                            await log_channel.send(embed=log_embed)
                    else:
                        embed = discord.Embed(
                            title="❌ Error",
                            description="Failed to activate guild premium.",
                            color=0xFF0000
                        )
            
            if embed is not None:
                await ctx.send(embed=embed)
            else:
                # Fallback error message
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred.",
                    color=0xFF0000
                )
                await ctx.send(embed=error_embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Database Error",
                description=f"Failed to grant premium: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @premium.command(name="deactive")
    async def premium_deactive(self, ctx, target: Optional[str] = None):
        """Remove premium access from a user or guild"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        if target is None:
            target_type = "guild"
            target_id = ctx.guild.id if ctx.guild else None
            target_obj = ctx.guild
        else:
            target_type, target_id, target_obj = await self.parse_target(ctx, target)
        
        if target_type is None or target_id is None:
            embed = discord.Embed(
                title="❌ Invalid Target",
                description="Please provide a valid user mention/ID or guild ID, or use in a guild.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            embed = None  # Initialize embed variable
            if target_type == "user":
                user = target_obj
                if user is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="User not found.",
                        color=0xFF0000
                    )
                else:
                    # Get user's premium info before revoking using MongoDB
                    db = await self.premium_system.mongo_db.ensure_connection()
                    user_data = await db.premium_users.find_one({"user_id": user.id})
                    
                    await self.premium_system.revoke_premium(user.id)
                    
                    embed = discord.Embed(
                        title="✅ Premium Deactivated",
                        description=f"Successfully removed premium access from {user.mention}",
                        color=0x00FF00
                    )
                    
                    # Send log to expiration channel
                    log_channel = self.bot.get_channel(self.premium_system.premium_expiration_log_channel)
                    if log_channel and user_data:
                        tier = user_data.get("tier")
                        expires_at = user_data.get("expires_at")
                        tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
                        log_embed = discord.Embed(
                            title="📝 Premium Deactivated",
                            description=f"Bot owner {ctx.author.mention} forcefully removed premium access from {user.mention}",
                            color=0xFF0000
                        )
                        log_embed.add_field(
                            name="📊 Details",
                            value=(
                                f"**User:** {user.mention} (`{user.id}`)\n"
                                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                            ),
                            inline=False
                        )
                        await log_channel.send(embed=log_embed)
                    
                    # Send DM to user
                    try:
                        dm_embed = discord.Embed(
                            title="🔔 Premium Deactivated",
                            description="Your premium access has been forcefully removed by the bot owner.",
                            color=0xFF0000
                        )
                        await user.send(embed=dm_embed)
                    except:
                        pass
            
            elif target_type == "guild":
                guild = target_obj
                if guild is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Guild not found.",
                        color=0xFF0000
                    )
                else:
                    # Get guild's premium info before removing using MongoDB
                    db = await self.premium_system.mongo_db.ensure_connection()
                    guild_data = await db.premium_guilds.find_one({"guild_id": guild.id})
                    
                    # Remove guild from premium access
                    await db.premium_guilds.delete_one({"guild_id": guild.id})
                    
                    embed = discord.Embed(
                        title="✅ Guild Premium Deactivated",
                        description=f"Successfully removed premium access from **{guild.name}**",
                        color=0x00FF00
                    )
                    
                    # Send log to expiration channel
                    log_channel = self.bot.get_channel(self.premium_system.premium_expiration_log_channel)
                    if log_channel and guild_data:
                        user_id = guild_data.get("user_id")
                        tier = guild_data.get("tier")
                        tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
                        
                        # Determine access type for logging
                        access_type = "Guild-wide (all members)" if user_id == 0 else "Bot owner activated"
                        
                        log_embed = discord.Embed(
                            title="📝 Guild Premium Deactivated",
                            description=f"Bot owner {ctx.author.mention} forcefully removed premium access from guild **{guild.name}**",
                            color=0xFF0000
                        )
                        log_embed.add_field(
                            name="📊 Details",
                            value=(
                                f"**Guild:** {guild.name} (`{guild.id}`)\n"
                                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                f"**Access Type:** {access_type}\n"
                                f"**Premium Owner:** <@{user_id}> (`{user_id}`)"
                            ),
                            inline=False
                        )
                        await log_channel.send(embed=log_embed)
            
            if embed is not None:
                await ctx.send(embed=embed)
            else:
                # Fallback error message
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred.",
                    color=0xFF0000
                )
                await ctx.send(embed=error_embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Database Error",
                description=f"Failed to remove premium: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @premium.command(name="status")
    async def premium_status(self, ctx, target: Optional[str] = None):
        """Check premium status of a user or guild"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        if target is None:
            # Default to command author
            target_type = "user"
            target_id = ctx.author.id
            target_obj = ctx.author
        else:
            target_type, target_id, target_obj = await self.parse_target(ctx, target)
        
        if target_type is None or target_id is None:
            embed = discord.Embed(
                title="❌ Invalid Target",
                description="Please provide a valid user mention/ID or guild ID.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            embed = None  # Initialize embed variable
            if target_type == "user":
                user = target_obj
                if user is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="User not found.",
                        color=0xFF0000
                    )
                else:
                    # Get user premium info using MongoDB
                    db = await self.premium_system.mongo_db.ensure_connection()
                    user_data = await db.premium_users.find_one({"user_id": user.id})
                    
                    if not user_data:
                        embed = discord.Embed(
                            title="❌ No Premium Access",
                            description=f"{user.mention} doesn't have premium access",
                            color=0xFF0000
                        )
                    else:
                        tier = user_data.get("tier")
                        expires_at = user_data.get("expires_at")
                        created_at = user_data.get("created_at")
                        tier_info = self.premium_system.tiers[tier]
                        
                        # Get guild count
                        guild_count = await db.premium_guilds.count_documents({"user_id": user.id})
                        
                        embed = discord.Embed(
                            title="✅ Premium Status",
                            description=f"Premium information for {user.mention}",
                            color=0x00FF00
                        )
                        
                        embed.add_field(
                            name="📊 Subscription Details",
                            value=(
                                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                f"**Active Servers:** {guild_count}/{tier_info['servers']}\n"
                                f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>\n"
                                f"**Created:** <t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                            ),
                            inline=False
                        )
            
            elif target_type == "guild":
                guild = target_obj
                if guild is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Guild not found.",
                        color=0xFF0000
                    )
                else:
                    # Check if guild has premium using MongoDB
                    db = await self.premium_system.mongo_db.ensure_connection()
                    guild_data = await db.premium_guilds.find_one({"guild_id": guild.id})
                                            
                    if not guild_data:
                        embed = discord.Embed(
                            title="❌ No Premium Access",
                            description=f"**{guild.name}** doesn't have premium access",
                            color=0xFF0000
                        )
                    else:
                        user_id = guild_data.get("user_id")
                        tier = guild_data.get("tier")
                        tier_info = self.premium_system.tiers[tier]
                                                
                        # Get premium user info
                        user_premium = await db.premium_users.find_one({"user_id": user_id})
                        
                        embed = discord.Embed(
                            title="✅ Guild Premium Status",
                            description=f"Premium information for **{guild.name}**",
                            color=0x00FF00
                        )
                        
                        expires_info = "Unknown"
                        if user_premium:
                            expires_at = user_premium[0]
                            expires_info = f"<t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                        
                        embed.add_field(
                            name="📊 Guild Details",
                            value=(
                                f"**Guild:** {guild.name}\n"
                                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                f"**Premium Owner:** <@{user_id}>\n"
                                f"**Expires:** {expires_info}"
                            ),
                            inline=False
                        )
            
            if embed is not None:
                await ctx.send(embed=embed)
            else:
                # Fallback error message
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred.",
                    color=0xFF0000
                )
                await ctx.send(embed=error_embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Database Error",
                description=f"Failed to retrieve premium status: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @premium.command(name="extend")
    async def premium_extend(self, ctx, target: Optional[str] = None, days: Optional[int] = None):
        """Extend premium subscription"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        if days is None or days <= 0:
            embed = discord.Embed(
                title="❌ Invalid Days",
                description="Please provide a positive number of days to extend.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        if target is None:
            target_type = "user"
            target_id = ctx.author.id
            target_obj = ctx.author
        else:
            target_type, target_id, target_obj = await self.parse_target(ctx, target)
        
        if target_type is None or target_id is None:
            embed = discord.Embed(
                title="❌ Invalid Target",
                description="Please provide a valid user mention/ID or guild ID.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            embed = None  # Initialize embed variable
            if target_type == "user":
                user = target_obj
                if user is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="User not found.",
                        color=0xFF0000
                    )
                else:
                    success = await self.premium_system.extend_premium(user.id, days)
                    
                    if success:
                        embed = discord.Embed(
                            title="✅ Subscription Extended",
                            description=f"Extended premium subscription for {user.mention} by {days} days",
                            color=0x00FF00
                        )
                        
                        # Send DM to user
                        try:
                            dm_embed = discord.Embed(
                                title="🔄 Premium Extended!",
                                description=f"Your premium subscription has been extended by {days} days!",
                                color=0x00FF00
                            )
                            await user.send(embed=dm_embed)
                        except:
                            pass
                    else:
                        embed = discord.Embed(
                            title="❌ Error",
                            description=f"{user.mention} doesn't have premium access to extend.",
                            color=0xFF0000
                        )
            
            elif target_type == "guild":
                guild = target_obj
                if guild is None:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Guild not found.",
                        color=0xFF0000
                    )
                else:
                    # For guild extension, extend bot owner's premium
                    success = await self.premium_system.extend_premium(self.premium_system.bot_owner_id, days)
                    
                    if success:
                        embed = discord.Embed(
                            title="✅ Guild Premium Extended",
                            description=f"Extended premium for **{guild.name}** by {days} days",
                            color=0x00FF00
                        )
                    else:
                        embed = discord.Embed(
                            title="❌ Error",
                            description="No premium access found to extend.",
                            color=0xFF0000
                        )
            
            if embed is not None:
                await ctx.send(embed=embed)
            else:
                # Fallback error message
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An unexpected error occurred.",
                    color=0xFF0000
                )
                await ctx.send(embed=error_embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Database Error",
                description=f"Failed to extend premium: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @premium.command(name="guilds", description="List guilds where you've used your premium slots")
    async def premium_guilds(self, ctx):
        """List guilds where you've used your premium slots"""
        # Check if user has premium using MongoDB
        db = await self.premium_system.mongo_db.ensure_connection()
        user_data = await db.premium_users.find_one({
            "user_id": ctx.author.id,
            "expires_at": {"$gt": datetime.now().isoformat()}
        })
        
        if not user_data:
            # User doesn't have premium, show premium required message
            embed = discord.Embed(
                title="<:ogstar:1420709631663013928> Premium Feature Required",
                description="You just found a premium feature! Please consider buying a rank from https://scyro.xyz/premium",
                color=0xFFD700
            )
            
            embed.add_field(
                name="<:premium:1409162823862325248> Premium Benefits",
                value=(
                    "> <a:dot:1396429135588626442> Access to exclusive commands\n"
                    "> <a:dot:1396429135588626442> Advanced features\n"
                    "> <a:dot:1396429135588626442> Priority support\n"
                    "> <a:dot:1396429135588626442> No Prefix Access\n"
                    "> <a:dot:1396429135588626442> Vip Support\n"
                    "> <a:dot:1396429135588626442> Early Commands Access\n"
                    "> <a:dot:1396429135588626442> Support bot development"
                ),
                inline=False
            )
            
            await ctx.send(embed=embed)
            return
        
        tier = user_data.get("tier")
        expires_at = user_data.get("expires_at")
        tier_info = self.premium_system.tiers[tier]
        
        # Get user's premium guilds
        guild_docs = []
        async for doc in db.premium_guilds.find({"user_id": ctx.author.id}):
            guild_docs.append(doc)
        
        guild_ids = [doc["guild_id"] for doc in guild_docs]
        used_slots = len(guild_ids)
        max_servers = tier_info['servers']
        remaining_slots = max_servers - used_slots
        
        # Get guild names
        guild_names = []
        for guild_id in guild_ids:
            guild = self.bot.get_guild(guild_id)
            if guild:
                guild_names.append(guild.name)
            else:
                guild_names.append(f"Unknown Guild ({guild_id})")
        
        # Create embed
        embed = discord.Embed(
            title=f"<:ogstar:1420709631663013928> {tier_info['name']} Tier - Guild Slots",
            color=0xFFD700
        )
        
        if guild_names:
            embed.add_field(
                name="📍 Active Premium Guilds",
                value="\n".join([f"• {name}" for name in guild_names]),
                inline=False
            )
        else:
            embed.add_field(
                name="📍 Active Premium Guilds",
                value="You haven't used any guild slots yet.",
                inline=False
            )
        
        embed.add_field(
            name="📊 Premium Usage",
            value=(
                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                f"**Active Servers:** {used_slots}/{max_servers}\n"
                f"**Remaining Slots:** {remaining_slots}\n"
                f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /premium use in a server to use a guild slot there")
        await ctx.send(embed=embed)
    
    @premium.command(name="info", description="Show subscription information including expiration and creation date")
    async def premium_status_user(self, ctx):
        """Show subscription information including expiration and creation date"""
        # Check if user has premium using MongoDB
        try:
            db = await self.premium_system.mongo_db.ensure_connection()
            user_data = await db.premium_users.find_one({
                "user_id": ctx.author.id,
                "expires_at": {"$gt": datetime.now().isoformat()}
            })
            
            if not user_data:
                # User doesn't have premium, show premium required message
                embed = discord.Embed(
                    title="<:ogstar:1420709631663013928> Premium Feature Required",
                    description="You just found a premium feature! Please consider buying a rank from https://scyro.xyz/premium",
                    color=0xFFD700
                )
                
                embed.add_field(
                    name="<:premium:1409162823862325248> Premium Benefits",
                    value=(
                        "> <a:dot:1396429135588626442> Access to exclusive commands\n"
                        "> <a:dot:1396429135588626442> Advanced features\n"
                        "> <a:dot:1396429135588626442> Priority support\n"
                        "> <a:dot:1396429135588626442> No Prefix Access\n"
                        "> <a:dot:1396429135588626442> Vip Support\n"
                        "> <a:dot:1396429135588626442> Early Commands Access\n"
                        "> <a:dot:1396429135588626442> Support bot development"
                    ),
                    inline=False
                )
                
                await ctx.send(embed=embed)
                return
            
            tier = user_data.get("tier")
            expires_at = user_data.get("expires_at")
            created_at = user_data.get("created_at")
            tier_info = self.premium_system.tiers[tier]
            
            # Get user's premium guilds count
            guild_count = await db.premium_guilds.count_documents({"user_id": ctx.author.id})
            
            max_servers = tier_info['servers']
            remaining_slots = max_servers - guild_count
            
            # Create embed
            embed = discord.Embed(
                title=f"<:ogstar:1420709631663013928> {tier_info['name']} Tier - Subscription Information",
                color=0xFFD700
            )
            
            embed.add_field(
                name="📊 Subscription Details",
                value=(
                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                    f"**Price:** {tier_info['price']}\n"
                    f"**Used Slots:** {guild_count}/{max_servers}\n"
                    f"**Remaining Slots:** {remaining_slots}"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📅 Date Information",
                value=(
                    f"**Purchased On:** <t:{int(datetime.fromisoformat(created_at).timestamp())}:F>\n"
                    f"**Expires On:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>\n"
                    f"**Time Remaining:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:R>"
                ),
                inline=False
            )
            
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to retrieve premium information: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @premium.command(name="use", description="Use a guild slot to activate premium in the current server")
    async def premium_use(self, ctx):
        """Use a guild slot to activate premium in the current server"""
        if not ctx.guild:
            embed = discord.Embed(
                title="❌ Server Required",
                description="This command can only be used in a server.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        # Check if user has premium using MongoDB
        try:
            db = await self.premium_system.mongo_db.ensure_connection()
            user_data = await db.premium_users.find_one({"user_id": ctx.author.id})
            
            # Check if subscription is expired
            if user_data:
                tier = user_data.get("tier")
                expires_at = user_data.get("expires_at")
                if datetime.fromisoformat(expires_at) < datetime.now():
                    # Subscription expired, remove user's premium access from this guild
                    await db.premium_guilds.delete_one({
                        "user_id": ctx.author.id,
                        "guild_id": ctx.guild.id
                    })
                    
                    # Send log to expiration channel
                    log_channel = self.bot.get_channel(self.premium_system.premium_expiration_log_channel)
                    if log_channel:
                        tier_info = self.premium_system.tiers[tier]
                        log_embed = discord.Embed(
                            title="📝 Premium Expired - Guild Access Removed",
                            description=f"User {ctx.author.mention}'s subscription expired. Removed premium access from guild **{ctx.guild.name}**",
                            color=0xFF0000
                        )
                        log_embed.add_field(
                            name="📊 Details",
                            value=(
                                f"**User:** {ctx.author.mention} (`{ctx.author.id}`)\n"
                                f"**Guild:** {ctx.guild.name} (`{ctx.guild.id}`)\n"
                                f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                                f"**Expired:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                            ),
                            inline=False
                        )
                        await log_channel.send(embed=log_embed)
                    
                    user_data = None  # Set to None to trigger the no premium message
            
            if not user_data:
                # User doesn't have premium, show premium required message
                embed = discord.Embed(
                    title="<:ogstar:1420709631663013928> Premium Feature Required",
                    description="You just found a premium feature! Please consider buying a rank from https://scyro.xyz/premium",
                    color=0xFFD700
                )
                
                embed.add_field(
                    name="<:premium:1409162823862325248> Premium Benefits",
                    value=(
                        "> <a:dot:1396429135588626442> Access to exclusive commands\n"
                        "> <a:dot:1396429135588626442> Advanced features\n"
                        "> <a:dot:1396429135588626442> Priority support\n"
                        "> <a:dot:1396429135588626442> No Prefix Access\n"
                        "> <a:dot:1396429135588626442> Vip Support\n"
                        "> <a:dot:1396429135588626442> Early Commands Access\n"
                        "> <a:dot:1396429135588626442> Support bot development"
                    ),
                    inline=False
                )
                
                await ctx.send(embed=embed)
                return
            
            tier = user_data.get("tier")
            expires_at = user_data.get("expires_at")
            tier_info = self.premium_system.tiers[tier]
            
            # Check if guild already has guild-wide premium
            guild_premium = await db.premium_guilds.find_one({
                "guild_id": ctx.guild.id,
                "$or": [
                    {"user_id": 0},
                    {"user_id": self.premium_system.bot_owner_id}
                ]
            })
            
            if guild_premium:
                # Guild already has premium, no need to use a slot
                embed = discord.Embed(
                    title="✅ Premium Already Active",
                    description=f"**{ctx.guild.name}** already has premium access enabled by the bot owner. All members can use premium features in this server.",
                    color=0x00FF00
                )
                await ctx.send(embed=embed)
                return
            
            # Check if user already has premium activated in this guild
            already_activated = await db.premium_guilds.find_one({
                "user_id": ctx.author.id,
                "guild_id": ctx.guild.id
            })
            
            if already_activated:
                embed = discord.Embed(
                    title="✅ Premium Already Active",
                    description=f"You have already activated premium in **{ctx.guild.name}**.",
                    color=0x00FF00
                )
                await ctx.send(embed=embed)
                return
            
            # Check if user has available server slots
            used_slots = await db.premium_guilds.count_documents({"user_id": ctx.author.id})
            max_servers = tier_info['servers']
            
            if used_slots >= max_servers:
                embed = discord.Embed(
                    title="❌ No Slots Remaining",
                    description=f"You have used all {max_servers} of your premium server slots. If you need more, consider buying a higher tier at [our support server](https://dsc.gg/scyrogg).",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            # Activate premium in this guild for this user
            await db.premium_guilds.update_one(
                {"user_id": ctx.author.id, "guild_id": ctx.guild.id},
                {
                    "$set": {
                        "user_id": ctx.author.id,
                        "guild_id": ctx.guild.id,
                        "tier": tier,
                        "activated_at": datetime.now().isoformat()
                    }
                },
                upsert=True
            )
            
            remaining_slots = max_servers - (used_slots + 1)
            
            embed = discord.Embed(
                title="✅ Guild Slot Used",
                description=f"Successfully used a **{tier_info['name']}** slot to activate premium in **{ctx.guild.name}**!",
                color=0x00FF00
            )
            
            embed.add_field(
                name="📊 Slot Usage Details",
                value=(
                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                    f"**Server:** {ctx.guild.name}\n"
                    f"**Remaining Slots:** {remaining_slots}/{max_servers}\n"
                    f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                ),
                inline=False
            )
            
            embed.set_footer(text="You can now use premium commands in this server with your slot")
            await ctx.send(embed=embed)
            
            # Send log to channel
            log_channel = self.bot.get_channel(self.premium_system.premium_use_log_channel)
            if log_channel:
                log_embed = discord.Embed(
                    title="📝 Premium Slot Usage Log",
                    description=f"User {ctx.author.mention} used a premium slot in guild **{ctx.guild.name}**",
                    color=0x00FF00
                )
                log_embed.add_field(
                    name="📊 Details",
                    value=(
                        f"**User:** {ctx.author.mention} (`{ctx.author.id}`)\n"
                        f"**Guild:** {ctx.guild.name} (`{ctx.guild.id}`)\n"
                        f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                        f"**Previous Slots:** {used_slots}/{max_servers}\n"
                        f"**New Slots:** {used_slots + 1}/{max_servers}\n"
                        f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                    ),
                    inline=False
                )
                await log_channel.send(embed=log_embed)
                
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to activate premium: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    # Bot owner only commands
    @commands.command(name="fillslot")
    async def fill_slot(self, ctx, user: discord.User, slots: int):
        """Fill a user's premium slots (Bot Owner Only)"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        # Validate slots
        if slots <= 0:
            embed = discord.Embed(
                title="❌ Invalid Slots",
                description="Please provide a positive number of slots to fill.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Get user's current premium info using MongoDB
            db = await self.premium_system.mongo_db.ensure_connection()
            user_data = await db.premium_users.find_one({"user_id": user.id})
            
            if not user_data:
                embed = discord.Embed(
                    title="❌ No Premium Access",
                    description=f"{user.mention} doesn't have premium access.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            tier = user_data.get("tier")
            expires_at = user_data.get("expires_at")
            tier_info = self.premium_system.tiers[tier]
            max_servers = tier_info['servers']
            
            # Get current slot count
            current_slots = await db.premium_guilds.count_documents({"user_id": user.id})
            
            # Check if adding slots would exceed limit
            new_slots = current_slots + slots
            if new_slots > max_servers:
                embed = discord.Embed(
                    title="❌ Slot Limit Exceeded",
                    description=f"Adding {slots} slots would exceed {user.mention}'s limit of {max_servers} slots. Current: {current_slots}, Requested: {slots}, Total would be: {new_slots}",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            # Add the slots by creating dummy guild entries
            bulk_operations = []
            for i in range(slots):
                # Create a dummy guild ID for logging purposes
                dummy_guild_id = 1000000000 + current_slots + i + 1
                bulk_operations.append(pymongo.UpdateOne(
                    {"user_id": user.id, "guild_id": dummy_guild_id},
                    {
                        "$set": {
                            "user_id": user.id,
                            "guild_id": dummy_guild_id,
                            "tier": tier,
                            "activated_at": datetime.now().isoformat()
                        }
                    },
                    upsert=True
                ))
            
            if bulk_operations:
                await db.premium_guilds.bulk_write(bulk_operations)
            
            embed = discord.Embed(
                title="✅ Slots Filled",
                description=f"Successfully filled {slots} premium slots for {user.mention}",
                color=0x00FF00
            )
            embed.add_field(
                name="📊 Details",
                value=(
                    f"**User:** {user.mention}\n"
                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                    f"**Previous Slots:** {current_slots}/{max_servers}\n"
                    f"**Added Slots:** {slots}\n"
                    f"**New Total:** {new_slots}/{max_servers}"
                ),
                inline=False
            )
            await ctx.send(embed=embed)
            
            # Send log to channel
            log_channel = self.bot.get_channel(self.premium_system.slot_fill_log_channel)
            if log_channel:
                log_embed = discord.Embed(
                    title="📝 Premium Slot Fill Log",
                    description=f"Bot owner {ctx.author.mention} filled {slots} premium slots for {user.mention}",
                    color=0x00FF00
                )
                log_embed.add_field(
                    name="📊 Details",
                    value=(
                        f"**User:** {user.mention} (`{user.id}`)\n"
                        f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                        f"**Previous Slots:** {current_slots}/{max_servers}\n"
                        f"**Added Slots:** {slots}\n"
                        f"**New Total:** {new_slots}/{max_servers}\n"
                        f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                    ),
                    inline=False
                )
                log_embed.add_field(
                    name="🛠️ Action By",
                    value=f"{ctx.author.mention} (`{ctx.author.id}`)",
                    inline=False
                )
                await log_channel.send(embed=log_embed)
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to fill slots: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="slotcheck")
    async def slot_check(self, ctx, user: discord.User):
        """Check all filled and empty slots of a user (Bot Owner Only)"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        try:
            # Get user's premium info using MongoDB
            db = await self.premium_system.mongo_db.ensure_connection()
            user_data = await db.premium_users.find_one({"user_id": user.id})
            
            if not user_data:
                embed = discord.Embed(
                    title="❌ No Premium Access",
                    description=f"{user.mention} doesn't have premium access.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            tier = user_data.get("tier")
            expires_at = user_data.get("expires_at")
            tier_info = self.premium_system.tiers[tier]
            max_servers = tier_info['servers']
            
            # Get user's premium guilds
            guild_docs = []
            async for doc in db.premium_guilds.find({"user_id": user.id}):
                guild_docs.append(doc)
            
            guild_ids = [doc["guild_id"] for doc in guild_docs]
            used_slots = len(guild_ids)
            remaining_slots = max_servers - used_slots
            
            # Get guild names
            guild_names = []
            for guild_id in guild_ids:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    guild_names.append(guild.name)
                else:
                    guild_names.append(f"Unknown Guild ({guild_id})")
            
            # Create embed
            embed = discord.Embed(
                title=f"📊 Slot Check for {user}",
                color=0xFFD700
            )
            
            embed.add_field(
                name="👤 User Information",
                value=(
                    f"**User:** {user.mention}\n"
                    f"**User ID:** `{user.id}`\n"
                    f"**Tier:** {tier_info['emoji']} {tier_info['name']}\n"
                    f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📊 Slot Usage",
                value=(
                    f"**Used Slots:** {used_slots}/{max_servers}\n"
                    f"**Remaining Slots:** {remaining_slots}\n"
                    f"**Total Slots:** {max_servers}"
                ),
                inline=False
            )
            
            if guild_names:
                embed.add_field(
                    name="📍 Active Premium Guilds",
                    value="\n".join([f"• {name}" for name in guild_names]),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📍 Active Premium Guilds",
                    value="No guilds activated yet.",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to check slots: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="premiumusers")
    async def premium_users(self, ctx):
        """Show all premium users with their tier and expiration date (Bot Owner Only)"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        try:
            # Get all premium users using MongoDB
            db = await self.premium_system.mongo_db.ensure_connection()
            users_list = []
            async for user_doc in db.premium_users.find().sort("expires_at", -1):
                users_list.append(user_doc)
            
            if not users_list:
                embed = discord.Embed(
                    title="❌ No Premium Users",
                    description="There are no premium users at the moment.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            # Create embed
            embed = discord.Embed(
                title="🌟 Premium Users",
                description=f"Showing {len(users_list)} premium users",
                color=0xFFD700
            )
            
            # Add users in batches (max 25 fields per embed)
            for i, user_doc in enumerate(users_list[:25]):
                user_id = user_doc["user_id"]
                tier = user_doc["tier"]
                expires_at = user_doc["expires_at"]
                created_at = user_doc["created_at"]
                
                user = self.bot.get_user(user_id)
                user_mention = user.mention if user else f"Unknown User ({user_id})"
                tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
                
                embed.add_field(
                    name=f"{tier_info['emoji']} {user_mention}",
                    value=(
                        f"**Tier:** {tier_info['name']}\n"
                        f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>\n"
                        f"**Created:** <t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                    ),
                    inline=False
                )
            
            if len(users_list) > 25:
                embed.set_footer(text=f"Showing first 25 of {len(users_list)} users")
            else:
                embed.set_footer(text=f"Showing all {len(users_list)} users")
            
            await ctx.send(embed=embed)
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to retrieve premium users: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    @premium.command(name="guild", description="List all premium guilds with details (Bot Owner Only)")
    async def premium_guild_list(self, ctx):
        """List all premium guilds with their details (Bot Owner Only)"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        try:
            # Get all premium guilds using MongoDB
            db = await self.premium_system.mongo_db.ensure_connection()
            guilds_list = []
            async for guild_doc in db.premium_guilds.find().sort("guild_id", 1):
                guilds_list.append(guild_doc)
            
            if not guilds_list:
                embed = discord.Embed(
                    title="❌ No Premium Guilds",
                    description="There are no premium guilds at the moment.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            # Create pagination view
            view = PremiumGuildPaginationView(guilds_list, self.bot, self.premium_system)
            
            # Create initial embed
            start_idx = 0
            end_idx = min(5, len(guilds_list))
            page_guilds = guilds_list[start_idx:end_idx]
            
            embed = discord.Embed(
                title="🏢 Premium Guilds",
                description=f"Showing {len(guilds_list)} premium guilds - Page 1/{view.total_pages}",
                color=0xFFD700
            )
            
            # Add guilds for first page
            for guild_doc in page_guilds:
                guild_id = guild_doc["guild_id"]
                user_id = guild_doc["user_id"]
                tier = guild_doc.get("tier", "plus")
                activated_at = guild_doc.get("activated_at", datetime.now().isoformat())
                
                guild = self.bot.get_guild(guild_id)
                guild_name = guild.name if guild else f"Unknown Guild ({guild_id})"
                
                user = self.bot.get_user(user_id) if user_id != 0 and user_id != self.premium_system.bot_owner_id else None
                user_mention = user.mention if user else ("Guild-wide Access" if user_id == 0 else "Bot Owner Activated")
                
                tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
                
                embed.add_field(
                    name=f"{tier_info['emoji']} {guild_name}",
                    value=(
                        f"**Guild ID:** `{guild_id}`\n"
                        f"**Owner/User:** {user_mention}\n"
                        f"**Tier:** {tier_info['name']}\n"
                        f"**Activated:** <t:{int(datetime.fromisoformat(activated_at).timestamp())}:R>"
                    ),
                    inline=False
                )
            
            embed.set_footer(text=f"Page 1/{view.total_pages} | Total Guilds: {len(guilds_list)}")
            
            await ctx.send(embed=embed, view=view)
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to retrieve premium guilds: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    @premium.command(name="user", description="List all premium users with details (Bot Owner Only)")
    async def premium_user_list(self, ctx):
        """List all premium users with their details (Bot Owner Only)"""
        if ctx.author.id != self.premium_system.bot_owner_id:
            return
        
        try:
            # Get all premium users using MongoDB
            db = await self.premium_system.mongo_db.ensure_connection()
            users_list = []
            async for user_doc in db.premium_users.find().sort("expires_at", -1):
                users_list.append(user_doc)
            
            if not users_list:
                embed = discord.Embed(
                    title="❌ No Premium Users",
                    description="There are no premium users at the moment.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
                return
            
            # Create pagination view
            view = PremiumUserPaginationView(users_list, self.bot, self.premium_system)
            
            # Create initial embed
            start_idx = 0
            end_idx = min(5, len(users_list))
            page_users = users_list[start_idx:end_idx]
            
            embed = discord.Embed(
                title="👥 Premium Users",
                description=f"Showing {len(users_list)} premium users - Page 1/{view.total_pages}",
                color=0xFFD700
            )
            
            # Add users for first page
            for user_doc in page_users:
                user_id = user_doc["user_id"]
                tier = user_doc["tier"]
                expires_at = user_doc["expires_at"]
                created_at = user_doc["created_at"]
                
                user = self.bot.get_user(user_id)
                user_mention = user.mention if user else f"Unknown User ({user_id})"
                tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
                
                # Get guild count for this user
                guild_count = await db.premium_guilds.count_documents({"user_id": user_id})
                max_servers = tier_info.get('servers', 0)
                
                embed.add_field(
                    name=f"{tier_info['emoji']} {user_mention}",
                    value=(
                        f"**User ID:** `{user_id}`\n"
                        f"**Tier:** {tier_info['name']}\n"
                        f"**Servers:** {guild_count}/{max_servers}\n"
                        f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>\n"
                        f"**Started:** <t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                    ),
                    inline=False
                )
            
            embed.set_footer(text=f"Page 1/{view.total_pages} | Total Users: {len(users_list)}")
            
            await ctx.send(embed=embed, view=view)
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to retrieve premium users: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)


class TierView(discord.ui.View):
    def __init__(self, tiers, premium_cogs=None):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.add_item(TierSelect(tiers))
        # Add the premium commands button
        if premium_cogs:
            self.add_item(PremiumCommandsButton(premium_cogs))


class PremiumGuildPaginationView(discord.ui.View):
    def __init__(self, guilds_list, bot, premium_system, page=1, per_page=5):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.guilds_list = guilds_list
        self.bot = bot
        self.premium_system = premium_system
        self.page = page
        self.per_page = per_page
        self.total_pages = ceil(len(guilds_list) / per_page)
        
        # Add navigation buttons
        if self.total_pages > 1:
            self.add_item(PremiumGuildFirstPageButton())
            self.add_item(PremiumGuildPrevPageButton())
            self.add_item(PremiumGuildNextPageButton())
            self.add_item(PremiumGuildLastPageButton())
    
    async def update_embed(self, interaction: discord.Interaction):
        # Calculate start and end indices for current page
        start_idx = (self.page - 1) * self.per_page
        end_idx = start_idx + self.per_page
        page_guilds = self.guilds_list[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="🏢 Premium Guilds",
            description=f"Showing {len(self.guilds_list)} premium guilds - Page {self.page}/{self.total_pages}",
            color=0xFFD700
        )
        
        # Add guilds for current page
        for guild_doc in page_guilds:
            guild_id = guild_doc["guild_id"]
            user_id = guild_doc["user_id"]
            tier = guild_doc.get("tier", "plus")
            activated_at = guild_doc.get("activated_at", datetime.now().isoformat())
            
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"Unknown Guild ({guild_id})"
            
            user = self.bot.get_user(user_id) if user_id != 0 and user_id != self.premium_system.bot_owner_id else None
            user_mention = user.mention if user else ("Guild-wide Access" if user_id == 0 else "Bot Owner Activated")
            
            tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
            
            embed.add_field(
                name=f"{tier_info['emoji']} {guild_name}",
                value=(
                    f"**Guild ID:** `{guild_id}`\n"
                    f"**Owner/User:** {user_mention}\n"
                    f"**Tier:** {tier_info['name']}\n"
                    f"**Activated:** <t:{int(datetime.fromisoformat(activated_at).timestamp())}:R>"
                ),
                inline=False
            )
        
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} | Total Guilds: {len(self.guilds_list)}")
        
        # Update button disabled states
        for child in self.children:
            if isinstance(child, PremiumGuildFirstPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumGuildPrevPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumGuildNextPageButton):
                child.disabled = (self.page == self.total_pages)
            elif isinstance(child, PremiumGuildLastPageButton):
                child.disabled = (self.page == self.total_pages)
        
        await interaction.response.edit_message(embed=embed, view=self)


class PremiumGuildFirstPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="<< First",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_first_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page != 1:
            view.page = 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumGuildPrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="< Prev",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_prev_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page > 1:
            view.page -= 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumGuildNextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next >",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_next_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page < view.total_pages:
            view.page += 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumGuildLastPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Last >>",
            style=discord.ButtonStyle.primary,
            custom_id="premium_guild_last_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumGuildPaginationView = self.view
        if view.page != view.total_pages:
            view.page = view.total_pages
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserPaginationView(discord.ui.View):
    def __init__(self, users_list, bot, premium_system, page=1, per_page=5):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.users_list = users_list
        self.bot = bot
        self.premium_system = premium_system
        self.page = page
        self.per_page = per_page
        self.total_pages = ceil(len(users_list) / per_page)
        
        # Add navigation buttons
        if self.total_pages > 1:
            self.add_item(PremiumUserFirstPageButton())
            self.add_item(PremiumUserPrevPageButton())
            self.add_item(PremiumUserNextPageButton())
            self.add_item(PremiumUserLastPageButton())
    
    async def update_embed(self, interaction: discord.Interaction):
        # Calculate start and end indices for current page
        start_idx = (self.page - 1) * self.per_page
        end_idx = start_idx + self.per_page
        page_users = self.users_list[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="👥 Premium Users",
            description=f"Showing {len(self.users_list)} premium users - Page {self.page}/{self.total_pages}",
            color=0xFFD700
        )
        
        # Add users for current page
        db = await self.premium_system.mongo_db.ensure_connection()
        for user_doc in page_users:
            user_id = user_doc["user_id"]
            tier = user_doc["tier"]
            expires_at = user_doc["expires_at"]
            created_at = user_doc["created_at"]
            
            user = self.bot.get_user(user_id)
            user_mention = user.mention if user else f"Unknown User ({user_id})"
            tier_info = self.premium_system.tiers.get(tier, {'emoji': '❓', 'name': tier})
            
            # Get guild count for this user
            guild_count = await db.premium_guilds.count_documents({"user_id": user_id})
            max_servers = tier_info.get('servers', 0)
            
            embed.add_field(
                name=f"{tier_info['emoji']} {user_mention}",
                value=(
                    f"**User ID:** `{user_id}`\n"
                    f"**Tier:** {tier_info['name']}\n"
                    f"**Servers:** {guild_count}/{max_servers}\n"
                    f"**Expires:** <t:{int(datetime.fromisoformat(expires_at).timestamp())}:F>\n"
                    f"**Started:** <t:{int(datetime.fromisoformat(created_at).timestamp())}:R>"
                ),
                inline=False
            )
        
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} | Total Users: {len(self.users_list)}")
        
        # Update button disabled states
        for child in self.children:
            if isinstance(child, PremiumUserFirstPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumUserPrevPageButton):
                child.disabled = (self.page == 1)
            elif isinstance(child, PremiumUserNextPageButton):
                child.disabled = (self.page == self.total_pages)
            elif isinstance(child, PremiumUserLastPageButton):
                child.disabled = (self.page == self.total_pages)
        
        await interaction.response.edit_message(embed=embed, view=self)


class PremiumUserFirstPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="<< First",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_first_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page != 1:
            view.page = 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserPrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="< Prev",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_prev_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page > 1:
            view.page -= 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserNextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next >",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_next_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page < view.total_pages:
            view.page += 1
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumUserLastPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Last >>",
            style=discord.ButtonStyle.primary,
            custom_id="premium_user_last_page"
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: PremiumUserPaginationView = self.view
        if view.page != view.total_pages:
            view.page = view.total_pages
            await view.update_embed(interaction)
        else:
            await interaction.response.defer()


class PremiumCommandsButton(discord.ui.Button):
    def __init__(self, premium_cogs):
        super().__init__(
            label="View All Premium Commands",
            style=discord.ButtonStyle.primary,
            emoji="⚡",
            custom_id="premium_commands"
        )
        self.premium_cogs = premium_cogs
    
    async def callback(self, interaction: discord.Interaction):
        if not self.premium_cogs:
            await interaction.response.send_message(
                "No premium commands available.", 
                ephemeral=True
            )
            return
        
        # Format the premium commands list
        commands_list = []
        for cog in self.premium_cogs:
            commands_list.append(f"• **{cog.capitalize()}** commands")
        
        embed = discord.Embed(
            title="⚡ All Premium Commands",
            description="Here are all the premium commands available with a premium subscription:",
            color=0xFFD700
        )
        
        embed.add_field(
            name="🔒 Premium Command Categories",
            value="\n".join(commands_list) if commands_list else "No premium commands configured",
            inline=False
        )
        
        embed.add_field(
            name="💡 How to Access",
            value=(
                "To use these premium commands:\n"
                "1. Purchase a premium subscription\n"
                "2. Use the `/premium use` command to activate premium in your server\n"
                "3. Enjoy exclusive features and commands!"
            ),
            inline=False
        )
        
        embed.set_footer(text="Premium features enhance your Scyro experience")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)



async def setup(bot):
    await bot.add_cog(Premium(bot))