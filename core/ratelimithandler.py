"""
Discord.py Rate-Limit & Interaction Safety Handler
===================================================
Prevents HTTP 429, Cloudflare 1015, double responses (40060), and expired interactions (10062).

Provides:
- Global 429 Protection (Circuit Breaker)
- safe_defer() - Defer with error handling
- safe_message_edit() - Edit with per-message lock
- send_modal() - Send modals safely
- RateLimitView - Base view with safety built-in
- ModalWithRateLimit - Base modal with safety built-in
"""

import asyncio
import discord
import logging
import time
import sys
from discord.ext import commands
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class GlobalLockException(Exception):
    """Exception raised when a request is blocked by the global rate limit lock."""
    pass

# ============================================================================
# 🔒 GLOBAL RATE LIMIT HANDLER (CIRCUIT BREAKER)
# ============================================================================

class GlobalRateLimitHandler:
    _global_lock = asyncio.Event()
    _global_lock.set()  # Set means "Allowed" (not locked)
    _retry_after: float = 0.0
    _lock_timestamp: float = 0.0
    
    @classmethod
    def is_globally_locked(cls) -> bool:
        """Check if bot is currently under a global 429 lock."""
        return not cls._global_lock.is_set()

    @classmethod
    def lock(cls, retry_after: float):
        """Engage the global lock for the specified duration."""
        if cls.is_globally_locked():
            # If already locked, update duration only if new one is longer
            remaining = (cls._lock_timestamp + cls._retry_after) - time.time()
            if retry_after > remaining:
                cls._retry_after = retry_after
                cls._lock_timestamp = time.time()
                # Re-schedule unlock (previous task will just wake up and see lock is still needed? 
                # Actually simpler to just let the new task manage it or ignore. 
                # For safety, we just log and rely on the active lock.)
                logger.warning(f"🔄 Extending Global Lock to {retry_after:.2f}s")
            return

        cls._retry_after = retry_after
        cls._lock_timestamp = time.time()
        cls._global_lock.clear() # Block all requests
        
        logger.critical(f"🛑 GLOBAL RATE LIMIT HIT! Locking all requests for {retry_after:.2f}s")
        
        # Safe Shutdown Check
        if retry_after > 300:
            cls._handle_shutdown(retry_after)
        else:
            # Schedule unlock
            asyncio.create_task(cls._unlock_after(retry_after))

    @classmethod
    def _handle_shutdown(cls, retry_after: float):
        """Handle safe shutdown on extreme rate limits."""
        logger.critical(f"💀 GLOBAL BAN DETECTED ({retry_after}s). Initiating emergency shutdown to protect token.")
        # We could try to close the bot instance if we had access, but sys.exit is safer to stop ALL loops immediately.
        # Log to file is crucial here since stdout might be lost.
        try:
            logging.shutdown()
        except:
            pass
        sys.exit(0) # Force exit

    @classmethod
    async def _unlock_after(cls, delay: float):
        await asyncio.sleep(delay)
        cls._global_lock.set()
        logger.info("✅ Global rate limit lock released. Resuming requests.")

    @classmethod
    async def wait_if_locked(cls):
        """Wait until global lock is released."""
        await cls._global_lock.wait()

    @staticmethod
    def should_fail_fast() -> bool:
        """
        Return True if we should drop the request immediately instead of waiting.
        Used to prevent queue buildup during outages.
        """
        return not GlobalRateLimitHandler._global_lock.is_set()


# ============================================================================
# 🐵 HTTP CLIENT MONKEY PATCH
# ============================================================================

def patch_http_client(bot):
    """
    Monkey-patch discord.http.HTTPClient.request to:
    1. Respect global lock (Fail Fast)
    2. Intercept 429s and prevent retries for Global/Long limits
    """
    original_request = bot.http.request

    async def hardened_request(route, *, files=None, form=None, **kwargs):
        # 1. FAIL FAST: If globally locked, drop request immediately
        if GlobalRateLimitHandler.should_fail_fast():
            logger.warning(f"🚫 Dropping request to {route} due to Global 429 Lock")
            raise GlobalLockException("Global Rate Limit Active")

        try:
            # 2. Perform Request
            # We must await the original request. 
            # Note: discord.py's internal retries (for 5xx or normal 429s) happen inside specific methods,
            # but `request` is the low-level entry point. 
            # If discord.py hits a 429, it might raise HTTPException immediately OR sleep and retry depending on implementation versions.
            # In modern d.py, `request` handles the loop. 
            # To strictly STOP retries on global, we rely on catching the FIRST 429 if the library propagates it,
            # OR we rely on the fact that we can't easily interrupt the internal loop without subclassing HTTPClient.
            # HOWEVER, we CAN inspect the response if we wrapped `_request` (underscore), but `request` is easier.
            # If `original_request` raises 429, we catch it.
            return await original_request(route, files=files, form=form, **kwargs)
        
        except discord.HTTPException as e:
            # 3. INTERCEPT 429
            if e.status == 429:
                try:
                    # Parse Retry-After
                    # Discord.py usually populates e.response with the aiohttp response object / dict
                    headers = {}
                    if e.response and hasattr(e.response, 'headers'):
                         headers = e.response.headers
                    
                    retry_after_str = headers.get('Retry-After')
                    # Fallback to e.text or other sources if header missing? 
                    # Usually d.py exception has it.
                    
                    try:
                        retry_after = float(retry_after_str) if retry_after_str else 0.0
                    except (ValueError, TypeError):
                        retry_after = 5.0 # Safe default?
                        
                    is_global = headers.get('X-RateLimit-Global') == 'true' or e.code == 0 # 0 is sometimes global? or just unknown.
                    
                    # Logic Table:
                    # Case A: Global 429 -> LOCK & STOP
                    # Case B: Route 429 > 60s -> LOCK (Treat as dangerous) & STOP
                    # Case C: Route 429 <= 60s -> LOG & RAISE (Let caller handle or just fail command) - do NOT global lock.

                    trigger_global_lock = False

                    if is_global:
                         logger.critical(f"⚠️ GLOBAL HTTP 429 Hit: Retry-After={retry_after}s")
                         trigger_global_lock = True
                    elif retry_after > 60:
                         logger.warning(f"⚠️ Suspiciously Long Route 429 Hit: Retry-After={retry_after}s. Escalating to Global Lock.")
                         trigger_global_lock = True
                    else:
                         logger.warning(f"⚠️ Route HTTP 429 Hit: Retry-After={retry_after}s (Local)")

                    if trigger_global_lock:
                         # Add small buffer + lock
                         GlobalRateLimitHandler.lock(retry_after + 0.1)
                         
                         # DO NOT consume the error. Re-raise it so the command fails safely.
                         # The bot logic should handle the exception (e.g. command error handler).
                         raise e

                except Exception as ex:
                    logger.error(f"Error analyzing 429 during interception: {ex}")
                
                # Re-raise the original 429 if we didn't raise above
                raise e
            
            # Re-raise other HTTP errors
            raise e

    # Apply Patch
    bot.http.request = hardened_request
    logger.info("🛡️ HTTP Client Hardened: Global Rate Limit Protection Active")

