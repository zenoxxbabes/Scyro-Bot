import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import os

class StickyModal(discord.ui.Modal, title="Sticky Message Configuration"):
    message_content = discord.ui.TextInput(
        label="Sticky Message Content",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the message you want to stick...",
        required=True,
        max_length=2000
    )

    def __init__(self, cog, channel, interaction):
        super().__init__()
        self.cog = cog
        self.channel = channel
        self.original_interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        content = self.message_content.value
        guild_id = interaction.guild.id
        channel_id = self.channel.id

        await self.cog.save_sticky(guild_id, channel_id, content)

        # Send initial sticky
        try:
            msg = await self.channel.send(content=content)
            await self.cog.update_last_message(channel_id, msg.id)
            
            await interaction.response.send_message(f"Sticky message set for {self.channel.mention}!", ephemeral=True)
            
            # Disable the button on the original setup message to prevent re-use
            try:
                await self.original_interaction.message.edit(view=None)
            except:
                pass

        except Exception as e:
            await interaction.response.send_message(f"Failed to set sticky message: {e}", ephemeral=True)

class StickySetupView(discord.ui.View):
    def __init__(self, cog, channel, ctx):
        super().__init__(timeout=60)
        self.cog = cog
        self.channel = channel
        self.ctx = ctx

    @discord.ui.button(label="Set Sticky Message", style=discord.ButtonStyle.blurple, emoji="📝")
    async def set_sticky(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This button is not for you.", ephemeral=True)
        
        await interaction.response.send_modal(StickyModal(self.cog, self.channel, interaction))

class StickyResetView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=30)
        self.cog = cog
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This button is not for you.", ephemeral=True)
        
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This button is not for you.", ephemeral=True)
        
        self.value = False
        await interaction.response.defer()
        self.stop()

