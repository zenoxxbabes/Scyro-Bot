import discord
import aiohttp
import datetime
import random
from discord.ext import commands
from utils.Tools import *
from core import Cog, Scyro, Context
from utils.config import *
from PIL import Image, ImageDraw, ImageFont
import io
import os
import textwrap

def RandomColor():
    randcolor = discord.Color(random.randint(0x2b2d31, 0xFFFFFF))
    return randcolor

class Fun(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.meme_api_key = 'p8rcvSyNcfOUchoLTt2YCbH0drgMUGKf'

    @commands.command(name="joke")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def joke(self, ctx):
        """Get a random joke from the internet"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://official-joke-api.appspot.com/random_joke") as response:
                    if response.status == 200:
                        data = await response.json()
                        setup = data.get('setup', 'No setup found')
                        punchline = data.get('punchline', 'No punchline found')
                        
                        embed = discord.Embed(
                            title="😂 Random Joke",
                            description=f"**{setup}**\n\n||{punchline}||",
                            color=RandomColor(),
                            timestamp=datetime.datetime.utcnow()
                        )
                        embed.set_footer(
                            text=f"Requested by {ctx.author.name}",
                            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                        )
                        await ctx.reply(embed=embed)
                    else:
                        await ctx.reply("> <:no:1396838761605890090> Failed to fetch a joke. Please try again later!")
        except Exception as e:
            await ctx.reply("> <:no:1396838761605890090> An error occurred while fetching the joke.")

    @commands.command(name="meme")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def meme(self, ctx):
        """Get a random meme"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://meme-api.com/gimme") as response:
                    if response.status == 200:
                        data = await response.json()
                        meme_url = data.get('url')
                        meme_title = data.get('title', 'Random Meme')
                        subreddit = data.get('subreddit', 'memes')
                        
                        if meme_url:
                            embed = discord.Embed(
                                title="😂 Random Meme",
                                description=f"**{meme_title}**\n\n*From r/{subreddit}*",
                                color=RandomColor(),
                                timestamp=datetime.datetime.utcnow()
                            )
                            embed.set_image(url=meme_url)
                            embed.set_footer(
                                text=f"Requested by {ctx.author.name}",
                                icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                            )
                            await ctx.reply(embed=embed)
                        else:
                            await ctx.reply("> <:no:1396838761605890090> No meme found. Please try again!")
                    else:
                        await ctx.reply("> <:no:1396838761605890090> Failed to fetch a meme. Please try again later!")
        except Exception as e:
            await ctx.reply(f"> <:no:1396838761605890090> An error occurred while fetching the meme: {str(e)}")

    @commands.command(name="nitro")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def nitro(self, ctx):
        """Fake Discord Nitro gift (rickroll)"""
        expiry_hours = random.randint(12, 72)
        
        gift_embed = discord.Embed(
            title="<:nitro:1409182140616151150> A Wild Nitro Gift Appears!",
            description=(
                f"<:nitroboost:1420349391352627230> **Discord Nitro Boost** has appeared!\n\n"
                f"> **Expires in:** {expiry_hours} hours\n"
                f"> **Value:** $9.99/month\n\n"
                f"> **Hurry up!** This gift won't last long...\n"
                f"> **Time's ticking...** Don't wait too long!"
            ),
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        
        gift_embed.set_thumbnail(url="https://digiseller.mycdn.ink/imgwebp.ashx?idp=3847592&dc=645926400&w=88")

        class NitroView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
            
            @discord.ui.button(label="Claim Nitro!", style=discord.ButtonStyle.success, emoji="🎁")
            async def claim_nitro(self, interaction: discord.Interaction, button: discord.ui.Button):
                rickroll_embed = discord.Embed(
                    title="😝 Oops! You Got Rickrolled!",
                    description=(
                        f"BOOM! Here's your **free Nitro**...\n\n"
                        f"😂 **Enjoy the Rickroll!** 😂\n\n"
                        f"*Never gonna give you up, never gonna let you down...*"
                    ),
                    color=0x2b2d31,
                    timestamp=datetime.datetime.utcnow()
                )
                
                rickroll_embed.set_image(url="https://media.tenor.com/x8v1oNUOmg4AAAAd/rickroll-roll.gif")
                
                rickroll_embed.set_footer(
                    text=f"Rickrolled by {ctx.author.name} • Hope you enjoyed it! 😄",
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                )
                
                button.disabled = True
                button.label = "Claimed"
                button.style = discord.ButtonStyle.secondary
                
                await interaction.response.edit_message(embed=rickroll_embed, view=self)
        
        view = NitroView()
        await ctx.reply(embed=gift_embed, view=view)

    @commands.command(name="ship", aliases=["love"])
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ship(self, ctx, user1: discord.Member = None, user2: discord.Member = None):
        """Calculate love compatibility between two users"""
        try:
            if user1 is None and user2 is None:
                user1 = ctx.author
                user2 = ctx.author
            elif user2 is None:
                user2 = user1
                user1 = ctx.author
            
            if user1 == user2:
                await ctx.reply("> <:no:1396838761605890090> You can't ship the same user with themselves!")
                return
            
            if user1.bot or user2.bot:
                await ctx.reply("> 🗿 Bots Don't have Feelings!")
                return
            
            # Remove the deterministic seed to make results truly random
            love_percentage = random.randint(0, 100)
            
            message_template = self.get_love_message(love_percentage, user1.display_name, user2.display_name)
            
            async with ctx.typing():
                image_buffer = await self.create_ship_image(user1, user2, love_percentage)
            
            message_content = f"**`{user1.display_name}` + `{user2.display_name}` = `{love_percentage}`% of Love ‼️**\n{message_template}"
            await ctx.reply(message_content, file=discord.File(image_buffer, filename="ship.png"))
        except discord.NotFound:
            await ctx.reply("> <:no:1396838761605890090> One of the users couldn't be found.")
        except discord.HTTPException:
            await ctx.reply("> <:no:1396838761605890090> Failed to download user avatars.")
        except Exception as e:
            await ctx.reply(f"> <:no:1396838761605890090> An error occurred: {str(e)}")

    def get_love_message(self, percentage, name1, name2):
        # Expanded to over 50 unique message templates
        messages = {
            0: [
                f"{name1} and {name2}? That's a big fat ZERO chance! Better luck finding love elsewhere! 💔",
                f"Looks like {name1} and {name2} are destined to be just friends... forever alone status! 🚫💘",
                f"{name1} + {name2} = 💀 Love connection failed! Try again next lifetime! 🛑",
                f"Even cupid couldn't make {name1} and {name2} work! Game over! 🎮💔",
                f"{name1} and {name2}: 0% compatibility. Even less than my WiFi signal! 📶",
                f"Warning: {name1} and {name2} together could cause a black hole of loneliness! 🕳️",
                f"{name1} and {name2} = Friendship only mode activated! No romance detected! 🤝",
                f"Compatibility check: {name1} vs {name2}... Result: System error! Love not found! ⚠️",
                f"{name1} and {name2}? More like {name1} and Netflix... solo forever! 🍿",
                f"Avoid {name1} and {name2} pairing at all costs! It's a love catastrophe! 🌋"
            ],
            (1, 10): [
                f"{name1} and {name2} have a tiny spark, but it might burn out quickly! 🔥💧",
                f"{name1} and {name2}: 1-10% match. Proceed with extreme caution! ⚠️",
                f"A small flame exists between {name1} and {name2}, but it needs constant fuel! 🕯️",
                f"{name1} and {name2} have less chemistry than baking soda and vinegar! 🧪",
                f"The love meter for {name1} and {name2} is barely registering! Check connections! 📡",
                f"{name1} and {name2}: Sparks are flying... in opposite directions! 🧨",
                f"There's a whisper of potential between {name1} and {name2}, but it's very faint! 💨",
                f"{name1} and {name2}'s love life resembles a dying lightbulb! 💡",
                f"Compatibility level: {name1} and {name2} = Sub-zero zone! Brrr! 🧊",
                f"{name1} and {name2}: Love is in the air... but it's not reaching them! 🌬️"
            ],
            (11, 30): [
                f"{name1} and {name2} have some chemistry, but it needs a lot of work! ⚗️",
                f"{name1} and {name2} are like puzzle pieces from different boxes! 🧩",
                f"There's hope for {name1} and {name2}, but they need a love manual! 📖",
                f"{name1} and {name2}: Dating app material, but swipe right cautiously! 📱",
                f"The foundation is there for {name1} and {name2}, but the blueprint is missing! 🏗️",
                f"{name1} and {name2} have potential, like a rough diamond! 💎",
                f"A little effort could make {name1} and {name2} work... emphasis on effort! 💪",
                f"{name1} and {name2}: Compatible enough to not hate each other! 😅",
                f"There's a glimmer of something between {name1} and {name2}. Feed it wisely! ✨",
                f"{name1} and {name2} are like WiFi with one bar... sometimes it works! 📶"
            ],
            (31, 50): [
                f"{name1} and {name2} have a decent chance! Give it a shot! 🎯",
                f"{name1} and {name2}: Middle of the road couple! Take it for a spin! 🚗",
                f"There's genuine potential here for {name1} and {name2}! Time to explore! 🔍",
                f"{name1} and {name2} are like a classic movie - worth watching till the end! 🎬",
                f"The stars are slightly aligned for {name1} and {name2}! May the force be with you! ⭐",
                f"{name1} and {name2}: Good odds, like flipping a coin! Heads you win, tails you try! 🪙",
                f"There's a solid base for {name1} and {name2} to build upon! Foundation ready! 🧱",
                f"{name1} and {name2} have crossed the friendship bridge! Now comes the real test! 🌉",
                f"{name1} and {name2}: Not bad, not great. Like Goldilocks' porridge - just right amount of risk! 🥣",
                f"There's a 50-50 vibe with {name1} and {name2}! Fortune favors the bold! 🍀"
            ],
            (51, 70): [
                f"{name1} and {name2} have a strong connection! Lovebirds alert! 🐦🐦",
                f"{name1} and {name2}: High voltage romance! Handle with care! ⚡",
                f"There's serious chemistry between {name1} and {name2}! Lab safety goggles recommended! 🔬",
                f"{name1} and {name2} are like peanut butter and jelly! Perfect combo! 🥪",
                f"The love radar is pinging for {name1} and {name2}! Match confirmed! 📡",
                f"{name1} and {name2}: Better together than apart! Synergy activated! 🔗",
                f"There's a magnetic pull between {name1} and {name2}! Opposites attract theory confirmed! 🧲",
                f"{name1} and {name2}: Romance level = Warm and cozy like hot cocoa! ☕",
                f"{name1} and {name2} have cleared the first hurdle! Marathon runners of love! 🏃‍♂️🏃‍♀️",
                f"{name1} and {name2}: Compatibility high! Like two peas in a pod! 🌱"
            ],
            (71, 80): [
                f"{name1} and {name2} are made for each other! Perfect match alert! 🔔💖",
                f"{name1} and {name2}: Soulmate energy detected! Activate wedding planner! 👰",
                f"There's cosmic alignment for {name1} and {name2}! Stars are conspiring! 🌌",
                f"{name1} and {name2} are like two halves of the same coin! Perfect fit! 🪙",
                f"The universe approves of {name1} and {name2}! Divine intervention confirmed! 🙏",
                f"{name1} and {name2}: Love goals achieved! Relationship status: Legendary! 🏆",
                f"There's fairy tale magic between {name1} and {name2}! Happily ever after in sight! 👑",
                f"{name1} and {name2}: Like Romeo and Juliet but without the tragedy! 🎭",
                f"{name1} and {name2} have found their missing piece! Puzzle complete! 🧩",
                f"{name1} and {name2}: Destiny written in the stars! Astrology approved! ⭐"
            ],
            (81, 90): [
                f"{name1} and {name2} are the definition of perfect love! 💯",
                f"{name1} and {name2}: Love so pure it could power a city! 💡❤️",
                f"There's rare chemistry between {name1} and {name2}! Nobel Prize worthy! 🏆",
                f"{name1} and {name2}: Like Yin and Yang - perfectly balanced! ☯️",
                f"The love frequency between {name1} and {name2} is off the charts! 📈",
                f"{name1} and {name2}: Heartbeat synchronization achieved! ❤️❤️",
                f"{name1} and {name2}: Love so strong it bends spacetime! 🌌",
                f"There's quantum entanglement between {name1} and {name2} hearts! 🔬",
                f"{name1} and {name2}: Relationship goals so high they need oxygen! 🧠",
                f"{name1} and {name2}: Love so intense it creates its own dimension! 🌐"
            ],
            (91, 99): [
                f"{name1} and {name2} are the ultimate soulmates! Legendary love story! 🏆",
                f"{name1} and {name2}: Love so epic it deserves a Hollywood movie! 🎥",
                f"There's mythological level bonding between {name1} and {name2}! Greek gods approve! ⚡",
                f"{name1} and {name2}: Like Endgame level commitment! Final form achieved! 🦸‍♂️",
                f"The love energy between {name1} and {name2} could solve world hunger! 🌍",
                f"{name1} and {name2}: Soul connection so deep it transcends reality! 🌠",
                f"{name1} and {name2}: Love so powerful it rewrites the laws of physics! 📚",
                f"There's multiverse level compatibility between {name1} and {name2}! Infinite possibilities! 🌌",
                f"{name1} and {name2}: Love so legendary it will be studied for centuries! 📚",
                f"{name1} and {name2}: Perfect 100% match material! Platonic ideal achieved! 🔱"
            ],
            100: [
                f"{name1} and {name2} are the ultimate soulmates! Legendary love story! 🏆",
                f"{name1} and {name2}: Maximum love output achieved! Heart overload! ❤️❤️❤️",
                f"Perfect 100% compatibility! {name1} and {name2} are love's chosen ones! 🎯",
                f"{name1} and {name2}: Love so perfect it created a new measurement unit! 📏",
                f"There's divine intervention between {name1} and {name2}! Miracle confirmed! ✨",
                f"{name1} and {name2}: Love so pure it glows in the dark! 💫",
                f"{name1} and {name2}: Relationship status: Unbreakable! Titanium bond achieved! 🛡️",
                f"{name1} and {name2}: Love so intense it achieved escape velocity! 🚀",
                f"{name1} and {name2}: Perfect harmony! Even their heartbeats are synchronized! 🎵",
                f"{name1} and {name2}: 100% match! Love's highest achievement unlocked! 🏅"
            ]
        }
        
        selected_messages = []
        if percentage == 0: selected_messages = messages[0]
        elif percentage == 100: selected_messages = messages[100]
        else:
            for range_key, range_messages in messages.items():
                if isinstance(range_key, tuple) and range_key[0] <= percentage <= range_key[1]:
                    selected_messages = range_messages
                    break
        
        return random.choice(selected_messages) if selected_messages else "These two are destined to be together! 💘"

    async def create_ship_image(self, user1, user2, percentage):
        """Create the ship image with the provided assets"""
        try:
            base_path = "data/ship/"
            bg_path = base_path + "bg.png"
            font_path = base_path + "font.ttf"
            frame_path = base_path + "loverframe.png"
            
            if percentage == 0: image_path = base_path + "0%.png"
            elif 1 <= percentage <= 10: image_path = base_path + "1to10%.png"
            elif 11 <= percentage <= 30: image_path = base_path + "11to30%.png"
            elif 31 <= percentage <= 50: image_path = base_path + "31to50%.png"
            elif 51 <= percentage <= 70: image_path = base_path + "51to70%.png"
            elif 71 <= percentage <= 80: image_path = base_path + "71to80%.png"
            elif 81 <= percentage <= 90: image_path = base_path + "71to80%.png"
            elif 91 <= percentage <= 99: image_path = base_path + "91to99%.png"
            elif percentage == 100: image_path = base_path + "100%.png"
            else: image_path = base_path + "51to70%.png"
            
            for p in [bg_path, font_path, frame_path, image_path]:
                if not os.path.exists(p): raise FileNotFoundError(f"Missing asset: {p}")
            
            # --- CANVAS SETUP ---
            W, H = 900, 400
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            
            bg = Image.open(bg_path).convert("RGBA").resize((W, H))
            canvas.paste(bg, (0, 0))
            
            # --- CONFIG ---
            frame_size = 220
            # INCREASED SIZE: 300px is significantly larger than the 220px frames
            heart_max_size = 300
            avatar_size = 170
            
            center_y = (H - frame_size) // 2 - 20 
            
            # Position Calculations
            gap = 30 # Small gap to keep everything on screen since heart is huge
            heart_center_x = W // 2
            
            # Frame Positions: Centered relative to the Middle Heart
            # [Frame] <gap> [Heart] <gap> [Frame]
            
            left_frame_x = heart_center_x - (heart_max_size // 2) - gap - frame_size
            right_frame_x = heart_center_x + (heart_max_size // 2) + gap
            
            # --- AVATARS ---
            avatar1_bytes = await self.download_avatar(user1)
            avatar2_bytes = await self.download_avatar(user2)
            img1 = Image.open(io.BytesIO(avatar1_bytes)).convert("RGBA")
            img2 = Image.open(io.BytesIO(avatar2_bytes)).convert("RGBA")
            img1 = self.make_circular_avatar(img1, (avatar_size, avatar_size))
            img2 = self.make_circular_avatar(img2, (avatar_size, avatar_size))
            
            # Paste Avatars
            offset = (frame_size - avatar_size) // 2
            canvas.paste(img1, (left_frame_x + offset, center_y + offset), img1)
            canvas.paste(img2, (right_frame_x + offset, center_y + offset), img2)
            
            # Paste Frames
            frame_img = Image.open(frame_path).convert("RGBA").resize((frame_size, frame_size))
            canvas.paste(frame_img, (left_frame_x, center_y), frame_img)
            canvas.paste(frame_img, (right_frame_x, center_y), frame_img)
            
            # --- HEART ---
            heart_img = Image.open(image_path).convert("RGBA")
            
            # Resize logic: Fit within box but maintain aspect ratio
            heart_img.thumbnail((heart_max_size, heart_max_size), Image.Resampling.LANCZOS)
            
            # Calculate exact center for the resized heart
            h_w, h_h = heart_img.size
            heart_paste_x = heart_center_x - (h_w // 2)
            
            # Vertically align heart center with frame center
            heart_paste_y = center_y + (frame_size - h_h) // 2 
            
            canvas.paste(heart_img, (heart_paste_x, heart_paste_y), heart_img)
            
            # --- TEXT ---
            draw = ImageDraw.Draw(canvas)
            try:
                font_big = ImageFont.truetype(font_path, 70)
                font_small = ImageFont.truetype(font_path, 40)
            except:
                font_big = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # 1. Percentage
            text = f"{percentage}%"
            bbox = draw.textbbox((0, 0), text, font=font_big)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            # Center exactly in the middle of the heart space
            tx = heart_center_x - (tw // 2)
            # Vertical center
            ty = center_y + (frame_size - th) // 2 - 8
            
            draw.text((tx-2, ty-2), text, font=font_big, fill="#ff69b4")
            draw.text((tx+2, ty-2), text, font=font_big, fill="#ff69b4")
            draw.text((tx-2, ty+2), text, font=font_big, fill="#ff69b4")
            draw.text((tx+2, ty+2), text, font=font_big, fill="#ff69b4")
            draw.text((tx, ty), text, font=font_big, fill="white")
            
            # 2. Names
            def draw_styled_name(name, center_x, top_y):
                name = name[:10]
                bbox = draw.textbbox((0, 0), name, font=font_small)
                nw = bbox[2] - bbox[0]
                nx = center_x + (frame_size - nw) // 2
                draw.text((nx-2, top_y-2), name, font=font_small, fill="white")
                draw.text((nx+2, top_y-2), name, font=font_small, fill="white")
                draw.text((nx-2, top_y+2), name, font=font_small, fill="white")
                draw.text((nx+2, top_y+2), name, font=font_small, fill="white")
                draw.text((nx, top_y), name, font=font_small, fill="#ff69b4")

            name_y = center_y + frame_size + 15
            draw_styled_name(user1.display_name, left_frame_x, name_y)
            draw_styled_name(user2.display_name, right_frame_x, name_y)
            
            buffer = io.BytesIO()
            canvas.save(buffer, format='PNG')
            buffer.seek(0)
            return buffer

        except Exception as e:
            print(f"Error in ship image: {e}")
            img = Image.new('RGB', (900, 400), color=(75, 0, 130))
            draw = ImageDraw.Draw(img)
            draw.text((50, 200), f"Error: {str(e)}", fill="white")
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            return buffer

    async def download_avatar(self, user):
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as response:
                return await response.read()

    def make_circular_avatar(self, avatar, size):
        avatar = avatar.resize(size, Image.Resampling.LANCZOS)
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        output = Image.new('RGBA', size, (0, 0, 0, 0))
        output.paste(avatar, (0, 0), mask)
        return output

async def setup(bot):
    await bot.add_cog(Fun(bot))