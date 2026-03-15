import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import aiohttp
import os
from utils.config import OWNER_IDS
import datetime

# Logs channel removed in favor of Webhook
WEBHOOK_URL = "https://discord.com/api/webhooks/1454806298439717026/-qwj2Lxmj_MRtPKTxb-bPZ9rjyOfo2uEdpio7i34T_4QHDhi_UUnuxwiT7-EYTlB_pWn"

COLOR = 0x2b2d31
TICK = "<:yes:1396838746862784582>"
CROSS = "<:no:1396838761605890090>"

class BioModal(Modal, title="Bot Bio"):
    def __init__(self, cog, ctx):
        super().__init__()
        self.cog = cog
        self.ctx = ctx

    bio = TextInput(
        label="Bot Bio",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the bot's bio for this server...",
        max_length=2000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # We need to defer since we will do logging and DB ops
        await interaction.response.defer()
        
        try:
            text = self.bio.value
            
            
            # Update MongoDB
            await self.cog.bot.db.custom_profiles.update_one(
                {"guild_id": self.ctx.guild.id},
                {"$set": {"user_id": self.ctx.author.id, "bio": text}},
                upsert=True
            )
            
            # Attempt to update Discord Bio via Raw API
            api_sync_msg = "(Discord API accepted the bio update)"
            api_sync_status = True
            
            try:
                from discord.http import Route
                route = Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=self.ctx.guild.id)
                await self.cog.bot.http.request(route, json={'bio': text})
            except Exception as api_error:
                api_sync_status = False
                err_str = str(api_error)
                if "50035" in err_str or "Must be 190 or fewer" in err_str:
                    api_sync_msg = "\n⚠️ **Note**: Discord Profile Sync failed (Bio > 190 characters). Saved to Database/Dashboard only."
                else:
                    api_sync_msg = f"\n⚠️ **Note**: Discord Sync failed: {err_str}"
                print(f"Bio update API failed: {api_error}")

            await self.cog.log_action(self.ctx, "bio", text)
            
            embed_color = COLOR if api_sync_status else 0xffaa00 # Yellow/Orange if partial warning
            embed = discord.Embed(title=f"{TICK} Success",
                                  description=f"Bot bio saved to **Server Custom Profile**.{api_sync_msg}\n\nYou may need to restart your discord client for results.",
                                  color=embed_color)
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await self.cog.log_action(self.ctx, "bio", self.bio.value, False, str(e))
            await interaction.followup.send(embed=discord.Embed(title=f"{CROSS} Error",
                                               description=f"Failed to update bio: {str(e)}",
                                               color=COLOR))


class CustomProfile(commands.Cog):
    """Manage per-server bot profile: nickname, avatar, banner, bio"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # MongoDB collection: self.bot.db.custom_profiles
        self.premium_watcher.start()

    def cog_unload(self):
        self.premium_watcher.cancel()

    # ---------------- CHECKS ----------------
    async def cog_check(self, ctx):
        if ctx.author.id in OWNER_IDS:
            return True
            
        # 1. Check Administrator Permission (Strict)
        if not ctx.author.guild_permissions.administrator:
            await ctx.send(embed=discord.Embed(
                title=f"{CROSS} Access Denied",
                description="You need **Administrator** permission to use these commands.",
                color=COLOR
            ))
            return False

        # 2. Check Premium Status (Author OR Guild Owner)
        # Access Premium System via Cog
        premium_cog = self.bot.get_cog('Premium')
        if premium_cog and hasattr(premium_cog, 'premium_system'):
            premium_system = premium_cog.premium_system
            
            # Check Author (Personal Premium)
            has_premium, _ = await premium_system.check_user_premium(ctx.author.id, ctx.guild.id)
            if has_premium:
                return True
            
            # Check Guild Owner (Server Premium inheritance)
            if ctx.guild.owner_id != ctx.author.id:
                 has_premium_owner, _ = await premium_system.check_user_premium(ctx.guild.owner_id, ctx.guild.id)
                 if has_premium_owner:
                     return True
                
        # If we reach here, no premium (or premium system not found)
        embed = discord.Embed(
            title=f"{CROSS} Premium Required",
            description="This server needs **Premium** (or you need personal Premium) to use this command!",
            color=COLOR
        )
        view = View()
        view.add_item(Button(label="Get Premium / Support", style=discord.ButtonStyle.link,
                             url="https://dsc.gg/scyrogg"))
        await ctx.send(embed=embed, view=view)
        return False

    async def check_owner(self, ctx):
        # Allow Administrators or Bot Owners
        if not ctx.author.guild_permissions.administrator and ctx.author.id not in OWNER_IDS:
            await ctx.send(embed=discord.Embed(
                title=f"{CROSS} Error",
                description="You need **Administrator** permission to use this command.",
                color=COLOR
            ))
            return False
        return True

    async def log_action(self, ctx, field, value, success=True, error_msg=None):
        try:
            embed = discord.Embed(
                title=f"{TICK} Profile Updated" if success else f"{CROSS} Profile Update Failed",
                color=COLOR,
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Server", value=f"{ctx.guild.name} (`{ctx.guild.id}`)", inline=False)
            embed.add_field(name="User", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
            embed.add_field(name="Field", value=field, inline=False)
            if error_msg:
                embed.add_field(name="Error", value=error_msg, inline=False)
            
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
                await webhook.send(embed=embed, username="Scyro Logging", avatar_url=self.bot.user.display_avatar.url)
        except Exception as e:
            print(f"Failed to send webhook log: {e}")

    # ---------------- MAIN GROUP ----------------
    @commands.hybrid_group(name="customprofile", aliases=["c"], invoke_without_command=True)
    async def customprofile(self, ctx):
        embed = discord.Embed(
            title="Custom Profile Commands",
            description="""`customprofile bot name <name>` - Update bot nickname
