import discord
import motor.motor_asyncio
import asyncio
from discord.ext import commands
from utils.Tools import *
import datetime
import os

class AutoRoleSetupView(discord.ui.View):
    def __init__(self, autorole_cog, ctx, original_message=None):
        super().__init__(timeout=300)
        self.autorole_cog = autorole_cog
        self.ctx = ctx
        self.original_message = original_message

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You can't interact with this menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Humans", style=discord.ButtonStyle.secondary, emoji="👤")
    async def humans_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_setup(interaction, "humans", "Human")

    @discord.ui.button(label="Bots", style=discord.ButtonStyle.secondary, emoji="🤖")
    async def bots_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_setup(interaction, "bots", "Bot")

    @discord.ui.button(label="Boosters", style=discord.ButtonStyle.secondary, emoji="💎")
    async def boosters_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_setup(interaction, "boosters", "Booster")

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Show confirmation dialog
        embed = discord.Embed(
            title="⚠️ **Confirm Reset**",
            description="Are you sure you want to **reset all autorole configurations**?\n\n**This will:**\n• Clear all human autoroles\n• Clear all bot autoroles\n• Clear all booster autoroles\n• Disable the autorole system\n\n**This action cannot be undone!**",
            color=0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        
        # Create confirmation view
        view = AutoRoleResetConfirmView(self.autorole_cog, self.ctx, self.original_message)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_role_setup(self, interaction: discord.Interaction, role_type: str, role_name: str):
        embed = discord.Embed(
            title=f"⚙️ **Setup {role_name} AutoRole**",
            description=f"Please mention the role or provide the role ID for **{role_name.lower()}** autorole.\n\n**You have 2 minutes to respond.**",
            color=0x3498DB,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Type 'cancel' to cancel setup")
        
        # Send ephemeral message (only user can see)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        def check(message):
            return message.author == self.ctx.author and message.channel == self.ctx.channel
        
        try:
            message = await self.ctx.bot.wait_for('message', check=check, timeout=120.0)
            
            if message.content.lower() == 'cancel':
                embed = discord.Embed(
                    title="❌ **Setup Cancelled**",
                    description=f"{role_name} autorole setup has been cancelled.",
                    color=0xE74C3C
                )
                await interaction.edit_original_response(embed=embed)
                return
            
            # Try to get role from mention or ID
            role = None
            
            # Check if it's a role mention
            if message.role_mentions:
                role = message.role_mentions[0]
            else:
                # Try to get role by ID
                try:
                    role_id = int(message.content.strip())
                    role = self.ctx.guild.get_role(role_id)
                except ValueError:
                    pass
            
            # Delete user's message
            try:
                await message.delete()
            except:
                pass  # Ignore if we can't delete
            
            if not role:
                embed = discord.Embed(
                    title="❌ **Invalid Role**",
                    description="Please provide a valid role mention or role ID.",
                    color=0xE74C3C
                )
                await interaction.edit_original_response(embed=embed)
                return
            
            # Check if role is assignable
            if role >= self.ctx.guild.me.top_role:
                embed = discord.Embed(
                    title="❌ **Role Too High**",
                    description="I cannot assign this role as it's higher than or equal to my highest role.",
                    color=0xE74C3C
                )
                await interaction.edit_original_response(embed=embed)
                return
            
            # Update database
            data = await self.autorole_cog.get_autorole(self.ctx.guild.id)
            data[role_type] = role.id
            data["enabled"] = True  # Enable when role is set
            await self.autorole_cog.update_autorole(self.ctx.guild.id, data)
            
            # Update the main embed in real-time
            if self.original_message:
                updated_main_embed = await self.autorole_cog.create_setup_embed(self.ctx.guild)
                await self.original_message.edit(embed=updated_main_embed, view=self)
            
            embed = discord.Embed(
                title="✅ **AutoRole Updated**",
                description=f"Successfully set {role.mention} as the **{role_name.lower()}** autorole!\n\nℹ️ The main setup embed has been updated to reflect your changes.",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Updated by {self.ctx.author.name}", icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
            
            await interaction.edit_original_response(embed=embed)
            
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ **Setup Timeout**",
                description=f"{role_name} autorole setup timed out after 2 minutes.",
                color=0xF39C12
            )
            await interaction.edit_original_response(embed=embed)

class AutoRoleResetConfirmView(discord.ui.View):
    def __init__(self, autorole_cog, ctx, original_message=None):
        super().__init__(timeout=300)
        self.autorole_cog = autorole_cog
        self.ctx = ctx
        self.original_message = original_message

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You can't interact with this menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, Reset All", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Reset all autorole settings
        reset_data = {"humans": None, "bots": None, "boosters": None, "enabled": False}
        await self.autorole_cog.update_autorole(self.ctx.guild.id, reset_data)
        
        # Update the main setup embed if it exists
        if self.original_message:
            try:
                updated_main_embed = await self.autorole_cog.create_setup_embed(self.ctx.guild)
                setup_view = AutoRoleSetupView(self.autorole_cog, self.ctx, self.original_message)
                await self.original_message.edit(embed=updated_main_embed, view=setup_view)
            except:
                pass  # If we can't update the main embed, continue
        
        embed = discord.Embed(
            title="✅ **AutoRole Reset Complete**",
            description="Successfully cleared all autorole configurations!\n\n**Reset Items:**\n• Human autorole\n• Bot autorole\n• Booster autorole\n\n**Status:** ❌ **Disabled**\n\nℹ️ The main setup embed has been updated to reflect the reset.",
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Reset by {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="No, Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ **Reset Cancelled**",
            description="The autorole reset has been cancelled. All settings remain unchanged.",
            color=0x95A5A6,
            timestamp=datetime.datetime.utcnow()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)

class AutoRoleConfigView(discord.ui.View):
    def __init__(self, autorole_cog, ctx):
        super().__init__(timeout=300)
        self.autorole_cog = autorole_cog
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You can't interact with this menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Toggle", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = await self.autorole_cog.get_autorole(self.ctx.guild.id)
        current_status = data.get("enabled", False)
        new_status = not current_status
        data["enabled"] = new_status
        await self.autorole_cog.update_autorole(self.ctx.guild.id, data)
        
        status_emoji = "✅" if new_status else "❌"
        status_text = "Enabled" if new_status else "Disabled"
        
        embed = discord.Embed(
            title=f"{status_emoji} **AutoRole System {status_text}**",
            description=f"The autorole system has been **{status_text.lower()}** for this server!",
            color=0x2ECC71 if new_status else 0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Toggled by {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = 0x9B59B6  # Purple color
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.collection = None

    async def cog_load(self):
        if not self.mongo_uri:
            print("CRITICAL: MONGO_URI not found for AutoRole cog!")
            return

        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client.get_default_database()
        self.collection = self.db.autoroles
        
        # Ensure unique index on guild_id
        await self.collection.create_index("guild_id", unique=True)

    async def get_autorole(self, guild_id: int):
        if self.collection is None:
             return {"bots": None, "humans": None, "boosters": None, "enabled": False}

        doc = await self.collection.find_one({"guild_id": guild_id})
        if doc:
            return {
                "bots": doc.get("bots"),
                "humans": doc.get("humans"),
                "boosters": doc.get("boosters"),
                "enabled": doc.get("enabled", False)
            }
        else:
            return {"bots": None, "humans": None, "boosters": None, "enabled": False}

    async def update_autorole(self, guild_id: int, data):
        if self.collection is None:
            return

        await self.collection.update_one(
            {"guild_id": guild_id},
            {"$set": {
                "bots": data.get('bots'),
                "humans": data.get('humans'),
                "boosters": data.get('boosters'),
                "enabled": bool(data.get('enabled', False))
            }},
            upsert=True
        )

    async def create_setup_embed(self, guild: discord.Guild):
        """Create setup embed with current configuration"""
        data = await self.get_autorole(guild.id)
        
        embed = discord.Embed(
            title="⚙️ **AutoRole Setup**",
            description=f"Configure automatic role assignment for **{guild.name}**\n\nℹ️ Click the buttons below to configure each role type.",
            color=self.color,
            timestamp=datetime.datetime.utcnow()
        )
        
        # Humans section
        human_role = guild.get_role(data["humans"]) if data["humans"] else None
        human_text = f"• {human_role.mention}" if human_role else "*Not configured*"
        embed.add_field(
            name="👤 **Human Members**",
            value=human_text,
            inline=True
        )
        
        # Bots section  
        bot_role = guild.get_role(data["bots"]) if data["bots"] else None
        bot_text = f"• {bot_role.mention}" if bot_role else "*Not configured*"
        embed.add_field(
            name="🤖 **Bot Accounts**",
            value=bot_text,
            inline=True
        )
        
        # Boosters section
        booster_role = guild.get_role(data["boosters"]) if data["boosters"] else None
        booster_text = f"• {booster_role.mention}" if booster_role else "*Not configured*"
        embed.add_field(
            name="💎 **Server Boosters**",
            value=booster_text,
            inline=True
        )
        
        # Status
        status_text = "✅ Enabled" if data.get("enabled", False) else "❌ Disabled" 
        embed.add_field(
            name="📊 **System Status**",
            value=status_text,
            inline=False
        )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text="Use the buttons below to configure each role type")
        return embed

    async def create_config_embed(self, guild: discord.Guild):
        """Create configuration display embed"""
        data = await self.get_autorole(guild.id)
        
        # Status indicator
        status_text = "✅ **Enabled**" if data.get("enabled", False) else "❌ **Disabled**"
        
        embed = discord.Embed(
            title="⚙️ **AutoRole Configuration**",
            description=f"Current autorole settings for **{guild.name}**\n\n**Status:** {status_text}",
            color=self.color if data.get("enabled", False) else 0x95A5A6,
            timestamp=datetime.datetime.utcnow()
        )
        
        # Humans section
        human_role = guild.get_role(data["humans"]) if data["humans"] else None
        human_text = f"• {human_role.mention}" if human_role else "*Not configured*"
        embed.add_field(
            name="👤 **Human Members**",
            value=human_text,
            inline=True
        )
        
        # Bots section  
        bot_role = guild.get_role(data["bots"]) if data["bots"] else None
        bot_text = f"• {bot_role.mention}" if bot_role else "*Not configured*"
        embed.add_field(
            name="🤖 **Bot Accounts**",
            value=bot_text,
            inline=True
        )
        
        # Boosters section
        booster_role = guild.get_role(data["boosters"]) if data["boosters"] else None
        booster_text = f"• {booster_role.mention}" if booster_role else "*Not configured*"
        embed.add_field(
            name="💎 **Server Boosters**",
            value=booster_text,
            inline=True
        )
        
        # Add info section
        info_text = (
            "• Roles assigned automatically on join\n"
            "• Booster roles toggle with boost status\n"
            "• Use the toggle button to enable/disable"
        )
        embed.add_field(
            name="📌 **System Info**",
            value=info_text,
            inline=False
        )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text="Scyro's autorole system")
        return embed

    # Main autorole group command
    @commands.hybrid_group(
        name="autorole",
        invoke_without_command=True,
        description="⚙️ AutoRole management system"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def autorole(self, ctx):
        """AutoRole command group"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="⚙️ **AutoRole System**",
                description=(
                    "Manage automatic role assignment for your server.\n\n"
                    "**Available Commands:**\n"
                    "• `/autorole setup` - Interactive setup with buttons\n"
                    "• `/autorole config` - View current configuration\n"
                    "• `/autorole reset` - Clear all settings\n"
                    "• `/autorole toggle` - Enable/disable system\n\n"
                    "📌 **How it works:**\n"
                    "Automatically assigns roles when members join the server!"
                ),
                color=self.color,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Server: {ctx.guild.name}")
            await ctx.send(embed=embed)

    # Setup subcommand - /autorole setup
    @autorole.command(
        name="setup",
        description="⚙️ Setup autoroles (Human, Bot, Booster)"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx, human_role: discord.Role, bot_role: discord.Role = None, booster_role: discord.Role = None):
        """Setup autoroles: <human_role> [bot_role] [booster_role]"""
        
        # Validation checks
        roles_to_check = [("Human", human_role)]
        if bot_role: roles_to_check.append(("Bot", bot_role))
        if booster_role: roles_to_check.append(("Booster", booster_role))
        
        for name, role in roles_to_check:
            if role >= ctx.guild.me.top_role:
                return await ctx.send(f"❌ **Error:** The {name} role ({role.mention}) is higher than or equal to my highest role. I cannot assign it.", ephemeral=True)
            if role.managed:
                return await ctx.send(f"❌ **Error:** The {name} role ({role.mention}) is a managed role (e.g. integration role) and cannot be assigned.", ephemeral=True)

        data = {
            "humans": human_role.id,
            "bots": bot_role.id if bot_role else None,
            "boosters": booster_role.id if booster_role else None,
            "enabled": True
        }
        await self.update_autorole(ctx.guild.id, data)
        
        # Prepare Embed Text
        human_text = human_role.mention
        bot_text = bot_role.mention if bot_role else "*Not configured*"
        booster_text = booster_role.mention if booster_role else "*Not configured*"
        
        embed = discord.Embed(
            title="✅ **AutoRole Setup Complete**",
            description=(
                "Successfully configured autoroles!\n\n"
                f"👤 **Humans:** {human_text}\n"
                f"🤖 **Bots:** {bot_text}\n"
                f"💎 **Boosters:** {booster_text}\n\n"
                "**System Status:** ✅ Enabled"
            ),
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Setup by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)

    # Config subcommand - /autorole config  
    @autorole.command(
        name="config",
        description="📋 View current autorole configuration"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def config(self, ctx):
        """View current autorole configuration with toggle button"""
        embed = await self.create_config_embed(ctx.guild)
        view = AutoRoleConfigView(self, ctx)
        await ctx.send(embed=embed, view=view)

    # Reset subcommand - /autorole reset
    @autorole.command(
        name="reset",
        description="🗑️ Reset all autorole configurations"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        """Reset all autorole configurations with confirmation"""
        data = await self.get_autorole(ctx.guild.id)
        
        if not any([data.get("humans"), data.get("bots"), data.get("boosters")]):
            embed = discord.Embed(
                title="❌ **No Configuration Found**",
                description="There are no autorole configurations to reset.",
                color=0xE74C3C,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Server: {ctx.guild.name}")
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Show confirmation dialog
        embed = discord.Embed(
            title="⚠️ **Confirm Reset**",
            description="Are you sure you want to **reset all autorole configurations**?\n\n**This will:**\n• Clear all human autoroles\n• Clear all bot autoroles\n• Clear all booster autoroles\n• Disable the autorole system\n\n**This action cannot be undone!**",
            color=0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        
        view = AutoRoleResetConfirmView(self, ctx)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    # Toggle subcommand - /autorole toggle
    @autorole.command(
        name="toggle",
        description="🔄 Toggle the autorole system on/off"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def toggle(self, ctx):
        """Toggle the autorole system on/off"""
        data = await self.get_autorole(ctx.guild.id)
        current_status = data.get("enabled", False)
        new_status = not current_status
        data["enabled"] = new_status
        await self.update_autorole(ctx.guild.id, data)
        
        status_emoji = "✅" if new_status else "❌"
        status_text = "Enabled" if new_status else "Disabled"
        
        embed = discord.Embed(
            title=f"{status_emoji} **AutoRole System {status_text}**",
            description=f"The autorole system has been **{status_text.lower()}** for this server!",
            color=0x2ECC71 if new_status else 0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Toggled by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        await ctx.send(embed=embed, ephemeral=True)

    # Event listeners
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Auto-assign role when members join"""
        if not member.guild:
            return
        
        try:
            data = await self.get_autorole(member.guild.id)
            
            if not data.get("enabled", False):
                return

            role_to_add = None
            
            if member.bot:
                # Bot autorole
                if data.get("bots"):
                    role_to_add = member.guild.get_role(data["bots"])
            else:
                # Human autorole
                if data.get("humans"):
                    role_to_add = member.guild.get_role(data["humans"])
            
            # Add role if found and assignable
            if role_to_add and role_to_add < member.guild.me.top_role:
                await member.add_roles(role_to_add, reason="AutoRole: New member")
                
        except discord.Forbidden:
            pass  # Missing permissions
        except discord.HTTPException:
            pass  # Failed to assign role
        except Exception:
            pass  # Unexpected error

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Handle server boost role changes"""
        if not after.guild:
            return
            
        if before.premium_since != after.premium_since:
            try:
                data = await self.get_autorole(after.guild.id)
                
                if not data.get("enabled", False) or not data.get("boosters"):
                    return
                
                booster_role = after.guild.get_role(data["boosters"])
                if not booster_role:
                    return

                if after.premium_since and not before.premium_since:
                    # Member started boosting - add booster role
                    if booster_role < after.guild.me.top_role:
                        await after.add_roles(booster_role, reason="AutoRole: Server booster")
                        
                elif before.premium_since and not after.premium_since:
                    # Member stopped boosting - remove booster role
                    if booster_role in after.roles:
                        await after.remove_roles(booster_role, reason="AutoRole: No longer boosting")
                        
            except discord.Forbidden:
                pass  # Missing permissions
            except discord.HTTPException:
                pass  # Failed to manage role
            except Exception:
                pass  # Unexpected error

    # Error handlers
    @autorole.error
    @setup.error
    @config.error
    @reset.error
    @toggle.error
    async def autorole_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ **Permission Denied**",
                description=(
                    "You need **Administrator** permission to use autorole commands!\n\n"
                    "💡 *Contact a server administrator for help*"
                ),
                color=0xE74C3C
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏰ **Cooldown Active**",
                description=(
                    f"Please wait **{error.retry_after:.1f}** seconds before using this command again!\n\n"
                    "💡 *This helps prevent spam*"
                ),
                color=0xF39C12
            )
            await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AutoRole(bot))
