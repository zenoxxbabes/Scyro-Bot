import discord
from discord.ext import commands
from core.Cog import Cog
from utils.Tools import *
import re
import aiohttp
import io

class Emoji(Cog):
    def __init__(self, bot):
        self.bot = bot

    """Emoji and Sticker management commands"""

    def help_custom(self):
        emoji = '🎭'
        label = "Emote Commands"
        description = "Manage server emojis and stickers with ease"
        return emoji, label, description

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emote(self, ctx):
        """Emote management commands"""
        prefix = ctx.prefix
        em = discord.Embed(
            title="🎭 Emote Management",
            description=f"**Add, steal, rename, and delete emojis and stickers easily!**\n\n"
                        f"`{prefix}emote steal <emoji/sticker_url> [name]` - Steal an emoji or add a sticker\n"
                        f"`{prefix}emote rename <emoji> <new_name>` - Rename an existing emoji\n"
                        f"`{prefix}emote delete <emoji/sticker>` - Delete emojis or stickers from the server\n",
            color=0x2F3136
        )
        em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=em)

    @emote.command(name="steal", aliases=["add"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emote_steal(self, ctx, emote_or_url: str, name: str = None):
        """Steal an emoji or add a sticker to the server"""
        # Check if it's a Discord emoji
        emoji_match = re.match(r'<(a?):([a-zA-Z0-9_]+):(\d+)>', emote_or_url)
        
        if emoji_match:
            # Handle emoji stealing
            animated = bool(emoji_match.group(1))
            emoji_name = emoji_match.group(2)
            emoji_id = emoji_match.group(3)
            
            # If no name provided, use the emoji's name
            if name is None:
                name = emoji_name
                
            # Validate emoji name (only alphanumeric and underscores, 2-32 chars)
            if not re.match(r'^[a-zA-Z0-9_]{2,32}$', name):
                embed = discord.Embed(
                    title="❌ Invalid Name",
                    description="Invalid emoji name. Names must be 2-32 characters long and contain only letters, numbers, and underscores.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)

            # Check if emoji with this name already exists
            existing_emojis = [e for e in ctx.guild.emojis if e.name == name]
            if existing_emojis:
                embed = discord.Embed(
                    title="❌ Emoji Already Exists",
                    description=f"An emoji with the name `{name}` already exists in this server.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)

            # Get the emoji image
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}?v=1"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji_url) as resp:
                    if resp.status != 200:
                        embed = discord.Embed(
                            title="❌ Download Error",
                            description="Failed to download the emoji.",
                            color=0xFF0000
                        )
                        return await ctx.send(embed=embed)
                    emoji_image = await resp.read()
            
            # Create the emoji in the server
            try:
                new_emoji = await ctx.guild.create_custom_emoji(
                    name=name,
                    image=emoji_image,
                    reason=f"Emoji stolen by {ctx.author} ({ctx.author.id})"
                )
                
                embed = discord.Embed(
                    title="✅ Emoji Stolen Successfully",
                    description=f"Stole {new_emoji} with name `{new_emoji.name}` and added it to the server!",
                    color=0x00FF00
                )
                embed.set_thumbnail(url=new_emoji.url)
                embed.add_field(name="Emoji ID", value=new_emoji.id, inline=True)
                embed.add_field(name="Animated", value="Yes" if new_emoji.animated else "No", inline=True)
                embed.set_footer(text=f"Stolen by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                await ctx.send(embed=embed)
            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Permission Error",
                    description="I don't have permission to add emojis.",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="❌ HTTP Error",
                    description=f"Failed to steal emoji: {str(e)}",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Unexpected Error",
                    description=f"An error occurred: {str(e)}",
                    color=0xFF0000
                )
                await ctx.send(embed=embed)
        else:
            # Handle sticker adding
            if not name:
                embed = discord.Embed(
                    title="❌ Missing Name",
                    description="Please provide a name for the sticker.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)
                
            # Validate sticker name (2-30 chars)
            if not (2 <= len(name) <= 30):
                embed = discord.Embed(
                    title="❌ Invalid Name",
                    description="Invalid sticker name. Names must be 2-30 characters long.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)
                
            # Check if sticker with this name already exists
            existing_stickers = [s for s in ctx.guild.stickers if s.name == name]
            if existing_stickers:
                embed = discord.Embed(
                    title="❌ Sticker Already Exists",
                    description=f"A sticker with the name `{name}` already exists in this server.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)
                
            # Download and add sticker
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(emote_or_url) as resp:
                        if resp.status != 200:
                            embed = discord.Embed(
                                title="❌ Download Error",
                                description="Failed to download the sticker. Please make sure the URL is valid.",
                                color=0xFF0000
                            )
                            return await ctx.send(embed=embed)
                        
                        # Check content type
                        content_type = resp.headers.get('content-type', '')
                        if not content_type.startswith(('image/png', 'image/apng', 'image/gif')):
                            embed = discord.Embed(
                                title="❌ Invalid Format",
                                description="Stickers must be PNG, APNG, or GIF images.",
                                color=0xFF0000
                            )
                            return await ctx.send(embed=embed)
                            
                        sticker_data = await resp.read()
                        
                        # Check file size (max 500KB for stickers)
                        if len(sticker_data) > 500 * 1024:
                            embed = discord.Embed(
                                title="❌ File Too Large",
                                description="Sticker file size must be less than 500KB.",
                                color=0xFF0000
                            )
                            return await ctx.send(embed=embed)
                        
                        # Create the sticker
                        new_sticker = await ctx.guild.create_sticker(
                            name=name,
                            description="Added via emote steal command",
                            emoji="😀",  # Default emoji
                            file=discord.File(io.BytesIO(sticker_data), filename=f"{name}.png"),
                            reason=f"Sticker added by {ctx.author} ({ctx.author.id})"
                        )
                        
                        embed = discord.Embed(
                            title="✅ Sticker Added Successfully",
                            description=f"Added sticker `{new_sticker.name}` to the server!",
                            color=0x00FF00
                        )
                        embed.set_thumbnail(url=new_sticker.url)
                        embed.add_field(name="Sticker ID", value=new_sticker.id, inline=True)
                        embed.set_footer(text=f"Added by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                        await ctx.send(embed=embed)
                except discord.Forbidden:
                    embed = discord.Embed(
                        title="❌ Permission Error",
                        description="I don't have permission to add stickers.",
                        color=0xFF0000
                    )
                    await ctx.send(embed=embed)
                except discord.HTTPException as e:
                    embed = discord.Embed(
                        title="❌ HTTP Error",
                        description=f"Failed to add sticker: {str(e)}",
                        color=0xFF0000
                    )
                    await ctx.send(embed=embed)
                except Exception as e:
                    embed = discord.Embed(
                        title="❌ Unexpected Error",
                        description=f"An error occurred: {str(e)}",
                        color=0xFF0000
                    )
                    await ctx.send(embed=embed)

    @emote.command(name="rename")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emote_rename(self, ctx, emote: discord.Emoji, name: str):
        """Rename an existing emoji in the server"""
        try:
            # Check if the emoji is from this server
            if emote.guild_id != ctx.guild.id:
                embed = discord.Embed(
                    title="❌ Invalid Emoji",
                    description="That emoji is not from this server!",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)
                
            # Validate emoji name (only alphanumeric and underscores, 2-32 chars)
            if not re.match(r'^[a-zA-Z0-9_]{2,32}$', name):
                embed = discord.Embed(
                    title="❌ Invalid Name",
                    description="Invalid emoji name. Names must be 2-32 characters long and contain only letters, numbers, and underscores.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)
                
            # Check if another emoji with this name already exists
            existing_emojis = [e for e in ctx.guild.emojis if e.name == name and e.id != emote.id]
            if existing_emojis:
                embed = discord.Embed(
                    title="❌ Emoji Already Exists",
                    description=f"An emoji with the name `{name}` already exists in this server.",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)

            # Rename the emoji
            old_name = emote.name
            renamed_emoji = await emote.edit(name=name, reason=f"Emoji renamed by {ctx.author} ({ctx.author.id})")
            
            embed = discord.Embed(
                title="✅ Emoji Renamed Successfully",
                description=f"Renamed {renamed_emoji} from `{old_name}` to `{renamed_emoji.name}`!",
                color=0x00FF00
            )
            embed.set_thumbnail(url=renamed_emoji.url)
            embed.add_field(name="Emoji ID", value=renamed_emoji.id, inline=True)
            embed.set_footer(text=f"Renamed by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission Error",
                description="I don't have permission to rename emojis.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ HTTP Error",
                description=f"Failed to rename emoji: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Unexpected Error",
                description=f"An error occurred: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    @emote.command(name="delete", aliases=["remove"])
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emote_delete(self, ctx, emote: discord.Emoji):
        """Delete an emoji from the server"""
        try:
            # Check if the emoji is from this server
            if emote.guild_id != ctx.guild.id:
                embed = discord.Embed(
                    title="❌ Invalid Emoji",
                    description="That emoji is not from this server!",
                    color=0xFF0000
                )
                return await ctx.send(embed=embed)
                
            # Delete the emoji
            emoji_name = emote.name
            await emote.delete(reason=f"Emoji deleted by {ctx.author} ({ctx.author.id})")
            
            embed = discord.Embed(
                title="✅ Emoji Deleted Successfully",
                description=f"Deleted emoji `{emoji_name}` from the server!",
                color=0x00FF00
            )
            embed.set_footer(text=f"Deleted by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission Error",
                description="I don't have permission to delete emojis.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ HTTP Error",
                description=f"Failed to delete emoji: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Unexpected Error",
                description=f"An error occurred: {str(e)}",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    # Error handlers as methods of the cog
    @emote_steal.error
    async def emote_steal_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Permission Error",
                description="You don't have permission to manage the server to use this command.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="❌ Bot Permission Error",
                description="I don't have permission to manage emojis and stickers.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Missing Argument",
                description="Please provide an emoji or sticker URL to steal.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    @emote_rename.error
    async def emote_rename_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Permission Error",
                description="You don't have permission to manage the server to use this command.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="❌ Bot Permission Error",
                description="I don't have permission to rename emojis.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Missing Argument",
                description="Please provide an emoji and a new name.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ Invalid Emoji",
                description="Invalid emoji. Please provide a valid custom emoji from this server.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

    @emote_delete.error
    async def emote_delete_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Permission Error",
                description="You don't have permission to manage the server to use this command.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                title="❌ Bot Permission Error",
                description="I don't have permission to delete emojis.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Missing Argument",
                description="Please specify an emoji to delete.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ Invalid Emoji",
                description="Invalid emoji. Please provide a valid custom emoji from this server.",
                color=0xFF0000
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Emoji(bot))