`customprofile bot avatar <url>` - Update bot avatar
`customprofile bot banner <url>` - Update bot banner
`customprofile bot bio` - Update bot bio (Popup)
`customprofile config` - Show current configuration
`customprofile reset` - Reset server profile""",
            color=COLOR
        )
        await ctx.send(embed=embed)

    # ---------------- CONFIG ----------------
    @customprofile.command(name="config", description="Show the current custom profile configuration for this server.")
    async def config(self, ctx):
        """Show the current custom profile configuration for this server."""
        # Check handled by cog_check
        await ctx.defer()
        try:
            data = await self.bot.db.custom_profiles.find_one({"guild_id": ctx.guild.id})
            
            if not data:
                return await ctx.send(embed=discord.Embed(title=f"{CROSS} No Profile",
                                                           description="This server has no custom profile set.",
                                                           color=COLOR))
            
            avatar = data.get("avatar")
            banner = data.get("banner")
            bio = data.get("bio")
            name = data.get("name")
            
            embed = discord.Embed(title=f"{TICK} Server Custom Profile", color=COLOR)
            embed.add_field(name="Nickname", value=name or "Not set", inline=False)
            embed.add_field(name="Bio", value=bio or "Not set", inline=False)
            embed.add_field(name="Avatar URL", value=avatar or "Not set", inline=False)
            embed.add_field(name="Banner URL", value=banner or "Not set", inline=False)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(embed=discord.Embed(title=f"{CROSS} Error", description=str(e), color=COLOR))

    # ---------------- RESET ----------------
    @customprofile.command(name="reset", description="Reset the custom profile settings for this server.")
    async def reset(self, ctx):
        """Reset the custom profile settings for this server."""
        # Check handled by cog_check
        await ctx.defer()
        try:
            # Try to reset name
            try:
                await ctx.guild.me.edit(nick=None)
            except:
                pass
            
            # Reset Avatar using Raw API
            try:
                from discord.http import Route
                route = Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'avatar': None})
            except:
                 pass
        except:
            pass
        
        await self.bot.db.custom_profiles.delete_one({"guild_id": ctx.guild.id})
        await self.log_action(ctx, "reset", "server profile reset")
        await ctx.send(embed=discord.Embed(title=f"{TICK} Success", description="Server profile reset successfully.", color=COLOR))

    # ---------------- BOT GROUP ----------------
    # ---------------- BOT GROUP ----------------
    @customprofile.group(name="bot", invoke_without_command=True)
    async def _bot(self, ctx):
        """Manage bot's custom profile (Avatar, Banner, Bio, Name)."""
        await ctx.send_help(ctx.command)

    # ---------------- AVATAR ----------------
    # ---------------- AVATAR ----------------
    # ---------------- AVATAR ----------------
    @_bot.command(name="avatar", aliases=["a"], description="Set the bot's avatar for this server.", help="Set the bot's avatar for this server.")
    @app_commands.describe(url="The direct URL of the image to set as avatar")
    async def avatar(self, ctx, url: str):
        """Set the bot's avatar for this server."""
        # Check handled by cog_check
        
        await ctx.defer()
        
        # Validate URL starts with http (basic check), detailed check via fetch
        if not url.startswith("http"):
             return await ctx.send(embed=discord.Embed(title=f"{CROSS} Error", description="Please provide a valid image URL.", color=COLOR))

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise ValueError("Invalid image URL or unable to access.")
                    img_bytes = await resp.read()
                    if len(img_bytes) > 10 * 1024 * 1024: # 10MB
                        return await ctx.send(embed=discord.Embed(title=f"{CROSS} Error", description="File is too large! Max size: 10MB.", color=COLOR))
                    content_type = resp.headers.get('Content-Type', 'image/png')
                    # Fix: Force image/gif if url ends in .gif (sometimes headers are wrong)
                    if url.lower().split('?')[0].endswith('.gif'):
                        content_type = 'image/gif'
            
            # Use raw API request to bypass library limitations/differences
            # PATCH /guilds/{guild.id}/members/@me
            import base64
            b64_image = f"data:{content_type};base64,{base64.b64encode(img_bytes).decode('utf-8')}"
            
            # Use discord.http.Route if available (common in d.py libs)
            try:
                from discord.http import Route
                route = Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'avatar': b64_image})
            except:
                # Fallback to direct request if Route fails
                headers = {"Authorization": f"Bot {self.bot.http.token}", "Content-Type": "application/json"}
                async with aiohttp.ClientSession() as session:
                    async with session.patch(f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me", headers=headers, json={'avatar': b64_image}) as r:
                         if r.status not in (200, 204):
                             try:
                                 err_json = await r.json()
                                 err_msg = err_json.get('message', await r.text())
                             except:
                                 err_msg = await r.text()
                             raise Exception(f"API Error {r.status}: {err_msg}")

            # Update MongoDB
            await self.bot.db.custom_profiles.update_one(
                {"guild_id": ctx.guild.id},
                {"$set": {"user_id": ctx.author.id, "avatar": url}},
                upsert=True
            )
            
            await self.log_action(ctx, "avatar", url)
            await ctx.send(embed=discord.Embed(title=f"{TICK} Success",
                                               description="Bot avatar set for this server! (Changes may take 2-3 minutes)",
                                               color=COLOR))
        except discord.Forbidden:
             await ctx.send(embed=discord.Embed(title=f"{CROSS} Error", description="I don't have permission to change my nickname/avatar (or I'm missing the needed scope/integration). Saved to database anyway.", color=COLOR))
        except Exception as e:
            await self.log_action(ctx, "avatar", url, False, str(e))
            await ctx.send(embed=discord.Embed(title=f"{CROSS} Error",
                                               description=f"Failed to set avatar: {str(e)}",
                                               color=COLOR))

    # ---------------- BANNER ----------------
    # ---------------- BANNER ----------------
    @_bot.command(name="banner", aliases=["b"], description="Set the bot's banner for this server.", help="Set the bot's banner for this server.")
    @app_commands.describe(url="The direct URL of the image to set as banner")
    async def banner(self, ctx, url: str):
        """Set the bot's banner for this server."""
        # Check handled by cog_check
        
        await ctx.defer()

        try:
             # Validate URL
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                         raise ValueError("Invalid image URL")
                    img_bytes = await resp.read()
                    if len(img_bytes) > 10 * 1024 * 1024:
                        return await ctx.send(embed=discord.Embed(title=f"{CROSS} Error", description="File is too large! Max size: 10MB.", color=COLOR))
                    content_type = resp.headers.get('Content-Type', 'image/png')
                    # Fix: Force image/gif if url ends in .gif
                    if url.lower().split('?')[0].endswith('.gif'):
                        content_type = 'image/gif'
            
            # Per-server banner IS NOT supported by Member.edit properly in all cases,
            # but we will save it to DB for dashboard/embed usage.
            # Attempt Raw API anyway (similar to Avatar)
            import base64
            b64_image = f"data:{content_type};base64,{base64.b64encode(img_bytes).decode('utf-8')}"
            
            try:
                from discord.http import Route
                route = Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'banner': b64_image})
            except:
                # Fallback
                headers = {"Authorization": f"Bot {self.bot.http.token}", "Content-Type": "application/json"}
                async with aiohttp.ClientSession() as session:
                    async with session.patch(f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me", headers=headers, json={'banner': b64_image}) as r:
                         if r.status not in (200, 204):
                             try:
                                 err_json = await r.json()
                                 err_msg = err_json.get('message', await r.text())
                             except:
                                 err_msg = await r.text()
                             raise Exception(f"API Error {r.status}: {err_msg}")

             # Update MongoDB
            await self.bot.db.custom_profiles.update_one(
                {"guild_id": ctx.guild.id},
                {"$set": {"user_id": ctx.author.id, "banner": url}},
                upsert=True
            )
            
            await self.log_action(ctx, "banner", url)
            await ctx.send(embed=discord.Embed(title=f"{TICK} Success",
                                               description="Bot banner saved for this server!\n You may need to restart you discord to see instant results.\n(Discord API accepted the banner update)",
                                               color=COLOR))
        except Exception as e:
            await self.log_action(ctx, "banner", url, False, str(e))
            await ctx.send(embed=discord.Embed(title=f"{CROSS} Error",
                                               description=f"Failed to set banner: {str(e)}",
                                               color=COLOR))

    @_bot.command(name="bio", aliases=["d"], description="Set the bot's bio for this server (Opens Modal).", help="Set the bot's bio for this server (Opens Modal).")
    async def bio(self, ctx):
        """Set the bot's bio for this server (Popup Modal)."""
        # Check handled by cog_check
        
        if ctx.interaction:
            # Open Modal for Slash Command
            await ctx.interaction.response.send_modal(BioModal(self, ctx))
        else:
            # Fallback/Error for Text Command
            embed = discord.Embed(
                title=f"{CROSS} Interaction Required",
                description="> 📝 **The Bio Popup** is only available via **Slash Commands**\n> 🚀 **Please use** `/customprofile bot bio` instead",
                color=COLOR
            )
            await ctx.send(embed=embed)

    # ---------------- NAME ----------------
    # ---------------- NAME ----------------
    @_bot.command(name="name", aliases=["n"], description="Set the bot's nickname for this server.", help="Set the bot's nickname for this server.")
    @app_commands.describe(nickname="The new nickname for the bot")
    async def name(self, ctx, *, nickname: str = None):
        """Set the bot's nickname for this server."""
        # Check handled by cog_check
        
        await ctx.defer()
        
        # Update MongoDB
        await self.bot.db.custom_profiles.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"user_id": ctx.author.id, "name": nickname}},
            upsert=True
        )

        try:
            await ctx.guild.me.edit(nick=nickname)
        except discord.Forbidden:
            return await ctx.send(embed=discord.Embed(title=f"{CROSS} Error",
                                                       description="I cannot change my nickname in this server (Missing Permissions).",
                                                       color=COLOR))
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(title=f"{CROSS} Error",
                                                       description=f"Failed to change nickname: {e.text}",
                                                       color=COLOR))
        except Exception as e:
            return await ctx.send(embed=discord.Embed(title=f"{CROSS} Error",
                                                       description=f"An unexpected error occurred: {str(e)}",
                                                       color=COLOR))
        await self.log_action(ctx, "name", nickname)
        await ctx.send(embed=discord.Embed(title=f"{TICK} Success",
                                           description="Bot nickname updated for this server.",
                                           color=COLOR))

    # ---------------- PREMIUM WATCHER ----------------
    @tasks.loop(minutes=15)
    async def premium_watcher(self):
        # Check all profiles, ensure they still have premium
        cursor = self.bot.db.custom_profiles.find({})
        async for doc in cursor:
            guild_id = doc["guild_id"]
            user_id = doc.get("user_id")
            
            if user_id in OWNER_IDS:
                continue
                
            # Check premium using system
            # Check premium using system
            premium_cog = self.bot.get_cog('Premium')
            if premium_cog and hasattr(premium_cog, 'premium_system'):
                # We can check by user_id
                has_premium, tier = await premium_cog.premium_system.check_user_premium(user_id)
                
                if not has_premium:
                    # Expired
                    await self.bot.db.custom_profiles.delete_one({"guild_id": guild_id})
                    
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        try:
                            await guild.me.edit(nick=None) # Reset nick
                        except:
                            pass
                        try:
                            await guild.me.edit(guild_avatar=None) # Reset avatar
                        except:
                            pass
                        
                        try:
                            embed = discord.Embed(title="Bot Profile Auto-Reset",
                                                  description=f"Server: {guild.name} (`{guild.id}`)\nReason: Premium expired, profile reset.",
                                                  color=COLOR,
                                                  timestamp=datetime.datetime.now())
                            async with aiohttp.ClientSession() as session:
                                webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
                                await webhook.send(embed=embed, username="Scyro Logging", avatar_url=self.bot.user.display_avatar.url)
                        except Exception as e:
                            print(f"Failed to log auto-reset: {e}")

    @premium_watcher.before_loop
    async def before_watcher(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomProfile(bot))