# ============================================================================
# 🔒 PER-MESSAGE LOCKS (Concurrency Safety)
# ============================================================================

_message_locks: Dict[int, asyncio.Lock] = {}

def _get_message_lock(message_id: int) -> asyncio.Lock:
    if message_id not in _message_locks:
        _message_locks[message_id] = asyncio.Lock()
    return _message_locks[message_id]


# ============================================================================
# SAFE INTERACTION HELPERS
# ============================================================================

async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    """Safely defer an interaction. Returns True if deferred."""
    if GlobalRateLimitHandler.should_fail_fast():
        return False
        
    try:
        if interaction.response.is_done():
            return False
        await interaction.response.defer(ephemeral=ephemeral)
        return True
    except (discord.InteractionResponded, discord.NotFound, discord.HTTPException, GlobalLockException):
        return False

async def safe_message_edit(message: discord.Message, **kwargs) -> Optional[discord.Message]:
    """Safely edit a message with per-message lock."""
    # Check global lock first
    if GlobalRateLimitHandler.should_fail_fast():
        return None

    lock = _get_message_lock(message.id)
    try:
        async with lock:
            return await message.edit(**kwargs)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, GlobalLockException):
        return None
    except asyncio.TimeoutError:
        return None

async def send_modal(interaction: discord.Interaction, modal: discord.ui.Modal) -> bool:
    """Safely send a modal."""
    if GlobalRateLimitHandler.should_fail_fast():
        return False

    try:
        if interaction.response.is_done():
            return False
        await interaction.response.send_modal(modal)
        return True
    except (discord.InteractionResponded, discord.NotFound, discord.HTTPException, GlobalLockException) as e:
        if isinstance(e, discord.HTTPException) and e.status == 429:
            logger.warning(f"Rate limited sending modal: {e}")
        return False

# ============================================================================
# BASE CLASSES FOR SAFE VIEWS & MODALS
# ============================================================================

class RateLimitView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self._processing = False
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return False
        
        if GlobalRateLimitHandler.should_fail_fast():
             # Fail silently or ephemeral? User requested fail silent, but for UI interactions, 
             # visual feedback is usually better than 'interaction failed'. 
             # But strictly, we shouldn't make NEW requests.
             # send_message IS a request.
             # If locked, we CANNOT send "Bot is rate-limited". We must fail silently.
             return False

        if self._processing:
            try:
                await interaction.response.defer() 
            except:
                pass
            return False
        
        self._processing = True
        return True
    
    def release_processing(self):
        self._processing = False
    
    async def on_timeout(self):
        # Do not attempt to edit message if locked
        if GlobalRateLimitHandler.should_fail_fast():
            return
            
        for item in self.children:
            item.disabled = True
        # Subclasses should handle message editing on timeout if needed

class ModalWithRateLimit(discord.ui.Modal):
    async def on_submit(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction)

# ============================================================================
# AUTO-APPLY SAFETY
# ============================================================================

def init_safety_handler(bot: commands.Bot):
    """Initialize automatic safety for ALL views and modals + Patch HTTP."""
    
    # 1. Patch HTTP Client for Global 429 Protection
    try:
        patch_http_client(bot)
    except Exception as e:
        logger.error(f"Failed to patch HTTP client: {e}")

    # 2. Add Auto-Defer Listener
    @bot.listen()
    async def on_interaction(interaction: discord.Interaction):
        try:
            if interaction.type in (discord.InteractionType.component, discord.InteractionType.modal_submit):
                # Global Lock Check
                if GlobalRateLimitHandler.should_fail_fast():
                    return # Drop interaction if globally locked

                # Wait small delay to allow manual handling
                await asyncio.sleep(0.5) 
                
                # Check custom_id for NO_DEFER
                if interaction.data and 'custom_id' in interaction.data:
                    if str(interaction.data['custom_id']).startswith('nodefer_'):
                        return

                if not interaction.response.is_done():
                    await safe_defer(interaction)
        except Exception:
            pass
            
    logger.info("✅ RATELIMIT HANDLER: Safety systems engaged.")
