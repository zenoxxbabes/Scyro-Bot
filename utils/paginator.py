from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional
import discord
from discord.ext import commands
from discord import Interaction, ButtonStyle


class Paginator(discord.ui.View):
    def __init__(self, ctx: commands.Context | Interaction, pages_list: list[discord.Embed]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.pages = pages_list
        self.current_page = 0
        self.message: Optional[discord.Message] = None
        # Track interaction to prevent editing expired interactions
        self._last_interaction: Optional[discord.Interaction] = None

        self.clear_items()
        self.fill_items()

    def fill_items(self) -> None:
        """Adds navigation buttons dynamically based on the number of pages."""
        if len(self.pages) > 1:
            self.add_item(self.first_page_button)
            self.add_item(self.previous_page_button)
            self.add_item(self.stop_button)
            self.add_item(self.next_page_button)
            self.add_item(self.last_page_button)

    async def update_page(self, interaction: discord.Interaction) -> None:
        """Updates the embed to the current page with rate-limit handling."""
        # Store interaction to track the latest one
        self._last_interaction = interaction
        
        embed = self.pages[self.current_page]
        self.first_page_button.disabled = self.current_page == 0
        self.previous_page_button.disabled = self.current_page == 0
        self.next_page_button.disabled = self.current_page == len(self.pages) - 1
        self.last_page_button.disabled = self.current_page == len(self.pages) - 1

        # Rate limit handling with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if interaction.response.is_done():
                    await self.message.edit(embed=embed, view=self)
                else:
                    await interaction.response.edit_message(embed=embed, view=self)
                break  # Success, exit retry loop
            except discord.NotFound:
                # Message was deleted, stop pagination
                self.stop()
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
                        raise  # Re-raise if all retries exhausted
                else:
                    raise  # Re-raise non-rate-limit errors
            except Exception:
                if attempt == max_retries - 1:  # Last attempt
                    raise
                await asyncio.sleep(1 << attempt)  # Exponential backoff

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensures only the command invoker can interact with the pagination."""
        if isinstance(self.ctx, Interaction):
            if interaction.user and interaction.user.id == self.ctx.user.id:
                return True
        elif interaction.user and interaction.user.id == self.ctx.author.id:
            return True

        # Rate limit handling for error responses
        try:
            await interaction.response.send_message("You cannot control this paginator!", ephemeral=True)
        except discord.HTTPException as e:
            if e.status != 429:  # Ignore rate limits on error responses
                raise
        return False

    async def on_timeout(self) -> None:
        """Disables buttons when the pagination times out."""
        if self.message:
            # Disable all buttons
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            
            # Rate limit handling for timeout edits
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.message.edit(view=self)
                    break
                except discord.NotFound:
                    # Message was deleted
                    break
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            retry_after = float(retry_after)
                        else:
                            retry_after = 1 << attempt
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(min(retry_after, 10))
                            continue
                        else:
                            break
                    else:
                        if attempt == max_retries - 1:
                            break
                        await asyncio.sleep(1 << attempt)
                except Exception:
                    if attempt == max_retries - 1:
                        break
                    await asyncio.sleep(1 << attempt)

    async def paginate(self, content: Optional[str] = None, ephemeral: bool = False) -> None:
        """Sends the paginator message and initializes the pagination session."""
        embed = self.pages[0]
        self.first_page_button.disabled = True
        self.previous_page_button.disabled = True
        if len(self.pages) == 1:
            self.next_page_button.disabled = True
            self.last_page_button.disabled = True

        # Rate limit handling for initial message sending
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if isinstance(self.ctx, Interaction):
                    self.message = await self.ctx.response.send_message(embed=embed, view=self, ephemeral=ephemeral)
                else:
                    self.message = await self.ctx.send(embed=embed, view=self, ephemeral=ephemeral)
                break
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                    else:
                        retry_after = 1 << attempt
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(retry_after, 10))
                        continue
                    else:
                        raise
                else:
                    raise
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 << attempt)

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:leftole:1430431612411314176>"),
        style=ButtonStyle.secondary
    )
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigates to the first page with rate-limit handling."""
        # Defer response immediately to prevent timeouts
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass  # Ignore if already responded
        
        self.current_page = 0
        await self.update_page(interaction)

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:leftsy:1430425364600983644>"),
        style=ButtonStyle.secondary
    )
    async def previous_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Goes back one page with rate-limit handling."""
        # Defer response immediately to prevent timeouts
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass  # Ignore if already responded
        
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_page(interaction)

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:deletesy:1430425309228040343>"),
        style=ButtonStyle.danger
    )
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stops the pagination session and deletes the message with rate-limit handling."""
        # Defer response immediately to prevent timeouts
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass  # Ignore if already responded
        
        # Rate limit handling for message deletion
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.message.delete()
                break
            except discord.NotFound:
                # Message already deleted
                break
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = e.response.headers.get('Retry-After')
                    if retry_after:
                        retry_after = float(retry_after)
                    else:
                        retry_after = 1 << attempt
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(retry_after, 10))
                        continue
                    else:
                        break
                else:
                    if attempt == max_retries - 1:
                        break
                    await asyncio.sleep(1 << attempt)
            except Exception:
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(1 << attempt)
        
        self.stop()

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:rightsy:1430425376135319683>"),
        style=ButtonStyle.secondary
    )
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Goes forward one page with rate-limit handling."""
        # Defer response immediately to prevent timeouts
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass  # Ignore if already responded
        
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_page(interaction)

    @discord.ui.button(
        emoji=discord.PartialEmoji.from_str("<:rightole:1430425351556694047>"),
        style=ButtonStyle.secondary
    )
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Goes to the last page with rate-limit handling."""
        # Defer response immediately to prevent timeouts
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass  # Ignore if already responded
        
        self.current_page = len(self.pages) - 1
        await self.update_page(interaction)
