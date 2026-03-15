from discord.ext import commands
from core import Scyro, Cog
import discord
import logging
import os
from discord.ui import View, Button, Select

logging.basicConfig(
    level=logging.INFO,
    format="\x1b[38;5;197m[\x1b[0m%(asctime)s\x1b[38;5;197m]\x1b[0m -> \x1b[38;5;197m%(message)s\x1b[0m",
    datefmt="%H:%M:%S",
)

class Guild(Cog):
    def __init__(self, client: Scyro):
        self.client = client

    @commands.Cog.listener(name="on_guild_join")
    async def on_guild_add(self, guild):
        try:
            # Log channel for guild joins
            join_log_channel_id = int(os.environ.get('GUILD_JOIN_LOG_CHANNEL', '1431956615590056027'))
            log_channel = self.client.get_channel(join_log_channel_id)
            
            if log_channel is None:
                logging.warning(f"Join log channel with ID {join_log_channel_id} not found or not accessible.")
            
            # Get invite link safely
            rope = None
            try:
                if guild.me.guild_permissions.manage_guild:
                    invites = await guild.invites()
                    permanent_invites = [inv for inv in invites if inv.max_age == 0 and inv.max_uses == 0]
                    rope = permanent_invites[0] if permanent_invites else None
            except discord.Forbidden:
                logging.info(f"No permission to fetch invites for guild: {guild.name}")
            except Exception as e:
                logging.warning(f"Error fetching invites for {guild.name}: {e}")

            # Send join log if channel is accessible
            if log_channel:
                try:
                    channels = len(set(self.client.get_all_channels()))
                    embed = discord.Embed(title=f"{guild.name}'s Information", color=0x000000)
                    
                    embed.set_author(name="Guild Joined")
                    embed.set_footer(text=f"Added in {guild.name}")

                    # Guild info
                    owner_mention = f"{guild.owner} (<@{guild.owner_id}>)" if guild.owner else "Unknown Owner"
                    embed.add_field(
                        name="**__About__**",
                        value=f"**Name:** {guild.name}\n**ID:** {guild.id}\n**Owner <:king:1348340519255937045>:** {owner_mention}\n**Created At:** {guild.created_at.month}/{guild.created_at.day}/{guild.created_at.year}\n**Members:** {len(guild.members)}",
                        inline=False
                    )
                    
                    # Description (handle None)
                    description = guild.description if guild.description else "No description available"
                    embed.add_field(
                        name="**__Description__**",
                        value=description,
                        inline=False
                    )
                    
                    # Member stats
                    humans = len([m for m in guild.members if not m.bot])
                    bots = len([m for m in guild.members if m.bot])
                    embed.add_field(
                        name="**__Members__**",
                        value=f"<:members:1348326443834146836> Members: {len(guild.members)}\n<:member:1348326398929932388> Humans: {humans}\n<:robot:1348340531335270420> Bots: {bots}",
                        inline=False
                    )
                    
                    # Channel stats
                    embed.add_field(
                        name="**__Channels__**",
                        value=f"Categories: {len(guild.categories)}\nText Channels: {len(guild.text_channels)}\nVoice Channels: {len(guild.voice_channels)}\nThreads: {len(guild.threads)}",
                        inline=False
                    )
                    
                    # Bot stats
                    embed.add_field(
                        name="__Bot Stats:__", 
                        value=f"Servers: `{len(self.client.guilds)}`\nUsers: `{len(self.client.users)}`\nChannels: `{channels}`", 
                        inline=False
                    )

                    if guild.icon:
                        embed.set_thumbnail(url=guild.icon.url)

                    embed.timestamp = discord.utils.utcnow()
                    
                    # Send with invite or fallback message
                    invite_text = str(rope) if rope else "No permanent invite found"
                    await log_channel.send(invite_text, embed=embed)
                    logging.info(f"Successfully logged guild join: {guild.name}")
                    
                except discord.Forbidden:
                    logging.warning(f"No permission to send to join log channel for guild: {guild.name}")
                except Exception as e:
                    logging.error(f"Error sending join log for {guild.name}: {e}")

            # Send welcome message to guild
            await self.send_welcome_message(guild)

        except Exception as e:
            logging.error(f"Error in on_guild_join for {guild.name if guild else 'Unknown'}: {e}")

    @commands.Cog.listener(name="on_guild_remove")
    async def on_guild_remove(self, guild):
        try:
            # Log channel for guild leaves
            leave_log_channel_id = int(os.environ.get('GUILD_LEAVE_LOG_CHANNEL', '1431956636251193436'))
            log_channel = self.client.get_channel(leave_log_channel_id)
            
            if log_channel is None:
                logging.warning(f"Leave log channel with ID {leave_log_channel_id} not found or not accessible.")
                return

            try:
                channels = len(set(self.client.get_all_channels()))
                embed = discord.Embed(title=f"{guild.name}'s Information", color=0xff0000)
            
                embed.set_author(name="Guild Removed")
                embed.set_footer(text=f"Removed from {guild.name}")

                # Guild info
                owner_mention = f"{guild.owner} (<@{guild.owner_id}>)" if guild.owner else "Unknown Owner"
                embed.add_field(
                    name="**__About__**",
                    value=f"**Name:** {guild.name}\n**ID:** {guild.id}\n**Owner <:king:1348340519255937045>:** {owner_mention}\n**Created At:** {guild.created_at.month}/{guild.created_at.day}/{guild.created_at.year}\n**Members:** {len(guild.members)}",
                    inline=False
                )
                
                # Description (handle None)
                description = guild.description if guild.description else "No description available"
                embed.add_field(
                    name="**__Description__**",
                    value=description,
                    inline=False
                )
                
                # Member stats
                humans = len([m for m in guild.members if not m.bot])
                bots = len([m for m in guild.members if m.bot])
                embed.add_field(
                    name="**__Members__**",
                    value=f"Members: {len(guild.members)}\nHumans: {humans}\nBots: {bots}",
                    inline=False
                )
                
                # Channel stats
                embed.add_field(
                    name="**__Channels__**",
                    value=f"Categories: {len(guild.categories)}\nText Channels: {len(guild.text_channels)}\nVoice Channels: {len(guild.voice_channels)}\nThreads: {len(guild.threads)}",
                    inline=False
                )
                
                # Bot stats
                embed.add_field(
                    name="__Bot Stats:__", 
                    value=f"Servers: `{len(self.client.guilds)}`\nUsers: `{len(self.client.users)}`\nChannels: `{channels}`", 
                    inline=False
                )

                if guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)

                embed.timestamp = discord.utils.utcnow()
                await log_channel.send(embed=embed)
                logging.info(f"Successfully logged guild leave: {guild.name}")
                
            except discord.Forbidden:
                logging.warning(f"No permission to send to leave log channel for guild: {guild.name}")
            except Exception as e:
                logging.error(f"Error sending leave log for {guild.name}: {e}")
                
        except Exception as e:
            logging.error(f"Error in on_guild_remove for {guild.name if guild else 'Unknown'}: {e}")

    async def send_welcome_message(self, guild):
        """Send concise welcome message to the guild"""
        try:
            # Chunk guild if needed
            if not guild.chunked:
                await guild.chunk()

            # Create concise welcome embed - SHORTENED TO 4-5 LINES
            embed = discord.Embed(
                title="<a:2659tadapurple:1414557673092943984> Thanks for Adding Scyro!",
                description=(
                    f" <:home3:1418851239315116073> **Welcome to {guild.name}!** Get started with `,help`\n\n"
                    "> <:automod3:1418851397343907900> **Advanced Moderation & Automod**\n> <:security3:1418851249662464022> **Antinuke** \n> <:ticket3:1418851327857000599> **Ticket system**\n"
                    "> <:fun3:1418851340787908638> **Fun games & activities**\n> <:logging3:1418851298106933279> **Server analytics**\n> <:welcomer3:1418851310643707995> **Welcome system**\n> <:list3:1418851206503075920> **Much More to explore...** \n\n"
                    f"> <:timer:1418470621490315356> **Quick Start:** **Antinuke:** `,antinuke` • **Automod:** `,automod`"
                ),
                color=0x9B59B6  # Purple color
            )
            
            # Set author with bot's avatar
            embed.set_author(
                name="Scyro - The Ultimate Discord Bot", 
                icon_url=guild.me.display_avatar.url
            )
            
            # Set footer with custom emoji
            embed.set_footer(
                text="Thanks for adding Me! I'm always ready to assist you.",
                icon_url="https://cdn.discordapp.com/avatars/1387046835322880050/bf2cb3db8bcba669de43a9ef32a2581f.png?size=1024"
            )
            
            # Set guild icon as thumbnail if available
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            
            # Add timestamp
            embed.timestamp = discord.utils.utcnow()

            # Create view with essential buttons only
            view = View(timeout=None)
            
            # Support server button
            support_btn = Button(
                label='Support Server',
                style=discord.ButtonStyle.primary,
                url='https://dsc.gg/scyrogg'
            )
            
            # Website button
            website_btn = Button(
                label='Website',
                style=discord.ButtonStyle.link,
                url='https://scyrobot.qzz.io/'
            )
            
            # Documentation button
            docs_btn = Button(
                label='Documentation',
                style=discord.ButtonStyle.secondary,
                url='https://scyrobot.qzz.io/docs'
            )
            
            # Invite button
            invite_btn = Button(
                label='Invite Scyro',
                style=discord.ButtonStyle.success,
                url='https://discord.com/oauth2/authorize?client_id=1387046835322880050&scope=bot%20applications.commands&permissions=30030655231&redirect_uri=https%3A%2F%2Fdsc.gg%2Fscyrogg'
            )
            
            view.add_item(support_btn)
            view.add_item(website_btn)
            view.add_item(docs_btn)
            view.add_item(invite_btn)

            # Find suitable channel to send welcome message
            target_channel = None
            
            # Priority order for channel selection
            channel_priorities = [
                lambda: discord.utils.get(guild.text_channels, name="general"),
                lambda: discord.utils.get(guild.text_channels, name="chat"),
                lambda: discord.utils.get(guild.text_channels, name="main"),
                lambda: discord.utils.get(guild.text_channels, name="lobby"),
                lambda: guild.system_channel if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages else None,
                lambda: next((channel for channel in guild.text_channels if channel.permissions_for(guild.me).send_messages), None)
            ]
            
            # Try each channel priority
            for get_channel in channel_priorities:
                try:
                    target_channel = get_channel()
                    if target_channel and target_channel.permissions_for(guild.me).send_messages:
                        break
                except:
                    continue
            
            # Send welcome message if we found a suitable channel
            if target_channel:
                try:
                    welcome_msg = await target_channel.send(embed=embed, view=view)
                    logging.info(f"Concise welcome message sent to {guild.name} in #{target_channel.name}")
                        
                except discord.Forbidden:
                    logging.warning(f"No permission to send welcome message in {guild.name} #{target_channel.name}")
                except Exception as e:
                    logging.error(f"Error sending welcome message to {guild.name}: {e}")
            else:
                logging.warning(f"No suitable channel found to send welcome message in guild: {guild.name}")

        except Exception as e:
            logging.error(f"Error in send_welcome_message for {guild.name}: {e}")

# Uncomment to add the cog
# client.add_cog(Guild(client))
