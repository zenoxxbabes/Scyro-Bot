import discord
from discord.ext import commands
from discord import app_commands
import motor.motor_asyncio
import asyncio
import time
import json
import zlib
import base64
import os
from datetime import datetime
from utils.Tools import *

# Define missing constants
DEFAULT_LIMITS = {
    'ban': 3,
    'kick': 5,
    'channel_create': 3,
    'channel_delete': 3,
    'channel_update': 5,
    'role_create': 3,
    'role_delete': 3,
    'role_update': 5,
    'member_update': 5,
    'guild_update': 3,
    'webhook_create': 2,
    'webhook_delete': 2,
    'webhook_update': 3,
    'integration_create': 2,
    'prune': 1
}

TIME_WINDOW = 60  # 60 seconds time window
BOT_OWNER_ID = 1218037361926209640  # Your bot owner ID
BOT_OWNER_EMOJI = "💎"  # Your custom bot owner emoji

class Antinuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_cooldowns = {} # Guild-specific cooldowns for dashboard sync
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.db_client["scyro"]
        self.antinuke_col = self.db["antinuke"]
        self.modules_col = self.db["antinuke_modules"]
        self.settings_col = self.db["antinuke_settings"]
        self.extra_col = self.db["extraowners"]
        self.snapshots_col = self.db["recovery_snapshots"]
        self.cooldowns_col = self.db["recovery_cooldowns"]

    async def cog_load(self):
        print("✅ [Antinuke] Extension loaded & DB initialized (MongoDB).")

    ANTINUKE_MODULES = [
        "ban", "kick", "bot", "channel_create", "channel_delete", "channel_update",
        "role_create", "role_delete", "role_update", "member_update", "guild_update",
        "integration", "webhook_create", "webhook_delete", "webhook_update", "prune",
        "everyone", "emoji", "sticker", "soundboard"
    ]

    async def is_module_enabled(self, guild_id, module):
        """Check if a specific module is enabled"""
        doc = await self.modules_col.find_one({"guild_id": guild_id, "module": module})
        return doc["enabled"] if doc else True

    async def enable_module(self, guild_id, module):
        """Enable a specific module"""
        await self.modules_col.update_one(
            {"guild_id": guild_id, "module": module},
            {"$set": {"enabled": True}},
            upsert=True
        )

    async def disable_module(self, guild_id, module):
        """Disable a specific module"""
        await self.modules_col.update_one(
            {"guild_id": guild_id, "module": module},
            {"$set": {"enabled": False}},
            upsert=True
        )

    async def enable_limit_settings(self, guild_id):
        """Enable default limit settings for a guild"""
        default_limits = DEFAULT_LIMITS
        for action, limit in default_limits.items():
            await self.settings_col.update_one(
                {"guild_id": guild_id, "action": action},
                {"$set": {"limit": limit, "time_window": TIME_WINDOW}},
                upsert=True
            )

    async def disable_limit_settings(self, guild_id):
        """Disable limit settings for a guild"""
        await self.settings_col.delete_many({"guild_id": guild_id})

    def is_bot_owner_check(self, user_id):
        return str(user_id) == str(BOT_OWNER_ID)

    async def sync_antinuke_setup(self, guild):
        """Syncs Discord Antinuke Role with DB config (Called by Dashboard API)"""
        if not guild.me.guild_permissions.administrator: return # Cannot sync without admin
        
        # Rate Limit Protection (10s cooldown per guild)
        if time.time() - self.sync_cooldowns.get(guild.id, 0) < 10:
            return
        self.sync_cooldowns[guild.id] = time.time()

        # Create/Assign Scyro Core role
        try:
            role = discord.utils.get(guild.roles, name="Scyro Core")
            
            # Create if missing
            if not role:
                role = await guild.create_role(
                    name="Scyro Core",
                    color=0x720e9e,
                    permissions=discord.Permissions(administrator=True),
                    hoist=False,
                    mentionable=False,
                    reason="Dashboard Sync - Antinuke Setup"
                )
                
            # Assign to Bot if missing
            if role not in guild.me.roles:
                await guild.me.add_roles(role, reason="Antinuke Self-Assignment")
                
            # Move role to highest possible position
            # Get bot's current highest role position
            bot_top_role = guild.me.top_role
            target_position = min(bot_top_role.position, len(guild.roles) - 2)
            
            if role.position < target_position:
                positions = {role: target_position}
                await guild.edit_role_positions(positions=positions)

        except discord.Forbidden:
            print(f"Antinuke Sync Error: Missing permissions in {guild.name}")
        except discord.HTTPException as e:
            print(f"Antinuke Sync Error: {e}")
            
    # --- RECOVERY SYSTEM LOGIC ---

    async def serialize_guild_state(self, guild):
        """Serialize guild state into a compressed JSON blob"""
        # 1. Guild Settings
        data = {
            "meta": {
                "ver": 1,
                "timestamp": int(time.time()),
                "guild_id": guild.id,
                "name": guild.name
            },
            "settings": {
                "verification_level": guild.verification_level.value,
                "default_notifications": guild.default_notifications.value,
                "explicit_content_filter": guild.explicit_content_filter.value,
                "mfa_level": guild.mfa_level,
                "system_channel_id": guild.system_channel.id if guild.system_channel else None,
                "rules_channel_id": guild.rules_channel.id if guild.rules_channel else None,
                "public_updates_channel_id": guild.public_updates_channel.id if guild.public_updates_channel else None,
                "afk_channel_id": guild.afk_channel.id if guild.afk_channel else None,
                "afk_timeout": guild.afk_timeout,
                "icon": str(guild.icon.url) if guild.icon else None
            },
            "roles": [],
            "channels": []
        }

        # 2. Roles (Reverse order to maintain hierarchy in list, though restoration logic handles position)
        for role in reversed(guild.roles):
            if role.is_default(): continue # Skip @everyone, handle separately if needed but usually immutable ID
            
            role_data = {
                "id": role.id,
                "name": role.name,
                "permissions": role.permissions.value,
                "color": role.color.value,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "position": role.position,
                "is_bot_managed": role.is_bot_managed(),
                "is_integration": role.is_integration()
            }
            data["roles"].append(role_data)

        # 3. Channels
        # Sort by position to ensure order
        channels = sorted(guild.channels, key=lambda c: c.position)
        for channel in channels:
            c_data = {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
                "position": channel.position,
                "category_id": channel.category_id,
                "overwrites": []
            }
            
            # Channel specific attributes
            if isinstance(channel, discord.TextChannel):
                c_data["topic"] = channel.topic
                c_data["nsfw"] = channel.nsfw
                c_data["slowmode_delay"] = channel.slowmode_delay
            elif isinstance(channel, discord.VoiceChannel):
                c_data["bitrate"] = channel.bitrate
                c_data["user_limit"] = channel.user_limit
                
            # Overwrites serialization
            for target, overwrite in channel.overwrites.items():
                # Store target ID and type
                target_type = "role" if isinstance(target, discord.Role) else "member"
                # Store allow/deny values
                allow, deny = overwrite.pair()
                c_data["overwrites"].append({
                    "id": target.id,
                    "type": target_type,
                    "allow": allow.value,
                    "deny": deny.value
                })
                
            data["channels"].append(c_data)

        # 4. Compression (Run in executor to avoid blocking)
        json_str = json.dumps(data, ensure_ascii=False)
        compressed = await self.bot.loop.run_in_executor(None, lambda: zlib.compress(json_str.encode('utf-8')))
        return compressed

    async def save_snapshot(self, guild, source="manual", triggered_by=None):
        """Save a new snapshot and rotate backup"""
        try:
            # 1. Generate new snapshot
            blob = await self.serialize_guild_state(guild)
            now = int(time.time())
            
            # 2. Transaction: Rotate & Save
            # Rotate: Slot 1 (Latest) -> Slot 2 (Backup)
            # MongoDB doesn't need explicit deletion for rotation if we upsert by ID, but we want to swap slots.
            
            # Delete old backup (Slot 2)
            await self.snapshots_col.delete_one({"guild_id": guild.id, "slot_id": 2})
            
            # Move Slot 1 to Slot 2
            await self.snapshots_col.update_one(
                {"guild_id": guild.id, "slot_id": 1},
                {"$set": {"slot_id": 2}}
            )
            
            # Insert new snapshot (Slot 1)
            await self.snapshots_col.insert_one({
                "guild_id": guild.id,
                "slot_id": 1,
                "data": blob,
                "created_at": now,
                "source": source,
                "triggered_by": triggered_by
            })
            
            print(f"✅ Saved snapshot for {guild.name} ({source})")
            return True
        except Exception as e:
            print(f"❌ Failed to save snapshot for {guild.name}: {e}")
            return False

    async def restore_snapshot(self, guild, snapshot_data):
        """Restore guild state from snapshot"""
        try:
            # Reconstruct Guild Settings
            settings = snapshot_data["settings"]
            await guild.edit(
                verification_level=discord.VerificationLevel(settings["verification_level"]),
                default_notifications=discord.NotificationLevel(settings["default_notifications"]),
                explicit_content_filter=discord.ContentFilter(settings["explicit_content_filter"]),
                afk_timeout=settings["afk_timeout"]
            )

            # Restore Roles
            # Strategy: Create missing, Update existing, Order matters
            # Needs careful handling to avoid API rate limits
            stored_roles = snapshot_data["roles"] 
            existing_roles = {r.id: r for r in guild.roles}
            
            for role_data in stored_roles:
                role_id = role_data["id"]
                if role_id in existing_roles:
                    # Update if needed (Permissions, Name, Color)
                    role = existing_roles[role_id]
                    try:
                        if role.name != role_data["name"] or role.permissions.value != role_data["permissions"] or role.color.value != role_data["color"]:
                            await role.edit(
                                name=role_data["name"],
                                permissions=discord.Permissions(role_data["permissions"]),
                                color=discord.Color(role_data["color"]),
                                hoist=role_data["hoist"],
                                mentionable=role_data["mentionable"]
                            )
                    except discord.Forbidden:
                        pass # Cannot edit top roles
                else:
                    # Create new role
                    try:
                        new_role = await guild.create_role(
                            name=role_data["name"],
                            permissions=discord.Permissions(role_data["permissions"]),
                            color=discord.Color(role_data["color"]),
                            hoist=role_data["hoist"],
                            mentionable=role_data["mentionable"]
                        )
                        # We cannot set ID, so mapping would be lost for channels. 
                        # This is a limitation of Discord API. 
                        # Ideally we map old_id -> new_id for channel overwrites.
                    except discord.Forbidden:
                        pass

            # Restore Channels
            stored_channels = snapshot_data["channels"]
            existing_channels = {c.id: c for c in guild.channels}
            
            for chan_data in stored_channels:
                cid = chan_data["id"]
                if cid not in existing_channels:
                    # Create missing channel
                    try:
                        # Simplified creation (Complex restoration requires category mapping etc)
                        if chan_data["type"] == "text":
                            await guild.create_text_channel(name=chan_data["name"], topic=chan_data.get("topic"))
                        elif chan_data["type"] == "voice":
                            await guild.create_voice_channel(name=chan_data["name"])
                        elif chan_data["type"] == "category":
                            await guild.create_category(name=chan_data["name"])
                    except:
                        pass
            
            return True
        except Exception as e:
            print(f"Restore Error: {e}")
            return False

    async def check_permissions(self, ctx):
        """Check if user has permission to use antinuke commands"""
        # Bot owner bypass - can use commands in any guild
        if self.is_bot_owner_check(ctx.author.id):
            return True
        
        # Check if user has administrator permissions
        is_admin = ctx.author.guild_permissions.administrator
        
        # Check if user is extra owner
        check = await self.extra_col.find_one({"guild_id": ctx.guild.id, "owner_id": ctx.author.id})

        # Permission check
        is_owner = ctx.author.id == ctx.guild.owner_id
        if not is_owner and not check and not ctx.author.guild_permissions.administrator:
            embed = discord.Embed(
                title="<:no:1396838761605890090> Access Denied",
                color=0x2b2d31,
                description="Only Server Owner, Extra Owner, Administrator, or Bot Owner can run this command!"
            )
            await ctx.send(embed=embed)
            return False
        return True

    async def get_antinuke_status(self, guild_id):
        """Get antinuke status for a guild"""
        doc = await self.antinuke_col.find_one({"guild_id": guild_id})
        return doc["status"] if doc else False

    # Main antinuke group command - HYBRID SUPPORT
    @commands.hybrid_group(
        name='antinuke',
        aliases=['antiwizz', 'anti'],  # Added aliases for prefix
        description="Anti-Nuke security system for your server",
        invoke_without_command=True
    )
    @commands.guild_only()
    @blacklist_check()
    @ignore_check()
    async def antinuke(self, ctx):
        """Main antinuke command group"""
        # Manual permission check that allows bot owner bypass
        if not await self.check_permissions(ctx):
            return
            
        if ctx.invoked_subcommand is None:
            # Get prefix dynamically
            if hasattr(ctx, 'prefix'):
                pre = ctx.prefix
            elif hasattr(ctx, 'clean_prefix'):
                pre = ctx.clean_prefix
            else:
                pre = '$'  # fallback prefix
            
            # Special indicator if user is bot owner
            owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(ctx.author.id) else ""
            
            embed = discord.Embed(
                title=f'__**Antinuke Security System**__{owner_badge}',
                description="Boost your server security with Antinuke! It automatically bans any admins involved in suspicious activities, ensuring the safety of your whitelisted members. Strengthen your defenses – activate Antinuke today!",
                color=0x2b2d31
            )
            embed.add_field(
                name='__**Available Commands**__',
                value=(
                    f'`{pre}antinuke enable` - Enable antinuke protection\n'
                    f'`{pre}antinuke disable` - Disable antinuke protection\n'
                    f'`{pre}antinuke enable [module]` - Enable a specific module\n'
                    f'`{pre}antinuke disable [module]` - Disable a specific module\n'
                    f'`{pre}antinuke status` - Check current status & modules\n\n'
                    f'**Available Modules:**\n`{", ".join(self.ANTINUKE_MODULES)}`'
                ),
                inline=False
            )
            
            if self.is_bot_owner_check(ctx.author.id):
                embed.add_field(
                    name=f'{BOT_OWNER_EMOJI} **Bot Owner Privileges**',
                    value='You have global access to antinuke commands in all servers',
                    inline=False
                )
                
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            await ctx.send(embed=embed)

    @antinuke.command(
        name='enable',
        aliases=['on', 'activate'],  # Added aliases
        description="Enable antinuke protection for your server"
    )
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    @app_commands.describe(module="Specific module to enable (optional)")
    @app_commands.choices(module=[app_commands.Choice(name=m, value=m) for m in ["ban", "kick", "bot", "channel_create", "channel_delete", "channel_update", "role_create", "role_delete", "role_update"]])
    async def antinuke_enable(self, ctx, module: str = None):
        """Enable antinuke protection or a specific module"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return

        guild_id = ctx.guild.id
        
        # If module is provided, just enable that module
        if module:
            if not await self.get_antinuke_status(guild_id):
                 embed = discord.Embed(
                    description=f"<:no:1396838761605890090> | Please enable the main Antinuke system first using `{ctx.prefix}antinuke enable`.",
                    color=0x2b2d31
                 )
                 await ctx.send(embed=embed)
                 return

            if module.lower() not in self.ANTINUKE_MODULES:
                embed = discord.Embed(
                    description=f"<:no:1396838761605890090> | Invalid module. Available modules: {', '.join(self.ANTINUKE_MODULES)}",
                    color=0x2b2d31
                )
                await ctx.send(embed=embed)
                return

            await self.enable_module(guild_id, module.lower())
            embed = discord.Embed(
                description=f"<:enabled:1396473501447098368> | Successfully **Enabled** the **{module.title()}** module.",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        # --- GLOBAL ENABLE LOGIC (Existing) ---
        is_activated = await self.get_antinuke_status(guild_id)

        if is_activated:
            owner_note = f" ({BOT_OWNER_EMOJI} Bot Owner Override)" if self.is_bot_owner_check(ctx.author.id) else ""
            embed = discord.Embed(
                description=f'**Antinuke Settings For {ctx.guild.name} <:antinuke:1396429037987168277>**{owner_note}\nYour server __**already has Antinuke enabled.**__\n\nCurrent Status: <:enabled:1396473501447098368> Enabled\nTo Disable use `{ctx.prefix if hasattr(ctx, "prefix") else "/"}antinuke disable`',
                color=0x2b2d31
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            await ctx.send(embed=embed)
            return

        # Setup process
        owner_badge = f" {BOT_OWNER_EMOJI}" if self.is_bot_owner_check(ctx.author.id) else ""
        setup_embed = discord.Embed(
            title=f"Antinuke System:{owner_badge}",
            color=0x6123ab
        )
        setup_embed.set_image(url="https://i.ibb.co/mrbVJWjK/standard-1.gif")
        setup_message = await ctx.send(embed=setup_embed)

        # Check permissions - bot owner can bypass some checks
        if not ctx.guild.me.guild_permissions.administrator:
            if self.is_bot_owner_check(ctx.author.id):
                pass # Owner bypass silently
            else:
                setup_embed.description = "\n<a:alert:1396429026842644584> | Setup failed: Missing **Administrator** permission."
                await setup_message.edit(embed=setup_embed)
                return

        
        # Create Scyro Core role
        try:
            # Check if role already exists
            existing_role = discord.utils.get(ctx.guild.roles, name="Scyro Core")
            if existing_role:
                role = existing_role
                if role not in ctx.guild.me.roles:
                    await ctx.guild.me.add_roles(role)
            else:
                role = await ctx.guild.create_role(
                    name="Scyro Core",
                    color=0x720e9e,
                    permissions=discord.Permissions(administrator=True),
                    hoist=False,
                    mentionable=False,
                    reason=f"Antinuke setup by {'Bot Owner' if self.is_bot_owner_check(ctx.author.id) else 'Server Admin'}"
                )
                await ctx.guild.me.add_roles(role)
        except discord.Forbidden:
            if self.is_bot_owner_check(ctx.author.id):
                pass
            else:
                setup_embed.description = "\n<a:alert:1396429026842644584> | Setup failed: Insufficient permissions to create role."
                await setup_message.edit(embed=setup_embed)
                return
        except discord.HTTPException as e:
            setup_embed.description = f"\n<a:alert:1396429026842644584> | Setup failed: HTTPException: {e}\nCheck Guild **Audit Logs**."
            await setup_message.edit(embed=setup_embed)
            return
        
        # Move role to highest possible position (safer approach)
        try:
            # Get bot's current highest role position
            bot_top_role = ctx.guild.me.top_role
            
            # Try to move the role just below the bot's highest role or as high as possible
            target_position = min(bot_top_role.position, len(ctx.guild.roles) - 2)
            
            # Only move if the role isn't already at a good position
            if 'role' in locals() and role.position < target_position:
                positions = {role: target_position}
                await ctx.guild.edit_role_positions(positions=positions)
            else:
                pass
                
        except discord.Forbidden:
            # Log failure locally or ignore
             pass
        except discord.HTTPException as e:
             pass
        except Exception:
             pass
        
        # Artificial delay to let the GIF play gracefully for a moment
        await asyncio.sleep(2.5)

        # Enable antinuke in database
        await self.antinuke_col.update_one(
            {"guild_id": guild_id},
            {"$set": {"status": True, "punishment": "ban"}},
            upsert=True
        )
        
        # Enable all modules by default
        for mod in self.ANTINUKE_MODULES:
             await self.enable_module(guild_id, mod)

        # Enable limit settings
        await self.enable_limit_settings(guild_id)

        await setup_message.delete()

        # Success embed
        owner_note = f"\n\n{BOT_OWNER_EMOJI} **Bot Owner Override:** Setup completed with elevated privileges!" if self.is_bot_owner_check(ctx.author.id) else ""
        
        # Grouped Modules with requested styling
        categories = {
            "``•`` Server Modules:": ["Anti Ban", "Anti Kick", "Anti Bot", "Anti Prune", "Anti Guild Update", "Anti Integration"],
            "``•`` Channel Modules:": ["Anti Channel Create", "Anti Channel Delete", "Anti Channel Update"],
            "``•`` Role Modules:": ["Anti Role Create", "Anti Role Delete", "Anti Role Update"],
            "``•`` Webhook Modules:": ["Anti Webhook Create", "Anti Webhook Delete", "Anti Webhook Update"],
            "``•`` Other Modules:": ["Anti Member Update", "Anti Everyone/Here"]
        }
        
        modules_text = ""
        for category, modules in categories.items():
            modules_text += f"\n**{category}**\n"
            for m in modules:
                 # Title case conversion (Keep Anti prefix)
                 m_display = m.title().replace("Everyone", "Everyone/Here") 
                 modules_text += f"> <:enabled:1396473501447098368> **`{m_display}`**\n"

        embed = discord.Embed(
            description=f"**Antinuke Settings For {ctx.guild.name} Enabled Successfully**\n\n"
                        f"<:bulb:1396429065266663534> **Tip:** Ensure my role has **Administrator** perms and is at the top.\n\n"
                        f"{modules_text}",
            color=0x2b2d31
        )

        embed.set_author(name="Scyro Antinuke", icon_url=self.bot.user.avatar.url)
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text=f"Powered by Scyro.xyz | {BOT_OWNER_EMOJI} Bot Owner Override" if self.is_bot_owner_check(ctx.author.id) else "Powered by Scyro.xyz", icon_url=self.bot.user.avatar.url)

        # --- AUTO SNAPSHOT ON ENABLE ---
        # Check if snapshot exists
        has_snapshot = await self.snapshots_col.find_one({"guild_id": guild_id, "slot_id": 1})
        
        if not has_snapshot:
            # Silent auto-save
            self.bot.loop.create_task(self.save_snapshot(ctx.guild, source="auto_enable", triggered_by=ctx.author.id))
            embed.description += "\n\n**``•``** <:syfolder:1445413611609788428> **Auto-Recovery:** Baseline snapshot created."

        # Add button view
        view = PunishmentView()
        await ctx.send(embed=embed, view=view)

    @antinuke.command(
        name='disable',
        aliases=['off', 'deactivate'],  # Added aliases
        description="Disable antinuke protection or a specific module"
    )
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @app_commands.describe(module="Specific module to disable (optional)")
    @app_commands.choices(module=[app_commands.Choice(name=m, value=m) for m in ["ban", "kick", "bot", "channel_create", "channel_delete", "channel_update", "role_create", "role_delete", "role_update"]])
    async def antinuke_disable(self, ctx, module: str = None):
        """Disable antinuke protection or a specific module"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return

        guild_id = ctx.guild.id
        
        # If module is provided, just disable that module
        if module:
            if not await self.get_antinuke_status(guild_id):
                 embed = discord.Embed(
                    description=f"<:no:1396838761605890090> | Antinuke is already disabled.",
                    color=0x2b2d31
                 )
                 await ctx.send(embed=embed)
                 return

            if module.lower() not in self.ANTINUKE_MODULES:
                embed = discord.Embed(
                    description=f"<:no:1396838761605890090> | Invalid module. Available modules: {', '.join(self.ANTINUKE_MODULES)}",
                    color=0x2b2d31
                )
                await ctx.send(embed=embed)
                return

            await self.disable_module(guild_id, module.lower())
            embed = discord.Embed(
                description=f"<:disabled:1396473518962507866> | Successfully **Disabled** the **{module.title()}** module.",
                color=0x2b2d31
            )
            await ctx.send(embed=embed)
            return

        # --- GLOBAL DISABLE LOGIC ---
        is_activated = await self.get_antinuke_status(guild_id)

        owner_note = f" ({BOT_OWNER_EMOJI} Bot Owner Override)" if self.is_bot_owner_check(ctx.author.id) else ""

        if not is_activated:
            embed = discord.Embed(
                description=f'**Antinuke Settings For {ctx.guild.name}**{owner_note} <:antinuke:1396429037987168277> \nUhh, looks like your server hasn\'t enabled Antinuke.\n\nCurrent Status: <:disabled:1396473518962507866> Disabled\n\nTo Enable use `{ctx.prefix if hasattr(ctx, "prefix") else "/"}antinuke enable` to make sure that your Server is **Protected**.',
                color=0x2b2d31
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            await ctx.send(embed=embed)
            return

        # --- CONFIRMATION VIEW ---
        from discord.ui import Button, View

        confirm_embed = discord.Embed(
            description=f"<a:alert:1396429026842644584> **Are you sure you want to disable Antinuke?**\n\nThis will leave your server **VULNERABLE** to attacks.",
            color=0x2b2d31
        )
        
        yes_button = Button(label="Yes, Disable", style=discord.ButtonStyle.danger)
        no_button = Button(label="No, Cancel", style=discord.ButtonStyle.success)

        async def yes_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("This interaction is not for you.", ephemeral=True)
            
            # Defer interaction to prevent timeout and "InteractionResponded" issues
            try:
                await interaction.response.defer()
            except:
                pass

            # Disable antinuke
            await self.antinuke_col.delete_one({"guild_id": guild_id})
            await self.modules_col.delete_many({"guild_id": guild_id}) # Clean up modules
            
            # Disable limit settings
            await self.disable_limit_settings(guild_id)
            
            success_embed = discord.Embed(
                description=f'**Antinuke Settings For {ctx.guild.name}**{owner_note} <:antinuke:1396429037987168277> \nSuccessfully disabled Antinuke for this Server.\n\nCurrent Status: <:disabled:1396473518962507866> Disabled\n\nTo Enable use `{ctx.prefix if hasattr(ctx, "prefix") else "/"}antinuke enable` to make sure that your Server is **Protected**.',
                color=0x2b2d31
            )
            success_embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            # Use edit_original_response since we deferred (or it was auto-deferred)
            try:
                await interaction.edit_original_response(embed=success_embed, view=None)
            except:
                # Fallback to message edit if interaction fails for some reason
                await interaction.message.edit(embed=success_embed, view=None)

        async def no_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("This interaction is not for you.", ephemeral=True)
            
            cancel_embed = discord.Embed(
                description="<:yes:1396838746862784582> **Cancelled.** Antinuke remains active.",
                color=0x2b2d31
            )
            await interaction.response.edit_message(embed=cancel_embed, view=None)

        view = View(timeout=30)
        view.add_item(yes_button)
        view.add_item(no_button)
        yes_button.callback = yes_callback
        no_button.callback = no_callback

        await ctx.send(embed=confirm_embed, view=view)

    @antinuke.command(
        name='status',
        aliases=['info', 'check'],  # Added aliases
        description="Check the current antinuke status and modules"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def antinuke_status(self, ctx):
        """Check antinuke status"""
        # Check permissions (includes bot owner bypass)
        if not await self.check_permissions(ctx):
            return

        guild_id = ctx.guild.id
        is_activated = await self.get_antinuke_status(guild_id)

        status_emoji = "<:enabled:1396473501447098368>" if is_activated else "<:disabled:1396473518962507866>"
        status_text = "Enabled" if is_activated else "Disabled"
        
        # Special title for bot owner
        title = f"<:antinuke:1396429037987168277> **Antinuke Status**"
        if self.is_bot_owner_check(ctx.author.id):
            title += f" {BOT_OWNER_EMOJI}"
        
        embed = discord.Embed(
            title=title,
            description=f"**Server:** {ctx.guild.name}\n**Status:** {status_emoji} **{status_text}**",
            color=0x00ff00 if is_activated else 0xff0000
        )
        
        if is_activated:
            embed.add_field(
                name="🛡️ **Protection Active**",
                value="Your server is protected by Scyro Antinuke",
                inline=False
            )
            
            # Show role info
            scyro_role = discord.utils.get(ctx.guild.roles, name="Scyro Core")
            role_status = f"✅ Present (Pos: {scyro_role.position})" if scyro_role else "❌ Missing"
            embed.add_field(name="🔒 **Security Role**", value=role_status, inline=False)
            
            # Module Statuses - Categorized with Blockquotes
            categories = {
                "Server Security": ["ban", "kick", "bot", "prune", "guild_update", "integration"],
                "Channels": ["channel_create", "channel_delete", "channel_update"],
                "Roles": ["role_create", "role_delete", "role_update"],
                "Webhooks": ["webhook_create", "webhook_delete", "webhook_update"],
                "Others": ["member_update", "everyone"]
            }

            modules_text = ""
            for category, modules in categories.items():
                modules_text += f"\n**{category}**\n"
                for mod in modules:
                    enabled = await self.is_module_enabled(guild_id, mod)
                    icon = "<:enabled:1396473501447098368>" if enabled else "<:disabled:1396473518962507866>"
                    # Apply Title Case correctly
                    name = mod.replace("_", " ").title().replace("Everyone", "Everyone/Here")
                    # Restore "Anti " logic (it was stripped in the previous regex or manually)
                    # The mod name usually comes as "ban", "kick" in the database check?
                    # Wait, `mod` iterating over `modules` which are "Anti Ban", "Anti Kick" etc.
                    # In Status embed (line 800+), `m` comes from `categories`.
                    # Categories are defined as "Anti Ban", "Anti Kick".
                    # So `mod` is ALREADY "Anti Ban".
                    # I just need to verify I'm not stripping it.
                    
                    # My previous code was: name = mod ... title() ... remove "Anti ".
                    # So `mod.title()` is "Anti Ban".
                    modules_text += f"> {icon}   **`{name}`**\n"
            
            # Use one main description block
            embed.description += f"\n\n{modules_text}"
            embed.color = 0x2b2d31 # Grey

        else:
             # ... (Disable embed)
            embed = discord.Embed(
                description=f"**Antinuke Settings For {ctx.guild.name} {f'{BOT_OWNER_EMOJI} ' if self.is_bot_owner_check(ctx.author.id) else ''}:antinuke:**\n"
                            f"Successfully disabled Antinuke for this Server.\n\n"
                            f"Current Status: <:disabled:1396473518962507866> Disabled\n\n"
                            f"To Enable use `/antinuke enable` to make sure that your Server is **Protected**.",
                color=0x2b2d31
            )
        
        if self.is_bot_owner_check(ctx.author.id):
             embed.set_footer(text=f"Powered by Scyro.xyz | {BOT_OWNER_EMOJI} Bot Owner Override", icon_url=self.bot.user.avatar.url)
        else:
             embed.set_footer(text="Powered by Scyro.xyz", icon_url=self.bot.user.avatar.url)
        await ctx.send(embed=embed)

    # Error handlers
    @antinuke.error
    @antinuke_enable.error
    @antinuke_disable.error
    @antinuke_status.error
    async def antinuke_error(self, ctx, error):
        """Error handler for antinuke commands"""
        if isinstance(error, commands.CommandOnCooldown):
            # Reduce cooldown display for bot owner
            if self.is_bot_owner_check(ctx.author.id):
                embed = discord.Embed(
                    title=f"{BOT_OWNER_EMOJI} **Bot Owner Cooldown**",
                    description=f"Please wait **{error.retry_after:.1f}** seconds (reduced for bot owner)",
                    color=0x2b2d31
                )
            else:
                embed = discord.Embed(
                    title="⏰ **Cooldown Active**",
                    description=f"Please wait **{error.retry_after:.1f}** seconds before using this command again!",
                    color=0x2b2d31
                )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.MaxConcurrencyReached):
            embed = discord.Embed(
                title="⚠️ **Setup In Progress**",
                description="Another antinuke setup is already running in this server. Please wait for it to complete.",
                color=0x2b2d31
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            print(f"Antinuke command error: {type(error).__name__}: {error}")

    # --- RECOVERY COMMANDS ---

    @antinuke.group(name="recovery", description="Manage antinuke recovery snapshots")
    async def recovery(self, ctx):
        pass

    @recovery.command(name="save", description="Manually save a recovery snapshot (Server Owner/Extra Owner only)")
    @commands.guild_only()
    async def recovery_save(self, ctx):
        """Manually save a recovery snapshot. 24h Cooldown."""
        guild = ctx.guild
        author_id = ctx.author.id

        # 1. Strict Permission Check (Owner or Extra Owner ONLY - NO ADMINS)
        is_owner = author_id == guild.owner_id
        is_bot_owner = self.is_bot_owner_check(author_id)
        
        async with self.db.execute("SELECT 1 FROM extraowners WHERE guild_id = ? AND owner_id = ?", (guild.id, author_id)) as cursor:
            is_extra_owner = await cursor.fetchone()

        if not (is_owner or is_extra_owner or is_bot_owner):
             embed = discord.Embed(
                description="<:no:1396838761605890090> | Only the **Server Owner** or **Extra Owners** can save snapshots.",
                color=0x2b2d31
             )
             await ctx.send(embed=embed, ephemeral=True)
             return

        # 2. Check Cooldown
        if not is_bot_owner:
            row = await self.cooldowns_col.find_one({"guild_id": guild.id})
            if row:
                last_save = row.get('last_manual_save', 0)
                diff = int(time.time()) - last_save
                if diff < 86400: # 24 hours
                    hours_left = (86400 - diff) // 3600
                    embed = discord.Embed(
                        description=f"<:alert:1396429026842644584> | Recovery settings are already up to date. Please wait **{hours_left} hours** before saving again.",
                        color=0x2b2d31
                    )
                    await ctx.send(embed=embed, ephemeral=True)
                    return

        # 3. Confirmation
        embed = discord.Embed(
            title="**``•``** <:syfolder:1445413611609788428> Save Recovery Snapshot?",
            description="This will overwrite your previous backup. Continue?",
            color=0x2b2d31
        )
        embed.set_footer(text="Abuse of this system may result in a blacklist.")
        
        view = ConfirmView(ctx.author.id)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        
        if not view.value:
            await msg.delete()
            return

        # 4. Save Process
        wait_embed = discord.Embed(description="<a:loading:1409448581911416904> | Saving server state... this may take a moment...", color=0x2b2d31)
        await msg.edit(embed=wait_embed, view=None)

        success = await self.save_snapshot(guild, source="manual", triggered_by=author_id)
        
        if success:
            now = int(time.time())
            await self.cooldowns_col.update_one(
                {"guild_id": guild.id},
                {"$set": {"last_manual_save": now}},
                upsert=True
            )
            
            done_embed = discord.Embed(
                description=f"<:enabled:1396473501447098368> | **Snapshot Saved.**\nThis state is now the `Latest` recovery point. Previous latest is now `Backup`.",
                color=0x2b2d31
            )
            await msg.edit(embed=done_embed)
        else:
            err_embed = discord.Embed(description="<:no:1396838761605890090> | Failed to save snapshot. Please contact support.", color=0x2b2d31)
            await msg.edit(embed=err_embed)

    @antinuke.command(name="recover", description="Manually restore server state from snapshot (Server Owner/Extra Owner only)")
    @commands.guild_only()
    async def recovery_recover(self, ctx):
        """Manually restore server state. 24h Cooldown."""
        guild = ctx.guild
        author_id = ctx.author.id

        is_owner = author_id == guild.owner_id
        is_bot_owner = self.is_bot_owner_check(author_id)
        
        is_extra_owner = await self.extra_col.find_one({"guild_id": guild.id, "owner_id": author_id})

        if not (is_owner or is_extra_owner or is_bot_owner):
             embed = discord.Embed(
                description="<:no:1396838761605890090> | Only the **Server Owner** or **Extra Owners** can recover the server.",
                color=0x2b2d31
             )
             await ctx.send(embed=embed, ephemeral=True)
             return

        # Cooldown Check
        if not is_bot_owner:
            row = await self.cooldowns_col.find_one({"guild_id": guild.id})
            if row:
                last_recover = row.get('last_manual_recover', 0)
                diff = int(time.time()) - last_recover
                if diff < 86400: # 24 hours
                    hours_left = (86400 - diff) // 3600
                    embed = discord.Embed(
                        description=f"<:alert:1396429026842644584> | Recovery is on cooldown. Please wait **{hours_left} hours** before recovering again.",
                        color=0x2b2d31
                    )
                    await ctx.send(embed=embed, ephemeral=True)
                    return

        # Fetch Snapshot
        row = await self.snapshots_col.find_one({"guild_id": guild.id, "slot_id": 1})
        if not row:
            embed = discord.Embed(description="<:no:1396838761605890090> | No recovery snapshot found.", color=0x2b2d31)
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Decompress
        try:
            blob = row['data']
            decompressed = await self.bot.loop.run_in_executor(None, lambda: zlib.decompress(blob))
            snapshot_data = json.loads(decompressed)
        except Exception as e:
            embed = discord.Embed(description="<:no:1396838761605890090> | Snapshot data is corrupted.", color=0x2b2d31)
            await ctx.send(embed=embed, ephemeral=True)
            print(f"Decompression Error: {e}")
            return

        # Confirmation
        ts = snapshot_data['meta']['timestamp']
        date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        
        embed = discord.Embed(
            title="**``•``** <:syfolder:1445413611609788428> Restore Server State?",
            description=f"This will attempt to restore settings, roles, and channels from the snapshot.\n**Snapshot Date:** `{date_str}`\n\n**WARNING:** This action cannot be undone.",
            color=0x2b2d31
        )
        
        view = ConfirmView(ctx.author.id)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        
        if not view.value:
            await msg.delete()
            return

        # Execute Restore
        wait_embed = discord.Embed(description="<a:loading:1409448581911416904> | Restoring server state... This allows take a while...", color=0x2b2d31)
        await msg.edit(embed=wait_embed, view=None)

        success = await self.restore_snapshot(guild, snapshot_data)
        
        if success:
            now = int(time.time())
            await self.cooldowns_col.update_one(
                {"guild_id": guild.id},
                {"$set": {"last_manual_recover": now}},
                upsert=True
            )
            
            done_embed = discord.Embed(
                description=f"<:enabled:1396473501447098368> | **Restoration Complete.**\nProcessed Roles, Channels, and Settings.",
                color=0x2b2d31
            )
            await msg.edit(embed=done_embed)
        else:
            err_embed = discord.Embed(description="<:no:1396838761605890090> | Restoration encountered errors. Check logs.", color=0x2b2d31)
            await msg.edit(embed=err_embed)

# Separate View class for the punishment button
class ConfirmView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="<:yes:1396838746862784582>")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This isn't for you.", ephemeral=True)
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="<:no:1396838761605890090>")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("This isn't for you.", ephemeral=True)
        self.value = False
        self.stop()
        await interaction.response.defer()

class PunishmentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="Show Punishments", 
        style=discord.ButtonStyle.secondary,
        emoji="⚖️",
        custom_id="show_punishment"
    )
    async def show_punishment(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show punishment types"""
        embed = discord.Embed(
            title="Punishment Types for Changes Made by Unwhitelisted Users/Admins/Mods",
            description=(
                "<a:dot:1396429135588626442> **Anti Ban:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Kick:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Bot:** Ban the bot Inviter\n"
                "<a:dot:1396429135588626442> **Anti Channel Create/Delete/Update:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Everyone/Here:** Remove the message & 1 hour timeout\n"
                "<a:dot:1396429135588626442> **Anti Role Create/Delete/Update:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Member Update:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Guild Update:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Integration:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Webhook Create/Delete/Update:** Ban\n"
                "<a:dot:1396429135588626442> **Anti Prune:** Ban\n"
                "<a:dot:1396429135588626442> **Auto Recovery:** Automatically recover damaged channels, roles, and settings\n\n"
                "<:bulb:1396429065266663534> **Note:** In the case of member updates, action will be taken only if the role contains dangerous permissions such as Ban Members, Administrator, Manage Guild, Manage Channels, Manage Roles, Manage Webhooks, or Mention Everyone"
            ),
            color=0x2b2d31
        )
        embed.set_footer(
            text="These punishment types are fixed and assigned as required to ensure guild security/protection", 
            icon_url=interaction.client.user.avatar.url
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        """Disable view when timeout occurs"""
        for item in self.children:
            item.disabled = True

async def setup(bot):
    await bot.add_cog(Antinuke(bot))
