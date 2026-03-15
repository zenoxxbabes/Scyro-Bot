import discord
from discord import app_commands
from discord.ext import commands
import wavelink
import motor.motor_asyncio
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import io
import asyncio
import os
import requests
import time
from functools import wraps 

# --- Configuration ---
GLASS_PATH = "data/music/glass.png"
FONT_HEADING = "data/music/heading.ttf"
FONT_OTHER = "data/music/other.ttf"
# DB_PATH removed
EMBED_COLOR = 0x2B2D31  # Dark Grey
VC_STATUS_TEXT = "**For Nerds: Use /play <song> **"

# --- LAVALINK CONFIGURATION ---
LAVALINK_DATA = {
    "lavalink": {
        "nodes": [
            {
                "name": "Main",
                "host": "lavalink.jirayu.net",
                "port": 443,
                "password": "youshallnotpass",
                "secure": True,
                "resume_key": "ahhshit_music_session",
                "resume_timeout": 600 # 10 minutes
            }
        ]
    }
}

# --- Emojis ---
E_ALERT = "<a:alert:1396429026842644584>"
E_YES = "<:yes:1396838746862784582>"
E_NO = "<:no:1396838761605890090>"
E_LOAD = "<a:4428ghosticonload:1409448581911416904>"

# --- Canvas Generator ---
class MusicCanvas:
    """Handles the image generation for the Now Playing card."""
    
    @staticmethod
    def add_corners(im, rad):
        circle = Image.new('L', (rad * 2, rad * 2), 0)
        draw = ImageDraw.Draw(circle)
        draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
        alpha = Image.new('L', im.size, 255)
        w, h = im.size
        alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
        alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
        alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
        alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
        im.putalpha(alpha)
        return im

    @classmethod
    async def generate_banner(cls, track: wavelink.Playable, bot_loop):
        def _generate():
            try:
                if track.artwork:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                        'Connection': 'keep-alive',
                    }
                    response = requests.get(track.artwork, timeout=10, headers=headers)
                    response.raise_for_status()
                    cover_data = io.BytesIO(response.content)
                    original_cover = Image.open(cover_data).convert("RGBA")
                else:
                    original_cover = Image.new("RGBA", (500, 500), (43, 45, 49))
            except Exception as e:
                print(f"Banner generation error: {e}")
                original_cover = Image.new("RGBA", (500, 500), (43, 45, 49))

            bg = original_cover.resize((680, 680))
            top = (680 - 240) // 2
            bg = bg.crop((0, top, 680, top + 240))
            bg = bg.filter(ImageFilter.GaussianBlur(15))

            glass_x, glass_y = 220, 10
            try:
                if os.path.exists(GLASS_PATH):
                    glass = Image.open(GLASS_PATH).convert("RGBA")
                    glass = glass.resize((430, 220)) 
                    bg.paste(glass, (glass_x, glass_y), glass)
            except Exception as e:
                print(f"Glass load error: {e}")

            art_size = 200
            stroke_width = 5
            total_art_size = art_size + stroke_width * 2
            
            final_art = Image.new("RGBA", (total_art_size, total_art_size), (0,0,0,0))
            draw_stroke = ImageDraw.Draw(final_art)
            draw_stroke.rounded_rectangle((0, 0, total_art_size, total_art_size), radius=15, fill=(255, 255, 255))
            
            art = original_cover.resize((art_size, art_size))
            art = cls.add_corners(art, 15)
            final_art.paste(art, (stroke_width, stroke_width), art)

            pos_x = 20
            pos_y = (240 - total_art_size) // 2
            bg.paste(final_art, (pos_x, pos_y), final_art)

            draw = ImageDraw.Draw(bg)
            try:
                font_h = ImageFont.truetype(FONT_HEADING, 55)
                font_sub = ImageFont.truetype(FONT_HEADING, 30)
                font_other = ImageFont.truetype(FONT_OTHER, 30)
            except:
                font_h = ImageFont.load_default()
                font_sub = ImageFont.load_default()
                font_other = ImageFont.load_default()

            text_x = 270 
            
            def draw_text_shadow(text, x, y, font, fill="white", shadow="black"):
                draw.text((x + 3, y + 3), text, font=font, fill=shadow)
                draw.text((x, y), text, font=font, fill=fill)

            title_text = f"#{track.title}"
            if len(title_text) > 13: 
                title_text = title_text[:11] + "..."
            draw_text_shadow(title_text, text_x, 35, font_h)

            draw_text_shadow("Artist", text_x, 115, font_sub)
            artist_text = track.author
            if len(artist_text) > 12: 
                artist_text = artist_text[:10] + "..."
            draw_text_shadow(artist_text, text_x, 150, font_other, fill="#dddddd")

            dur_x = text_x + 220 
            minutes, seconds = divmod(track.length / 1000, 60)
            duration_str = f"{int(minutes)}:{int(seconds):02d}"
            
            draw_text_shadow("Duration", dur_x, 115, font_sub)
            draw_text_shadow(duration_str, dur_x, 150, font_other, fill="#dddddd")

            buffer = io.BytesIO()
            bg.save(buffer, format="PNG")
            buffer.seek(0)
            return buffer

        return await bot_loop.run_in_executor(None, _generate)

