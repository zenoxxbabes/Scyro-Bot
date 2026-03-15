import discord
from discord.ext import commands
from discord import app_commands
import redis
import os
import time
from typing import Optional
from utils.Tools import *
import json

black1 = 0
black2 = 0
black3 = 0

class BasicView(discord.ui.View):
    def __init__(self, ctx: commands.Context, timeout: Optional[int] = None):
        super().__init__(timeout=timeout)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            # Rate limit handling for error responses
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"Only **{self.ctx.author}** can use this command. Use {self.ctx.prefix}**{self.ctx.command}** to run the command",
                        color=self.ctx.author.color
                    ),
                    ephemeral=True
                )
            except discord.HTTPException as e:
                if e.status != 429:  # Ignore rate limits on error responses
                    print(f"Interaction check error: {e}")
            return False
        return True

class SlashBasicView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, timeout: Optional[int] = None):
        super().__init__(timeout=timeout)
        self.interaction = interaction

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            # Rate limit handling for error responses
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"Only **{self.interaction.user}** can use this command.",
                        color=self.interaction.user.color
                    ),
                    ephemeral=True
                )
            except discord.HTTPException as e:
                if e.status != 429:  # Ignore rate limits on error responses
                    print(f"Interaction check error: {e}")
            return False
        return True

class AFKScopeView(BasicView):
    def __init__(self, ctx: commands.Context):
        super().__init__(ctx, timeout=60)
        self.value = None

    @discord.ui.button(label="Global AFK", emoji="🌍", custom_id='global', style=discord.ButtonStyle.primary)
    async def global_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'global'
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Local AFK", emoji="🏠", custom_id='local', style=discord.ButtonStyle.secondary)
    async def local_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'local'
        await interaction.response.defer()
        self.stop()

class SlashAFKScopeView(SlashBasicView):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(interaction, timeout=60)
        self.value = None

    @discord.ui.button(label="Global AFK", emoji="🌍", custom_id='global', style=discord.ButtonStyle.primary)
    async def global_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'global'
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Local AFK", emoji="🏠", custom_id='local', style=discord.ButtonStyle.secondary)
    async def local_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = 'local'
        await interaction.response.defer()
        self.stop()

