from discord.ext import commands, tasks
import datetime, random, asyncio, logging, os, discord, json
import motor.motor_asyncio
from utils.Tools import *
import aiohttp
import io
from PIL import Image
import re 



def manage_server_only():
    """STRICT permission check - ONLY Manage Server permission allowed"""
    async def predicate(ctx):
        if not ctx.guild:
            return False  # No DMs allowed
        
        # Check if user has manage_guild (Manage Server) permission
        if not ctx.author.guild_permissions.manage_guild:
            return False
        
        return True
    return commands.check(predicate)


class GiveawayRerollView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Reroll", style=discord.ButtonStyle.grey, custom_id="giveaway:reroll", emoji="<:reroll:1457368810184249567>")
    async def reroll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Get Host ID from Embed
        if not interaction.message.embeds:
            return await interaction.response.send_message("❌ Error: Original embed not found.", ephemeral=True)
        
        embed = interaction.message.embeds[0]
        host_id = None
        
        # Try finding Host ID in description via Regex or parsing
        # Description format: "**Hosted by:** <@123456>"
        if embed.description:
            match = re.search(r"Hosted by:\*\* <@!?(\d+)>", embed.description)
            if match:
                host_id = int(match.group(1))

        # 2. Permission Check
        is_host = host_id == interaction.user.id
        is_admin = interaction.user.guild_permissions.administrator
        
        if not (is_host or is_admin):
            return await interaction.response.send_message("❌ Only the **Host** or and **Admin** can reroll this giveaway.", ephemeral=True)

        # 3. Trigger Reroll
        cog = self.bot.get_cog("Giveaway")
        if cog:
            await interaction.response.defer(ephemeral=True)
            await cog.do_reroll(interaction.message, interaction)
        else:
            await interaction.response.send_message("❌ Error: Giveaway system not active.", ephemeral=True)



