import discord
from discord.ext import commands
from discord import app_commands
import io
import random
import string
import time
import asyncio
from captcha.image import ImageCaptcha
import motor.motor_asyncio
import os
from discord import ui
from typing import Optional

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

EMBED_COLOR = 0x3C0069  
BANNER_URL = "https://cdn.discordapp.com/attachments/1454037590675034274/1454109457821728887/fff.png?ex=694fe476&is=694e92f6&hm=1bcb84e7f797111836004c5d1ea136323eac63fee53329647d436a0ea2e08d84&"

# Emojis
EMOJI_VERIFY = "<:verify:1454085078165622825>" 
EMOJI_ENTER = "<:enter:1454085903810035762>"

# --- UTILS ---
def generate_captcha_text(length=5):
    # Removed ambiguous characters
    characters = "ABDEFGHJLMNQRTYabdefghijkmnqrty23456789"
    return ''.join(random.choice(characters) for _ in range(length))

def create_captcha_image(text):
    image = ImageCaptcha(width=300, height=100)
    data = image.generate(text)
    return io.BytesIO(data.getvalue())

# --- VIEWS & MODALS ---

class VerifyModal(ui.Modal, title="Verification"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.captcha_text = generate_captcha_text()
        self.ans = ui.TextInput(label=f"CAPTCHA: {self.captcha_text}", placeholder="Enter the code above...", min_length=5, max_length=5)
        self.add_item(self.ans)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if self.ans.value.upper() == self.captcha_text.upper():
            cfg = await self.cog.get_config(interaction.guild.id)
            if not cfg:
                return await interaction.followup.send("<:no:1396838761605890090> System not configured.", ephemeral=True)

            role_id = cfg.get('role_id')
            role = interaction.guild.get_role(role_id)
            
            if role:
                try: 
                    await interaction.user.add_roles(role, reason="[Scyro Verification] Successful Captcha")
                    await self.cog.reset_failures(interaction.guild.id, interaction.user.id)
                    await interaction.followup.send(content="<:yes:1396838746862784582> Verified!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send(content="<a:alert:1396429026842644584> Verified, but I cannot give you the role (Missing Permissions).", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(content=f"An error occurred while adding role: {e}. Contact staff.", ephemeral=True)
            else:
                 await interaction.followup.send(content="Role not found in server. Contact staff.", ephemeral=True)
        else:
            count = await self.cog.add_failure(interaction.guild.id, interaction.user.id)
            
            if count >= 3:
                try:
                    await interaction.user.send(f"You have been kicked from **{interaction.guild.name}**\nReason: Failed verification 3 times.")
                    await interaction.guild.kick(interaction.user, reason="[Scyro Verification] Failed Captcha 3 times")
                    await interaction.followup.send("<:no:1396838761605890090> **Failed.** You have been kicked.", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send("<:no:1396838761605890090> **Failed.** (Kick failed - Missing Permissions).", ephemeral=True)
                except Exception:
                    await interaction.followup.send("<:no:1396838761605890090> **Failed.** (Kick failed - Unknown error).", ephemeral=True)
            else:
                remaining = 3 - count
                await interaction.followup.send(
                    f"<:no:1396838761605890090> **Incorrect.** Attempts left: **{remaining}**.", 
                    ephemeral=True
                )

class VerifyButton(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        
    @discord.ui.button(label="Begin Verification", style=discord.ButtonStyle.secondary, emoji=EMOJI_ENTER, custom_id="verify_start")
    async def verify_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        config = await self.cog.get_config(interaction.guild.id)
        if not config:
            return await interaction.followup.send("<a:alert:1396429026842644584> Verification system was deactivated on this server. Use `/verification setup` to activate it again.", ephemeral=True)
        
        role_id = config.get('role_id')
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return await interaction.followup.send("<:dead:1397874874776817746> **Chill!** You are already verified.", ephemeral=True)
        
        fails, last = await self.cog.get_failures(interaction.guild.id, interaction.user.id)
        if fails >= 3 and (time.time() - last) < 300: 
            return await interaction.followup.send(f"<a:7596clock:1413390466979991572> Too many failed attempts. Try again <t:{int(last+300)}:R>.", ephemeral=True)
            
        await interaction.response.send_modal(VerifyModal(self.cog))

class ConfirmResetView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your command.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

# --- COMMAND GROUP ---

class VerificationGroup(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="verification", description="Manage Verification System", guild_only=True)
        self.cog = cog

    @app_commands.command(name="setup", description="Setup verification system")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
        await interaction.response.defer(ephemeral=True)

        existing_config = await self.cog.get_config(interaction.guild.id)
        if existing_config:
            return await interaction.followup.send(f"<:no:1396838761605890090> Verification already setup in <#{existing_config['channel_id']}>. Use `/verification reset` first.", ephemeral=True)

        embed = discord.Embed(
            title=f"<:srvverify:1454092862978265128> {interaction.guild.name} Verification",
            description="Click the **Verify** button below to gain access to the server.\nThis helps us protect the community from raids and bots.",
            color=EMBED_COLOR
        )
        if BANNER_URL: embed.set_image(url=BANNER_URL)
        embed.set_footer(text=interaction.guild.name)

        view = VerifyButton(self.cog)
        try:
            msg = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(f"<:no:1396838761605890090> I cannot send messages in {channel.mention}.", ephemeral=True)

        await self.cog.set_config(interaction.guild.id, channel.id, role.id, msg.id)
        await interaction.followup.send(f"<:yes:1396838746862784582> **Setup Complete!** Panel sent to {channel.mention}. Role: {role.mention}", ephemeral=True)

    @app_commands.command(name="edit", description="Edit verification settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def edit(self, interaction: discord.Interaction, role: discord.Role = None, channel: discord.TextChannel = None):
        cfg = await self.cog.get_config(interaction.guild.id)
        if not cfg:
            return await interaction.response.send_message("<:no:1396838761605890090> Verification not setup. Use `/verification setup`.", ephemeral=True)
        
        updates = {}
        msg = []
        if role:
            updates["role_id"] = role.id
            msg.append(f"Role updated to {role.mention}")
        if channel:
            updates["channel_id"] = channel.id
            msg.append(f"Channel updated to {channel.mention} (Note: Does not move panel message)")
        
        if not updates:
            return await interaction.response.send_message("No changes specified.", ephemeral=True)

        await self.cog.settings.update_one({"guild_id": interaction.guild.id}, {"$set": updates})
        await interaction.response.send_message(embed=discord.Embed(description=f"<:yes:1396838746862784582> **Updated:**\n" + "\n".join(msg), color=EMBED_COLOR), ephemeral=True)

    @app_commands.command(name="reset", description="Disable and reset verification system")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.send_message("Reset verification?", view=ConfirmResetView(interaction.user.id), ephemeral=True)
        
    @app_commands.command(name="config", description="View current configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def config(self, interaction: discord.Interaction):
        cfg = await self.cog.get_config(interaction.guild.id)
        if not cfg: 
            return await interaction.response.send_message(embed=discord.Embed(description="Not setup.", color=discord.Color.red()), ephemeral=True)
        
        role = interaction.guild.get_role(cfg.get('role_id'))
        chan = interaction.guild.get_channel(cfg.get('channel_id'))
        
        desc = f"**Channel:** {chan.mention if chan else 'Unknown'}\n**Role:** {role.mention if role else 'Unknown'}\n**Message ID:** {cfg.get('message_id')}"
        await interaction.response.send_message(embed=discord.Embed(title="Verification Config", description=desc, color=EMBED_COLOR), ephemeral=True)

    @app_commands.command(name="force", description="Force verify a user")
    @app_commands.checks.has_permissions(administrator=True)
    async def force(self, interaction: discord.Interaction, user: discord.Member):
        cfg = await self.cog.get_config(interaction.guild.id)
        if not cfg: return await interaction.response.send_message("Not setup.", ephemeral=True)
        
        role = interaction.guild.get_role(cfg.get('role_id'))
        if not role: return await interaction.response.send_message("Role missing.", ephemeral=True)
        
        try:
            await user.add_roles(role)
            await self.cog.reset_failures(interaction.guild.id, user.id)
            await interaction.response.send_message(f"<:yes:1396838746862784582> Forced verification for {user.mention}", ephemeral=True)
        except:
            await interaction.response.send_message("Failed to add role.", ephemeral=True)

# --- COG IMPLEMENTATION ---

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.settings = self.db["verify_settings"]
        self.failures = self.db["verify_failures"]

    async def cog_load(self):
        self.bot.add_view(VerifyButton(self))
        # Add the Group
        self.bot.tree.add_command(VerificationGroup(self))
        print("✅ [Verification] Extension loaded & DB initialized.")

    async def cog_unload(self):
        self.bot.tree.remove_command("verification")

    async def get_config(self, guild_id):
        return await self.settings.find_one({"guild_id": guild_id})

    async def set_config(self, guild_id, channel_id, role_id, message_id):
        await self.settings.update_one(
            {"guild_id": guild_id},
            {"$set": {
                "channel_id": channel_id,
                "role_id": role_id,
                "message_id": message_id
            }},
            upsert=True
        )

    async def delete_config(self, guild_id):
        # First get to delete msg
        config = await self.get_config(guild_id)
        if config:
            await self.settings.delete_one({"guild_id": guild_id})
            await self.failures.delete_many({"guild_id": guild_id})
            return config
        return None

    async def get_failures(self, guild_id, user_id):
        doc = await self.failures.find_one({"guild_id": guild_id, "user_id": user_id})
        if doc:
            return doc.get("failures", 0), doc.get("last_attempt", 0)
        return 0, 0

    async def add_failure(self, guild_id, user_id):
        now = time.time()
        await self.failures.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"failures": 1}, "$set": {"last_attempt": now}},
            upsert=True
        )
        doc = await self.failures.find_one({"guild_id": guild_id, "user_id": user_id})
        return doc.get("failures", 0)

    async def reset_failures(self, guild_id, user_id):
        await self.failures.delete_one({"guild_id": guild_id, "user_id": user_id})

async def setup(bot):
    await bot.add_cog(Verification(bot))