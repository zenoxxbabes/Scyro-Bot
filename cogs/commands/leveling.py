import discord
from discord.ext import commands, tasks
import motor.motor_asyncio
import random
import time
import os
import math
import json
from io import BytesIO
from collections import defaultdict
from pymongo import UpdateOne

# Try importing PIL for rank card
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.xp_cooldowns = {}
        self.config_cache = {} # {guild_id: (config_dict, timestamp)}
        self.stats_batch = defaultdict(int) # {(guild_id, user_id): count}
        
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.users = None
        self.settings = None

        self.bot.loop.create_task(self.init_db())
        self.flush_stats.start()

    def cog_unload(self):
        self.flush_stats.cancel()
    
    @tasks.loop(seconds=10)
    async def flush_stats(self):
        if not self.stats_batch or self.users is None: return
        
        # Snapshot and clear
        current_batch = self.stats_batch.copy()
        self.stats_batch.clear()
        
        try:
            operations = []
            for (guild_id, user_id), count in current_batch.items():
                operations.append(UpdateOne(
                    {"guild_id": guild_id, "user_id": user_id},
                    {"$inc": {"msg_count": count}, "$setOnInsert": {"xp": 0, "level": 0, "voice_time": 0}},
                    upsert=True
                ))
            
            if operations:
                await self.users.bulk_write(operations)

        except Exception as e:
            print(f"[Leveling] Failed to flush stats: {e}")

    @flush_stats.before_loop
    async def before_flush(self):
        await self.bot.wait_until_ready()

    async def init_db(self):
        if not self.mongo_uri:
            print("❌ [Leveling] MONGO_URI not found.")
            return

        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            self.db = self.client.get_database() # Or self.client["scyro"] if a specific DB is needed
            self.users = self.db.leveling_users # This is the collection for user data
            self.settings = self.db.leveling_settings

            # Indexes
            await self.users.create_index([("guild_id", 1), ("user_id", 1)], unique=True)
            await self.settings.create_index("guild_id", unique=True)
            
            print("✅ [Leveling] MongoDB connected.")
        except Exception as e:
            print(f"❌ [Leveling] DB Init Error: {e}")

    def get_xp_for_level(self, level):
        # User requested specific curve: 50, 150(total?), etc.
        # Using quadratic curve starting at 50 for L1.
        return 50 * (level ** 2)

    def get_level_for_xp(self, xp):
        return int(math.sqrt(xp / 50))

    async def get_config(self, guild_id):
        # Check cache (TTL 60s)
        if guild_id in self.config_cache:
            data, timestamp = self.config_cache[guild_id]
            if time.time() - timestamp < 60:
                return data

        if self.settings is None: return {"enabled": 0}

        doc = await self.settings.find_one({"guild_id": guild_id})
        if doc:
            data = doc
            self.config_cache[guild_id] = (data, time.time())
            return data
        
        return {"enabled": 0, "levelup_channel": None, "levelup_message": "GG {user.mention}, you just leveled up to **Level {level}**!", "msg_config": None, "voice_config": None, "reaction_config": None, "rewards": None, "ignores": None, "auto_reset": 0}

    def check_ignores(self, member, channel, ignores_json):
        if not ignores_json: return False
        try:
            data = json.loads(ignores_json)
            # Check Roles
            if "roles" in data:
                for role_id in data["roles"]:
                    if member.get_role(int(role_id)): return True
            # Check Channels
            if "channels" in data:
                if str(channel.id) in data["channels"] or channel.id in data["channels"]: return True
        except: pass
        return False

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        config = await self.get_config(member.guild.id)
        if config and config.get('auto_reset'):
             try:
                 await self.users.delete_one({"guild_id": member.guild.id, "user_id": member.id})
             except Exception: pass

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not reaction.message.guild: return
        config = await self.get_config(reaction.message.guild.id)
        
        # Check Ignores
        if self.check_ignores(user, reaction.message.channel, config.get('ignores')): return

        # Load Config
        try:
            rc = json.loads(config['reaction_config']) if config.get('reaction_config') else {}
        except: rc = {}
        
        if not rc.get('enabled', True): return 
        
        # Cooldown
        key = f"react_{reaction.message.guild.id}_{user.id}"
        if key in self.xp_cooldowns and time.time() - self.xp_cooldowns[key] < rc.get('cooldown', 300):
            return
        self.xp_cooldowns[key] = time.time()

        # Award XP
        mode = rc.get('awards', 'Both') # Both, Author, Reactor, None
        xp_min = int(rc.get('min', 25))
        xp_max = int(rc.get('max', 25))
        
        xp_to_give = random.randint(xp_min, xp_max)
        
        targets = []
        if mode in ['Reactor', 'Both']: targets.append(user)
        if mode in ['Author', 'Both'] and not reaction.message.author.bot: targets.append(reaction.message.author)
        
        for target in targets:
            await self.award_xp(reaction.message.guild, target, xp_to_give, config)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        
        # Start Session
        if before.channel is None and after.channel is not None:
             self.xp_cooldowns[f"voice_{member.id}"] = time.time()
             
        # End Session
        elif before.channel is not None and after.channel is None:
             start_time = self.xp_cooldowns.pop(f"voice_{member.id}", None)
             if start_time:
                 config = await self.get_config(member.guild.id)
                 
                 # Check Ignores
                 if self.check_ignores(member, before.channel, config.get('ignores')): return

                 try:
                    vc_conf = json.loads(config['voice_config']) if config.get('voice_config') else {}
                 except: vc_conf = {}
                 
                 # Checks
                 if vc_conf.get('min_members', 0) > 0 and len(before.channel.members) < vc_conf['min_members']: return
                 if vc_conf.get('anti_afk', False) and (member.voice.self_deaf or member.voice.self_mute): return 
                 
                 duration = time.time() - start_time
                 cooldown = vc_conf.get('cooldown', 60) 
                 
                 if duration > 10: 
                     xp_min = int(vc_conf.get('min', 15))
                     xp_max = int(vc_conf.get('max', 40))
                     avg_xp = (xp_min + xp_max) / 2
                     
                     intervals = int(duration / cooldown) if cooldown > 0 else 0
                     if intervals < 1: return

                     xp_gain = int(intervals * avg_xp)
                     
                     await self.award_xp(member.guild, member, xp_gain, config, voice_time_add=duration)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # Optimized: Add to batch instead of DB write (handled by flush_stats)
        self.stats_batch[(message.guild.id, message.author.id)] += 1
        
        config = await self.get_config(message.guild.id)
        
        # Check Ignores
        if self.check_ignores(message.author, message.channel, config.get('ignores')): 
            return

        # Msg Config
        try:
            mc = json.loads(config['msg_config']) if config.get('msg_config') else {}
        except: mc = {}

        mode = mc.get('mode', 'Default')
        if mode == 'None': return
        
        # Cooldown check
        cooldown = mc.get('cooldown', 1) 
        key = (message.guild.id, message.author.id)
        if key in self.xp_cooldowns and time.time() - self.xp_cooldowns[key] < cooldown:
            return
        self.xp_cooldowns[key] = time.time()
        
        # Calculate XP based on Character Count (User Request)
        char_count = len(message.content.replace(" ", "").replace("\n", ""))
        
        # Max 100 XP per message regardless of length
        xp_gain = min(char_count, 100)
        
        # Minimum 1 XP if message has content
        if xp_gain < 1 and char_count > 0: xp_gain = 1
        elif xp_gain < 1: return # Empty message

        await self.award_xp(message.guild, message.author, xp_gain, config)

    async def award_xp(self, guild, member, amount, config, voice_time_add=0):
        if self.users is None: return
        
        # Check if Leveling is Enabled before awarding XP
        # But we still want to record voice_time if passed (similar to flush_stats for msgs)
        # However, flush_stats handles message counts. Voice time is handled here.
        # If disabled, maybe we still track voice time but not XP?
        # User said "dont stop cmds in tracker.py make them work as usual".
        # This implies tracking should continue.
        # But if we don't award XP, then level stays 0.
        
        enabled = config.get('enabled', 0)
        
        # Atomic Upsert with $inc
        try:
            update_fields = {}
            if enabled:
                update_fields["xp"] = amount
            
            if voice_time_add > 0:
                update_fields["voice_time"] = voice_time_add
            
            # If nothing to update (disabled and not voice), skip
            if not update_fields: return
            
            result = await self.users.find_one_and_update(
                {"guild_id": guild.id, "user_id": member.id},
                {
                    "$inc": update_fields,
                    "$setOnInsert": {"level": 0, "msg_count": 0}
                },
                upsert=True,
                return_document=True # Return AFTER update
            )
            
            new_xp = result.get('xp', 0)
            current_level = result.get('level', 0)
            
            calculated_level = self.get_level_for_xp(new_xp)
            
            if calculated_level > current_level:
                await self.users.update_one(
                    {"guild_id": guild.id, "user_id": member.id},
                    {"$set": {"level": calculated_level}}
                )
                
                # Send announcement - ONLY IF ENABLED
                if config.get('enabled', 0):
                    if config.get('levelup_channel'):
                        ch = guild.get_channel(config['levelup_channel'])
                        try:
                            msg = config['levelup_message'].replace("{user.mention}", member.mention)\
                                             .replace("{user.name}", member.name)\
                                             .replace("{level}", str(calculated_level))\
                                             .replace("{server.name}", guild.name)
                            if ch: await ch.send(msg)
                            elif not config['levelup_channel']: await member.send(msg) # Optional fallback
                        except: pass
                
                # Grant Rewards
                if config.get('enabled', 0) and config.get('rewards'):
                    try:
                        rewards_raw = config['rewards']
                        if isinstance(rewards_raw, str):
                            rewards = json.loads(rewards_raw)
                        else:
                            rewards = rewards_raw # Already list/dict
                            
                        # Ensure list
                        if not isinstance(rewards, list): rewards = []

                        for r in rewards:
                            req_level = int(r['level'])
                            # Reward logic: check crossing threshold
                            if current_level < req_level <= calculated_level:
                                role_id = int(r['role'])
                                role = guild.get_role(role_id)
                                if role:
                                    await member.add_roles(role, reason="Level Up Reward")
                    except Exception as e:
                        print(f"Reward Error: {e}")
        except Exception as e:
            print(f"Award XP Error: {e}")

    @commands.hybrid_group(name='leveling', invoke_without_command=True)
    async def leveling(self, ctx):
        await ctx.send_help(ctx.command)

    async def get_user_data(self, guild_id, user_id):
        if self.users is None: return None
        doc = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        return (doc['xp'], doc['level']) if doc else None

    @leveling.command(name='config', aliases=['conf'], description="View the detailed configuration of the leveling system")
    @commands.has_permissions(manage_guild=True)
    async def config(self, ctx):
        """View the current Leveling configuration for this server."""
        config = await self.get_config(ctx.guild.id)
        if not config or not config.get('enabled'):
            return await ctx.send("Leveling is not configured for this server.")

        embed = discord.Embed(title=f"📊 Leveling Configuration for {ctx.guild.name}", color=0x5865F2)
        
        # Status
        status = "✅ Enabled" if config.get('enabled') else "❌ Disabled"
        embed.add_field(name="Status", value=status, inline=True)
        
        # Channel
        ch_id = config.get('levelup_channel')
        ch = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_text = ch.mention if ch else "**Current Channel** (Context)"
        embed.add_field(name="Level Up Channel", value=ch_text, inline=True)
        
        # Message
        msg_preview = config.get('levelup_message', "Default message")
        if len(msg_preview) > 50: msg_preview = msg_preview[:47] + "..."
        embed.add_field(name="Level Message", value=f"`{msg_preview}`", inline=False)

        # Rewards (Parsed from JSON)
        try:
            rewards = json.loads(config['rewards']) if config.get('rewards') else []
            if rewards:
                rewards.sort(key=lambda x: int(x['level']))
                lines = []
                for r in rewards:
                    role = ctx.guild.get_role(int(r['role']))
                    role_name = role.mention if role else "`Deleted Role`"
                    lines.append(f"**Lvl {r['level']}**: {role_name}")
                rewards_text = "\n".join(lines)
            else:
                rewards_text = "No rewards set."
        except:
            rewards_text = "Error parsing rewards."
        
        embed.add_field(name="🏆 Level Rewards", value=rewards_text, inline=False)

        # XP Rates Summary
        try:
            # Message
            mc = json.loads(config['msg_config']) if config.get('msg_config') else {}
            msg_mode = mc.get('mode', 'Random')
            msg_rate = f"{mc.get('min', 15)}-{mc.get('max', 25)} XP (CD: {mc.get('cooldown', 60)}s)" if msg_mode != 'None' else "Disabled"
            
            # Voice
            vc = json.loads(config['voice_config']) if config.get('voice_config') else {}
            voice_rate = f"{vc.get('min', 15)}-{vc.get('max', 40)} XP / {vc.get('cooldown', 60)}s" if config.get('enabled') else "Disabled" 
            
            # React
            rc = json.loads(config['reaction_config']) if config.get('reaction_config') else {}
            react_enabled = rc.get('enabled', True)
            react_rate = f"{rc.get('min', 25)}-{rc.get('max', 25)} XP" if react_enabled else "Disabled"

            embed.add_field(name="📈 XP Rates", value=f"**Msg**: {msg_rate}\n**Voice**: {voice_rate}\n**React**: {react_rate}", inline=False)
        except Exception as e:
            embed.add_field(name="📈 XP Rates", value="Error parsing config.", inline=False)

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=embed)

    @leveling.command(name='setup', description="Quickly set up the leveling system via Dashboard link")
    async def setup(self, ctx):
        embed = discord.Embed(
            title="⚙️ Leveling Setup",
            description=(
                "Setting up leveling through commands can be slow and tedious.\n"
                "**We recommend using our powerful Dashboard for instant setup!**\n\n"
                "🔗 **[Click here to Configure Leveling](https://scyro.xyz/dashboard)**\n\n"
                "On the dashboard you can:\n"
                "• Enable/Disable the system\n"
                "• Set Custom Level Up Messages\n"
                "• Choose Level Up Channels\n"
                "• Reset Data"
            ),
            color=0x5865F2
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        await ctx.send(embed=embed)

    @leveling.command(name='reset', description="Reset all leveling data for this server (Irreversible)")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        # Quick confirmation
        confirm_embed = discord.Embed(
            title="⚠️ Reset Leveling Data",
            description="Are you sure you want to **RESET ALL** XP and Levels for this server?\nThis action cannot be undone.",
            color=0xFF0000
        )
        
        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
            async def confirm(self, interaction, button):
                if interaction.user.id != ctx.author.id: return
                self.value = True
                self.stop()
                await interaction.response.defer()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction, button):
                if interaction.user.id != ctx.author.id: return
                self.value = False
                self.stop()
                await interaction.response.defer()

        view = ConfirmView()
        msg = await ctx.send(embed=confirm_embed, view=view)
        await view.wait()
        
        if view.value:
            try:
                await self.users.delete_many({"guild_id": ctx.guild.id})
                embed = discord.Embed(description="✅ **Leveling data has been reset.**", color=0x00FF00)
                await msg.edit(embed=embed, view=None)
            except Exception as e:
                await ctx.send(f"Error resetting data: {e}")
        else:
            embed = discord.Embed(description="❌ **Reset cancelled.**", color=0x2b2d31)
            await msg.edit(embed=embed, view=None)

    def generate_rank_card(self, user, xp, level, rank, next_level_xp, current_level_xp_start):
        # Canvas Logic
        width, height = 800, 250
        bg_color = (43, 45, 49)
        card = Image.new("RGBA", (width, height), bg_color)
        draw = ImageDraw.Draw(card)

        # Background accents (Purple theme)
        draw.ellipse((600, -100, 900, 200), fill=(88, 101, 242, 60))
        draw.ellipse((500, 150, 900, 450), fill=(88, 101, 242, 40))

        # Placeholder logic for generate_rank_card mostly - real card drawing logic is inside the command
        return card

    @commands.hybrid_command(name='level', aliases=['rank', 'xp'], description="Check your or another user's rank and level")
    async def rank(self, ctx, member: discord.Member = None):
        if not HAS_PIL:
            await ctx.send("❌ Error: Image library missing. Cannot generate rank card.")
            return

        member = member or ctx.author
        
        # Get user data
        row = await self.get_user_data(ctx.guild.id, member.id)
        
        if not row:
            xp, level = 0, 0
            rank_pos = "N/A"
        else:
            xp, level = row
            # Calculate Rank
            try:
                count_above = await self.users.count_documents({"guild_id": ctx.guild.id, "xp": {"$gt": xp}})
                rank_pos = count_above + 1
            except:
                rank_pos = "N/A"

        # XP Calcs
        next_level_xp = self.get_xp_for_level(level + 1)
        current_level_xp_start = self.get_xp_for_level(level)
        xp_needed = next_level_xp - current_level_xp_start
        xp_progress = xp - current_level_xp_start
        percentage = min(xp_progress / xp_needed, 1.0) if xp_needed > 0 else 0

        # Create Image
        await ctx.typing()
        
        try:
            # Prepare Assets in Thread
            avatar_bytes = await member.display_avatar.with_format("png").read()
            
            def make_image():
                bg_color = (35, 39, 42)
                fg_color = (255, 255, 255)
                purple = (155, 89, 182)
                
                card = Image.new("RGBA", (934, 282), bg_color)
                draw = ImageDraw.Draw(card)
                
                # Avatar
                avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
                avatar = avatar.resize((200, 200))
                
                # Make avatar circular
                mask = Image.new("L", (200, 200), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, 200, 200), fill=255)
                
                card.paste(avatar, (40, 41), mask)
                
                # Progress Bar Background
                bar_x, bar_y = 280, 210
                bar_w, bar_h = 600, 30
                draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=(48, 51, 57)) # Darker rail
                
                # Progress Bar Fill
                fill_w = int(bar_w * percentage)
                if fill_w > 0:
                     draw.rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), fill=purple)
                
                # Fonts
                try:
                    font_large = ImageFont.truetype("data/music/heading.ttf", 65)
                    font_small = ImageFont.truetype("data/music/other.ttf", 35)
                except:
                    try:
                        font_large = ImageFont.truetype("arial.ttf", 60)
                        font_small = ImageFont.truetype("arial.ttf", 30)
                    except:
                        font_large = ImageFont.load_default()
                        font_small = ImageFont.load_default()

                # User Name
                draw.text((280, 70), str(member.name), font=font_large, fill=fg_color)
                
                # Stats
                stats_text = f"Rank #{rank_pos}   Level {level}"
                draw.text((280, 150), stats_text, font=font_small, fill=purple)
                
                xp_text = f"{xp_progress} / {xp_needed} XP"
                try:
                     w = draw.textlength(xp_text, font=font_small)
                     draw.text((880 - w, 170), xp_text, font=font_small, fill=(180, 180, 180))
                except:
                     draw.text((700, 170), xp_text, font=font_small, fill=(180, 180, 180))

                return card

            final_card = await self.bot.loop.run_in_executor(None, make_image)
            
            with BytesIO() as image_binary:
                final_card.save(image_binary, 'PNG')
                image_binary.seek(0)
                await ctx.send(file=discord.File(fp=image_binary, filename='rank.png'))
                
        except Exception as e:
            print(f"Rank Card Error: {e}")
            await ctx.send(f"Failed to generate rank card: {e}")

async def setup(bot):
    await bot.add_cog(Leveling(bot))