# --- UI View ---
class PlayerControls(discord.ui.View):
    def __init__(self, player: wavelink.Player, cog):
        super().__init__(timeout=None)
        self.player = player
        self.cog = cog # Pass cog to access DB
        self.message = None 

    async def get_requestor_id(self, guild_id):
        doc = await self.cog.state.find_one({"guild_id": guild_id})
        return doc.get("requester_id") if doc else None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        req_id = await self.get_requestor_id(interaction.guild_id)
        if req_id and interaction.user.id != req_id:
            await interaction.response.send_message(f"> {E_NO} You are not the requestor of current playing Song", ephemeral=True)
            return False
        return True

    def disable_buttons(self):
        """Disable all buttons in the view"""
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
    
    async def disable_and_update_view(self):
        """Disable all buttons and update the view"""
        self.disable_buttons()
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass
            except Exception as e:
                print(f"Error disabling buttons: {e}")

    # --- BUTTON CALLBACKS ---

    @discord.ui.button(emoji="<:volminus:1447210179853549660>", style=discord.ButtonStyle.secondary, row=0)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            vol = max((self.player.volume or 100) - 10, 0)
            await self.player.set_volume(vol)
            await interaction.followup.send(f"> {E_YES} Volume: **{vol}%**", ephemeral=True)
        except Exception as e:
            print(f"Volume down error: {e}")
            await interaction.followup.send(f"> {E_ALERT} Failed to adjust volume.", ephemeral=True)

    @discord.ui.button(emoji="<:pauseplay:1447210211382132757>", style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if self.player.paused:
                await self.player.pause(False)
                await interaction.followup.send(f"> {E_YES} Music resumed.", ephemeral=True)
            else:
                await self.player.pause(True)
                await interaction.followup.send(f"> {E_YES} Music paused.", ephemeral=True)
        except Exception as e:
            print(f"Pause/resume error: {e}")
            await interaction.followup.send(f"> {E_ALERT} Failed to pause/resume music.", ephemeral=True)

    @discord.ui.button(emoji="<:volplus:1447210140494336000>", style=discord.ButtonStyle.secondary, row=0)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            vol = min((self.player.volume or 100) + 10, 100) 
            await self.player.set_volume(vol)
            await interaction.followup.send(f"> {E_YES} Volume: **{vol}%**", ephemeral=True)
        except Exception as e:
            print(f"Volume up error: {e}")
            await interaction.followup.send(f"> {E_ALERT} Failed to adjust volume.", ephemeral=True)

    @discord.ui.button(emoji="<:sybackward:1447210676836630548>", style=discord.ButtonStyle.secondary, row=1)
    async def rewind(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if not self.player.current:
                await interaction.followup.send(f"> {E_ALERT} No track is currently playing.", ephemeral=True)
                return
            
            pos = max(self.player.position - 10000, 0)
            await self.player.seek(pos)
            await interaction.followup.send(f"> {E_YES} Rewound 10s.", ephemeral=True)
        except Exception as e:
            print(f"Rewind error: {e}")
            await interaction.followup.send(f"> {E_ALERT} Failed to rewind track.", ephemeral=True)

    @discord.ui.button(emoji="<:systop:1447211215280537780>", style=discord.ButtonStyle.danger, row=1)
    async def stop_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.disable_buttons()
        try:
            await self.message.edit(view=self)
            if not self.player.queue.is_empty:
                await self.player.skip(force=True)
                await interaction.followup.send(f"> {E_LOAD} Skipping track...", ephemeral=True)
            else:
                await self.player.disconnect()
                if hasattr(self.player, 'home') and self.player.home:
                    try: await self.player.home.send(f"> {E_YES} All Tracks have been Played. Leaving VC.")
                    except: pass
                await interaction.followup.send(f"> {E_YES} Stopped.", ephemeral=True)
        except Exception as e:
            print(f"Stop player error: {e}")
            await interaction.followup.send(f"> {E_ALERT} Failed to stop player.", ephemeral=True)

    @discord.ui.button(emoji="<:syforward:1447210328797478974>", style=discord.ButtonStyle.secondary, row=1)
    async def forward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if not self.player.current:
                await interaction.followup.send(f"> {E_ALERT} No track is currently playing.", ephemeral=True)
                return
            
            pos = min(self.player.position + 10000, self.player.current.length)
            await self.player.seek(pos)
            await interaction.followup.send(f"> {E_YES} Forwarded 10s.", ephemeral=True)
        except Exception as e:
            print(f"Forward error: {e}")
            await interaction.followup.send(f"> {E_ALERT} Failed to forward track.", ephemeral=True)


# --- Main Cog ---
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.inactivity_tasks = {} 
        self.twenty_four_seven = set()
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.state = None
        self.state = None
        # self.bot.loop.create_task(self.init_db()) # Moved to cog_load

    async def init_db(self):
        if not self.mongo_uri: return
        self.client_mongo = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client_mongo.get_database()
        self.state = self.db.music_state
        await self.state.create_index("guild_id", unique=True)

    async def cog_load(self):
        print(f"Loading Music Cog. Wavelink Version: {wavelink.__version__}")
        
        # Initialize DB first
        await self.init_db()
        
        nodes_to_connect = []
        try:
            for node_cfg in LAVALINK_DATA["lavalink"]["nodes"]:
                scheme = "https" if node_cfg.get("secure") else "http"
                uri = f"{scheme}://{node_cfg['host']}:{node_cfg['port']}"
                
                node = wavelink.Node(
                    identifier=node_cfg["name"],
                    uri=uri,
                    password=node_cfg["password"]
                )
                nodes_to_connect.append(node)
                print(f"🔹 Configured Node: {node.identifier} at {uri} (Resume Key: {node_cfg.get('resume_key')})")

            if nodes_to_connect:
                await wavelink.Pool.connect(nodes=nodes_to_connect, client=self.bot, cache_capacity=100)
                print("✅ Wavelink Pool Connected Successfully.")
            else:
                print("⚠️ No nodes configured in LAVALINK_DATA.")
                
        except Exception as e:
            print(f"❌ Failed to connect to Wavelink Node: {e}")

    async def _set_vc_status(self, channel):
        """Helper to set voice channel status safely."""
        try:
            if not channel: return
            if channel.permissions_for(channel.guild.me).manage_channels:
                await channel.edit(status=VC_STATUS_TEXT)
        except Exception as e:
            print(f"Failed to set VC status for {channel.id}: {e}")

    async def connect_safely(self, channel, attempts=3, timeout=90):
        """Robust connection handler with retry logic."""
        backoff = 2
        for i in range(attempts):
            try:
                if channel.guild.voice_client:
                    if channel.guild.voice_client.channel and channel.guild.voice_client.channel.id == channel.id:
                        if channel.guild.voice_client.is_connected():
                             return channel.guild.voice_client

                    try: await channel.guild.voice_client.disconnect(force=True)
                    except: pass
                    
                print(f"🔄 Connection Attempt {i+1}/{attempts} for {channel.name}")
                player: wavelink.Player = await channel.connect(cls=wavelink.Player, self_deaf=True, timeout=timeout)
                return player
            except (asyncio.TimeoutError, discord.ClientException, TimeoutError) as e:
                print(f"⚠️ Connection Failed ({e}). Retrying in {backoff}s...")
                if i == attempts - 1:
                    raise e
                await asyncio.sleep(backoff)
                backoff *= 2 # Exponential backoff
        return None

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        """Called when a Wavelink node is ready. Handles 24/7 reconnection."""
        node = payload.node
        print(f"🟢 Wavelink Node {node.identifier} is READY. Resumed: {payload.resumed}")

        if payload.resumed:
            return 
            
        print("Attempting 24/7 Reconnections...")
        await self.bot.wait_until_ready()
        
        # Dispatch reconnection task
        self.bot.loop.create_task(self._reconnect_247())

    async def _reconnect_247(self):
        """Internal method to handle 24/7 reconnection logic"""
        if self.state is None:
            print("❌ DB Connection failed, skipping 24/7 reconnection.")
            return

        reconnect_count = 0
        try:
            # Iterate over MongoDB cursor
            async for doc in self.state.find({"247_channel_id": {"$exists": True, "$ne": None}}):
                try:
                    guild_id = doc['guild_id']
                    channel_id = doc['247_channel_id']
                    
                    self.twenty_four_seven.add(guild_id)
                    
                    guild = self.bot.get_guild(guild_id)
                    if not guild: 
                        # Try to fetch if not in cache (rare but possible)
                        try: guild = await self.bot.fetch_guild(guild_id)
                        except: pass
                    
                    if not guild: 
                        print(f"⚠️ Guild {guild_id} not found for 24/7 music.")
                        continue
                        
                    channel = guild.get_channel(channel_id)
                    if not channel: 
                         # Try fetch
                        try: channel = await self.bot.fetch_channel(channel_id)
                        except: pass
                    
                    if not channel:
                        print(f"⚠️ Channel {channel_id} not found in guild {guild.name}.")
                        continue
                        
                    if guild.voice_client and guild.voice_client.is_connected():
                         # Check if connected to correct channel
                         if guild.voice_client.channel.id != channel.id:
                             await guild.voice_client.move_to(channel)
                         continue
                        
                    player = await self.connect_safely(channel)
                    if player:
                        print(f"🔄 Auto-joined 24/7: {channel.name} in {guild.name}")
                        await self._set_vc_status(channel)
                        reconnect_count += 1
                    else:
                        print(f"❌ Failed to auto-join {channel.name} in {guild.name} after retries.")
                except Exception as inner_e:
                    print(f"Error reconnecting guild {doc.get('guild_id')}: {inner_e}")
                    
            print(f"✅ 24/7 Reconnection Complete. Rejoined {reconnect_count} channels.")
        except Exception as e:
            print(f"❌ Critical Error in 24/7 Reconnection: {e}")

    @commands.Cog.listener()
    async def on_wavelink_node_closed(self, node: wavelink.Node, disconnected: list[wavelink.Player]):
        print(f"⚠️ Node {node.identifier} disconnected! Check console for errors.")

    def cancel_timer(self, guild_id):
        if guild_id in self.inactivity_tasks:
            self.inactivity_tasks[guild_id].cancel()
            del self.inactivity_tasks[guild_id]

    async def start_timer(self, player):
        guild_id = player.guild.id
        if guild_id in self.twenty_four_seven:
            return
            
        self.cancel_timer(guild_id)

        async def timer_task():
            await asyncio.sleep(300) 
            if player and player.connected and not player.playing:
                await player.disconnect()
                if hasattr(player, 'home') and player.home:
                    await player.home.send(f"> {E_YES} Nothing to Play from last 5 minutes. Leaving VC.")
                self.inactivity_tasks.pop(guild_id, None)

        self.inactivity_tasks[guild_id] = self.bot.loop.create_task(timer_task())

    async def update_db_requestor(self, guild_id, requester_id):
        await self.state.update_one(
            {"guild_id": guild_id},
            {"$set": {"requester_id": requester_id}},
            upsert=True
        )

    async def check_db_perm(self, ctx):
        if not ctx.guild: return False
        doc = await self.state.find_one({"guild_id": ctx.guild.id})
        req_id = doc.get("requester_id") if doc else None
        
        if not req_id: return True 
        if ctx.author.id == req_id: return True
        else:
            await ctx.send(f"> {E_NO} You are not the requestor of current playing Song", ephemeral=True)
            return False
                
    async def check_premium_access(self, ctx):
        """Check if user or guild has premium access for 24/7 feature"""
        premium_cog = self.bot.get_cog("Premium")
        
        # 1. Try using the Premium Cog if loaded
        if premium_cog:
            if ctx.author.id == premium_cog.premium_system.bot_owner_id:
                return True
            try:
                has_premium, tier = await premium_cog.premium_system.check_user_premium(ctx.author.id, ctx.guild.id)
                if has_premium: return True
                return False
            except Exception as e:
                print(f"Premium Cog Check Failed: {e}")
        
        # 2. Manual Fallback
        try:
             # Check User Table
             # Assuming standard collection names from Premium migration
             user_doc = await self.db.premium_users.find_one({"user_id": ctx.author.id})
             # We should check expiry too, assuming standard field 'expires_at' (timestamp)
             if user_doc:
                 # If expires_at is future
                 if user_doc.get("expires_at", 0) > time.time():
                     return True
                     
             # Check Guild Table
             guild_doc = await self.db.premium_guilds.find_one({"guild_id": ctx.guild.id})
             if guild_doc:
                 # Check if guild premium covers this (usually active if present)
                 # Check expiry if applicable
                 if guild_doc.get("expires_at", 0) > time.time():
                     return True
                     
        except Exception as e:
            print(f"Manual Premium Check Failed: {e}")
            
        return False

    @commands.hybrid_command(name="247", description="Toggle 24/7 mode to keep bot in VC (Premium Only)")
    async def twentyfourseven(self, ctx: commands.Context):
        """Toggle 24/7 mode - keeps bot in voice channel even when queue is empty"""
        await ctx.defer()
        
        if not ctx.guild:
            return await ctx.send(f"> {E_ALERT} This command can only be used in servers.")
            
        player: wavelink.Player = ctx.voice_client
        
        if not player:
            if not ctx.author.voice:
                return await ctx.send(f"> {E_ALERT} You need to be in a voice channel to use this command.")
            
            has_premium = await self.check_premium_access(ctx)
            if not has_premium:
                embed = discord.Embed(
                    title="<:ogstar:1420709631663013928> Premium Required",
                    description="You just found a premium feature! Please consider buying a rank from https://scyro.xyz/premium\nif already purchased so use `.premium use` to use your guild slot here.",
                    color=0xFFD700
                )
                return await ctx.send(embed=embed)
                
            try:
                try:
                    player: wavelink.Player = await self.connect_safely(ctx.author.voice.channel, timeout=90)
                except Exception as e:
                    print(f"Connection Error: {e}")
                    return await ctx.send(f"> {E_ALERT} Failed to join voice channel. Check permissions or try again.")
                
                player.home = ctx.channel
                await self._set_vc_status(ctx.author.voice.channel)
            except Exception as e:
                print(f"Connection Error: {e}")
                return await ctx.send(f"> {E_ALERT} Failed to join voice channel. Check permissions or try again.")
        else:
            has_premium = await self.check_premium_access(ctx)
            if not has_premium:
                embed = discord.Embed(
                    title="<:ogstar:1420709631663013928> Premium Required",
                    description="You just found a premium feature! Please consider buying a rank from https://scyro.xyz/premium\nif already purchased so use `.premium use` to use your guild slot here.",
                    color=0xFFD700
                )
                return await ctx.send(embed=embed)
            
        guild_id = ctx.guild.id
        
        is_enabled = guild_id in self.twenty_four_seven
        
        if not is_enabled:
            self.twenty_four_seven.add(guild_id)
            await self.state.update_one(
                {"guild_id": guild_id},
                {"$set": {"247_channel_id": player.channel.id}},
                upsert=True
            )
            
            await ctx.send(f"> {E_YES} Enabled 24/7 mode in {player.channel.mention}")
            self.cancel_timer(guild_id)
        else:
            self.twenty_four_seven.discard(guild_id)
            await self.state.update_one(
                {"guild_id": guild_id},
                {"$unset": {"247_channel_id": ""}}
            )
                
            await ctx.send(f"> {E_YES} 24/7 mode **disabled**. I'll leave when the queue is empty.")
            if player.queue.is_empty and not player.playing:
                await self.start_timer(player)

    @commands.hybrid_command(name="play", aliases=["p"], description="Search and play a song.")
    @app_commands.describe(query="The song name or link to play")
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer()
        if not ctx.guild:
             return await ctx.send(f"> {E_ALERT} This command can only be used in servers.")

        self.cancel_timer(ctx.guild.id)

        if not wavelink.Pool.nodes:
            return await ctx.send(f"> {E_ALERT} Music server is offline. Please try again later.")

        if not ctx.voice_client:
            if not ctx.author.voice:
                return await ctx.send(f"> {E_ALERT} Join Voice Channel.")
            try:
                try:
                    player: wavelink.Player = await self.connect_safely(ctx.author.voice.channel, timeout=90)
                except Exception as e:
                     print(f"Connection Error: {e}")
                     return await ctx.send(f"> {E_ALERT} Voice join failed. Check permissions or try again.")

                await self._set_vc_status(ctx.author.voice.channel)
            except Exception as e:
                print(f"Connection Error: {e}")
                return await ctx.send(f"> {E_ALERT} Voice join failed. Check permissions or try again.")
        else:
            player: wavelink.Player = ctx.voice_client
            if ctx.voice_client.channel != ctx.author.voice.channel:
                 return await ctx.send(f"> {E_ALERT} You need to be in same vc as me to use this command", ephemeral=True)
        
        player.home = ctx.channel

        try:
            tracks: wavelink.Search = await wavelink.Playable.search(query)
        except Exception as e:
            return await ctx.send(f"> {E_ALERT} Search error: {e}")

        if not tracks:
            return await ctx.send(f"> {E_ALERT} No tracks found.")
        
        track = tracks[0]
        track.extras = {"requester_id": ctx.author.id}

        await player.queue.put_wait(track)
        
        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="ADDED TO QUEUE", icon_url=ctx.author.display_avatar.url)
        embed.description = f"> {E_YES} [{track.title}]({track.uri}) Added To The Queue"
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        await ctx.send(embed=embed)

        if not player.playing:
            next_track = player.queue.get()
            await ctx.send(f"> {E_LOAD} Be Ready for **{next_track.title}!!**")
            try:
                await player.play(next_track)
            except Exception as e:
                print(f"Play Error (Retrying after clear): {e}")
                await player.set_filters(wavelink.Filters())
                await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player: return

        if payload.reason.lower() == "replaced":
            return
        
        if hasattr(player, '_previous_view') and player._previous_view:
            try:
                await player._previous_view.disable_and_update_view()
            except Exception as e:
                print(f"Error disabling previous view: {e}")
        
        player.last_track_id = None 

        if not player.queue.is_empty:
            next_track = player.queue.get()
            if hasattr(player, 'home') and player.home:
                await player.home.send(f"> {E_LOAD} Be Ready for **{next_track.title}!!**")
            
            try:
                await player.play(next_track)
            except Exception as e:
                print(f"TrackEnd Play Error (Recovering): {e}")
                await player.set_filters(wavelink.Filters())
                try:
                    await player.play(next_track)
                except Exception as e2:
                    print(f"CRITICAL Playback Failure: {e2}")
        else:
            await self.start_timer(player)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player or not player.guild: return

        track = payload.track
        
        if getattr(player, "last_track_id", None) == track.identifier:
            return
        
        player.last_track_id = track.identifier

        self.cancel_timer(player.guild.id)
        
        req_id = getattr(track.extras, "requester_id", None)

        if req_id:
            await self.update_db_requestor(player.guild.id, req_id)
            requestor = player.guild.get_member(req_id)
        else:
            requestor = player.client.user 
            await self.update_db_requestor(player.guild.id, player.client.user.id)

        try:
            img_buffer = await MusicCanvas.generate_banner(track, self.bot.loop)
            file = discord.File(img_buffer, filename="banner.png")
            
            embed = discord.Embed(color=EMBED_COLOR)
            embed.description = f"## <a:100714capybara:1415998359109505117> Now Playing: [{track.title}]({track.uri})"
            embed.set_image(url="attachment://banner.png")
            if requestor:
                 embed.set_footer(text=f"Requested by {requestor.display_name}", icon_url=requestor.display_avatar.url)
            
            view = PlayerControls(player, self)
            
            if hasattr(player, 'home') and player.home:
                message = await player.home.send(embed=embed, file=file, view=view)
                view.message = message
                player._previous_view = view
        except Exception as e:
            print(f"Canvas/Send Error: {e}")
            try:
                if hasattr(player, 'home') and player.home:
                    await player.home.send(f"> {E_YES} Now Playing: **{track.title}**")
            except Exception as fallback_e:
                print(f"Fallback Send Error: {fallback_e}")

    @commands.hybrid_command(name="skip", description="Skip the current playing song.")
    async def skip(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player or not player.playing: return await ctx.send(f"> {E_ALERT} Nothing playing.")
        
        if await self.check_db_perm(ctx):
            await player.skip(force=True)
            await ctx.send(f"> {E_LOAD} Skipped track.")

    @commands.hybrid_command(name="stop", description="Stop the music and clear the queue.")
    async def stop(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player: return
        
        if await self.check_db_perm(ctx):
            if not player.queue.is_empty:
                await player.skip(force=True)
                await ctx.send(f"> {E_LOAD} Skipping track...")
            else:
                await player.disconnect()
                await ctx.send(f"> {E_YES} All Tracks has been Played. Leaving VC.")

    @commands.hybrid_command(name="volume", description="Set the player volume (0-100%).")
    @app_commands.describe(level="The volume percentage to set")
    async def volume(self, ctx: commands.Context, level: int):
        player: wavelink.Player = ctx.voice_client
        if not player: return
        if await self.check_db_perm(ctx):
            await player.set_volume(level)
            await ctx.send(f"> {E_YES} Volume: **{level}%**")

    @commands.hybrid_command(name="pause", description="Pause or Resume the music.")
    async def pause(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player or not player.playing: return await ctx.send(f"> {E_ALERT} Nothing playing.")
        if await self.check_db_perm(ctx):
            if player.paused:
                await player.pause(False)
                await ctx.send(f"> {E_YES} Music resumed.")
            else:
                await player.pause(True)
                await ctx.send(f"> {E_YES} Music paused.")

    @commands.hybrid_command(name="shuffle", description="Shuffle the current queue (Admin only).")
    @commands.has_permissions(administrator=True)
    async def shuffle(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player or player.queue.is_empty: return await ctx.send(f"> {E_ALERT} Queue empty.")
        player.queue.shuffle()
        await ctx.send(f"> {E_YES} Queue shuffled.")

    @commands.hybrid_command(name="clearqueue", aliases=["cq"], description="Clear all songs in queue (Admin only).")
    @commands.has_permissions(administrator=True)
    async def clearqueue(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player or player.queue.is_empty: return await ctx.send(f"> {E_ALERT} Queue is empty.")
        player.queue.clear()
        await ctx.send(f"> {E_YES} Queue cleared.")

    @commands.hybrid_command(name="showqueue", description="Display the current music queue.")
    async def showqueue(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player or player.queue.is_empty: return await ctx.send(f"> {E_ALERT} Queue empty.")
        desc = ""
        for index, track in enumerate(player.queue[:10]): 
            desc += f"**{index+1}.** [{track.title}]({track.uri})\n"
        embed = discord.Embed(title="Current Queue", description=desc, color=EMBED_COLOR)
        if player.queue.count > 10:
            embed.set_footer(text=f"And {player.queue.count - 10} more songs...")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="autoplay", description="Toggle Autoplay mode on/off.")
    async def autoplay(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player: return
        if await self.check_db_perm(ctx):
            if player.autoplay == wavelink.AutoPlayMode.enabled:
                player.autoplay = wavelink.AutoPlayMode.disabled
                await ctx.send(f"> {E_YES} Autoplay off.")
            else:
                player.autoplay = wavelink.AutoPlayMode.enabled
                await ctx.send(f"> {E_YES} Autoplay on.")

    # --- FILTER SLASH COMMANDS ---
    @commands.hybrid_group(name="filter", description="Audio filters management")
    async def filter_cmd(self, ctx): pass

    @filter_cmd.command(name="enable", description="Enable a specific audio effect")
    @app_commands.describe(name="The audio filter to enable")
    @app_commands.choices(name=[
        app_commands.Choice(name="Nightcore", value="nightcore"),
        app_commands.Choice(name="Vaporwave", value="vaporwave"),
        app_commands.Choice(name="Bass Boost", value="bass"),
        app_commands.Choice(name="Karaoke", value="karaoke"),
        app_commands.Choice(name="Tremolo", value="tremolo"),
        app_commands.Choice(name="Vibrato", value="vibrato"),
        app_commands.Choice(name="Distortion", value="distortion"),
        app_commands.Choice(name="Low Pass", value="lowpass"),
        app_commands.Choice(name="Volume Boost", value="vol_boost"),
        app_commands.Choice(name="Mono Mix", value="mono")
    ])
    async def filter_enable(self, ctx, name: app_commands.Choice[str]):
        player: wavelink.Player = ctx.voice_client
        if not player: return await ctx.send(f"> {E_ALERT} Nothing playing.")
        
        if await self.check_db_perm(ctx):
            filters = wavelink.Filters()
            val = name.value

            if val == "nightcore":
                filters.timescale.set(pitch=1.2, speed=1.2)
            elif val == "vaporwave":
                filters.timescale.set(pitch=0.8, speed=0.85)
            elif val == "bass":
                filters.equalizer.set(bands=[(i, 0.25) for i in range(5)])
            elif val == "karaoke":
                filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
            elif val == "tremolo":
                filters.tremolo.set(frequency=2.0, depth=0.5)
            elif val == "vibrato":
                filters.vibrato.set(frequency=2.0, depth=0.5)
            elif val == "distortion":
                filters.distortion.set(sin_offset=0.0, sin_scale=1.0, cos_offset=0.0, cos_scale=1.0, tan_offset=0.0, tan_scale=1.0, offset=0.0, scale=1.0)
            elif val == "lowpass":
                filters.low_pass.set(smoothing=20.0)
            elif val == "vol_boost":
                filters.volume = 1.5 
            elif val == "mono":
                filters.channel_mix.set(left_to_left=0.5, left_to_right=0.5, right_to_left=0.5, right_to_right=0.5)
            
            try:
                await player.set_filters(filters)
                await ctx.send(f"> {E_YES} Enabled **{name.name}**.")
            except Exception as e:
                print(f"Filter Set Error: {e}")
                await player.set_filters(wavelink.Filters())
                await ctx.send(f"> {E_ALERT} Failed to apply filter. Reset to default.")

    @filter_cmd.command(name="disable", description="Disable all audio filters")
    async def filter_disable(self, ctx):
        player: wavelink.Player = ctx.voice_client
        if not player: return await ctx.send(f"> {E_ALERT} Nothing playing.")
        
        if await self.check_db_perm(ctx):
            try:
                await player.set_filters(wavelink.Filters())
                await ctx.send(f"> {E_YES} Filters reset.")
            except Exception as e:
                print(f"Filter Reset Error: {e}")
                await ctx.send(f"> {E_ALERT} Failed to reset filters.")

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Show the currently playing song.")
    async def nowplaying(self, ctx: commands.Context):
        player: wavelink.Player = ctx.voice_client
        if not player or not player.playing: return await ctx.send(f"> {E_ALERT} Nothing playing.")
        
        track = player.current
        
        embed = discord.Embed(color=EMBED_COLOR)
        embed.description = f"### [{track.title}]({track.uri})"
        embed.add_field(name="Artist", value=track.author, inline=True)
        minutes, seconds = divmod(track.length / 1000, 60)
        embed.add_field(name="Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)
        
        active_filters = []
        f = player.filters
        try:
            if (hasattr(f.timescale, 'speed') and f.timescale.speed != 1.0) or \
               (hasattr(f.timescale, 'pitch') and f.timescale.pitch != 1.0):
                active_filters.append("Timescale")
        except:
            pass 
            
        filter_checks = [
            ("Karaoke", f.karaoke, "level", 0.0),
            ("Tremolo", f.tremolo, "depth", 0.0),
            ("Vibrato", f.vibrato, "depth", 0.0),
            ("Distortion", f.distortion, "sin_scale", 1.0),
            ("LowPass", f.low_pass, "smoothing", 0.0),
            ("Equalizer", f.equalizer, "bands", None)
        ]
        
        for filter_name, filter_obj, attr_name, comparison_value in filter_checks:
            try:
                if hasattr(filter_obj, attr_name):
                    attr_value = getattr(filter_obj, attr_name)
                    if attr_value != comparison_value and (comparison_value is not None or attr_value):
                        active_filters.append(filter_name)
            except:
                pass 
                
        if f.volume is not None and f.volume != 1.0: active_filters.append(f"Vol:{int(f.volume*100)}%")
        
        if active_filters:
            embed.add_field(name="🎛️ Active Filters", value=", ".join(active_filters), inline=False)
        
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
            
        req_id = getattr(track.extras, "requester_id", None)
        requestor = ctx.guild.get_member(req_id) if req_id else ctx.author
        embed.set_footer(text=f"Requested by {requestor.display_name}", icon_url=requestor.display_avatar.url)
        
        await ctx.send(embed=embed)

    async def cog_unload(self):
        """Gracefully close wavelink connections on bot shutdown."""
        try:
            for task in self.inactivity_tasks.values():
                if task and not task.done():
                    task.cancel()
            
            for node in wavelink.Node.all_nodes():
                try: await node.close()
                except Exception: pass
        except Exception:
            pass

async def setup(bot):
    await bot.add_cog(Music(bot))