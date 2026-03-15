import discord
import json
import os
import motor.motor_asyncio
from datetime import datetime
from discord.ext import commands
from discord.ext.commands import hybrid
from discord.ui import View, button, Button, Select, Modal, TextInput
from typing import List

# Helper functions moved to Cog class as methods

def save_guild_data(guild_id: str, join_channel_id: int, category_id: int, interface_id: int):
    """Save guild setup data to database"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO guild_settings 
        (guild_id, join_channel_id, category_id, interface_id)
        VALUES (?, ?, ?, ?)
    ''', (guild_id, join_channel_id, category_id, interface_id))
    
    conn.commit()
    conn.close()

def load_guild_data(guild_id: str):
    """Load guild setup data from database"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return {
            "join_channel_id": result[1],
            "category_id": result[2],
            "interface_id": result[3]
        }
    return {}

def save_user_settings(user_id: int, guild_id: str, vc_name = None, user_limit = None, rtc_region = None):
    """Save user VC settings to database"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    fields = []
    values = []
    
    if vc_name is not None:
        fields.append("vc_name = ?")
        values.append(vc_name)
    
    if user_limit is not None:
        fields.append("user_limit = ?")
        values.append(user_limit)
        
    if rtc_region is not None:
        fields.append("rtc_region = ?")
        values.append(rtc_region)
    
    if fields:
        values.extend([user_id, guild_id])
        query = f'''
            INSERT OR REPLACE INTO user_vc_settings 
            (user_id, guild_id, {', '.join([field.split(' = ')[0] for field in fields])})
            VALUES (?, ?, {', '.join(['?' for _ in fields])})
        '''
        cursor.execute(query, values)
    else:
        cursor.execute('''
            INSERT OR IGNORE INTO user_vc_settings 
            (user_id, guild_id, vc_name, user_limit, rtc_region)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, guild_id, f"<@{user_id}>'s VC", 0, None))
    
    conn.commit()
    conn.close()

def load_user_settings(user_id: int, guild_id: str):
    """Load user VC settings from database"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT vc_name, user_limit, rtc_region 
        FROM user_vc_settings 
        WHERE user_id = ? AND guild_id = ?
    ''', (user_id, guild_id))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "vc_name": result[0],
            "user_limit": result[1],
            "rtc_region": result[2]
        }
    return None

def save_vc_permissions(vc_id: int, owner_id: int, is_locked: bool = False, is_hidden: bool = False):
    """Save VC permissions to database"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO vc_permissions 
        (vc_id, owner_id, is_locked, is_hidden)
        VALUES (?, ?, ?, ?)
    ''', (vc_id, owner_id, int(is_locked), int(is_hidden)))
    
    conn.commit()
    conn.close()

