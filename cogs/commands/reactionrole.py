import discord
import motor.motor_asyncio
from bson import ObjectId
import asyncio
from discord.ext import commands
from utils.Tools import *
import datetime
import re
from typing import Optional
import os

class ReactionRoleRemoveSelect(discord.ui.Select):
    def __init__(self, reactionrole_cog, ctx, message_id, reaction_roles):
        self.reactionrole_cog = reactionrole_cog
        self.ctx = ctx
        self.message_id = message_id
        self.reaction_roles = reaction_roles
        
        options = []
        for rr in reaction_roles:
            emoji = rr['emoji']
            role = ctx.guild.get_role(rr['role_id'])
            role_name = role.name if role else "Unknown Role"
            # Handle custom emojis properly in dropdown
            select_emoji = None
            if emoji.startswith('<') and emoji.endswith('>'):
                # Custom emoji format: <:name:id> or <a:name:id>
                emoji_parts = emoji.strip('<>').split(':')
                if len(emoji_parts) >= 3:
                    try:
                        emoji_id = int(emoji_parts[-1])
                        select_emoji = discord.PartialEmoji(name=emoji_parts[1], id=emoji_id)
                    except:
                        select_emoji = None
            # Process emoji for display - show only the emoji, not the full format
            display_emoji = emoji
            if emoji.startswith('<') and emoji.endswith('>') and select_emoji:
                # For custom emojis, show only the emoji without the <:name:id> format
                display_emoji = str(select_emoji)
            elif emoji.startswith('<') and emoji.endswith('>'):
                # If we couldn't create a PartialEmoji, try to extract just the emoji part
                emoji_parts = emoji.strip('<>').split(':')
                if len(emoji_parts) >= 3:
                    try:
                        emoji_id = int(emoji_parts[-1])
                        temp_emoji = discord.PartialEmoji(name=emoji_parts[1], id=emoji_id)
                        display_emoji = str(temp_emoji)
                    except:
                        # If all else fails, show just the emoji name
                        display_emoji = emoji_parts[1] if len(emoji_parts) >= 2 else emoji
            
            options.append(discord.SelectOption(
                label=f"{role_name}",
                value=f"{rr['id']}",  # Note: id is now string/OID? or we should use logic to handle.
                # Actually, Mongo IDs are ObjectIds. If we use auto-increment logic or just use distinct fields...
                # The existing code expects 'id'.
                # To minimize changes, let's include '_id' as string in the dict returned by getters.
                description=f"Role ID: {rr['role_id']}",
                emoji=select_emoji if select_emoji else emoji
            ))
        
        super().__init__(
            placeholder="Select reaction role to remove...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Acknowledge the interaction immediately
        await interaction.response.defer(ephemeral=True)
        
        try:
            selected_id = self.values[0] # Mongo IDs are strings usually
            selected_rr = next((rr for rr in self.reaction_roles if str(rr['id']) == selected_id), None)
            
            if not selected_rr:
                embed = discord.Embed(
                    title="❌ **Error**",
                    description="Could not find the selected reaction role.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Remove from database
            await self.reactionrole_cog.remove_reaction_role(selected_id)
            
            # Try to remove reaction from message
            try:
                if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                    message = await interaction.channel.fetch_message(self.message_id)
                    await message.clear_reaction(selected_rr['emoji'])
            except:
                pass  # Ignore if we can't remove reaction
            
            role = interaction.guild.get_role(selected_rr['role_id']) if interaction.guild else None
            role_name = role.name if role else "Unknown Role"
            
            embed = discord.Embed(
                title="✅ **Reaction Role Removed**",
                description=f"Successfully removed reaction role!\n\n"
                           f"**Message ID:** `{self.message_id}`\n"
                           f"**Emoji:** {selected_rr['emoji']}\n"
                           f"**Role:** {role.mention if role else role_name}",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            user_avatar = interaction.user.avatar.url if interaction.user and interaction.user.avatar else None
            embed.set_footer(text=f"Removed by {interaction.user.name}" if interaction.user else "Removed", icon_url=user_avatar)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Try to update the original message
            try:
                if interaction.message:
                    await interaction.message.delete()
            except:
                pass  # Ignore if we can't delete the message
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ **Error**",
                description=f"An error occurred: {str(e)}",
                color=0xE74C3C
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class ReactionRoleRemoveView(discord.ui.View):
    def __init__(self, reactionrole_cog, ctx, message_id, reaction_roles):
        super().__init__(timeout=300)
        self.reactionrole_cog = reactionrole_cog
        self.ctx = ctx
        self.message_id = message_id
        
        # Add the select menu
        self.add_item(ReactionRoleRemoveSelect(reactionrole_cog, ctx, message_id, reaction_roles))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You can't interact with this menu!", ephemeral=True)
            return False
        return True

class ReactionRoleResetConfirmView(discord.ui.View):
    def __init__(self, reactionrole_cog, ctx, message_id):
        super().__init__(timeout=300)
        self.reactionrole_cog = reactionrole_cog
        self.ctx = ctx
        self.message_id = message_id

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You can't interact with this menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, Reset All", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge the interaction immediately
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild_id = self.ctx.guild.id if self.ctx and self.ctx.guild else interaction.guild.id if interaction.guild else None
            if not guild_id:
                raise ValueError("Could not determine guild ID")
                
            # Get all reaction roles for this message
            reaction_roles = await self.reactionrole_cog.get_reaction_roles_for_message(guild_id, self.message_id)
            
            # Remove all from database
            await self.reactionrole_cog.remove_all_reaction_roles_for_message(guild_id, self.message_id)
            
            # Try to remove all reactions from message
            try:
                if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                    message = await interaction.channel.fetch_message(self.message_id)
                    await message.clear_reactions()
            except:
                pass  # Ignore if we can't remove reactions
            
            embed = discord.Embed(
                title="✅ **Reaction Roles Reset**",
                description=f"Successfully removed all reaction roles from message `{self.message_id}`!",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            user_avatar = interaction.user.avatar.url if interaction.user and interaction.user.avatar else None
            embed.set_footer(text=f"Reset by {interaction.user.name}" if interaction.user else "Reset", icon_url=user_avatar)
            
            # Try to edit the original message, if that fails send a new message
            try:
                await interaction.edit_original_response(embed=embed, view=None)
            except:
                await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ **Error**",
                description=f"An error occurred: {str(e)}",
                color=0xE74C3C
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="No, Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ **Reset Cancelled**",
            description="The reaction role reset has been cancelled.",
            color=0x95A5A6,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.edit_message(embed=embed, view=None)

class ReactionRoleEditSelect(discord.ui.Select):
    def __init__(self, reactionrole_cog, ctx, message_id, reaction_roles):
        self.reactionrole_cog = reactionrole_cog
        self.ctx = ctx
        self.message_id = message_id
        self.reaction_roles = reaction_roles
        
        options = []
        for rr in reaction_roles:
            emoji = rr['emoji']
            role = ctx.guild.get_role(rr['role_id'])
            role_name = role.name if role else "Unknown Role"
            # Handle custom emojis properly in dropdown
            select_emoji = None
            if emoji.startswith('<') and emoji.endswith('>'):
                # Custom emoji format: <:name:id> or <a:name:id>
                emoji_parts = emoji.strip('<>').split(':')
                if len(emoji_parts) >= 3:
                    try:
                        emoji_id = int(emoji_parts[-1])
                        select_emoji = discord.PartialEmoji(name=emoji_parts[1], id=emoji_id)
                    except:
                        select_emoji = None
            # Process emoji for display - show only the emoji, not the full format
            display_emoji = emoji
            if emoji.startswith('<') and emoji.endswith('>') and select_emoji:
                # For custom emojis, show only the emoji without the <:name:id> format
                display_emoji = str(select_emoji)
            elif emoji.startswith('<') and emoji.endswith('>'):
                # If we couldn't create a PartialEmoji, try to extract just the emoji part
                emoji_parts = emoji.strip('<>').split(':')
                if len(emoji_parts) >= 3:
                    try:
                        emoji_id = int(emoji_parts[-1])
                        temp_emoji = discord.PartialEmoji(name=emoji_parts[1], id=emoji_id)
                        display_emoji = str(temp_emoji)
                    except:
                        # If all else fails, show just the emoji name
                        display_emoji = emoji_parts[1] if len(emoji_parts) >= 2 else emoji
            
            options.append(discord.SelectOption(
                label=f"{role_name}",
                value=f"{rr['id']}",
                description=f"Role ID: {rr['role_id']}",
                emoji=select_emoji if select_emoji else emoji
            ))
        
        super().__init__(
            placeholder="Select reaction role to edit...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_id = self.values[0]
            selected_rr = next((rr for rr in self.reaction_roles if str(rr['id']) == selected_id), None)
            
            if not selected_rr:
                embed = discord.Embed(
                    title="❌ **Error**",
                    description="Could not find the selected reaction role.",
                    color=0xE74C3C
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Show modal for editing
            modal = ReactionRoleEditModal(
                self.reactionrole_cog, 
                self.ctx, 
                self.message_id, 
                selected_rr
            )
            # Send modal using the proper method
            await interaction.response.send_modal(modal)
        except Exception as e:
            embed = discord.Embed(
                title="❌ **Error**",
                description=f"An error occurred: {str(e)}",
                color=0xE74C3C
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class ReactionRoleEditEmojiSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        
        # Common emojis for reaction roles
        emojis = ["😀", "😂", "🥰", "😎", "🤩", "🥳", "😍", "🤗", "🤔", "🙄", 
                 "😔", "😴", "🥳", "🔥", "💯", "✅", "❌", "❤️", "💙", "💚",
                 "💛", "💜", "🧡", "🖤", "🤍", "🤎", "💔", "❣️", "💕", "💞",
                 "💓", "💗", "💖", "💘", "💝", "💟", "☮️", "✝️", "☪️", "🕉️",
                 "☸️", "✡️", "🔯", "🕎", "☯️", "☦️", "🛐", "⛎", "♈", "♉"]
        
        options = []
        for emoji in emojis[:25]:  # Limit to 25 options
            options.append(discord.SelectOption(
                label=emoji,
                value=emoji,
                emoji=emoji
            ))
        
        super().__init__(
            placeholder="Select new emoji...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.view:
            self.view.new_emoji = self.values[0]
            if hasattr(self.view, 'update_preview'):
                await self.view.update_preview(interaction)

class ReactionRoleEditRoleSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        
        # Get roles (limit to 25 for select menu)
        roles = [role for role in ctx.guild.roles if role.name != "@everyone"]
        roles = sorted(roles, key=lambda r: r.position, reverse=True)[:25]
        
        options = []
        for role in roles:
            options.append(discord.SelectOption(
                label=role.name,
                value=str(role.id),
                description=f"Position: {role.position}"
            ))
        
        super().__init__(
            placeholder="Select new role...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.view:
            self.view.new_role_id = int(self.values[0])
            if hasattr(self.view, 'update_preview'):
                await self.view.update_preview(interaction)


class ReactionRoleEditModal(discord.ui.Modal, title="Edit Reaction Role"):
    def __init__(self, reactionrole_cog, ctx, message_id, selected_rr):
        super().__init__()
        self.reactionrole_cog = reactionrole_cog
        self.ctx = ctx
        self.message_id = message_id
        self.selected_rr = selected_rr
        
        # Pre-fill current values
        self.emoji = discord.ui.TextInput(
            label="Emoji",
            placeholder="Enter emoji or custom emoji ID",
            default=selected_rr['emoji'],
            required=True,
            max_length=100
        )
        
        # Get current role for default value
        current_role = ctx.guild.get_role(selected_rr['role_id'])
        current_role_name = str(selected_rr['role_id']) if current_role else str(selected_rr['role_id'])
        
        self.role_id = discord.ui.TextInput(
            label="Role ID",
            placeholder="Enter role ID",
            default=current_role_name,
            required=True,
            max_length=25
        )
        
        self.add_item(self.emoji)
        self.add_item(self.role_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Acknowledge the interaction immediately
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate emoji
            new_emoji = self.emoji.value.strip()
            
            # Validate role ID
            try:
                new_role_id = int(self.role_id.value.strip())
                new_role = interaction.guild.get_role(new_role_id) if interaction.guild else None
                if not new_role:
                    embed = discord.Embed(
                        title="❌ Invalid role ID",
                        description="Please provide a valid role ID.",
                        color=0xE74C3C
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                if interaction.guild and interaction.guild.me and new_role >= interaction.guild.me.top_role:
                    embed = discord.Embed(
                        title="❌ Role Too High",
                        description="I cannot assign this role as it's higher than or equal to my highest role.",
                        color=0xE74C3C
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                    
                if new_role.is_default():
                    embed = discord.Embed(
                        title="❌ Invalid Role",
                        description="You cannot use the @everyone role as a reaction role.",
                        color=0xE74C3C
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid role ID",
                    description="Please provide a numeric role ID.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Update in database
            await self.reactionrole_cog.update_reaction_role(
                self.selected_rr['id'], # This should be the OID string
                new_emoji,
                new_role_id
            )
            
            # Update reaction on message
            try:
                if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                    message = await interaction.channel.fetch_message(self.message_id)
                    # Remove old reaction
                    await message.clear_reaction(self.selected_rr['emoji'])
                    # Add new reaction
                    await message.add_reaction(new_emoji)
            except:
                pass  # Ignore if we can't update reactions
            
            embed = discord.Embed(
                title="✅ **Reaction Role Updated**",
                description=f"Successfully updated reaction role!\n\n"
                           f"**Message ID:** `{self.message_id}`\n"
                           f"**Old Emoji:** {self.selected_rr['emoji']} → **New Emoji:** {new_emoji}\n"
                           f"**Old Role:** <@&{self.selected_rr['role_id']}> → **New Role:** {new_role.mention}",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Updated by {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ **Error**",
                description=f"An error occurred: {str(e)}",
                color=0xE74C3C
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class ReactionRoleEditView(discord.ui.View):
    def __init__(self, reactionrole_cog, ctx, message_id, reaction_roles):
        super().__init__(timeout=300)
        self.reactionrole_cog = reactionrole_cog
        self.ctx = ctx
        self.message_id = message_id
        self.reaction_roles = reaction_roles
        
        # Add the initial select menu
        self.add_item(ReactionRoleEditSelect(reactionrole_cog, ctx, message_id, reaction_roles))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You can't interact with this menu!", ephemeral=True)
            return False
        return True

class ReactionRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = 0x9B59B6  # Purple color
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.rr_coll = None
        self.bot.loop.create_task(self.setup_database())

    async def setup_database(self):
        if not self.mongo_uri:
            print("MONGO_URI not found!")
            return

        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_database()
        self.rr_coll = self.db.reaction_roles
        
        await self.rr_coll.create_index([("guild_id", 1), ("message_id", 1), ("emoji", 1)], unique=True)
        print("ReactionRole Cog MongoDB Connected")

    async def add_reaction_role(self, guild_id: int, message_id: int, emoji: str, role_id: int):
        await self.rr_coll.update_one(
            {"guild_id": guild_id, "message_id": message_id, "emoji": emoji},
            {"$set": {"guild_id": guild_id, "message_id": message_id, "emoji": emoji, "role_id": role_id}},
            upsert=True
        )

    async def get_reaction_roles_for_message(self, guild_id: int, message_id: int):
        cursor = self.rr_coll.find({"guild_id": guild_id, "message_id": message_id})
        rows = await cursor.to_list(length=None)
        return [
            {
                "id": str(row["_id"]),
                "guild_id": row["guild_id"],
                "message_id": row["message_id"],
                "emoji": row["emoji"],
                "role_id": row["role_id"]
            }
            for row in rows
        ]

    async def remove_reaction_role(self, rr_id: str):
        try:
            await self.rr_coll.delete_one({"_id": ObjectId(rr_id)})
        except Exception:
            pass

    async def remove_all_reaction_roles_for_message(self, guild_id: int, message_id: int):
        await self.rr_coll.delete_many({"guild_id": guild_id, "message_id": message_id})

    async def update_reaction_role(self, rr_id: str, new_emoji: str, new_role_id: int):
        try:
            await self.rr_coll.update_one(
                {"_id": ObjectId(rr_id)},
                {"$set": {"emoji": new_emoji, "role_id": new_role_id}}
            )
        except Exception:
            pass

    async def process_emoji(self, ctx, emoji_input: str):
        """Process emoji input to handle both standard and custom emojis"""
        # Check if it's a custom emoji (in format <:name:id> or <a:name:id>)
        custom_emoji_pattern = r'<(a)?:([a-zA-Z0-9_]+):([0-9]+)>'
        match = re.match(custom_emoji_pattern, emoji_input)
        
        if match:
            # It's a custom emoji, extract the ID
            emoji_id = match.group(3)
            # Try to get the emoji from the bot's known emojis
            emoji = discord.utils.get(self.bot.emojis, id=int(emoji_id))
            if emoji:
                return str(emoji)
            else:
                # If we can't find the emoji, use the full format
                return emoji_input
        else:
            # It's a standard emoji or emoji ID
            return emoji_input

    async def format_emoji_for_display(self, emoji_str: str):
        """Format emoji for proper display in dropdowns and UI"""
        # If it's already a custom emoji object, return as is
        if isinstance(emoji_str, discord.Emoji) or isinstance(emoji_str, discord.PartialEmoji):
            return emoji_str
        
        # Check if it's a custom emoji format
        custom_emoji_pattern = r'<(a)?:([a-zA-Z0-9_]+):([0-9]+)>'
        match = re.match(custom_emoji_pattern, emoji_str)
        
        if match:
            # It's a custom emoji, create PartialEmoji object
            animated = bool(match.group(1))
            name = match.group(2)
            emoji_id = int(match.group(3))
            return discord.PartialEmoji(name=name, id=emoji_id, animated=animated)
        else:
            # It's a standard emoji
            return emoji_str

    async def get_reaction_role(self, guild_id: int, message_id: int, emoji: str):
        row = await self.rr_coll.find_one({"guild_id": guild_id, "message_id": message_id, "emoji": emoji})
        return row["role_id"] if row else None

    async def get_reaction_role_by_id(self, guild_id: int, message_id: int, emoji_id: int):
        """Get reaction role by custom emoji ID"""
        # Try finding emoji ending with :{emoji_id}> or containing :{emoji_id}>
        # Using regex to simulate LIKE queries
        
        # Regex for LIKE '%:{}>' -> means ends with :{emoji_id}>
        # Regex for LIKE '%{}%' -> means contains {emoji_id}
        
        # Priority 1: Exact match format often used for custom emojis in discord: <:name:id>
        # We look for something ending in :{emoji_id}>
        row = await self.rr_coll.find_one({
            "guild_id": guild_id, 
            "message_id": message_id, 
            "emoji": {"$regex": f":{emoji_id}>$"}
        })
        if row:
            return row["role_id"]
            
        # Priority 2: Partial match (contains ID)
        row = await self.rr_coll.find_one({
            "guild_id": guild_id, 
            "message_id": message_id, 
            "emoji": {"$regex": str(emoji_id)}
        })
        return row["role_id"] if row else None

    # Main reactionrole group command
    @commands.hybrid_group(
        name="reactionrole",
        aliases=["rr"],
        description="⚙️ Reaction role management system"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_roles=True)
    async def reactionrole(self, ctx):
        """Reaction role command group"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="⚙️ **Reaction Role System**",
                description=(
                    "Manage reaction roles for your server.\n\n"
                    "**Available Commands:**\n"
                    "• `/reactionrole add <message_id> <emoji> <role>` - Add a reaction role\n"
                    "• `/reactionrole remove <message_id>` - Remove a reaction role\n"
                    "• `/reactionrole reset <message_id>` - Remove all reaction roles from a message\n"
                    "• `/reactionrole edit <message_id>` - Edit a reaction role\n\n"
                    "📌 **How it works:**\n"
                    "Users can react to messages to get roles automatically!"
                ),
                color=self.color,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Server: {ctx.guild.name}")
            await ctx.send(embed=embed, ephemeral=True)

    # Add subcommand - /reactionrole add
    @reactionrole.command(
        name="add",
        description="➕ Add a reaction role to a message"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_roles=True)
    async def add(self, ctx, message_id: str, emoji: str, role: discord.Role):
        """Add a reaction role to a message"""
        # Validate message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            embed = discord.Embed(
                title="❌ **Invalid Message ID**",
                description="Please provide a valid numeric message ID.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
            
        # Check if role is manageable
        if role >= ctx.guild.me.top_role:
            embed = discord.Embed(
                title="❌ **Role Too High**",
                description="I cannot assign this role as it's higher than or equal to my highest role.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
            
        if role.is_default():
            embed = discord.Embed(
                title="❌ **Invalid Role**",
                description="You cannot use the @everyone role as a reaction role.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Process custom emojis
        processed_emoji = await self.process_emoji(ctx, emoji)
        if processed_emoji is None:
            return  # Error message already sent
        
        # Check if this reaction role already exists
        existing_role_id = await self.get_reaction_role(ctx.guild.id, msg_id, processed_emoji)
        if existing_role_id:
            existing_role = ctx.guild.get_role(existing_role_id)
            embed = discord.Embed(
                title="❌ **Already Exists**",
                description=f"A reaction role with this emoji already exists for this message!\n\n"
                           f"**Current Role:** {existing_role.mention if existing_role else 'Unknown Role'}",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        try:
            # Get the message
            if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                message = await ctx.channel.fetch_message(msg_id)
            else:
                embed = discord.Embed(
                    title="❌ **Invalid Channel**",
                    description="This command can only be used in text channels or threads.",
                    color=0xE74C3C
                )
                return await ctx.send(embed=embed, ephemeral=True)
            
            # Add reaction to the message
            await message.add_reaction(processed_emoji)
            
            # Save to database
            await self.add_reaction_role(
                ctx.guild.id, 
                msg_id, 
                processed_emoji, 
                role.id
            )
            
            embed = discord.Embed(
                title="✅ **Reaction Role Added**",
                description=f"Successfully added reaction role to message!\n\n"
                           f"**Message ID:** `{msg_id}`\n"
                           f"**Emoji:** {processed_emoji}\n"
                           f"**Role:** {role.mention}",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Added by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except discord.NotFound:
            embed = discord.Embed(
                title="❌ **Message Not Found**",
                description="Could not find a message with that ID in this channel.",
                color=0xE74C3C
            )
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ **Error**",
                description=f"An error occurred: {str(e)}",
                color=0xE74C3C
            )
            await ctx.send(embed=embed, ephemeral=True)

    # Remove subcommand - /reactionrole remove
    @reactionrole.command(
        name="remove",
        description="➖ Remove a reaction role from a message"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_roles=True)
    async def remove(self, ctx, message_id: str):
        """Remove a reaction role from a message"""
        # Validate message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            embed = discord.Embed(
                title="❌ **Invalid Message ID**",
                description="Please provide a valid numeric message ID.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
            
        # Get all reaction roles for this message
        reaction_roles = await self.get_reaction_roles_for_message(ctx.guild.id, msg_id)
        
        if not reaction_roles:
            embed = discord.Embed(
                title="❌ **No Reaction Roles**",
                description=f"No reaction roles found for message `{msg_id}`.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Show selection menu
        embed = discord.Embed(
            title="🗑️ **Remove Reaction Role**",
            description=f"Select which reaction role to remove from message `{msg_id}`:",
            color=0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        
        view = ReactionRoleRemoveView(self, ctx, msg_id, reaction_roles)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    # Reset subcommand - /reactionrole reset
    @reactionrole.command(
        name="reset",
        description="🗑️ Remove all reaction roles from a message"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_roles=True)
    async def reset(self, ctx, message_id: str):
        """Remove all reaction roles from a message"""
        # Validate message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            embed = discord.Embed(
                title="❌ **Invalid Message ID**",
                description="Please provide a valid numeric message ID.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
            
        # Get all reaction roles for this message
        reaction_roles = await self.get_reaction_roles_for_message(ctx.guild.id, msg_id)
        
        if not reaction_roles:
            embed = discord.Embed(
                title="❌ **No Reaction Roles**",
                description=f"No reaction roles found for message `{msg_id}`.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Show confirmation
        embed = discord.Embed(
            title="⚠️ **Confirm Reset**",
            description=f"Are you sure you want to remove **all** reaction roles from message `{msg_id}`?\n\n"
                       f"**This will remove {len(reaction_roles)} reaction role(s)!**\n\n"
                       f"This action cannot be undone!",
            color=0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Click a button to confirm or cancel")
        
        view = ReactionRoleResetConfirmView(self, ctx, msg_id)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    # Edit subcommand - /reactionrole edit
    @reactionrole.command(
        name="edit",
        description="✏️ Edit a reaction role for a message"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_roles=True)
    async def edit(self, ctx, message_id: str):
        """Edit a reaction role for a message"""
        # Validate message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            embed = discord.Embed(
                title="❌ **Invalid Message ID**",
                description="Please provide a valid numeric message ID.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
            
        # Get all reaction roles for this message
        reaction_roles = await self.get_reaction_roles_for_message(ctx.guild.id, msg_id)
        
        if not reaction_roles:
            embed = discord.Embed(
                title="❌ **No Reaction Roles**",
                description=f"No reaction roles found for message `{msg_id}`.",
                color=0xE74C3C
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Show selection menu
        embed = discord.Embed(
            title="✏️ **Edit Reaction Role**",
            description=f"Select which reaction role to edit for message `{msg_id}`:",
            color=0x3498DB,
            timestamp=datetime.datetime.utcnow()
        )
        
        view = ReactionRoleEditView(self, ctx, msg_id, reaction_roles)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    # Event listeners
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role assignment"""
        if payload.user_id == self.bot.user.id:
            return
            
        if not payload.guild_id:
            return
            
        # Process emoji for custom emojis
        emoji_str = str(payload.emoji)
        
        # Get the role for this reaction
        role_id = await self.get_reaction_role(payload.guild_id, payload.message_id, emoji_str)
        if not role_id:
            return
            
        # Get guild and member
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
            
        member = guild.get_member(payload.user_id)
        if not member:
            return
            
        # Get role
        role = guild.get_role(role_id)
        if not role:
            return
            
        # Check if member already has role
        if role in member.roles:
            return
            
        # Add role
        try:
            await member.add_roles(role, reason="Reaction Role")
            
            # Silently assign role without notification
        except discord.Forbidden:
            pass  # Missing permissions
        except discord.HTTPException:
            pass  # Failed to assign role

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role removal"""
        if payload.user_id == self.bot.user.id:
            return
            
        if not payload.guild_id:
            return
            
        # Process emoji for custom emojis
        emoji_str = str(payload.emoji)
        
        # Get the role for this reaction
        role_id = await self.get_reaction_role(payload.guild_id, payload.message_id, emoji_str)
        if not role_id:
            return
            
        # Get guild and member
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
            
        member = guild.get_member(payload.user_id)
        if not member:
            return
            
        # Get role
        role = guild.get_role(role_id)
        if not role:
            return
            
        # Check if member has role
        if role not in member.roles:
            return
            
        # Remove role
        try:
            await member.remove_roles(role, reason="Reaction Role Removed")
            
            # Silently remove role without notification
        except discord.Forbidden:
            pass  # Missing permissions
        except discord.HTTPException:
            pass  # Failed to remove role

    # Error handlers
    @reactionrole.error
    @add.error
    @remove.error
    @reset.error
    @edit.error
    async def reactionrole_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ **Permission Denied**",
                description=(
                    "You need **Manage Roles** permission to use reaction role commands!\n\n"
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
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ **Invalid Argument**",
                description="Please check your command arguments and try again.",
                color=0xE74C3C
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ **Missing Argument**",
                description="Please provide all required arguments for this command.",
                color=0xE74C3C
            )
            await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ReactionRole(bot))