class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_default_database()
        self.collection = self.db.giveaways
        self.embed_color = 0x6123ab  # Updated purple color


    async def get_dominant_color(self, url):
        """Extract dominant color from image URL"""
        if not url:
            return discord.Color.dark_grey()
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(url)) as resp:
                    if resp.status != 200:
                        return discord.Color.dark_grey()
                    data = await resp.read()
                    
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
            img = img.resize((1, 1))
            color = img.getpixel((0, 0))
            return discord.Color.from_rgb(*color)
        except Exception:
            return discord.Color.dark_grey()

    async def cog_load(self) -> None:
        """Initialize database and start background tasks"""
        await self.collection.create_index("message_id", unique=True)
        print("✅ Giveaway MongoDB indexes initialized")
        
        await self.check_for_ended_giveaways()
        self.bot.add_view(GiveawayRerollView(self.bot))
        self.GiveawayEnd.start()


    async def cog_unload(self) -> None:
        """Clean up resources when cog is unloaded"""
        self.GiveawayEnd.cancel()


    async def ensure_connection(self):
        """Ensure database connection is active (Legacy placeholder)"""
        pass

    async def get_participants(self, message):
        """Safely get participants from message reactions"""
        if not message.reactions:
            return []
        
        try:
            reaction = message.reactions[0]
            users = []
            async for user in reaction.users():
                if not user.bot:
                    users.append(user.id)
            return users
        except (IndexError, AttributeError):
            return []


    async def safe_send(self, ctx, *args, **kwargs):
        """Send response safely for both prefix and slash commands"""
        try:
            if hasattr(ctx, 'response') and ctx.response.is_done():
                await ctx.followup.send(*args, **kwargs)
            elif hasattr(ctx, 'followup'):
                await ctx.followup.send(*args, **kwargs)
            else:
                await ctx.send(*args, **kwargs)
        except Exception as e:
            try:
                await ctx.send(*args, **kwargs)
            except Exception as fallback_error:
                logging.error(f"Failed to send message: {fallback_error}")


    async def check_for_ended_giveaways(self):
        """Check for and process ended giveaways"""
        current_time = datetime.datetime.now().timestamp()
        
        # 1. End active giveaways
        ended_cursor = self.collection.find({
            "ends_at": {"$lte": current_time},
            "participants": {"$exists": False}  # Active giveaways don't have participants stored yet? Or check active state
            # Logic check: In original SQLite, "participants IS NULL" meant active.
            # In MongoDB, we can just check if it's not ended or process it.
            # Assuming logic matches: ends_at <= now, and not yet processed (which we'll mark by setting participants)
        })
        
        # Original: SELECT ... WHERE ends_at <= ? AND participants IS NULL
        
        # In this logic, we iterate active giveaways that should end
        async for giveaway in ended_cursor:
             # Map dict to expected tuple/obj structure if needed, or pass dict directly to end_giveaway
             # end_giveaway expects tuple access like giveaway[1] if we don't change it.
             # Let's adapt end_giveaway to accept dict.
             await self.end_giveaway(giveaway)

        # 2. Cleanup old giveaways (24 hours after end)
        cleanup_time = current_time - 86400 # 24 hours ago
        await self.collection.delete_many({"ends_at": {"$lt": cleanup_time}})


    async def end_giveaway(self, giveaway, forced=False, forced_by=None):
        """End a giveaway and select winners"""
        try:
            # Handle both Tuple (SQLite legacy) and Dict (MongoDB)
            if isinstance(giveaway, dict):
                guild_id = giveaway["guild_id"]
                message_id = giveaway["message_id"]
                channel_id = giveaway["channel_id"]
                winners_count_req = giveaway["winners"]
                prize = giveaway["prize"]
                host_id = giveaway["host_id"]
            else:
                # Should not happen if fully migrated, but for safety during transition
                guild_id = giveaway[1]
                message_id = giveaway[2]
                channel_id = giveaway[6]
                winners_count_req = giveaway[4]
                prize = giveaway[5]
                host_id = giveaway[3]


            guild = self.bot.get_guild(guild_id)
            if guild is None:
                await self.collection.delete_one({"message_id": message_id, "guild_id": guild_id})
                return


            channel = self.bot.get_channel(channel_id)
            if not channel:
                return


            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                await self.collection.delete_one({"message_id": message_id, "guild_id": guild_id})
                return


            # Get participants safely
            users = await self.get_participants(message)
            winners_count = min(len(users), int(winners_count_req))

            # Get embed color and thumbnail
            thumbnail_url = self.bot.user.display_avatar.url
            embed_color = self.embed_color # Fixed purple

            # Create ended embed based on scenario
            if forced:
                ended_embed = discord.Embed(
                    title=f"<:giftttt:1457367596058935458> **{prize}**",
                    description=f"> <a:dot:1396429135588626442> **Ended by:** <@{forced_by}>\n**Status:** Cancelled",
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow()
                )
            else:
                if winners_count == 0:
                    ended_embed = discord.Embed(
                        title=f"**{prize}**",
                        description="**No Winner** - Not enough participants!",
                        color=discord.Color.red(),
                        timestamp=discord.utils.utcnow()
                    )
                else:
                    winner_ids = random.sample(users, k=winners_count)
                    winner_mentions = ", ".join(f"<@!{uid}>" for uid in winner_ids)
                    
                    ended_embed = discord.Embed(
                        title=f"<:giftttt:1457367596058935458> **{prize}**",
                        description=(
                            f"> <a:dot:1396429135588626442> **Winner{'s' if winners_count > 1 else ''}:** {winner_mentions}\n"
                            f"> <a:dot:1396429135588626442> **Hosted by:** <@{host_id}>\n"
                            f"> <a:dot:1396429135588626442> **Ended:** <t:{int(datetime.datetime.now().timestamp())}:R>"
                        ),
                        color=embed_color,
                        timestamp=discord.utils.utcnow()
                    )
                    
                    # Send congratulatory message
                    try:
                        congrats_msg = f"> <a:2659tadapurple:1414557673092943984> Congrats, {winner_mentions} you have won **{prize}**, hosted by <@{host_id}>"
                        await channel.send(congrats_msg)
                    except Exception as e:
                        logging.warning(f"Failed to send congratulatory message: {e}")                    
                    # DM winners
                    for winner_id in winner_ids:
                        try:
                            winner_user = self.bot.get_user(winner_id)
                            if winner_user:
                                dm_embed = discord.Embed(
                                    title="<a:2659tadapurple:1414557673092943984> **You Won a Giveaway!**",
                                    description=f"> <a:dot:1396429135588626442> You won the giveaway **{prize}** in **{guild.name}**!\n\nClaim your prize fast!",
                                    color=discord.Color.gold()
                                )
                                await winner_user.send(embed=dm_embed)
                        except Exception as e:
                            logging.warning(f"Failed to DM winner {winner_id}: {e}")

            if thumbnail_url:
                ended_embed.set_thumbnail(url=thumbnail_url)

            ended_embed.set_footer(text=f"Ended • Giveaway ID: {message.id}")
            
            # Remove reactions first
            try:
                await message.clear_reactions()
            except discord.Forbidden:
                pass # Can't clear if no perms, minimal issue

            # Update message with Reroll Button
            view = GiveawayRerollView(self.bot)
            await message.edit(content=None, embed=ended_embed, view=view)


            # Save participants to DB for reroll
            # In MongoDB, we update the existing document
            await self.collection.update_one(
                {"message_id": message.id},
                {"$set": {"participants": users}} # Store as list directly
            )
            # await self.connection.commit() (Not needed)
            # Do NOT delete from DB yet (wait 24h)


        except Exception as e:
            logging.error(f"[GiveawayEnd] Error: {e}")


    @tasks.loop(seconds=5)
    async def GiveawayEnd(self):
        """Background task to check for ended giveaways"""
        await self.check_for_ended_giveaways()


    @commands.hybrid_group(name="giveaway", description="Giveaway commands", invoke_without_command=True)
    @blacklist_check()
    @ignore_check()
    @manage_server_only()  # ONLY Manage Server permission
    async def giveaway(self, ctx):
        """Main giveaway command group - MANAGE SERVER ONLY"""
        # Triple check at runtime
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
            
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="**🔒 Giveaway Commands**",
                description="**Available Commands:**\n`/giveaway start` - Start a new giveaway\n`/giveaway end` - End an active giveaway\n`/giveaway reroll` - Reroll giveaway winner\n`/giveaway list` - List all active giveaways\n\n**🛡️ Restricted Access:** Manage Server permission only",
                color=self.embed_color
            )
            embed.set_footer(text=f"🔒 Manage Server Required • Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)


    @giveaway.command(name="start", description="Start a new giveaway")
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        """Start a new giveaway - MANAGE SERVER ONLY"""
        # Triple check at runtime
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
            
        # await self.ensure_connection() # MongoDB handles this

        # Parse duration
        time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
        duration_seconds = 0

        try:
            if duration[-1].lower() in time_units:
                duration_seconds = int(duration[:-1]) * time_units[duration[-1].lower()]
            else:
                duration_seconds = int(duration)
        except (ValueError, IndexError):
            error_embed = discord.Embed(
                title="**Invalid Duration**",
                description="Please use format like: `1h`, `30m`, `1d`, `1w` or just seconds",
                color=discord.Color.red()
            )
            return await ctx.send(embed=error_embed)


        # Validate duration
        if duration_seconds < 10:
            error_embed = discord.Embed(
                title="**Duration Too Short**",
                description="Giveaway must last at least 10 seconds!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=error_embed)


        # Validate winners count
        if winners < 1 or winners > 20:
            error_embed = discord.Embed(
                title="**Invalid Winners Count**",
                description="Winners must be between 1 and 20!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=error_embed)


        # Calculate end time
        ends_at = datetime.datetime.now().timestamp() + duration_seconds


        # Get embed color and thumbnail
        thumbnail_url = self.bot.user.display_avatar.url
        embed_color = self.embed_color


        # Create giveaway embed
        giveaway_embed = discord.Embed(
            title=f"<:giftttt:1457367596058935458> **{prize}**",
            description=(
                f"> <a:dot:1396429135588626442> **Ends:** <t:{int(ends_at)}:R>\n"
                f"> <a:dot:1396429135588626442> **Winners:** {winners}\n"
                f"> <a:dot:1396429135588626442> **Hosted by:** {ctx.author.mention}\n\n"
                f"> <a:dot:1396429135588626442> **React with <a:2659tadapurple:1414557673092943984> to participate!**"
            ),
            color=embed_color,
            timestamp=discord.utils.utcnow()
        )
        
        giveaway_embed.set_thumbnail(url=thumbnail_url)
            
        giveaway_embed.set_footer(text=f"Hosted by {ctx.author.display_name} • Good luck!", icon_url=ctx.author.display_avatar.url)


        # Send message and add reaction
        message = await ctx.send(embed=giveaway_embed)
        await message.add_reaction("<a:2659tadapurple:1414557673092943984>")


        # Save to database
        await self.collection.update_one(
            {"guild_id": ctx.guild.id, "message_id": message.id},
            {"$set": {
                "guild_id": ctx.guild.id,
                "host_id": ctx.author.id,
                "start_time": datetime.datetime.now().timestamp(),
                "ends_at": ends_at,
                "prize": prize,
                "winners": winners,
                "message_id": message.id,
                "channel_id": message.channel.id
            }},
            upsert=True
        )


    @giveaway.command(name="end", description="End a giveaway with message ID")
    async def giveaway_end(self, ctx, message_id: str):
        """End an active giveaway - MANAGE SERVER ONLY"""
        # Triple check at runtime
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
            
        # Defer for slash commands
        if hasattr(ctx, 'response'):
            await ctx.defer(ephemeral=True)
        
        # Validate message ID
        try:
            message_id_int = int(message_id)
        except ValueError:
            error_embed = discord.Embed(
                title="**Invalid Message ID**",
                description="Please provide a valid message ID (numbers only)!",
                color=discord.Color.red()
            )
            return await self.safe_send(ctx, embed=error_embed, ephemeral=True)


        # Check if giveaway exists
        # await self.ensure_connection()
        row = await self.collection.find_one({"message_id": message_id_int, "guild_id": ctx.guild.id})


        if not row:
            error_embed = discord.Embed(
                title="**Giveaway Not Found**",
                description=f"No active giveaway found with ID: `{message_id}`",
                color=discord.Color.red()
            )
            return await self.safe_send(ctx, embed=error_embed, ephemeral=True)


        # End the giveaway
        await self.end_giveaway(row, forced=True, forced_by=ctx.author.id)


        success_embed = discord.Embed(
            title="<a:scyromoney:1419323691707138120> **Giveaway Ended Successfully** <a:scyromoney:1419323691707138120>",
            description=f"> <:scyrogift:1419323376539009154> Successfully ended giveaway: **{row['prize']}** <:scyrogift:1419323376539009154>",
            color=discord.Color.green()
        )
        success_embed.set_footer(text=f"🔒 Ended by {ctx.author.display_name} • Manage Server")
        await self.safe_send(ctx, embed=success_embed, ephemeral=True)


    @giveaway.command(name="reroll", description="Reroll giveaway winner")
    async def giveaway_reroll(self, ctx, message_id: str):
        """Reroll winners for a giveaway - MANAGE SERVER ONLY"""
        # Triple check at runtime
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
            
        # Defer for slash commands
        if hasattr(ctx, 'response'):
            await ctx.defer(ephemeral=True)
        
        # Validate message ID
        try:
            message_id_int = int(message_id)
        except ValueError:
            error_embed = discord.Embed(
                title="**Invalid Message ID**",
                description="Please provide a valid message ID (numbers only)!",
                color=discord.Color.red()
            )
            return await self.safe_send(ctx, embed=error_embed, ephemeral=True)


        # Fetch the message
        try:
            message = await ctx.channel.fetch_message(message_id_int)
        except discord.NotFound:
            error_embed = discord.Embed(
                title="**Message Not Found**",
                description=f"Could not find message with ID: `{message_id}`",
                color=discord.Color.red()
            )
            return await self.safe_send(ctx, embed=error_embed, ephemeral=True)


        await self.do_reroll(message, ctx)


    async def do_reroll(self, message: discord.Message, interaction_or_ctx):
        """Shared reroll logic"""
        # Determine how to reply (Context vs Interaction)
        async def reply(content=None, embed=None, ephemeral=True):
            if isinstance(interaction_or_ctx, discord.Interaction):
                if not interaction_or_ctx.response.is_done():
                    await interaction_or_ctx.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
                else:
                    await interaction_or_ctx.followup.send(content=content, embed=embed, ephemeral=ephemeral)
            else:
                 # Context
                await self.safe_send(interaction_or_ctx, content=content, embed=embed, ephemeral=ephemeral)

        # Get participants
        # Try fetching from DB first (for ended giveaways where reactions are cleared)
        users = []
        try:
            # await self.ensure_connection()
            row = await self.collection.find_one({"message_id": message.id})
            if row and "participants" in row:
                users = row["participants"] # Should be list from MongoDB
                # Double check type just in case migration from old system stored string
                if isinstance(users, str):
                    try:
                        users = json.loads(users)
                    except:
                        users = []
        except Exception as e:
            logging.error(f"Failed to fetch participants from DB: {e}")

        # If not in DB (or active giveaway?), fallback to reactions
        if not users:
            users = await self.get_participants(message)

        if not users:
            error_embed = discord.Embed(
                title="<:7477purplemember:1414555528784515112> **No Participants** <:7477purplemember:1414555528784515112>",
                description="> **No participants found to reroll!**",
                color=discord.Color.red()
            )
            return await reply(embed=error_embed)


        # Exclude existing winners (from Embed description)
        existing_winner_ids = set()
        if message.embeds:
            embed = message.embeds[0]
            if embed.description:
                # Regex to find all mentions in description lines starting with "Winner"
                # Pattern: **Winner(s):** <@ID>, <@ID>
                # Simplest is just grab all mentions in the whole description? 
                # Better: Look for specific line to avoid hostility/footer mentions?
                # The description format is: > ... **Winner(s):** <@...>
                matches = re.findall(r"<@!?(\d+)>", embed.description)
                # Filter out Host ID if present (Host line is also in description)
                # Host line: **Hosted by:** <@ID>
                # We can try to parse lines.
                for line in embed.description.split('\n'):
                    if "Winner" in line:
                        ids = re.findall(r"<@!?(\d+)>", line)
                        existing_winner_ids.update(int(id) for id in ids)

        # Filter potential winners
        potential_winners = [u for u in users if u not in existing_winner_ids]

        if not potential_winners:
             error_embed = discord.Embed(
                title="<:7477purplemember:1414555528784515112> **No Valid Winners** <:7477purplemember:1414555528784515112>",
                description="> **All participants have already won!**",
                color=discord.Color.red()
            )
             return await reply(embed=error_embed)

        # Select new winner
        new_winner_id = random.choice(potential_winners)
        new_winner = self.bot.get_user(new_winner_id)
        
        # Get executor
        executor = interaction_or_ctx.user if isinstance(interaction_or_ctx, discord.Interaction) else interaction_or_ctx.author


        # Create reroll embed
        reroll_embed = discord.Embed(
            title="**<a:2659tadapurple:1414557673092943984> Giveaway Rerolled**",
            description=f"> <a:dot:1396429135588626442> **New Winner:** {new_winner.mention if new_winner else f'<@{new_winner_id}>'}",
            color=self.embed_color,
            timestamp=discord.utils.utcnow()
        )
        reroll_embed.add_field(name="> <:7477purplemember:1414555528784515112> **Participants**", value=f"{len(users)} users", inline=True)
        reroll_embed.add_field(name="> <:host:1419325442757759077> **Rerolled by**", value=f"{executor.mention}", inline=True)
        reroll_embed.set_footer(
            text=f"Status: Rerolled • Message ID: {message.id}",
            icon_url=executor.display_avatar.url
        )


        if isinstance(interaction_or_ctx, discord.Interaction):
             await message.reply(embed=reroll_embed)
             await reply(content="✅ Reroll successful!", ephemeral=True)
        else:
             await self.safe_send(interaction_or_ctx, embed=reroll_embed)


        # DM the new winner
        if new_winner:
            try:
                dm_embed = discord.Embed(
                    title="**<a:2659tadapurple:1414557673092943984> You Won a Rerolled Giveaway!**",
                    description=f"> <a:dot:1396429135588626442> You won a rerolled giveaway in **{message.guild.name}**!\n\nClaim your prize fast!",
                    color=discord.Color.gold()
                )
                dm_embed.set_footer(text="Contact the host to claim your prize!")
                await new_winner.send(embed=dm_embed)
            except Exception as e:
                logging.warning(f"Failed to DM reroll winner {new_winner_id}: {e}")


    @giveaway.command(name="list", description="List all active giveaways")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def giveaway_list(self, ctx):
        """List all active giveaways in the server - MANAGE SERVER ONLY"""
        # Triple check at runtime
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
            
        # await self.ensure_connection()
        cursor = self.collection.find({"guild_id": ctx.guild.id}).sort("ends_at", 1)
        rows = await cursor.to_list(length=None)


        if not rows:
            no_giveaways_embed = discord.Embed(
                title="**🔒 Active Giveaways**",
                description="> <a:dot:1396429135588626442> No active giveaways found in this server.\n\nUse `/giveaway start` to create one!\n\n**🛡️ Manage Server Required**",
                color=self.embed_color
            )
            no_giveaways_embed.set_footer(
                text=f"🔒 Requested by {ctx.author.display_name} • Manage Server",
                icon_url=ctx.author.display_avatar.url
            )
            return await ctx.send(embed=no_giveaways_embed)


        list_embed = discord.Embed(
            title="**🔒 Active Giveaways**",
            description=f"> <a:dot:1396429135588626442> Found **{len(rows)}** active giveaway{'s' if len(rows) != 1 else ''}\n\n**🛡️ Manage Server Access**",
            color=self.embed_color,
            timestamp=discord.utils.utcnow()
        )


        for i, giveaway in enumerate(rows[:10], 1):
            prize = giveaway['prize']
            ends_at = giveaway['ends_at']
            message_id = giveaway['message_id']
            host_id = giveaway['host_id']
            winners = giveaway['winners']
            channel_id = giveaway['channel_id']
            
            channel = self.bot.get_channel(int(channel_id))
            channel_mention = channel.mention if channel else "Unknown Channel"
            
            list_embed.add_field(
                name=f"<:giftttt:1457367596058935458> **{i}. {prize}**",
                value=(
                    f"> <a:dot:1396429135588626442> **Ends:** <t:{int(ends_at)}:R>\n"
                    f"> <a:dot:1396429135588626442> **Winners:** {winners}\n"
                    f"> <a:dot:1396429135588626442> **Host:** <@{host_id}>\n"
                    f"> <a:dot:1396429135588626442> **Channel:** {channel_mention}\n"
                    f"> <a:dot:1396429135588626442> **[Jump to Giveaway](https://discord.com/channels/{ctx.guild.id}/{channel_id}/{message_id})**"
                ),
                inline=False
            )


        if len(rows) > 10:
            list_embed.add_field(
                name="**Note**",
                value=f"Showing first 10 of {len(rows)} giveaways",
                inline=False
            )


        list_embed.set_footer(
            text=f"🔒 Requested by {ctx.author.display_name} • Total: {len(rows)} • Manage Server",
            icon_url=ctx.author.display_avatar.url
        )


        await ctx.send(embed=list_embed)


    # ================= PREFIX ALIASES WITH MANAGE SERVER PERMISSION =================
    @commands.command(name="gstart", aliases=["giveawaystart"])
    @blacklist_check()
    @ignore_check()
    @manage_server_only()
    async def gstart_prefix(self, ctx, duration: str, winners: int, *, prize: str):
        """Prefix alias for giveaway start - MANAGE SERVER ONLY"""
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
        await self.giveaway_start(ctx, duration, winners, prize=prize)


    @commands.command(name="gend", aliases=["giveawayend"])
    @blacklist_check()
    @ignore_check()
    @manage_server_only()
    async def gend_prefix(self, ctx, message_id: str):
        """Prefix alias for giveaway end - MANAGE SERVER ONLY"""
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
        await self.giveaway_end(ctx, message_id)


    @commands.command(name="greroll", aliases=["giveawayreroll"])
    @blacklist_check()
    @ignore_check()
    @manage_server_only()
    async def greroll_prefix(self, ctx, message_id: str):
        """Prefix alias for giveaway reroll - MANAGE SERVER ONLY"""
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
        await self.giveaway_reroll(ctx, message_id)


    @commands.command(name="glist", aliases=["giveawaylist"])
    @blacklist_check()
    @ignore_check()
    @manage_server_only()
    async def glist_prefix(self, ctx):
        """Prefix alias for giveaway list - MANAGE SERVER ONLY"""
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
            return
        await self.giveaway_list(ctx)


    # Error handlers
    @giveaway.error
    @gstart_prefix.error
    @gend_prefix.error
    @greroll_prefix.error
    @glist_prefix.error
    async def giveaway_error_handler(self, ctx, error):
        """Handle giveaway command errors"""
        if isinstance(error, commands.CheckFailure):
            # EXACT ERROR MESSAGE FOR MANAGE SERVER PERMISSION
            await ctx.reply("You need `Manage Server` to do that.", mention_author=False)
        elif isinstance(error, commands.CommandOnCooldown):
            error_embed = discord.Embed(
                title="**Command on Cooldown**",
                description=f"Please wait {error.retry_after:.1f} seconds before using this command again.",
                color=discord.Color.orange()
            )
            await self.safe_send(ctx, embed=error_embed, ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            error_embed = discord.Embed(
                title="**Missing Required Argument**",
                description="Please provide all required arguments for this command.",
                color=discord.Color.red()
            )
            await self.safe_send(ctx, embed=error_embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
    