class afk(commands.Cog):
    def __init__(self, client, *args, **kwargs):
        self.client = client
        # Initialize Redis connection
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            username=os.getenv('REDIS_USERNAME', None),
            password=os.getenv('REDIS_PASSWORD', None),
            decode_responses=True
        )

    async def time_formatter(self, seconds: float):
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        tmp = ((str(days) + " days, ") if days else "") + \
              ((str(hours) + " hours, ") if hours else "") + \
              ((str(minutes) + " minutes, ") if minutes else "") + \
              ((str(seconds) + " seconds, ") if seconds else "")
        return tmp[:-2]

    def get_afk_key(self, user_id):
        return f"afk:{user_id}"

    def get_afk_guilds_key(self, user_id):
        return f"afk_guilds:{user_id}"

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.author.bot:
                return

            # Check if user is AFK
            afk_data_str = self.redis_client.get(self.get_afk_key(message.author.id))
            if afk_data_str:
                afk_data = json.loads(afk_data_str)
                if afk_data.get('AFK') == 'True':
                    scope = afk_data.get('scope', 'local')
                    
                    # Check if user should be unmarked based on scope
                    should_unmark = False
                    if scope == 'global':
                        should_unmark = True
                    else:  # local scope
                        guilds_data = self.redis_client.smembers(self.get_afk_guilds_key(message.author.id))
                        should_unmark = str(message.guild.id) in guilds_data

                    if should_unmark:
                        meth = int(time.time()) - int(afk_data.get('time', 0))
                        been_afk_for = await self.time_formatter(meth)
                        mentionz = afk_data.get('mentions', 0)
                        
                        if scope == 'global':
                            # Remove all AFK data for global AFK
                            self.redis_client.delete(self.get_afk_key(message.author.id))
                            self.redis_client.delete(self.get_afk_guilds_key(message.author.id))
                        else:
                            # For local AFK, remove guild from set and delete user data if no guilds left
                            self.redis_client.srem(self.get_afk_guilds_key(message.author.id), str(message.guild.id))
                            remaining_guilds = self.redis_client.scard(self.get_afk_guilds_key(message.author.id))
                            if remaining_guilds == 0:
                                # No more guilds, remove all AFK data
                                self.redis_client.delete(self.get_afk_key(message.author.id))
                                self.redis_client.delete(self.get_afk_guilds_key(message.author.id))
                            else:
                                # Still has guilds, just update AFK status
                                afk_data['AFK'] = 'False'
                                afk_data['reason'] = 'None'
                                self.redis_client.set(self.get_afk_key(message.author.id), json.dumps(afk_data))
                        
                        wlbat = discord.Embed(
                            title=f'{message.author.display_name} Welcome Back!',
                            description=f'I removed your AFK\nYou got **{mentionz}** mentions while you were AFK\nAFK Duration: **{been_afk_for}**',
                            color=0x2b2d31
                        )
                        # Rate limit handling for message replies
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                await message.reply(embed=wlbat)
                                break
                            except discord.Forbidden:
                                print(f"(AFK module) Missing permissions to send messages in channel: {message.channel.id}")
                                break
                            except discord.HTTPException as e:
                                if e.status == 429:  # Rate limited
                                    retry_after = e.response.headers.get('Retry-After')
                                    if retry_after:
                                        retry_after = float(retry_after)
                                    else:
                                        retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                                    
                                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                                        await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                                        continue
                                    else:
                                        print(f"Rate limit exceeded while sending AFK removal message: {e}")
                                        break
                                else:
                                    if attempt == max_retries - 1:
                                        print(f"Failed to send AFK removal message: {e}")
                                    continue
                            except Exception as e:
                                if attempt == max_retries - 1:
                                    print(f"Unexpected error while sending AFK removal message: {e}")
                                continue

            if message.mentions:
                for user_mention in message.mentions:
                    afk_data_str = self.redis_client.get(self.get_afk_key(user_mention.id))
                    if afk_data_str:
                        afk_data = json.loads(afk_data_str)
                        if afk_data.get('AFK') == 'True':
                            scope = afk_data.get('scope', 'local')
                            should_notify = False
                            
                            if scope == 'global':
                                should_notify = True
                            else:  # local scope
                                guilds_data = self.redis_client.smembers(self.get_afk_guilds_key(user_mention.id))
                                should_notify = str(message.guild.id) in guilds_data

                            if should_notify:
                                reason = afk_data.get('reason', 'I\'m AFK (;')
                                ok = afk_data.get('time', 0)
                                wl = discord.Embed(
                                    description=f'**<@{user_mention.id}>** went AFK <t:{ok}:R> for the following reason:\n**{reason}**',
                                    color=0x2b2d31
                                )
                                # Rate limit handling for AFK notification replies
                                max_retries = 3
                                for attempt in range(max_retries):
                                    try:
                                        await message.reply(embed=wl)
                                        break
                                    except discord.Forbidden:
                                        print(f"(AFK module) Missing permissions to send messages to user: {user_mention.id}")
                                        break
                                    except discord.HTTPException as e:
                                        if e.status == 429:  # Rate limited
                                            retry_after = e.response.headers.get('Retry-After')
                                            if retry_after:
                                                retry_after = float(retry_after)
                                            else:
                                                retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                                            
                                            if attempt < max_retries - 1:  # Don't sleep on last attempt
                                                await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                                                continue
                                            else:
                                                print(f"Rate limit exceeded while sending AFK notification: {e}")
                                                break
                                        else:
                                            if attempt == max_retries - 1:
                                                print(f"Failed to send AFK notification: {e}")
                                            continue
                                    except Exception as e:
                                        if attempt == max_retries - 1:
                                            print(f"Unexpected error while sending AFK notification: {e}")
                                        continue

                                new_mentions = afk_data.get('mentions', 0) + 1
                                afk_data['mentions'] = new_mentions
                                self.redis_client.set(self.get_afk_key(user_mention.id), json.dumps(afk_data))

                                embed = discord.Embed(
                                    description=f'You were mentioned in **{message.guild.name}** by **{message.author}**',
                                    color=discord.Color.from_rgb(black1, black2, black3)
                                )
                                embed.add_field(name="Total mentions:", value=new_mentions, inline=False)
                                embed.add_field(name="Message:", value=message.content, inline=False)
                                embed.add_field(name="Jump Message:", value=f"[Jump to message]({message.jump_url})", inline=False)

                                if afk_data.get('dm') == 'True':
                                    # Rate limit handling for DM sending
                                    max_retries = 3
                                    for attempt in range(max_retries):
                                        try:
                                            await user_mention.send(embed=embed)
                                            break
                                        except discord.Forbidden:
                                            print(f"(AFK module) Missing permissions to send DMs to user: {user_mention.id}")
                                            break
                                        except discord.HTTPException as e:
                                            if e.status == 429:  # Rate limited
                                                retry_after = e.response.headers.get('Retry-After')
                                                if retry_after:
                                                    retry_after = float(retry_after)
                                                else:
                                                    retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                                                
                                                if attempt < max_retries - 1:  # Don't sleep on last attempt
                                                    await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                                                    continue
                                                else:
                                                    print(f"Rate limit exceeded while sending AFK DM: {e}")
                                                    break
                                            else:
                                                if attempt == max_retries - 1:
                                                    print(f"Failed to send AFK DM: {e}")
                                                continue
                                        except Exception as e:
                                            if attempt == max_retries - 1:
                                                print(f"Unexpected error while sending AFK DM: {e}")
                                            continue

        except Exception as e:
            print(f"Ignoring exception in on_message: {e}")

    async def handle_afk_command(self, ctx_or_interaction, reason=None, is_slash=False):
        if not reason:
            reason = "I'm AFK (;"

        if any(invite in reason.lower() for invite in ['discord.gg', 'gg/']):
            emd = discord.Embed(
                description="<a:alert:1396429026842644584> | You can't advertise Server Invite in the AFK reason",
                color=0x2b2d31
            )
            # Rate limit handling for error responses
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if is_slash:
                        return await ctx_or_interaction.followup.send(embed=emd, ephemeral=True)
                    else:
                        return await ctx_or_interaction.send(embed=emd)
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            retry_after = float(retry_after)
                        else:
                            retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                        
                        if attempt < max_retries - 1:  # Don't sleep on last attempt
                            await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                            continue
                        else:
                            print(f"Rate limit exceeded while sending AFK invite error: {e}")
                            return
                    else:
                        if attempt == max_retries - 1:
                            print(f"Failed to send AFK invite error: {e}")
                        continue
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"Unexpected error while sending AFK invite error: {e}")
                    continue

        if is_slash:
            view = SlashAFKScopeView(ctx_or_interaction)
            user = ctx_or_interaction.user
        else:
            view = AFKScopeView(ctx_or_interaction)
            user = ctx_or_interaction.author

        em = discord.Embed(
            description="**Choose AFK Scope:**\n\n🌍 **Global AFK** - You'll be marked AFK across all servers\n🏠 **Local AFK** - You'll be marked AFK only in this server",
            color=0x2b2d31
        )
        try:
            em.set_author(name=str(user), icon_url=user.avatar.url)
        except:
            em.set_author(name=str(user))

        # Rate limit handling for initial AFK setup message
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if is_slash:
                    await ctx_or_interaction.followup.send(embed=em, view=view)
                else:
                    test = await ctx_or_interaction.reply(embed=em, view=view)
                break
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                    else:
                        retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                    
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                        continue
                    else:
                        print(f"Rate limit exceeded while sending AFK setup message: {e}")
                        return
                else:
                    if attempt == max_retries - 1:
                        print(f"Failed to send AFK setup message: {e}")
                    continue
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Unexpected error while sending AFK setup message: {e}")
                continue

        await view.wait()

        if not view.value:
            timeout_msg = "Timed out, please try again."
            # Rate limit handling for timeout responses
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if is_slash:
                        return await ctx_or_interaction.edit_original_response(content=timeout_msg, embed=None, view=None)
                    else:
                        return await test.edit(content=timeout_msg, embed=None, view=None)
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            retry_after = float(retry_after)
                        else:
                            retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                        
                        if attempt < max_retries - 1:  # Don't sleep on last attempt
                            await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                            continue
                        else:
                            print(f"Rate limit exceeded while sending AFK timeout message: {e}")
                            return
                    else:
                        if attempt == max_retries - 1:
                            print(f"Failed to send AFK timeout message: {e}")
                        continue
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"Unexpected error while sending AFK timeout message: {e}")
                    continue

        scope = view.value
        dm_status = 'True'  # Default to True for DM notifications

        # Create AFK data
        afk_data = {
            'AFK': 'True',
            'reason': reason,
            'time': int(time.time()),
            'mentions': 0,
            'dm': dm_status,
            'scope': scope
        }
        
        # Store AFK data in Redis
        self.redis_client.set(self.get_afk_key(user.id), json.dumps(afk_data))
        
        # Add guild to the set
        self.redis_client.sadd(self.get_afk_guilds_key(user.id), str(ctx_or_interaction.guild.id))

        scope_text = "globally" if scope == 'global' else "in this server"
        af = discord.Embed(
            title='<:yes:1396838746862784582> Success', 
            description=f'{user.mention}, You are now marked as AFK {scope_text} due to: **{reason}**', 
            color=0x2b2d31
        )
        
        # Rate limit handling for final AFK confirmation
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if is_slash:
                    await ctx_or_interaction.edit_original_response(embed=af, view=None)
                else:
                    await test.delete()
                    await ctx_or_interaction.reply(embed=af)
                break
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                    else:
                        retry_after = 1 << attempt  # Exponential backoff: 1s, 2s, 4s
                    
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        await asyncio.sleep(min(retry_after, 10))  # Cap at 10s
                        continue
                    else:
                        print(f"Rate limit exceeded while sending AFK confirmation: {e}")
                        break
                else:
                    if attempt == max_retries - 1:
                        print(f"Failed to send AFK confirmation: {e}")
                    continue
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Unexpected error while sending AFK confirmation: {e}")
                continue

    @commands.command(name="afk", help="Set your AFK status")
    @blacklist_check()
    @ignore_check()
    @commands.guild_only()
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def afk_prefix(self, ctx, *, reason=None):
        await self.handle_afk_command(ctx, reason, is_slash=False)

    @app_commands.command(name="afk", description="Set your AFK status")
    @app_commands.describe(reason="The reason for being AFK")
    @app_commands.guild_only()
    async def afk_slash(self, interaction: discord.Interaction, reason: str = None):
        await interaction.response.defer()
        await self.handle_afk_command(interaction, reason, is_slash=True)


async def setup(client):
    await client.add_cog(afk(client))