class Sticky(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db = None
        self.sticky_coll = None
        self.locks = {} # Lock per channel to prevent race conditions
        self.bot.loop.create_task(self.setup_db())

    async def setup_db(self):
        if not self.mongo_uri:
            print("MONGO_URI not found!")
            return

        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
        self.db = self.mongo_client.get_database()
        self.sticky_coll = self.db.sticky_messages
        
        await self.sticky_coll.create_index([("channel_id", 1)], unique=True)
        print("Sticky Cog MongoDB Connected")

    async def save_sticky(self, guild_id, channel_id, content):
        await self.sticky_coll.update_one(
            {"channel_id": channel_id},
            {"$set": {"guild_id": guild_id, "channel_id": channel_id, "content": content, "last_message_id": None}},
            upsert=True
        )

    async def update_last_message(self, channel_id, message_id):
        await self.sticky_coll.update_one(
            {"channel_id": channel_id},
            {"$set": {"last_message_id": message_id}}
        )

    async def get_sticky(self, channel_id):
        data = await self.sticky_coll.find_one({"channel_id": channel_id})
        if data:
            return (data["content"], data.get("last_message_id"))
        return None

    async def delete_sticky(self, channel_id):
        await self.sticky_coll.delete_one({"channel_id": channel_id})
            
    async def reset_guild_stickies(self, guild_id):
        await self.sticky_coll.delete_many({"guild_id": guild_id})

    async def get_guild_stickies(self, guild_id):
        cursor = self.sticky_coll.find({"guild_id": guild_id})
        results = []
        async for doc in cursor:
            results.append((doc["channel_id"], doc["content"]))
        return results

    @commands.group(name="sticky", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def sticky(self, ctx):
        embed = discord.Embed(
            title="Sticky Message Help",
            description=(
                "`sticky create <channel>` - Create a sticky message\n"
                "`sticky list` - List all sticky messages\n"
                "`sticky remove <channel>` - Remove a sticky message\n"
                "`sticky reset` - Remove ALL sticky messages"
            ),
            color=0x6a0dad
        )
        await ctx.send(embed=embed)

    @sticky.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def sticky_create(self, ctx, channel: discord.TextChannel):
        stickies = await self.get_guild_stickies(ctx.guild.id)
        if len(stickies) >= 5:
             return await ctx.send(embed=discord.Embed(description="You have reached the limit of 5 sticky messages for this server.", color=0xFF0000))
             
        embed = discord.Embed(
            title="Sticky Message Setup",
            description=f"Click the button below to set the sticky message content for {channel.mention}.",
            color=0x6a0dad
        )
        view = StickySetupView(self, channel, ctx)
        await ctx.send(embed=embed, view=view)

    @sticky.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def sticky_list(self, ctx):
        stickies = await self.get_guild_stickies(ctx.guild.id)
        if not stickies:
            return await ctx.send(embed=discord.Embed(description="No sticky messages found in this server.", color=0xFF0000))
        
        embed = discord.Embed(title=f"Sticky Messages in {ctx.guild.name}", color=0x6a0dad)
        for channel_id, content in stickies:
            channel = ctx.guild.get_channel(channel_id)
            chan_name = channel.mention if channel else f"Deleted Channel ({channel_id})"
            preview = content[:50] + "..." if len(content) > 50 else content
            embed.add_field(name=f"Channel: {chan_name}", value=f"Content: {preview}", inline=False)
        
        await ctx.send(embed=embed)

    @sticky.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def sticky_remove(self, ctx, channel: discord.TextChannel):
        # Check if exists
        curr = await self.get_sticky(channel.id)
        if not curr:
            return await ctx.send(embed=discord.Embed(description="No sticky message set for that channel.", color=0xFF0000))

        await self.delete_sticky(channel.id)
        
        # Try to delete the last sticky message logic if possible?
        # Maybe unnecessary, but clean.
        last_msg_id = curr[1]
        if last_msg_id:
             try:
                 msg = await channel.fetch_message(last_msg_id)
                 await msg.delete()
             except:
                 pass

        await ctx.send(embed=discord.Embed(description=f"Sticky message removed from {channel.mention}.", color=0x00FF00))

    @sticky.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def sticky_reset(self, ctx):
        embed = discord.Embed(
            title="Reset All Sticky Messages",
            description="Are you sure you want to remove **ALL** sticky messages in this server? This cannot be undone.",
            color=0xFF0000
        )
        view = StickyResetView(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.value is None:
            await msg.edit(content="Timed out.", view=None)
        elif view.value is True:
            await self.reset_guild_stickies(ctx.guild.id)
            await msg.edit(content="All sticky messages have been reset.", view=None, embed=None)
        else:
            await msg.edit(content="Reset cancelled.", view=None, embed=None)

    async def force_stick(self, channel):
        data = await self.get_sticky(channel.id)
        if not data: return

        content, last_msg_id = data
        
        try:
             # Delete old manually
             if last_msg_id:
                 try:
                     old_msg = await channel.fetch_message(last_msg_id)
                     await old_msg.delete()
                 except:
                     pass
            
             # Send new
             new_msg = await channel.send(content=content)
             await self.update_last_message(channel.id, new_msg.id)
        except Exception as e:
            print(f"Force Stick Error: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if not message.guild:
            return

        # Check if channel has sticky
        data = await self.get_sticky(message.channel.id)
        if not data:
            return

        content, last_msg_id = data
        
        # Determine if we should repost
        # If the last message in channel is NOT the sticky message, repost.
        # But we just received 'message', so we are definitely NOT at the bottom if sticky was 'last_msg_id' (before 'message').
        # So we definitely need to repost.
        
        # Lock to avoid spam/race
        lock_key = f"{message.guild.id}-{message.channel.id}"
        if lock_key in self.locks and self.locks[lock_key]:
            return # Already processing
        
        self.locks[lock_key] = True
        
        try:
             # Delete old if exists
             if last_msg_id:
                 try:
                     old_msg = await message.channel.fetch_message(last_msg_id)
                     await old_msg.delete()
                 except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                     pass
            
             # Send new
             new_msg = await message.channel.send(content=content)
             
             # Create another task to update DB to avoid blocking
             await self.update_last_message(message.channel.id, new_msg.id)
        except Exception as e:
            print(f"Sticky Error: {e}")
        finally:
            self.locks[lock_key] = False
            
async def setup(bot):
    await bot.add_cog(Sticky(bot))