def load_vc_permissions(vc_id: int):
    """Load VC permissions from database"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    cursor.execute('SELECT owner_id, is_locked, is_hidden FROM vc_permissions WHERE vc_id = ?', (vc_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return {
            "owner_id": result[0],
            "is_locked": bool(result[1]),
            "is_hidden": bool(result[2])
        }
    return None

def block_user(guild_id: str, vc_owner_id: int, user_id: int):
    """Block a user from joining a specific temp VC"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO blocked_users (guild_id, vc_owner_id, user_id)
        VALUES (?, ?, ?)
    ''', (guild_id, vc_owner_id, user_id))
    
    conn.commit()
    conn.close()

def unblock_user(guild_id: str, vc_owner_id: int, user_id: int):
    """Unblock a user from joining a specific temp VC"""
    conn = sqlite3.connect("db/tempvc.db")
    cursor = conn.cursor()
    


class NameModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Rename Voice Channel")
        self.vc_control = vc_control
        
        self.name = TextInput(
            label="New Name",
            placeholder="Enter new voice channel name",
            required=True,
            min_length=1,
            max_length=100
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            await self.vc_control.vc.edit(name=self.name.value)
            await self.vc_control.cog.save_user_settings(interaction.user.id, str(interaction.guild.id), vc_name=self.name.value)
            await interaction.response.send_message(f"<:yes:1396838746862784582> Channel renamed to {self.name.value}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:no:1396838761605890090> Error renaming channel: {e}", ephemeral=True)

class LimitModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Set User Limit")
        self.vc_control = vc_control
        
        self.limit = TextInput(
            label="User Limit",
            placeholder="Enter a number between 0-99 (0 for unlimited)",
            required=True,
            min_length=1,
            max_length=2
        )
        self.add_item(self.limit)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            limit = int(self.limit.value)
            if limit < 0 or limit > 99:
                await interaction.response.send_message("<a:alert:1396429026842644584> Limit must be between 0-99", ephemeral=True)
                return
                
            await self.vc_control.vc.edit(user_limit=limit)
            await self.vc_control.cog.save_user_settings(interaction.user.id, str(interaction.guild.id), user_limit=limit)
            await interaction.response.send_message(f"<:yes:1396838746862784582> User limit set to {limit if limit > 0 else 'unlimited'}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid number", ephemeral=True)

class TransferModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Transfer Ownership")
        self.vc_control = vc_control
        
        self.user_id = TextInput(
            label="User ID",
            placeholder="Enter the ID of the user to transfer ownership to",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            user_id = int(self.user_id.value)
            member = interaction.guild.get_member(user_id)
            
            if not member or member.bot:
                await interaction.response.send_message("<a:alert:1396429026842644584> Invalid user ID or user is a bot", ephemeral=True)
                return
                
            await self.vc_control.cog.save_vc_permissions(self.vc_control.vc.id, user_id)
            await self.vc_control.vc.set_permissions(member, manage_channels=True, connect=True)
            await interaction.response.send_message(f"<:syowner:1446125485066158172> VC ownership transferred to {member.mention}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)

# [Continue with all Select and View classes - keeping them exactly as they are]
# I'm including the key ones here, add the rest from your original code

class PrivacySelect(Select):
    def __init__(self, vc_control):
        self.vc_control = vc_control
        options = [
            discord.SelectOption(label="Lock", description="Prevent others from joining", emoji="<:sylock:1446126662411485224>"),
            discord.SelectOption(label="Unlock", description="Allow everyone to join", emoji="<:syunlock:1446126652835758281>"),
            discord.SelectOption(label="Hide", description="Hide the channel", emoji="<:syhide:1446126681692836044>"),
            discord.SelectOption(label="Unhide", description="Make channel visible", emoji="<:syunhide:1446126671676706938>"),
        ]
        super().__init__(placeholder="Select privacy option...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        choice = self.values[0]
        
        if choice == "Lock":
            await self.vc_control.vc.set_permissions(interaction.guild.default_role, connect=False)
            trusted_users = await self.vc_control.cog.get_trusted_users(self.vc_control.vc.id)
            for user_id in trusted_users:
                trusted_member = interaction.guild.get_member(user_id)
                if trusted_member:
                    await self.vc_control.vc.set_permissions(trusted_member, connect=True)
            vc_perms = await self.vc_control.cog.load_vc_permissions(self.vc_control.vc.id)
            if vc_perms:
                await self.vc_control.cog.save_vc_permissions(self.vc_control.vc.id, vc_perms["owner_id"], is_locked=True, is_hidden=vc_perms["is_hidden"])
            await interaction.response.send_message("<:sylock:1446126662411485224> Channel locked!", ephemeral=True)
        elif choice == "Unlock":
            await self.vc_control.vc.set_permissions(interaction.guild.default_role, connect=True)
            vc_perms = await self.vc_control.cog.load_vc_permissions(self.vc_control.vc.id)
            if vc_perms:
                await self.vc_control.cog.save_vc_permissions(self.vc_control.vc.id, vc_perms["owner_id"], is_locked=False, is_hidden=vc_perms["is_hidden"])
            await interaction.response.send_message("<:syunlock:1446126652835758281> Channel unlocked!", ephemeral=True)
        elif choice == "Hide":
            await self.vc_control.vc.set_permissions(interaction.guild.default_role, view_channel=False)
            trusted_users = await self.vc_control.cog.get_trusted_users(self.vc_control.vc.id)
            for user_id in trusted_users:
                trusted_member = interaction.guild.get_member(user_id)
                if trusted_member:
                    await self.vc_control.vc.set_permissions(trusted_member, view_channel=True)
            vc_perms = await self.vc_control.cog.load_vc_permissions(self.vc_control.vc.id)
            if vc_perms:
                await self.vc_control.cog.save_vc_permissions(self.vc_control.vc.id, vc_perms["owner_id"], is_locked=vc_perms["is_locked"], is_hidden=True)
            await interaction.response.send_message("<:syhide:1446126681692836044> Channel hidden!", ephemeral=True)
        elif choice == "Unhide":
            await self.vc_control.vc.set_permissions(interaction.guild.default_role, view_channel=True)
            vc_perms = await self.vc_control.cog.load_vc_permissions(self.vc_control.vc.id)
            if vc_perms:
                await self.vc_control.cog.save_vc_permissions(self.vc_control.vc.id, vc_perms["owner_id"], is_locked=vc_perms["is_locked"], is_hidden=False)
            await interaction.response.send_message("<:syunhide:1446126671676706938> Channel visible again!", ephemeral=True)

class PrivacyView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        self.add_item(PrivacySelect(vc_control))

class KickModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Kick User")
        self.vc_control = vc_control
        
        self.user_id = TextInput(
            label="User ID",
            placeholder="Enter the ID of the user to kick",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        if len(self.vc_control.vc.members) < 2:
            await interaction.response.send_message("<a:alert:1396429026842644584> Your VC should at least have 2 members!", ephemeral=True)
            return
            
        try:
            member_id = int(self.user_id.value)
            member = interaction.guild.get_member(member_id)
            
            if member and member in self.vc_control.vc.members:
                await member.move_to(None)
                await interaction.response.send_message(f"<:sykick:1446128068044259443> {member.mention} has been kicked from the VC", ephemeral=True)
            else:
                await interaction.response.send_message("<a:alert:1396429026842644584> User not found in this server or not in VC", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)

class KickView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

class RegionSelect(Select):
    def __init__(self, vc_control):
        self.vc_control = vc_control
        # Updated with valid Discord regions
        regions = [
            "brazil", "hongkong", "india", "japan", 
            "rotterdam", "singapore", "south-korea", "southafrica",
            "sydney", "us-central", "us-east", "us-south", "us-west"
        ]
        
        options = [
            discord.SelectOption(label=region.replace("-", " ").title(), value=region)
            for region in regions
        ][:25]
        
        super().__init__(placeholder="Select voice region...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            region_value = self.values[0]
            await self.vc_control.vc.edit(rtc_region=region_value)
            await self.vc_control.cog.save_user_settings(interaction.user.id, str(interaction.guild.id), rtc_region=region_value)
            await interaction.response.send_message(f"<:syregion:1446128207563591691> Voice region changed to {region_value.replace('-', ' ').title()}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:no:1396838761605890090> Error changing region: {e} report this to us use /report.", ephemeral=True)

class RegionView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        self.add_item(RegionSelect(vc_control))

class BlockModal(Modal):
    def __init__(self, vc_control, block=True):
        action = "Block" if block else "Unblock"
        super().__init__(title=f"{action} User")
        self.vc_control = vc_control
        self.block = block
        
        self.user_id = TextInput(
            label="User ID",
            placeholder=f"Enter the ID of the user to {action.lower()}",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            member_id = int(self.user_id.value)
            member = interaction.guild.get_member(member_id)
            
            if not member or member.bot:
                await interaction.response.send_message("<a:alert:1396429026842644584> User not found in this server or is a bot", ephemeral=True)
                return
                
            guild_id = str(interaction.guild.id)
                
            if self.block:
                await self.vc_control.cog.block_user(guild_id, interaction.user.id, member_id)
                if member in self.vc_control.vc.members:
                    await member.move_to(None)
                
                # Hide only this specific VC from the blocked user
                try:
                    await self.vc_control.vc.set_permissions(member, view_channel=False)
                except:
                    pass
                
                await interaction.response.send_message(f"<:syblock:1446125578016260097> {member.mention} has been blocked from your VC", ephemeral=True)
            else:
                await self.vc_control.cog.unblock_user(guild_id, interaction.user.id, member_id)
                # Reveal only this specific VC to the unblocked user
                try:
                    await self.vc_control.vc.set_permissions(member, overwrite=None)
                except:
                    pass
                await interaction.response.send_message(f"<:yes:1396838746862784582> {member.mention} has been unblocked from your VC", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)

class BlockView(View):
    def __init__(self, vc_control, block=True):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

class TrustModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Trust User")
        self.vc_control = vc_control
        
        self.user_id = TextInput(
            label="User ID",
            placeholder="Enter the ID of the user to trust",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            member_id = int(self.user_id.value)
            member = interaction.guild.get_member(member_id)
            
            if not member or member.bot:
                await interaction.response.send_message("<a:alert:1396429026842644584> User not found in this server or is a bot", ephemeral=True)
                return
                
            await self.vc_control.cog.save_trusted_user(self.vc_control.vc.id, member_id)
            
            # Allow trusted user to connect and view the VC
            await self.vc_control.vc.set_permissions(member, connect=True, view_channel=True)
            
            await interaction.response.send_message(f"<:sytrust:1446125534621863946> {member.mention} has been trusted for this VC", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:no:1396838761605890090> Error trusting user: {e}", ephemeral=True)

class TrustView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

class UntrustModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Untrust User")
        self.vc_control = vc_control
        
        self.user_id = TextInput(
            label="User ID",
            placeholder="Enter the ID of the user to untrust",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            member_id = int(self.user_id.value)
            member = interaction.guild.get_member(member_id)
            
            if not member or member.bot:
                await interaction.response.send_message("<a:alert:1396429026842644584> User not found in this server or is a bot", ephemeral=True)
                return
                
            await self.vc_control.cog.remove_trusted_user(self.vc_control.vc.id, member_id)
            
            # Check if user is blocked by the VC owner, if so hide the VC from them
            guild_id = str(interaction.guild.id)
            if await self.vc_control.cog.is_user_blocked(guild_id, interaction.user.id, member_id):
                await self.vc_control.vc.set_permissions(member, view_channel=False)
            else:
                await self.vc_control.vc.set_permissions(member, overwrite=None)
                
            await interaction.response.send_message(f"<:no:1396838761605890090> {member.mention} has been untrusted for this VC", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:no:1396838761605890090> Error untrusting user: {e}", ephemeral=True)

class UntrustView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

class InviteModal(Modal):
    def __init__(self, vc_control):
        super().__init__(title="Invite User")
        self.vc_control = vc_control
        
        self.user_id = TextInput(
            label="User ID",
            placeholder="Enter the ID of the user to invite",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            member_id = int(self.user_id.value)
            member = interaction.guild.get_member(member_id)
            
            if not member or member.bot:
                await interaction.response.send_message("<a:alert:1396429026842644584> User not found in this server or is a bot", ephemeral=True)
                return
                
            embed = discord.Embed(
                title="🎙️ Temp VC Invite",
                description=f"{interaction.user.mention} has invited you to join their temporary voice channel: {self.vc_control.vc.mention}",
                color=0x2f3136
            )
            
            view = InviteActionView(interaction.user.id, member_id, self.vc_control.vc.id)
            
            try:
                await member.send(embed=embed, view=view)
                await interaction.response.send_message(f"<:yes:1396838746862784582> Invite sent to {member.mention}", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(f"<:no:1396838761605890090> Could not send invite to {member.mention}. They may have DMs disabled.", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)

class InviteView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

class InviteActionView(View):
    def __init__(self, inviter_id: int, invitee_id: int, vc_id: int):
        super().__init__(timeout=300)
        self.inviter_id = inviter_id
        self.invitee_id = invitee_id
        self.vc_id = vc_id

    @button(label="Block this user Invites", style=discord.ButtonStyle.secondary)
    async def disable_invites(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.invitee_id:
            await interaction.response.send_message("<:no:1396838761605890090> You don't have permission to use this button.", ephemeral=True)
            return
            
        await interaction.response.send_message("<:yes:1396838746862784582> You will no longer receive invites from this user.", ephemeral=True)
        self.stop()

    @button(label="Block All Invites", style=discord.ButtonStyle.danger)
    async def block_all_invites(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.invitee_id:
            await interaction.response.send_message("<:no:1396838761605890090> You don't have permission to use this button.", ephemeral=True)
            return
            
        await interaction.response.send_message("<:yes:1396838746862784582> You will no longer receive any temp VC invites.", ephemeral=True)
        self.stop()

class MuteModal(Modal):
    def __init__(self, vc_control, mute=True):
        action = "Mute" if mute else "Unmute"
        super().__init__(title=f"{action} User")
        self.vc_control = vc_control
        self.mute = mute
        
        self.user_id = TextInput(
            label="User ID",
            placeholder=f"Enter the ID of the user to {action.lower()}",
            required=True,
            min_length=1,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        try:
            member_id = int(self.user_id.value)
            member = interaction.guild.get_member(member_id)
            
            if not member or member.bot:
                await interaction.response.send_message("<a:alert:1396429026842644584> User not found in this server or is a bot", ephemeral=True)
                return
                
            if member not in self.vc_control.vc.members:
                await interaction.response.send_message("<a:alert:1396429026842644584> That user is not in your VC", ephemeral=True)
                return
                
            if self.mute:
                await member.edit(mute=True, reason="Muted by VC owner")
                await interaction.response.send_message(f"<:symute:1446125563646447738> {member.mention} has been muted", ephemeral=True)
            else:
                await member.edit(mute=False, reason="Unmuted by VC owner")
                await interaction.response.send_message(f"<:syunmute:1446125549796851826> {member.mention} has been unmuted", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("<a:alert:1396429026842644584> Please enter a valid user ID", ephemeral=True)

class MuteView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

class UnmuteView(View):
    def __init__(self, vc_control):
        super().__init__(timeout=60)
        # This view is now just a placeholder since we're using modals
        pass

# THE KEY FIX: Make TempVCControlPanel properly persistent
class TempVCControlPanel(View):
    def __init__(self, cog):
        # CRITICAL: timeout=None makes the view persistent
        super().__init__(timeout=None)
        self.cog = cog
        self.vc = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.bot:
            await interaction.response.send_message("<:no:1396838761605890090> Bots cannot use this panel.", ephemeral=True)
            return False
        return True

    async def _get_user_vc(self, interaction: discord.Interaction):
        """Helper to find user's VC"""
        if not interaction.guild:
            return None
            
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    return vc
        
        for vc_id, owner_id in self.cog.owners.items():
            vc = interaction.guild.get_channel(vc_id)
            if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)) and await self.cog.is_user_trusted(vc_id, interaction.user.id):
                return vc
        
        return None

    @button(emoji="<:syname:1446125460995182673>", style=discord.ButtonStyle.secondary, custom_id="tempvc_rename")
    async def rename(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = await self._get_user_vc(interaction)
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own or aren't trusted in a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        await interaction.response.send_modal(NameModal(view))

    @button(emoji="<:sylimit:1446125472030130258>", style=discord.ButtonStyle.secondary, custom_id="tempvc_limit")
    async def limit(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = await self._get_user_vc(interaction)
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own or aren't trusted in a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        await interaction.response.send_modal(LimitModal(view))

    @button(emoji="<:syowner:1446125485066158172>", style=discord.ButtonStyle.secondary, custom_id="tempvc_transfer")
    async def transfer(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc:
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        await interaction.response.send_modal(TransferModal(view))

    @button(emoji="<:syprivacy:1446125505106677922>", style=discord.ButtonStyle.secondary, custom_id="tempvc_privacy")
    async def privacy(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = await self._get_user_vc(interaction)
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own or aren't trusted in a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        await interaction.response.send_message("Select a privacy option:", view=PrivacyView(view), ephemeral=True)

    @button(emoji="<:sytrust:1446125534621863946>", style=discord.ButtonStyle.secondary, custom_id="tempvc_trust")
    async def trust(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = TrustModal(view)
        await interaction.response.send_modal(modal)

    @button(emoji="<:syuntrust:1446125520533061732>", style=discord.ButtonStyle.secondary, custom_id="tempvc_untrust")
    async def untrust(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc:
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = UntrustModal(view)
        await interaction.response.send_modal(modal)

    @button(emoji="<:sykick:1446128068044259443>", style=discord.ButtonStyle.secondary, custom_id="tempvc_kick")
    async def kick(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, discord.VoiceChannel):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        if len(user_vc.members) < 2:
            await interaction.response.send_message("<a:alert:1396429026842644584> Your VC should at least have 2 members!", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = KickModal(view)
        await interaction.response.send_modal(modal)

    @button(emoji="<:symute:1446125563646447738>", style=discord.ButtonStyle.secondary, custom_id="tempvc_mute")
    async def mute(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = MuteModal(view, mute=True)
        await interaction.response.send_modal(modal)

    @button(emoji="<:syunmute:1446125549796851826>", style=discord.ButtonStyle.secondary, custom_id="tempvc_unmute")
    async def unmute(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        # Check if there are at least 2 members in the VC
        if len(user_vc.members) < 2:
            await interaction.response.send_message("<a:alert:1396429026842644584> Your VC should at least have 2 members!", ephemeral=True)
            return
            
        members_to_unmute = []
        if isinstance(user_vc, (discord.VoiceChannel, discord.StageChannel)):
            members_to_unmute = [member for member in user_vc.members if member.id != interaction.user.id]
        if not members_to_unmute:
            await interaction.response.send_message("<a:alert:1396429026842644584> No members to unmute in your VC.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = MuteModal(view, mute=False)
        await interaction.response.send_modal(modal)

    @button(emoji="<:syregion:1446128207563591691>", style=discord.ButtonStyle.secondary, custom_id="tempvc_region")
    async def region(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = await self._get_user_vc(interaction)
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own or aren't trusted in a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        await interaction.response.send_message("Select a voice region:", view=RegionView(view), ephemeral=True)

    @button(emoji="<:syblock:1446125578016260097>", style=discord.ButtonStyle.secondary, custom_id="tempvc_block")
    async def block(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc:
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = BlockModal(view, block=True)
        await interaction.response.send_modal(modal)

    @button(emoji="<:syunblock:1446125600745197619>", style=discord.ButtonStyle.secondary, custom_id="tempvc_unblock")
    async def unblock(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc:
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = BlockModal(view, block=False)
        await interaction.response.send_modal(modal)

    @button(emoji="<:sythread:1446125647855357992>", style=discord.ButtonStyle.secondary, custom_id="tempvc_thread")
    async def create_thread(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        guild_data = await self.cog.get_guild_data(str(interaction.guild.id))
        interface_channel_id = guild_data.get("interface_id")
        interface_channel = interaction.guild.get_channel(interface_channel_id) if interface_channel_id else None
        
        if not interface_channel or not isinstance(interface_channel, discord.TextChannel):
            await interaction.response.send_message("<a:alert:1396429026842644584> Could not find interface text channel.", ephemeral=True)
            return
            
        thread_name = f"{interaction.user.display_name}'s VC Thread"
        try:
            existing_thread = None
            for thread in interface_channel.threads:
                if thread.name == thread_name:
                    existing_thread = thread
                    break
            
            if existing_thread:
                await interaction.response.send_message(f"<:yes:1396838746862784582> Thread already exists: {existing_thread.mention}", ephemeral=True)
                return
            
            thread = await interface_channel.create_thread(
                name=thread_name[:100],
                auto_archive_duration=60,
                reason="Temp VC thread"
            )
            
            try:
                await thread.add_user(interaction.user)
            except:
                pass
            
            embed = discord.Embed(
                title="<:sythread:1446125647855357992> Temp VC Thread",
                description=f"Welcome to your private thread for {user_vc.mention}!\nUse this space to coordinate with your VC members.",
                color=discord.Color.green()
            )
            try:
                await thread.send(embed=embed, content=interaction.user.mention)
            except:
                pass
            
            await interaction.response.send_message(f"<:yes:1396838746862784582> Thread created: {thread.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:no:1396838761605890090> Error creating thread: {e}", ephemeral=True)

    @button(emoji="<:syinvite:1446125623113416857>", style=discord.ButtonStyle.secondary, custom_id="tempvc_invite")
    async def invite(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        view = TempVCControlPanel(self.cog)
        view.vc = user_vc
        modal = InviteModal(view)
        await interaction.response.send_modal(modal)

    @button(emoji="<:sydelete:1446125637172596869>", style=discord.ButtonStyle.secondary, custom_id="tempvc_delete")
    async def delete(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            await interaction.response.send_message("<a:alert:1396429026842644584> This command can only be used in a server.", ephemeral=True)
            return
            
        user_vc = None
        for vc_id, owner_id in self.cog.owners.items():
            if owner_id == interaction.user.id:
                vc = interaction.guild.get_channel(vc_id)
                if vc and isinstance(vc, (discord.VoiceChannel, discord.StageChannel)):
                    user_vc = vc
                    break
        
        if not user_vc:
            await interaction.response.send_message("<a:alert:1396429026842644584> You don't own a temporary voice channel.", ephemeral=True)
            return
            
        try:
            guild_data = await self.cog.get_guild_data(str(interaction.guild.id))
            interface_id = guild_data.get("interface_id")
            if interface_id:
                interface_channel = interaction.guild.get_channel(interface_id)
                if interface_channel and isinstance(interface_channel, discord.TextChannel):
                    for thread in interface_channel.threads:
                        owner = interaction.guild.get_member(interaction.user.id)
                        owner_name = owner.display_name if owner else "Unknown"
                        if (user_vc.name in thread.name or 
                            f"{owner_name}" in thread.name or 
                            str(user_vc.id) in thread.name):
                            try:
                                await thread.delete(reason="Associated VC deleted")
                            except:
                                pass
            
            await user_vc.delete(reason="Owner deleted VC via panel")
            await interaction.response.send_message("<:delete:1432730483556352071> VC deleted!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:no:1396838761605890090> Error deleting VC: {e}", ephemeral=True)

class TempVC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.guild_settings = None
        self.user_settings = None
        self.vc_permissions = None
        self.blocked_users = None
        self.trusted_users = None
        self.control_panels = None
        self.logs = None
        self.invites = None
        self.log_channels = None
        
        # Initialize DB
        if self.mongo_uri:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            self.db = self.mongo_client.get_database()
            self.guild_settings = self.db.tempvc_settings
            self.user_settings = self.db.tempvc_user_settings
            self.vc_permissions = self.db.tempvc_permissions
            self.blocked_users = self.db.tempvc_blocked_users
            self.trusted_users = self.db.tempvc_trusted_users
            self.control_panels = self.db.tempvc_control_panels
            self.logs = self.db.tempvc_logs
            self.invites = self.db.tempvc_invites
            self.log_channels = self.db.tempvc_log_channels
            
            self.bot.loop.create_task(self.setup_db())

        self.created_channels = {}
        self.owners = {}
        self._panels_restored = False
        print("[TempVC] Cog initialized")

    async def setup_db(self):
        # Create indexes
        await self.guild_settings.create_index("guild_id", unique=True)
        await self.user_settings.create_index([("user_id", 1), ("guild_id", 1)], unique=True)
        await self.vc_permissions.create_index("vc_id", unique=True)
        await self.blocked_users.create_index([("guild_id", 1), ("vc_owner_id", 1), ("user_id", 1)], unique=True)
        await self.trusted_users.create_index([("vc_id", 1), ("user_id", 1)], unique=True)
        await self.control_panels.create_index("guild_id", unique=True)
        await self.log_channels.create_index("guild_id", unique=True)
        print("[TempVC] MongoDB indexes created")

    # Helper Methods
    async def save_guild_data(self, guild_id: str, join_channel_id: int, category_id: int, interface_id: int):
        await self.guild_settings.update_one(
            {"guild_id": guild_id},
            {"$set": {"join_channel_id": join_channel_id, "category_id": category_id, "interface_id": interface_id}},
            upsert=True
        )

    async def get_guild_data(self, guild_id: str):
        return await self.guild_settings.find_one({"guild_id": guild_id})

    async def save_user_settings(self, user_id: int, guild_id: str, **kwargs):
        # Filter None values
        update_data = {k: v for k, v in kwargs.items() if v is not None}
        if not update_data:
            return
        await self.user_settings.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$set": update_data},
            upsert=True
        )

    async def load_user_settings(self, user_id: int, guild_id: str):
        return await self.user_settings.find_one({"user_id": user_id, "guild_id": guild_id})

    async def save_vc_permissions(self, vc_id: int, owner_id: int, is_locked: bool = None, is_hidden: bool = None):
        update_data = {"owner_id": owner_id}
        if is_locked is not None:
            update_data["is_locked"] = is_locked
        if is_hidden is not None:
            update_data["is_hidden"] = is_hidden
            
        await self.vc_permissions.update_one(
            {"vc_id": vc_id},
            {"$set": update_data},
            upsert=True
        )
    
    async def load_vc_permissions(self, vc_id: int):
        return await self.vc_permissions.find_one({"vc_id": vc_id})

    async def block_user(self, guild_id: str, vc_owner_id: int, user_id: int):
        await self.blocked_users.update_one(
            {"guild_id": guild_id, "vc_owner_id": vc_owner_id, "user_id": user_id},
            {"$set": {"timestamp": datetime.now()}},
            upsert=True
        )

    async def unblock_user(self, guild_id: str, vc_owner_id: int, user_id: int):
        await self.blocked_users.delete_one({"guild_id": guild_id, "vc_owner_id": vc_owner_id, "user_id": user_id})

    async def is_user_blocked(self, guild_id: str, vc_owner_id: int, user_id: int):
        return await self.blocked_users.find_one({"guild_id": guild_id, "vc_owner_id": vc_owner_id, "user_id": user_id}) is not None

    async def get_blocked_users(self, guild_id: str, vc_owner_id: int):
        cursor = self.blocked_users.find({"guild_id": guild_id, "vc_owner_id": vc_owner_id})
        users = []
        async for doc in cursor:
            users.append(doc["user_id"])
        return users

    async def save_trusted_user(self, vc_id: int, user_id: int):
        await self.trusted_users.update_one(
            {"vc_id": vc_id, "user_id": user_id},
            {"$set": {"timestamp": datetime.now()}},
            upsert=True
        )

    async def remove_trusted_user(self, vc_id: int, user_id: int):
        await self.trusted_users.delete_one({"vc_id": vc_id, "user_id": user_id})

    async def get_trusted_users(self, vc_id: int):
        cursor = self.trusted_users.find({"vc_id": vc_id})
        users = []
        async for doc in cursor:
            users.append(doc["user_id"])
        return users
        
    async def is_user_trusted(self, vc_id: int, user_id: int):
        return await self.trusted_users.find_one({"vc_id": vc_id, "user_id": user_id}) is not None

    async def save_tempvc_log(self, guild_id: str, user_id: int, vc_id: int, action: str):
        await self.logs.insert_one({
            "guild_id": guild_id,
            "user_id": user_id,
            "vc_id": vc_id,
            "action": action,
            "timestamp": datetime.now()
        })

    async def set_log_channel(self, guild_id: str, channel_id: int):
        await self.log_channels.update_one(
            {"guild_id": guild_id},
            {"$set": {"channel_id": channel_id}},
            upsert=True
        )

    async def get_log_channel(self, guild_id: str):
        data = await self.log_channels.find_one({"guild_id": guild_id})
        return data["channel_id"] if data else None

    async def cog_load(self):
        print("[TempVC] Cog loaded - panels will be restored when bot is ready")

    @commands.Cog.listener()
    async def on_ready(self):
        """Restore panels when bot is ready"""
        if not self._panels_restored:
            print("[TempVC] Bot is ready! Starting panel restoration...")
            await self.restore_control_panels()

    async def restore_control_panels(self):
        """Restore control panels for all guilds"""
        if self._panels_restored:
            return
            
        cursor = self.control_panels.find({})
        
        try:
            async for doc in cursor:
                guild_id = doc["guild_id"]
                channel_id = doc["channel_id"]
                message_id = doc["message_id"]
                
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue
                    
                channel = guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    continue
                    
                try:
                    message = await channel.fetch_message(message_id)
                    view = TempVCControlPanel(self)
                    self.bot.add_view(view, message_id=message.id)
                    print(f"[TempVC] Restored interface embed in {guild_id}")
                    
                except discord.NotFound:
                    embed = discord.Embed(
                        title="<:hash:1445406962727522373> Temporary VC Interface",
                        description="This interface can be used to manage **temporary voice channels.** See this **image** for help.",
                        color=discord.Color.blurple()
                    )
                    embed.set_image(url="https://cdn.discordapp.com/attachments/1434091084358877256/1446137968371961919/tempvc.png?ex=6932e46f&is=693192ef&hm=6ceb626aa673a743d17fa862f502372dd6e3720d5f04145e4de982a471d3e48d&")
                    
                    view = TempVCControlPanel(self)
                    new_message = await channel.send(embed=embed, view=view)
                    
                    await self.control_panels.update_one(
                        {"guild_id": guild_id},
                        {"$set": {"message_id": new_message.id}}
                    )
                    
                    self.bot.add_view(view, message_id=new_message.id)
                    print(f"[TempVC] Restored and updated interface embed in {guild_id}")
                    
                except Exception as e:
                    print(f"[TempVC] Error restoring specific panel in {guild_id}: {e}")
            
            self._panels_restored = True
                    
        except Exception as e:
            print(f"[TempVC] Error restoring panels: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
 
        guild_id = str(member.guild.id)
        guild_data = await self.get_guild_data(guild_id) # Updated copy-paste from original logic but using await
        
        if not guild_data:
            return

        join_channel_id = guild_data.get("join_channel_id")
        category_id = guild_data.get("category_id")

        if not all([join_channel_id, category_id]):
            return

        # Check if user is blocked by the owner of the VC they're trying to join
        if after.channel and after.channel.id in self.created_channels.values():
            vc_owner_id = self.owners.get(after.channel.id)
            if vc_owner_id:
                # Check if user is blocked by this specific VC owner
                is_blocked_by_owner = await self.is_user_blocked(guild_id, vc_owner_id, member.id)
                
                if is_blocked_by_owner:
                    try:
                        # Hide this specific VC from the blocked user
                        await after.channel.set_permissions(member, view_channel=False)
                        # Move them out of the VC
                        await member.move_to(None)
                        try:
                            await member.send("<:no:1396838761605890090> You are blocked from accessing this voice channel.")
                        except:
                            pass
                    except:
                        pass
                    return

        if after.channel and after.channel.id == join_channel_id:
            category = member.guild.get_channel(category_id)
            if not category:
                return

            user_settings = await self.load_user_settings(member.id, guild_id)
            
            channel_kwargs = {"category": category, "reason": "TempVC"}
            
            if user_settings:
                if user_settings.get("vc_name"):
                    channel_kwargs["name"] = user_settings["vc_name"]
                if user_settings.get("user_limit") is not None:
                    channel_kwargs["user_limit"] = user_settings["user_limit"]
                if user_settings.get("rtc_region"):
                    channel_kwargs["rtc_region"] = user_settings["rtc_region"]
            else:
                channel_kwargs["name"] = f"{member.name}'s VC"

            new_channel = await member.guild.create_voice_channel(**channel_kwargs)

            await member.move_to(new_channel)
            self.created_channels[member.id] = new_channel.id
            
            await self.save_vc_permissions(new_channel.id, member.id)
            self.owners[new_channel.id] = member.id

            await new_channel.set_permissions(member, manage_channels=True, connect=True)

            # Hide the new channel from users blocked by this owner
            blocked_users = await self.get_blocked_users(guild_id, member.id)
            for blocked_user_id in blocked_users:
                blocked_member = member.guild.get_member(blocked_user_id)
                if blocked_member:
                    try:
                        await new_channel.set_permissions(blocked_member, view_channel=False)
                    except:
                        pass

            vc_perms = await self.load_vc_permissions(new_channel.id)
            if vc_perms:
                if vc_perms.get("is_locked"):
                    await new_channel.set_permissions(member.guild.default_role, connect=False)
                    trusted_users = await self.get_trusted_users(new_channel.id)
                    for user_id in trusted_users:
                        trusted_member = member.guild.get_member(user_id)
                        if trusted_member:
                            await new_channel.set_permissions(trusted_member, connect=True)
                
                if vc_perms.get("is_hidden"):
                    await new_channel.set_permissions(member.guild.default_role, view_channel=False)
                    trusted_users = await self.get_trusted_users(new_channel.id)
                    for user_id in trusted_users:
                        trusted_member = member.guild.get_member(user_id)
                        if trusted_member:
                            await new_channel.set_permissions(trusted_member, view_channel=True)

            trusted_users = await self.get_trusted_users(new_channel.id)
            for user_id in trusted_users:
                trusted_member = member.guild.get_member(user_id)
                if trusted_member:
                    await new_channel.set_permissions(trusted_member, connect=True)

            await self.save_tempvc_log(guild_id, member.id, new_channel.id, "created")
            
            log_channel_id = await self.get_log_channel(guild_id)
            if log_channel_id:
                log_channel = member.guild.get_channel(log_channel_id)
                if log_channel:
                    try:
                        timestamp = int(datetime.now().timestamp())
                        embed = discord.Embed(
                            title="🎙️ Temp VC Created",
                            color=0x2f3136,
                            timestamp=datetime.fromtimestamp(timestamp)
                        )
                        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
                        embed.add_field(name="Channel", value=f"{new_channel} ({new_channel.id})", inline=False)
                        embed.add_field(name="Time", value=f"<t:{timestamp}:F>", inline=False)
                        await log_channel.send(embed=embed)
                    except:
                        pass

        if before.channel and before.channel.id in self.created_channels.values():
            if len(before.channel.members) == 0:
                try:
                    vc_id = before.channel.id
                    owner_id = self.owners.get(vc_id)
                    
                    if owner_id:
                        # Delete associated thread when VC is automatically deleted
                        guild_data = await self.get_guild_data(guild_id)
                        interface_id = guild_data.get("interface_id")
                        if interface_id:
                            interface_channel = before.channel.guild.get_channel(interface_id)
                            if interface_channel and isinstance(interface_channel, discord.TextChannel):
                                for thread in interface_channel.threads:
                                    owner = before.channel.guild.get_member(owner_id)
                                    owner_name = owner.display_name if owner else "Unknown"
                                    if (before.channel.name in thread.name or 
                                        f"{owner_name}" in thread.name or 
                                        str(vc_id) in thread.name):
                                        try:
                                            await thread.delete(reason="Associated VC deleted")
                                        except:
                                            pass
                        
                        await self.save_tempvc_log(guild_id, owner_id, vc_id, "deleted")
                        
                        log_channel_id = await self.get_log_channel(guild_id)
                        if log_channel_id:
                            log_channel = before.channel.guild.get_channel(log_channel_id)
                            if log_channel:
                                try:
                                    timestamp = int(datetime.now().timestamp())
                                    embed = discord.Embed(
                                        title="<:sydelete:1446125637172596869> Temp VC Deleted",
                                        color=0x2f3136,
                                        timestamp=datetime.fromtimestamp(timestamp)
                                    )
                                    embed.add_field(name="Owner ID", value=owner_id, inline=False)
                                    embed.add_field(name="Channel ID", value=vc_id, inline=False)
                                    embed.add_field(name="Time", value=f"<t:{timestamp}:F>", inline=False)
                                    await log_channel.send(embed=embed)
                                except:
                                    pass
                    
                    try:
                        await before.channel.set_permissions(before.channel.guild.default_role, overwrite=None)
                    except:
                        pass
                    
                    await before.channel.delete(reason="Empty TempVC")
                except discord.Forbidden:
                    pass
                except discord.NotFound:
                    pass

                if before.channel.id in self.owners:
                    del self.owners[before.channel.id]
                if before.channel.id in self.created_channels:
                    del self.created_channels[before.channel.id]

    @commands.hybrid_group(name="tempvc", description="Manage temporary voice channels")
    @commands.has_permissions(administrator=True)
    async def tempvc(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🎙️ TempVC Commands",
                description=(
                    "`/tempvc setup` - Setup TempVC system for this server\n"
                    "`/tempvc reset` - Reset TempVC system in this server\n"
                    "`/tempvc logs <#channel>` - Set logs channel for TempVC"
                ),
                color=0x2f3136,
            )
            await ctx.send(embed=embed, ephemeral=True)

    @tempvc.command(name="setup", description="Setup TempVC system for this server")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def setup(self, ctx):
        await ctx.defer(ephemeral=True)
        
        guild_id = str(ctx.guild.id)
        print(f"[TempVC] Setting up for guild {guild_id}")

        guild_data = await self.get_guild_data(guild_id)
        if guild_data:
            await ctx.send("<a:alert:1396429026842644584> TempVC is already set up for this server! Use `!tempvc reset` first.", ephemeral=True)
            return

        try:
            guild = ctx.guild
            category = await guild.create_category("Temporary VC")
            join_channel = await guild.create_voice_channel("➕ Join to Create", category=category)
            interface = await guild.create_text_channel("interface", category=category, topic="TempVC control panel")

            await self.save_guild_data(guild_id, join_channel.id, category.id, interface.id)
            print(f"[TempVC] Guild data saved for {guild_id}")

            await interface.set_permissions(guild.default_role, send_messages=False, add_reactions=False)
            await interface.set_permissions(guild.me, send_messages=True, add_reactions=True, read_message_history=True, view_channel=True)

            embed = discord.Embed(
                title="<:hash:1445406962727522373> Temporary VC Interface",
                description="This interface can be used to manage **temporary voice channels.** See this **image** for help.",
                color=0x2f3136
            )
            embed.set_image(url="https://cdn.discordapp.com/attachments/1434091084358877256/1446137968371961919/tempvc.png?ex=6932e46f&is=693192ef&hm=6ceb626aa673a743d17fa862f502372dd6e3720d5f04145e4de982a471d3e48d&")

            view = TempVCControlPanel(self)
            message = await interface.send(embed=embed, view=view)
            print(f"[TempVC] Control panel sent")
            
            # CRITICAL: Register the view for persistence
            self.bot.add_view(view, message_id=message.id)
            
            await self.control_panels.update_one(
                {"guild_id": guild_id},
                {"$set": {"channel_id": interface.id, "message_id": message.id}},
                upsert=True
            )
            print(f"[TempVC] Control panel registered")

            embed = discord.Embed(
                title="<:yes:1396838746862784582> TempVC Setup Complete!",
                description=(
                    f"**Join Channel:** {join_channel.mention}\n"
                    f"**Category:** {category.name}\n"
                    f"**Interface Channel:** {interface.mention}\n\n"
                    f"The interface will work even after bot restarts!"
                ),
                color=0x2f3136,
            )

            await ctx.send(embed=embed, ephemeral=True)
            print(f"[TempVC] Setup complete for guild {guild_id}")
        except discord.Forbidden:
            await ctx.send("<:no:1396838761605890090> Bot missing permissions. Need 'Manage Channels' and 'Manage Roles'.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:no:1396838761605890090> Error: {str(e)}", ephemeral=True)
            print(f"[TempVC] Setup error: {e}")

    @tempvc.command(name="reset", description="Reset TempVC system")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        guild_id = str(ctx.guild.id)
        guild_data = await self.get_guild_data(guild_id)

        if not guild_data:
            await ctx.send("<a:alert:1396429026842644584> No TempVC setup found.", ephemeral=True)
            return

        category = ctx.guild.get_channel(guild_data.get("category_id"))
        if category:
            try:
                for channel in category.channels:
                    try:
                        await channel.delete(reason="TempVC reset")
                    except:
                        pass
                await category.delete(reason="TempVC reset")
            except:
                pass

        if self.guild_settings:
            await self.guild_settings.delete_one({"guild_id": guild_id})
            await self.control_panels.delete_one({"guild_id": guild_id})
            await self.log_channels.delete_one({"guild_id": guild_id})

        await ctx.send("<:sydelete:1446125637172596869> TempVC system reset complete.", ephemeral=True)

    @tempvc.command(name="logs", description="Set logs channel")
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx, channel: discord.TextChannel):
        await ctx.defer(ephemeral=True)
        
        guild_id = str(ctx.guild.id)
        guild_data = await self.get_guild_data(guild_id)
        if not guild_data:
            await ctx.send("<a:alert:1396429026842644584> Setup TempVC first with `!tempvc setup`", ephemeral=True)
            return
            
        await self.set_log_channel(guild_id, channel.id)
        
        embed = discord.Embed(
            title="<:yes:1396838746862784582> Logs Channel Set",
            description=f"TempVC logs → {channel.mention}",
            color=0x2f3136
        )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TempVC(bot))