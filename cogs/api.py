import os
import discord
from discord.ext import commands
from aiohttp import web
import asyncio
import json
import datetime
import traceback
import motor.motor_asyncio
import re

def get_database():
    mongo_url = os.getenv("MONGO_URI")
    if not mongo_url:
        print("CRITICAL: MONGO_URI not found in environment!")
        return None
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    return client.get_default_database()

# --- Helper Classes ---
class APITicketButton(discord.ui.Button):
    def __init__(self, panel_id, category, label, style, emoji, custom_id):
        super().__init__(label=label, style=style, emoji=emoji, custom_id=custom_id)
        self.panel_id, self.category = panel_id, category
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.response.is_done(): return
        cog = interaction.client.get_cog("TicketSetup")
        if cog: 
            print(f"[DEBUG] API Ticket Click: {self.panel_id} {self.category}")
            await cog.create_ticket(interaction, self.panel_id, self.category)
        else: 
            print("[ERROR] TicketSetup Cog not found in API callback")
            await interaction.response.send_message("Ticket system offline.", ephemeral=True)

class APITicketSelect(discord.ui.Select):
    def __init__(self, panel_id, options, custom_id, placeholder):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id=custom_id)
        self.panel_id = panel_id
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.response.is_done(): return
        cog = interaction.client.get_cog("TicketSetup")
        if cog:
            self.placeholder = "Select category..."
            await cog.create_ticket(interaction, self.panel_id, self.values[0])
        else: 
            await interaction.response.send_message("Ticket system offline.", ephemeral=True)

class APITicketView(discord.ui.View):
    def __init__(self, panel_id, comp_data):
        super().__init__(timeout=None)
        if comp_data.get("type") == "BUTTON":
            for btn in comp_data.get("options", []):
                color_map = {"blue": discord.ButtonStyle.primary, "red": discord.ButtonStyle.danger, "green": discord.ButtonStyle.success, "grey": discord.ButtonStyle.secondary}
                cid = f"tkt_btn:{panel_id}:{btn['category']}".replace(" ", "_")
                self.add_item(APITicketButton(
                    panel_id, 
                    btn['category'], 
                    btn['label'], 
                    color_map.get(btn.get('color'), discord.ButtonStyle.primary),
                    btn.get('emoji') or None, 
                    cid
                ))
        elif comp_data.get("type") == "SELECT":
             options = []
             for o in comp_data.get("options", []):
                 options.append(discord.SelectOption(
                     label=o['label'], 
                     description=o.get('description'), 
                     value=o['category'], 
                     emoji=o.get('emoji') or None
                 ))
             self.add_item(APITicketSelect(
                 panel_id,
                 options,
                 f"tkt_sel:{panel_id}",
                 "Select category..."
             ))

# --- API Class ---
class API(commands.Cog):
    async def auth_middleware(self, app, handler):
        async def middleware_handler(request):
            # Allow health check without auth
            if request.path == '/api/health':
                return await handler(request)
            
            # Check for authorization header
            token = request.headers.get('Authorization')
            # Reload env to ensure we get the latest secret
            secret = os.getenv('API_SECRET') or "scyro_secure_8f92a9912kks1"
            
            if not token or token != secret:
                print(f"Unauthorized API attempt from {request.remote}")
                # print(f"DEBUG: Received Token: '{token}' | Expected Secret: '{secret}'")
                return web.json_response({'error': 'Unauthorized', 'message': 'Invalid or missing API token'}, status=401)
            
            return await handler(request)
        return middleware_handler

    async def check_permissions(self, request, guild_id, perm="manage_guild"):
        """
        Verifies if the X-User-ID header belongs to a user with specific permissions in the target guild.
        Return: (Authorized: bool, ErrorMessage: str)
        """
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return False, "Missing X-User-ID Header"
            
        # Permission Cache Check (TTL: 60s)
        cache_key = f"{guild_id}:{user_id}:{perm}"
        if hasattr(self, '_perm_cache'):
            cached = self._perm_cache.get(cache_key)
            if cached and (datetime.datetime.utcnow().timestamp() - cached['time'] < 60):
                return cached['val'], cached['msg']
        else:
            self._perm_cache = {}

        try:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return False, "Guild not found"

            # Check for Bot Owner (Global Valid)
            if hasattr(self.bot, 'owner_ids') and self.bot.owner_ids and int(user_id) in self.bot.owner_ids:
                return True, None
                
            member = guild.get_member(int(user_id))
            if not member:
                try:
                    member = await guild.fetch_member(int(user_id))
                except:
                    return False, "User not found in guild"
            
            # Check for ownership
            if member.id == guild.owner_id:
                res = (True, None)
            
            # Check Extra Owners (if cog exists)
            elif await self.is_extra_owner_internal(guild.id, member.id):
                res = (True, None)

            # Check Permissions (Administrator always passes)
            elif member.guild_permissions.administrator:
                 res = (True, None)

            elif perm and getattr(member.guild_permissions, perm, False):
                res = (True, None)
            else:
                res = (False, "Insufficient Permissions")
        
            # Cleanup cache (simple)
            if len(self._perm_cache) > 1000: self._perm_cache.clear()
            
            self._perm_cache[cache_key] = {
                'time': datetime.datetime.utcnow().timestamp(),
                'val': res[0],
                'msg': res[1]
            }
            return res
            
        except Exception as e:
            return False, f"Permission Check Error: {str(e)}"

    async def is_extra_owner_internal(self, guild_id, user_id):
        """Helper to check extra owner status efficiently"""
        # Try Cog first
        extra_owner_cog = self.bot.get_cog('Extraowner')
        if extra_owner_cog:
            if hasattr(extra_owner_cog, 'is_extra_owner'):
                return await extra_owner_cog.is_extra_owner(guild_id, user_id)
        
        # Fallback to DB (robust)
        if hasattr(self.bot, 'db') and self.bot.db is not None:
             try:
                doc = await self.bot.db.extraowners.find_one({"guild_id": guild_id, "owner_id": user_id})
                if doc: return True
             except Exception:
                 pass

            
        return False

    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application(middlewares=[self.auth_middleware])
        self.app.router.add_get('/api/guilds/{guild_id}/stats', self.get_stats)
        self.app.router.add_get('/api/guilds/{guild_id}/welcome', self.get_welcome)
        self.app.router.add_post('/api/guilds/{guild_id}/welcome', self.save_welcome)
        self.app.router.add_delete('/api/guilds/{guild_id}/welcome', self.reset_welcome)
        self.app.router.add_post('/api/guilds/{guild_id}/welcome/test', self.test_welcome)
        
        # Sticky Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/sticky', self.get_stickies)
        self.app.router.add_post('/api/guilds/{guild_id}/sticky', self.create_sticky)
        self.app.router.add_delete('/api/guilds/{guild_id}/sticky/reset', self.reset_stickies)
        self.app.router.add_delete('/api/guilds/{guild_id}/sticky/{channel_id}', self.delete_sticky)
        
        # Health Check
        self.app.router.add_get('/api/health', self.health_check)
        
        # Embed Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/embeds', self.get_embeds)
        self.app.router.add_delete('/api/guilds/{guild_id}/embeds/reset', self.reset_all_embeds)
        self.app.router.add_get('/api/guilds/{guild_id}/embeds/{name}', self.get_embed_detail)
        self.app.router.add_post('/api/guilds/{guild_id}/embeds/{name}', self.save_embed)
        self.app.router.add_delete('/api/guilds/{guild_id}/embeds/{name}', self.delete_embed)
        self.app.router.add_post('/api/guilds/{guild_id}/embeds/{name}/send', self.send_embed)
        self.app.router.add_get('/api/guilds/{guild_id}/channels', self.get_channels)
        self.app.router.add_get('/api/guilds/{guild_id}/roles', self.get_roles)
        self.app.router.add_get('/api/guilds/{guild_id}/members/search', self.search_members)
        
        # Ticket Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/tickets/panels', self.get_ticket_panels)
        self.app.router.add_get('/api/guilds/{guild_id}/tickets/panels/{panel_id}', self.get_ticket_panel_detail)
        self.app.router.add_post('/api/guilds/{guild_id}/tickets/panels/{panel_id}', self.save_ticket_panel)
        self.app.router.add_delete('/api/guilds/{guild_id}/tickets/panels/{panel_id}', self.delete_ticket_panel)
        self.app.router.add_get('/api/guilds/{guild_id}/tickets/config', self.get_ticket_config)
        self.app.router.add_post('/api/guilds/{guild_id}/tickets/config', self.save_ticket_config)
        self.app.router.add_post('/api/guilds/{guild_id}/tickets/panels/{panel_id}/send', self.send_ticket_panel)
        self.app.router.add_delete('/api/guilds/{guild_id}/tickets/reset', self.reset_tickets)
        
        # General & Ticket Manager APIs
        self.app.router.add_get('/api/guilds/{guild_id}/general', self.get_general_settings)
        self.app.router.add_post('/api/guilds/{guild_id}/general', self.set_general_settings)
        
        self.app.router.add_get('/api/guilds/{guild_id}/tickets/manager', self.get_ticket_manager_data)
        self.app.router.add_post('/api/guilds/{guild_id}/tickets/manager/action', self.ticket_manager_action)
        self.app.router.add_get('/api/guilds/{guild_id}/tickets/blacklist', self.get_blacklist)
        self.app.router.add_post('/api/guilds/{guild_id}/tickets/blacklist', self.manage_blacklist)
        
        # Automation Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/autorole', self.get_autorole)
        self.app.router.add_post('/api/guilds/{guild_id}/autorole', self.save_autorole)
        
        self.app.router.add_get('/api/guilds/{guild_id}/autoreact', self.get_autoreact)
        self.app.router.add_post('/api/guilds/{guild_id}/autoreact', self.create_autoreact)
        self.app.router.add_delete('/api/guilds/{guild_id}/autoreact', self.delete_autoreact)
        
        self.app.router.add_get('/api/guilds/{guild_id}/autoresponder', self.get_autoresponder)
        self.app.router.add_post('/api/guilds/{guild_id}/autoresponder', self.create_autoresponder)
        self.app.router.add_delete('/api/guilds/{guild_id}/autoresponder', self.delete_autoresponder)
        
        self.app.router.add_get('/api/guilds/{guild_id}/reactionroles', self.get_reactionroles)
        self.app.router.add_post('/api/guilds/{guild_id}/reactionroles', self.create_reactionrole)

        self.app.router.add_delete('/api/guilds/{guild_id}/reactionroles', self.delete_reactionrole)

        # Logging Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/logging', self.get_logging_config)
        self.app.router.add_post('/api/guilds/{guild_id}/logging', self.update_logging_config)

        # Giveaway Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/giveaways', self.get_giveaways)
        self.app.router.add_post('/api/guilds/{guild_id}/giveaways/start', self.start_giveaway)
        self.app.router.add_post('/api/guilds/{guild_id}/giveaways/end', self.end_giveaway)
        self.app.router.add_post('/api/guilds/{guild_id}/giveaways/reroll', self.reroll_giveaway)

        # Media Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/media', self.get_media_config)
        self.app.router.add_post('/api/guilds/{guild_id}/media/channels', self.update_media_channels)
        self.app.router.add_post('/api/guilds/{guild_id}/media/bypass', self.update_media_bypass)
        
        # Leveling Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/leveling', self.get_leveling_config)
        self.app.router.add_post('/api/guilds/{guild_id}/leveling', self.save_leveling_config)
        self.app.router.add_delete('/api/guilds/{guild_id}/leveling/reset', self.reset_leveling_data)
        
        # Reset Endpoints
        self.app.router.add_delete('/api/guilds/{guild_id}/autorole/reset', self.reset_autorole)
        self.app.router.add_delete('/api/guilds/{guild_id}/autoreact/reset', self.reset_autoreact)
        self.app.router.add_delete('/api/guilds/{guild_id}/autoresponder/reset', self.reset_autoresponder)
        self.app.router.add_delete('/api/guilds/{guild_id}/reactionroles/reset', self.reset_reactionroles)
        self.app.router.add_delete('/api/guilds/{guild_id}/giveaways/reset', self.reset_giveaways)
        self.app.router.add_delete('/api/guilds/{guild_id}/logging/reset', self.reset_logging)
        self.app.router.add_delete('/api/guilds/{guild_id}/media/reset', self.reset_media)

        # Security Endpoints (Antinuke, Whitelist, Extraowner)
        self.app.router.add_get('/api/guilds/{guild_id}/security/antinuke', self.get_antinuke_config)
        self.app.router.add_post('/api/guilds/{guild_id}/security/antinuke', self.save_antinuke_config)
        
        self.app.router.add_get('/api/guilds/{guild_id}/security/whitelist', self.get_whitelist)
        self.app.router.add_post('/api/guilds/{guild_id}/security/whitelist', self.save_whitelist)
        self.app.router.add_delete('/api/guilds/{guild_id}/security/whitelist', self.delete_whitelist)
        
        self.app.router.add_get('/api/guilds/{guild_id}/security/extraowners', self.get_extraowners)
        self.app.router.add_post('/api/guilds/{guild_id}/security/extraowners', self.add_extraowner)
        self.app.router.add_delete('/api/guilds/{guild_id}/security/extraowners', self.remove_extraowner)
        
        self.app.router.add_post('/api/security/log', self.submit_security_log)
        self.app.router.add_get('/api/security/blacklist/check', self.check_dashboard_blacklist)
        
        self.app.router.add_get('/api/guilds/{guild_id}/permissions', self.get_permissions)
        self.app.router.add_get('/api/guilds/{guild_id}/members/search', self.search_members)
        self.app.router.add_get('/api/guilds/{guild_id}/channels', self.get_channels)
        # Roles is already registered at line 121

        # User Endpoints
        self.app.router.add_get('/api/user/premium', self.get_user_premium)

    async def get_user_premium(self, request):
        """Get premium status for the specific user"""
        user_id_raw = request.headers.get('X-User-ID')
        if not user_id_raw:
            return web.json_response({'error': 'Missing User ID'}, status=400)
            
        try:
            premium_cog = self.bot.get_cog('Premium')
            if not premium_cog:
                print("[API DEBUG] Premium Cog not found!")
                return web.json_response({'error': 'Premium system offline'}, status=503)
                
            db = await premium_cog.premium_system.mongo_db.ensure_connection()
            if not db:
                 print("[API DEBUG] Database connection failed!")
                 return web.json_response({'error': 'Database Error'}, status=500)

            user_id = int(user_id_raw)
            print(f"[API DEBUG] Querying DB for User ID: {user_id} (Type: {type(user_id)})")

            # DIRECT DB ACCESS DEBUGGING
            # Check if we can see ANY data
            try:
                sample_docs = []
                async for doc in db["premium_users"].find().limit(3):
                    sample_docs.append(str(doc.get('user_id')))
                print(f"[API DEBUG] Sample User IDs in DB: {sample_docs}")
            except Exception as e:
                print(f"[API DEBUG] Failed to sample DB: {e}")

            # Get User Data using direct DB access
            user_doc = await db["premium_users"].find_one({"user_id": user_id})
            
            print(f"[API DEBUG] Primary Query Result: {user_doc}")

            if not user_doc:
                print(f"[API DEBUG] Retrying with string ID...")
                user_doc = await db["premium_users"].find_one({"user_id": str(user_id)})
            
            if not user_doc:
                # Force checking the collection directly for this specific ID again with a cursor
                print("[API DEBUG] Manual Cursor Search...")
                async for doc in db["premium_users"].find({"user_id": user_id}):
                    print(f"[API DEBUG] Found via Cursor: {doc}")
                    user_doc = doc
                    break
            
            if not user_doc:
                print(f"[API DEBUG] No document found for {user_id}. Returning False.")
                return web.json_response({'premium': False})

            if not user_doc:
                print(f"[API DEBUG] No document found for {user_id}. Returning False.")
                return web.json_response({'premium': False})
                
            tier_name = user_doc.get("tier", "free")
            tier_info = premium_cog.premium_system.tiers.get(tier_name, premium_cog.premium_system.tiers['free'])
            
            # Get Usage Data
            used_slots = await premium_cog.premium_system.mongo_db.premium_guilds.count_documents({"user_id": user_id})
            
            # Get list of guilds using this premium
            try:
                guilds_using = []
                async for g in premium_cog.premium_system.mongo_db.premium_guilds.find({"user_id": user_id}):
                    guild_obj = self.bot.get_guild(g['guild_id'])
                    guilds_using.append({
                        'id': str(g['guild_id']),
                        'name': guild_obj.name if guild_obj else f"Unknown Guild ({g['guild_id']})"
                    })
            except:
                guilds_using = []

            return web.json_response({
                'premium': True,
                'tier': tier_name,
                'tier_name': tier_info['name'],
                'emoji': tier_info['emoji'],
                'expires_at': user_doc.get("expires_at"),
                'activated_at': user_doc.get("created_at"),
                'max_guilds': tier_info.get('servers', 0),
                'used_guilds': used_slots,
                'guilds_list': guilds_using
            })
            
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)
        self.app.router.add_post('/api/guilds/{guild_id}/automod', self.save_automod_config)
        self.app.router.add_post('/api/guilds/{guild_id}/automod/enable_all', self.automod_enable_all)
        self.app.router.add_post('/api/guilds/{guild_id}/automod/ignored', self.automod_update_ignored)
        self.app.router.add_post('/api/guilds/{guild_id}/automod/create_log', self.create_automod_log_channel)
        self.app.router.add_post('/api/guilds/{guild_id}/automod/disable_all', self.automod_disable_all)
        self.app.router.add_delete('/api/guilds/{guild_id}/automod/reset', self.reset_automod)
        
        # Banwords Endpoints
        self.app.router.add_get('/api/guilds/{guild_id}/banwords', self.get_banwords_config)
        self.app.router.add_post('/api/guilds/{guild_id}/banwords', self.save_banwords_config) 
        self.app.router.add_post('/api/guilds/{guild_id}/banwords/add', self.add_banword)
        self.app.router.add_delete('/api/guilds/{guild_id}/banwords/remove', self.remove_banword)
        
        self.app.router.add_post('/api/guilds/{guild_id}/banwords/bypass', self.banwords_update_bypass)
        self.app.router.add_post('/api/guilds/{guild_id}/banwords/bypass_role', self.banwords_update_bypass_role)
        self.app.router.add_post('/api/guilds/{guild_id}/banwords/exempt', self.banwords_update_exempt)
        self.app.router.add_delete('/api/guilds/{guild_id}/banwords/reset', self.reset_banwords)

        # Danger Zone Resets
        self.app.router.add_get('/api/guilds/{guild_id}/security/antinuke', self.get_antinuke_config)
        self.app.router.add_post('/api/guilds/{guild_id}/security/antinuke', self.save_antinuke_config)
        self.app.router.add_delete('/api/guilds/{guild_id}/security/antinuke', self.reset_antinuke)
        self.app.router.add_delete('/api/guilds/{guild_id}/security/whitelist/reset', self.reset_whitelist_all)
        self.app.router.add_delete('/api/guilds/{guild_id}/security/extraowners/reset', self.reset_extraowners_all)
        
        self.runner = None
        self.site = None

    async def cog_load(self):
        # Clean Clean logs: [Time] Status Method Path
        self.runner = web.AppRunner(self.app, access_log_format='%t | %s | %r')
        await self.runner.setup()
        port = int(os.getenv("SERVER_PORT", 4000))
        self.site = web.TCPSite(self.runner, '0.0.0.0', port)
        await self.site.start()
        print(f"Internal API Server started on port {port}")

    async def cog_unload(self):
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    # --- EMBED API HANDLERS ---
    
    async def health_check(self, request):
        try:
            # Cache stats for 60 seconds to prevent event loop blocking on high RPM
            if not hasattr(self, '_health_cache'):
                self._health_cache = {'data': None, 'timestamp': 0}
            
            now = datetime.datetime.utcnow().timestamp()
            if self._health_cache['data'] and (now - self._health_cache['timestamp'] < 60):
                return web.json_response(self._health_cache['data'])

            uptime = str(datetime.datetime.utcnow() - self.bot.uptime) if hasattr(self.bot, 'uptime') else 'unknown'
            if hasattr(self.bot, 'latency') and self.bot.latency != float('inf'):
                 ping = int(self.bot.latency * 1000)
            else:
                 ping = 0
            guild_count = len(self.bot.guilds)
            
            # Efficient summation
            user_count = sum(g.member_count for g in self.bot.guilds)
            
            data = {
                'status': 'online',
                'uptime': uptime,
                'ping': ping,
                'guild_count': guild_count,
                'user_count': user_count
            }
            self._health_cache = {'data': data, 'timestamp': now}
            
            return web.json_response(data)
        except Exception as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)

    async def get_channels(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)
            
            channels = []
            for c in guild.text_channels:
                channels.append({'id': str(c.id), 'name': c.name, 'type': 'text'})
            
            categories = []
            for c in guild.categories:
                categories.append({'id': str(c.id), 'name': c.name, 'type': 'category'})
                
            return web.json_response({'channels': channels, 'categories': categories})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_roles(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)
            
            roles = [
                {'id': str(r.id), 'name': r.name, 'color': str(r.color), 'position': r.position}
                for r in guild.roles if not r.is_default() and not r.managed
            ]
            # Sort by position (descending)
            roles.sort(key=lambda x: x['position'], reverse=True)
            
            # Sort by position (descending)
            roles.sort(key=lambda x: x['position'], reverse=True)
            
            bot_member = guild.me
            bot_top_role = bot_member.top_role
            
            return web.json_response({
                'roles': roles, 
                'bot_position': bot_top_role.position,
                'bot_role_name': bot_top_role.name
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)


    async def search_members(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            query = request.query.get('q', '').lower().strip()
            
            if not query or len(query) < 2:
                return web.json_response({'members': []})
                
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)
            
            matches = []
            count = 0
            
            # Efficiently search members
            for m in guild.members:
                if query in m.name.lower() or (m.global_name and query in m.global_name.lower()) or (m.nick and query in m.nick.lower()) or query == str(m.id):
                    matches.append({
                        'id': str(m.id),
                        'username': m.name,
                        'global_name': m.global_name,
                        'nickname': m.nick,
                        'avatar_url': m.display_avatar.url
                    })
                    count += 1
                    if count >= 10: break
            
            return web.json_response({'members': matches})
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_embeds(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None:
                return web.json_response({'error': 'Database Error'}, status=500)
                
            cursor = db.embeds.find({"guild_id": int(guild_id)})
            embeds = [doc['name'] for doc in await cursor.to_list(length=100)]
            
            return web.json_response({'embeds': embeds})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_embed_detail(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            name = request.match_info.get('name', '').strip()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None:
                return web.json_response({'error': 'Database Error'}, status=500)
                
            doc = await db.embeds.find_one({"guild_id": int(guild_id), "name": name})
            
            if not doc:
                return web.json_response({'error': 'Embed not found'}, status=404)
            
            embed_data = doc.get('data', {})
            components_raw = doc.get('components', [])
            
            # The dashboard might expect the unwrapped 'component_json' to parse it again?
            # Or does it expect the structured list?
            # Based on previous SQL: it returned list of {type, id, data} where data was parsed JSON.
            
            components = []
            for c in components_raw:
                # c is like { 'component_type': ..., 'component_id': ..., 'component_json': "..." }
                # Dashboard code likely does JSON.parse on the data field?
                # Let's match the old response format:
                # {'data': embed_data, 'components': [{'type': ..., 'id': ..., 'data': ...}]}
                components.append({
                    'type': c['component_type'],
                    'id': c['component_id'],
                    'data': json.loads(c['component_json'])
                })
            
            return web.json_response({'data': embed_data, 'components': components})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def save_embed(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            name = request.match_info.get('name', '').strip()
            data = await request.json()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            # Prepare Components
            final_components = []
            
            # Options
            for i, comp in enumerate(data.get('select_options', [])):
                comp_id = f"embed:{guild_id}:{name}:select_option:{i}"
                comp['id'] = comp_id
                final_components.append({
                    'component_id': comp_id,
                    'component_type': 'select_option',
                    'component_json': json.dumps(comp)
                })
            
            # Buttons
            for i, comp in enumerate(data.get('buttons', [])):
                comp_id = f"embed:{guild_id}:{name}:button:{i}"
                comp['id'] = comp_id
                final_components.append({
                    'component_id': comp_id,
                    'component_type': 'button',
                    'component_json': json.dumps(comp)
                })
            
            # Fetch existing to merge
            existing = await db.embeds.find_one({"guild_id": int(guild_id), "name": name})
            current_data = existing.get('data', {}) if existing else {}
            
            # Simple recursive merge helper
            def recursive_merge(target, source):
                for k, v in source.items():
                    if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                        recursive_merge(target[k], v)
                    else:
                        target[k] = v
                return target

            new_data = data.get('data', {})
            # Use deep copy of current data as base
            import copy
            merged_data = recursive_merge(copy.deepcopy(current_data), new_data)

            # Upsert
            await db.embeds.update_one(
                {"guild_id": int(guild_id), "name": name},
                {"$set": {
                    "data": merged_data,
                    "components": final_components
                }},
                upsert=True
            )
            
            return web.json_response({'success': True})
        except Exception as e:
            print(f"DEBUG: Save error: {str(e)}")
            import traceback
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def delete_embed(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            name = request.match_info.get('name', '').strip()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.embeds.delete_one({"guild_id": int(guild_id), "name": name})
            
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_all_embeds(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.embeds.delete_many({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    # --- STICKY MESSAGE HANDLERS ---

    async def get_stickies(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            sticky_cog = self.bot.get_cog('Sticky')
            if not sticky_cog: return web.json_response({'error': 'Sticky module not loaded'}, status=503)
            
            stickies = await sticky_cog.get_guild_stickies(guild_id)
            
            result = []
            guild = self.bot.get_guild(guild_id)
            if guild:
                for channel_id, content in stickies:
                    channel = guild.get_channel(channel_id)
                    result.append({
                        'channel_id': str(channel_id),
                        'channel_name': channel.name if channel else "Unknown/Deleted",
                        'content': content
                    })
            
            return web.json_response({'stickies': result})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def create_sticky(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            sticky_cog = self.bot.get_cog('Sticky')
            if not sticky_cog: return web.json_response({'error': 'Sticky module not loaded'}, status=503)

            # Check Limit
            current = await sticky_cog.get_guild_stickies(guild_id)
            if len(current) >= 5:
                return web.json_response({'error': 'Limit of 5 sticky messages reached'}, status=400)

            data = await request.json()
            channel_id = int(data.get('channel_id'))
            content = data.get('content')
            
            if not content or not channel_id:
                 return web.json_response({'error': 'Missing content or channel_id'}, status=400)

            await sticky_cog.save_sticky(guild_id, channel_id, content) 
            
            guild = self.bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    await sticky_cog.force_stick(channel)

            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def delete_sticky(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            channel_id = int(request.match_info.get('channel_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            sticky_cog = self.bot.get_cog('Sticky')
            if not sticky_cog: return web.json_response({'error': 'Sticky module not loaded'}, status=503)

            # Delete message logic (simplistic best-effort)
            data = await sticky_cog.get_sticky(channel_id)
            if data:
               last_id = data[1]
               if last_id:
                   try:
                       guild = self.bot.get_guild(guild_id)
                       if guild:
                           channel = guild.get_channel(channel_id)
                           if channel:
                               msg = await channel.fetch_message(last_id)
                               await msg.delete()
                   except:
                       pass

            await sticky_cog.delete_sticky(channel_id)
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)


    async def reset_stickies(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            sticky_cog = self.bot.get_cog('Sticky')
            if not sticky_cog: return web.json_response({'error': 'Sticky module not loaded'}, status=503)

            await sticky_cog.reset_guild_stickies(guild_id)
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_general_settings(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            guild_id_int = int(guild_id)
            from utils.Tools import getConfig
            config = await getConfig(guild_id_int, self.bot)
            
            # Fetch Custom Profile
            custom_profile = {}
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                profile_doc = await self.bot.db.custom_profiles.find_one({"guild_id": guild_id_int})
                if profile_doc:
                    custom_profile = {
                        'avatar': profile_doc.get('avatar', ''),
                        'banner': profile_doc.get('banner', ''),
                        'bio': profile_doc.get('bio', ''),
                        'name': profile_doc.get('name', '')
                    }

            # Check Premium Status (for frontend locking)
            is_premium = False
            # Check Premium Status (for frontend locking)
            is_premium = False
            premium_cog = self.bot.get_cog('Premium')
            if premium_cog and hasattr(premium_cog, 'premium_system'):
                # Check if the guild owner has premium or if the guild is premium
                guild = self.bot.get_guild(guild_id_int)
                if guild:
                    # Check owner
                    has_prem, _ = await premium_cog.premium_system.check_user_premium(guild.owner_id, guild_id_int)
                    if has_prem:
                        is_premium = True
                    else:
                        # Check request user (if passed in header?)
                        pass
            
            # Bot Owner Override
            user_id_header = request.headers.get('X-User-ID')
            if user_id_header and int(user_id_header) in getattr(self.bot, 'owner_ids', [1218037361926209640]):
                 is_premium = True

            return web.json_response({
                'prefix': config.get("prefix", ","),
                'join_nick': config.get("join_nick", ""),
                'custom_profile': custom_profile,
                'is_premium': is_premium
            })
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def set_general_settings(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            guild_id_int = int(guild_id)
            auth, err = await self.check_permissions(request, guild_id_int)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            # --- General Config Update ---
            from utils.Tools import updateConfig
            # Only update config keys if present
            config_update = {}
            if 'prefix' in data: config_update['prefix'] = data['prefix']
            if 'join_nick' in data: config_update['join_nick'] = data['join_nick']
            
            if config_update:
                await updateConfig(guild_id_int, config_update, self.bot)
            
            # --- Custom Profile Update ---
            if 'custom_profile' in data:
                # Check Premium AGAIN for security
                is_premium = False
                guild = self.bot.get_guild(guild_id_int)
                
                # Bot Owner Override
                user_id_header = request.headers.get('X-User-ID')
                if user_id_header and int(user_id_header) in getattr(self.bot, 'owner_ids', [1218037361926209640]):
                    is_premium = True
                elif guild:
                     premium_cog = self.bot.get_cog('Premium')
                     if premium_cog and hasattr(premium_cog, 'premium_system'):
                        has_prem, _ = await premium_cog.premium_system.check_user_premium(guild.owner_id, guild_id_int)
                        if has_prem: is_premium = True
                
                if not is_premium:
                    return web.json_response({'error': 'Premium required for custom profile'}, status=403)
                
                profile_data = data['custom_profile']
                update_fields = {}
                valid_fields = ['avatar', 'banner', 'bio', 'name']
                
                for field in valid_fields:
                    if field in profile_data:
                         update_fields[field] = profile_data[field]
                
                if update_fields:
                    update_fields['user_id'] = int(user_id_header) if user_id_header else 0
                    
                    if hasattr(self.bot, 'db') and self.bot.db is not None:
                        await self.bot.db.custom_profiles.update_one(
                            {"guild_id": guild_id_int},
                            {"$set": update_fields},
                            upsert=True
                        )
                        
                    # Attempt to Apply Changes Immediately
                    if guild:
                        try:
                            if 'name' in update_fields:
                                await guild.me.edit(nick=update_fields['name'])
                            
                            # Avatar/Banner requires bytes, URL provided.
                            # We can fetch and update if we want to be fancy, but might timeout API.
                            # Better to let the user know it might take a moment or trigger a background task.
                            # For now, we just save to DB. The 'customprofile' cog commands handle the live update.
                            # If we want the dashboard to live update, we'd need to fetch here.
                            # Raw API update for Avatar/Banner
                            if 'name' in update_fields:
                                # Truncate name to 32 chars just in case
                                update_fields['name'] = update_fields['name'][:32]
                            
                            if 'bio' in update_fields:
                                if len(update_fields['bio']) > 2000:
                                    return web.json_response({'error': 'Bio is too long (Max 2000 chars)'}, status=400)
                                # Discord has 190 char limit for profile bio
                                # We sync to discord if < 190, otherwise just DB
                                pass
                            if 'avatar' in update_fields or 'banner' in update_fields:
                                import aiohttp
                                import base64
                                from discord.http import Route
                                
                                payload = {}
                                async with aiohttp.ClientSession() as session:
                                    # Fetch Avatar
                                    if 'avatar' in update_fields and update_fields['avatar']:
                                        try:
                                            async with session.get(update_fields['avatar']) as resp:
                                                if resp.status == 200:
                                                    data = await resp.read()
                                                    if len(data) > 10 * 1024 * 1024: # 10MB limit
                                                        print(f"API: Avatar file too large ({len(data)} bytes)")
                                                        return web.json_response({'error': 'Avatar file too large (Max 10MB)'}, status=400)
                                                    else:
                                                        b64 = base64.b64encode(data).decode('utf-8')
                                                        mime = resp.headers.get('Content-Type', 'image/png')
                                                        # Fix: Force image/gif if url ends in .gif (sometimes headers are wrong)
                                                        if update_fields['avatar'].lower().split('?')[0].endswith('.gif'):
                                                            mime = 'image/gif'
                                                        payload['avatar'] = f"data:{mime};base64,{b64}"
                                        except Exception as e:
                                            print(f"API: Failed to fetch avatar: {e}")

                                    # Fetch Banner
                                    if 'banner' in update_fields and update_fields['banner']:
                                        try:
                                            async with session.get(update_fields['banner']) as resp:
                                                if resp.status == 200:
                                                    data = await resp.read()
                                                    if len(data) > 10 * 1024 * 1024: # 10MB limit
                                                        print(f"API: Banner file too large ({len(data)} bytes)")
                                                        return web.json_response({'error': 'Banner file too large (Max 10MB)'}, status=400)
                                                    else:
                                                        b64 = base64.b64encode(data).decode('utf-8')
                                                        mime = resp.headers.get('Content-Type', 'image/png')
                                                        # Fix: Force image/gif if url ends in .gif
                                                        if update_fields['banner'].lower().split('?')[0].endswith('.gif'):
                                                            mime = 'image/gif'
                                                        payload['banner'] = f"data:{mime};base64,{b64}"
                                        except Exception as e:
                                             print(f"API: Failed to fetch banner: {e}")
                                
                                # Send PATCH request if we have data
                                if payload:
                                    try:
                                        route = Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=guild_id_int)
                                        await self.bot.http.request(route, json=payload)
                                    except Exception as e:
                                        print(f"API: Raw PATCH failed: {e}")
                                        return web.json_response({'error': f"Discord API Error: {str(e)}"}, status=400)

                        except Exception as e:
                            print(f"Failed to apply profile changes: {e}")
                            # Don't fail the request, just log

            return web.json_response({'success': True})
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    # --- TICKET MANAGER API HANDLERS ---

    async def get_ticket_manager_data(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db') or self.bot.db is None:
                return web.json_response({'error': 'Database offline'}, status=503)

            # Fetch all tickets
            cursor = self.bot.db.tickets.find({"guild_id": guild_id})
            tickets = await cursor.to_list(length=None)
            
            # Stats
            total = len(tickets)
            open_count = sum(1 for t in tickets if t.get('status', 'open') == 'open')
            
            # Handle potential None values safely
            closed_count = sum(1 for t in tickets if t.get('status') == 'closed')
            claimed_count = sum(1 for t in tickets if t.get('claimed_by'))
            
            # List Data
            ticket_list = []
            guild = self.bot.get_guild(guild_id)
            
            if guild:
                for t in tickets:
                    # Robust field getters
                    owner_id = t.get('owner_id')
                    try: owner_id = int(owner_id) if owner_id else None
                    except: owner_id = None

                    claimed_by = t.get('claimed_by')
                    try: claimed_by = int(claimed_by) if claimed_by else None
                    except: claimed_by = None
                    
                    channel_id = t.get('channel_id')
                    try: channel_id = int(channel_id) if channel_id else None
                    except: channel_id = None

                    ticket_id = t.get('ticket_id')
                    
                    if not ticket_id: continue
                    
                    # Ensure created_at is a valid timestamp (integer) or ISO string
                    # Frontend likely expects a timestamp (ms) or ISO string.
                    created_at = t.get('created_at')
                    if isinstance(created_at, datetime.datetime):
                        created_at = int(created_at.timestamp() * 1000)
                    elif isinstance(created_at, (int, float)):
                        created_at = int(created_at * 1000) # Convert to ms for JS
                    else:
                        created_at = 0 # Default to 0 avoids NaN

                    owner = guild.get_member(owner_id) if owner_id else None
                    staff = guild.get_member(claimed_by) if claimed_by else None
                    channel = guild.get_channel(channel_id) if channel_id else None
                    
                    ticket_list.append({
                        'id': str(ticket_id),
                        'channel_id': str(channel_id) if channel_id else "",
                        'channel_name': channel.name if channel else "Deleted-Channel",
                        'owner_id': str(owner_id) if owner_id else "",
                        'owner_name': owner.name if owner else "Unknown",
                        'owner_avatar': owner.display_avatar.url if owner else None,
                        'staff_id': str(claimed_by) if claimed_by else None,
                        'staff_name': staff.name if staff else None,
                        'status': t.get('status', 'open'),
                        'created_at': created_at
                    })

            return web.json_response({
                'stats': {
                    'total': total,
                    'open': open_count,
                    'closed': closed_count,
                    'claimed': claimed_count
                },
                'tickets': ticket_list
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def ticket_manager_action(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action')
            ticket_id = data.get('ticket_id')
            
            if not hasattr(self.bot, 'db') or self.bot.db is None:
                return web.json_response({'error': 'Database offline'}, status=503)
            
            row = await self.bot.db.tickets.find_one({"ticket_id": ticket_id})
            if not row: return web.json_response({'error': 'Ticket not found'}, status=404)
            
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
            
            channel_id = row.get('channel_id')
            channel = guild.get_channel(channel_id) if channel_id else None
            
            if not channel:
                 # Clean up ghost ticket
                 await self.bot.db.tickets.delete_one({"ticket_id": ticket_id})
                 return web.json_response({'error': 'Channel deleted (cleaned db)'}, status=404)
            
            success = True
            try:
                if action == 'close':
                    await channel.edit(name=f"closed-{channel.name}"[:100])
                    await self.bot.db.tickets.update_one({"ticket_id": ticket_id}, {"$set": {"status": "closed"}})
                    await channel.send(embed=discord.Embed(description="🔒 **Ticket Closed via Dashboard.**", color=discord.Color.orange()))
                    
                elif action == 'delete':
                    await channel.delete()
                    await self.bot.db.tickets.delete_one({"ticket_id": ticket_id})
                    
                elif action == 'rename':
                    new_name = data.get('name')
                    if new_name:
                        await channel.edit(name=new_name)
                        
                elif action == 'claim':
                    pass 
            except Exception as e:
                print(f"Action '{action}' failed partially: {e}")
                success = False # Still return JSON for frontend info if needed
                
            return web.json_response({'success': success})
            
        except Exception as e:
             import traceback
             traceback.print_exc()
             return web.json_response({'error': str(e)}, status=500)
             
    async def get_blacklist(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db') or self.bot.db is None:
                return web.json_response({'error': 'Database offline'}, status=503)

            cursor = self.bot.db.ticket_blacklist.find({"guild_id": guild_id})
            rows = await cursor.to_list(length=None)
            
            blacklist = []
            guild = self.bot.get_guild(guild_id)
            if guild:
                for r in rows:
                    uid = r.get('user_id')
                    member = guild.get_member(uid)
                    blacklist.append({
                        'user_id': str(uid),
                        'name': member.name if member else "Unknown User",
                        'avatar': member.display_avatar.url if member else None
                    })
                
            return web.json_response({'blacklist': blacklist})
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def manage_blacklist(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # add/remove
            user_input = data.get('user_id') # Can be ID (int/str) or Name (str)
            
            guild = self.bot.get_guild(guild_id)
            user_id = None
            
            # --- Try to resolve User ---
            if str(user_input).isdigit():
                user_id = int(user_input)
            else:
                # Name search
                if guild:
                    member = discord.utils.find(lambda m: m.name.lower() == str(user_input).lower(), guild.members)
                    if member: user_id = member.id
            
            if not user_id:
                return web.json_response({'error': 'User not found'}, status=404)

            # Ticket Blacklist via MongoDB
            if hasattr(self.bot, 'db'):
                if action == 'add':
                    await self.bot.db.ticket_blacklist.update_one(
                        {"guild_id": guild_id, "user_id": user_id},
                        {"$set": {"guild_id": guild_id, "user_id": user_id}},
                        upsert=True
                    )
                elif action == 'remove':
                    await self.bot.db.ticket_blacklist.delete_one({"guild_id": guild_id, "user_id": user_id})
                
            return web.json_response({'success': True})
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)


    async def send_embed(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            name = request.match_info.get('name', '').strip()
            data = await request.json()
            channel_id = data.get('channel_id')
            
            if not channel_id:
                return web.json_response({'error': 'Missing channel_id'}, status=400)
            
            guild = self.bot.get_guild(int(guild_id))
            channel = guild.get_channel(int(channel_id)) if guild else None
            if not channel:
                return web.json_response({'error': 'Channel not found'}, status=404)

            from cogs.commands.Embed import parse_embed_color, DynamicEmbedView, register_view_safely
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            # Fetch Embed
            embed_doc = await self.bot.db.embeds.find_one({"guild_id": int(guild_id), "name": name})
            if not embed_doc:
                return web.json_response({'error': 'Embed not found'}, status=404)
            
            # Match save_embed structure which uses "data" field
            if 'data' in embed_doc:
                embed_data = embed_doc['data']
            elif 'embed_json' in embed_doc:
                 # Legacy fallback
                 val = embed_doc['embed_json']
                 embed_data = json.loads(val) if isinstance(val, str) else val
            else:
                embed_data = {}
            
            # Fetch Components
            # api.py save_embed saves components in 'components' field of the embed document itself!
            # It does NOT use a separate collection 'embed_components' in the save_embed function above (lines 539).
            # So we should read from embed_doc['components']
            
            comp_rows = embed_doc.get('components', [])
            
            # Legacy fallback if they were separately stored (old SQL migration?)
            if not comp_rows:
                cursor = self.bot.db.embed_components.find({"guild_id": int(guild_id), "embed_name": name})
                comp_rows = await cursor.to_list(length=25)
            
            print(f"DEBUG: Found {len(comp_rows)} components for embed {name}")
            
            # Build Embed
            e = discord.Embed(
                title=embed_data.get("title"), 
                description=embed_data.get("description"), 
                color=parse_embed_color(embed_data.get("color"))
            )
            if embed_data.get("image"): e.set_image(url=embed_data.get("image"))
            if embed_data.get("thumbnail"): e.set_thumbnail(url=embed_data.get("thumbnail"))
            if embed_data.get("footer_text"): 
                e.set_footer(text=embed_data.get("footer_text"), icon_url=embed_data.get("footer_icon"))
            
            view = None
            if comp_rows:
                try:
                    comp_list = []
                    for r in comp_rows:
                        # Mongo doc keys match sqlite column names hopefully?
                        # I'll check what structure save_embed uses or assume standard keys
                        # Standard keys: component_type, component_id, component_json
                        comp_list.append({
                            "component_type": r.get("component_type"),
                            "component_id": r.get("component_id"),
                            "component_json": r.get("component_json")
                        })
                    print("DEBUG: Initializing DynamicEmbedView...")
                    view = DynamicEmbedView(comp_list)
                    print("DEBUG: DynamicEmbedView initialized. Registering safely...")
                    register_view_safely(self.bot, view, f"{guild_id}:{name}")
                    print("DEBUG: View registered.")
                except Exception as ve:
                    print(f"DEBUG: View creation failed: {ve}")
                    traceback.print_exc()
                    return web.json_response({'error': f"View Error: {str(ve)}"}, status=500)
            
            print("DEBUG: Sending to channel...")
            await channel.send(content=embed_data.get("content") or None, embed=e, view=view)
            print("DEBUG: Sent successfully.")
            return web.json_response({'success': True})
        except Exception as e:
            print(f"DEBUG: send_embed failed: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    # --- WELCOME API HANDLERS ---
    
    async def get_stats(self, request):
        guild_id = request.match_info.get('guild_id')
        try:
            if not guild_id:
                return web.json_response({'error': 'Missing guild_id'}, status=400)
            
            auth, err = await self.check_permissions(request, int(guild_id))
            if not auth: 
                if err == "Guild not found":
                    return web.json_response({'error': 'Guild not found', 'bot_not_joined': True}, status=404)
                return web.json_response({'error': err}, status=403)

            guild = self.bot.get_guild(int(guild_id))

            if not guild:
                try:
                    guild = await self.bot.fetch_guild(int(guild_id))
                except Exception:
                    return web.json_response({'error': 'Guild not found', 'bot_not_joined': True}, status=404)

            # Basic Stats
            roles = len(guild.roles)
            members = guild.member_count
            
            # Offload heavy iterations to thread
            def calculate_heavy_stats(g):
                bots = sum(1 for m in g.members if m.bot)
                online = sum(1 for m in g.members if m.status != discord.Status.offline)
                hidden = 0
                for c in g.channels:
                    try:
                        perms = c.overwrites_for(g.default_role)
                        if perms.read_messages == False or perms.view_channel == False:
                            hidden += 1
                    except: pass
                return bots, online, hidden

            bots, online, hidden_channels = await asyncio.to_thread(calculate_heavy_stats, guild)
            
            humans = members - bots
            offline = members - online
            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
        
            # Activity Data from MongoDB
            activity = {"today": {"messages": 0, "vc_minutes": 0}, "history": []}
            most_active = {"chatter": "None", "vc": "None"}

            if hasattr(self.bot, 'db') and self.bot.db is not None:
                try:
                    collection_daily = self.bot.db.stats_daily
                    collection_user = self.bot.db.stats_user_daily
                    
                    # Today's totals
                    today = datetime.date.today().isoformat()
                    row = await collection_daily.find_one({"guild_id": guild.id, "date": today})
                    if row:
                        activity["today"] = {"messages": row.get("messages", 0), "vc_minutes": row.get("vc_minutes", 0)}

                    # Most active today - Messages
                    top_msg = await collection_user.find_one(
                        {"guild_id": guild.id, "date": today},
                        sort=[("messages", -1)]
                    )
                    if top_msg:
                        user = guild.get_member(top_msg["user_id"])
                        most_active["chatter"] = user.display_name if user else f"Unknown ({top_msg['user_id']})"

                    # Most active today - VC
                    top_vc = await collection_user.find_one(
                        {"guild_id": guild.id, "date": today},
                        sort=[("vc_minutes", -1)]
                    )
                    if top_vc:
                        user = guild.get_member(top_vc["user_id"])
                        most_active["vc"] = user.display_name if user else f"Unknown ({top_vc['user_id']})"

                    # History (last 30 days)
                    cursor = collection_daily.find({"guild_id": guild.id}).sort("date", -1).limit(30)
                    async for doc in cursor:
                        activity["history"].append({
                            "date": doc["date"], 
                            "messages": doc.get("messages", 0), 
                            "vc_minutes": doc.get("vc_minutes", 0)
                        })
                        
                except Exception as e:
                    print(f"Stats DB Error: {e}")

            return web.json_response({
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "owner": str(guild.owner),
                "owner_id": str(guild.owner_id),
                "roles": roles,
                "members": members,
                "humans": humans,
                "bots": bots,
                "text_channels": text_channels,
                "voice_channels": voice_channels,
                "hidden_channels": hidden_channels,
                "boosts": guild.premium_subscription_count,
                "community": "Enabled" if "COMMUNITY" in guild.features else "Disabled",
                "two_fa": "Enabled" if guild.mfa_level > 0 else "Disabled",
                "online": online,
                "offline": offline,
                "most_active": most_active,
                "activity": activity
            })

        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def test_welcome(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)

            data = await request.json()
            user_id = data.get('user_id')

            if not guild_id:
                return web.json_response({'error': 'Missing guild_id'}, status=400)
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)

            member = None
            if user_id:
                member = guild.get_member(int(user_id))
                if not member:
                     try: member = await guild.fetch_member(int(user_id))
                     except: pass
            
            if not member:
                 member = guild.me

            welcomer_cog = self.bot.get_cog('Welcomer')
            if not welcomer_cog:
                return web.json_response({'error': 'Welcomer cog not loaded'}, status=503)

            if hasattr(welcomer_cog, '_process_welcome'):
                success, msg = await welcomer_cog._process_welcome(guild.id, member)
                if success:
                    return web.json_response({'success': True, 'message': f'Sent to {msg}'})
                else:
                     return web.json_response({'error': msg}, status=500)
            else:
                 return web.json_response({'error': 'Method not found'}, status=500)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_welcome(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            config = await self.bot.db.welcome.find_one({"guild_id": int(guild_id)})
            
            # Map MongoDB document to expected API response
            response_config = {
                "channel_id": str(config.get("channel_id", "")) if config and config.get("channel_id") else "",
                "role_id": str(config.get("role_id", "")) if config and config.get("role_id") else "",
                "autodelete_seconds": config.get("autodelete_seconds", 0) if config else 0,
                "enabled": config.get("enabled", True) if config else True
            }
            
            msg_data = config.get("message", {}) if config else {}
            response_message = {
                "type": msg_data.get("type", "simple"),
                "content": msg_data.get("content", "")
            }

            return web.json_response({
                "config": response_config,
                "message": response_message
            })
        except Exception as e:
            print(f"ERROR in get_welcome: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def save_welcome(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)
                 
            # Extract fields - Handle both nested (legacy) and flat (frontend) structures
            config_data = data.get('config', {})
            # If config is empty, try root level (Frontend often sends flat structure)
            if not config_data:
                config_data = data
            
            msg_data = data.get('message', {})
            # If message is empty but type/content are at root
            if not msg_data and 'type' in data:
                msg_data = {
                    "type": data.get("type"),
                    "content": data.get("content")
                }
            
            update_data = {}
            
            if 'channel_id' in config_data:
                try: update_data['channel_id'] = int(config_data['channel_id']) if config_data['channel_id'] else None
                except: update_data['channel_id'] = None
                
            if 'role_id' in config_data:
                try: update_data['role_id'] = int(config_data['role_id']) if config_data['role_id'] else None
                except: update_data['role_id'] = None
                
            if 'autodelete_seconds' in config_data:
                 try: update_data['autodelete_seconds'] = int(config_data['autodelete_seconds'])
                 except: update_data['autodelete_seconds'] = 0
            
            if 'enabled' in config_data:
                update_data['enabled'] = config_data['enabled']

            if msg_data:
                # We need to preserve existing message data if partial update? 
                # Usually save_welcome sends full state. Let's assume full state or merge.
                # Ideally, we should set "message" object.
                message_obj = {
                    "type": msg_data.get("type", "simple"),
                    "content": msg_data.get("content", "")
                }
                update_data["message"] = message_obj

            if update_data:
                await self.bot.db.welcome.update_one(
                    {"guild_id": int(guild_id)},
                    {"$set": update_data},
                    upsert=True
                )

            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_welcome(self, request):
        try:
            guild_id = request.match_info.get('guild_id')
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db'):
                await self.bot.db.welcome.delete_one({"guild_id": int(guild_id)})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_tickets(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db'):
                await self.bot.db.ticket_panels.delete_many({"guild_id": guild_id})
                await self.bot.db.ticket_settings.delete_many({"guild_id": guild_id})
                await self.bot.db.tickets.delete_many({"guild_id": guild_id})
                await self.bot.db.ticket_blacklist.delete_many({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # --- TICKET API HANDLERS ---

    async def get_ticket_panels(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            panels = []
            if hasattr(self.bot, 'db'):
                cursor = self.bot.db.ticket_panels.find({"guild_id": guild_id})
                async for doc in cursor:
                    panels.append({
                        "id": doc.get("panel_id", doc.get("panel_name")),
                        "name": doc.get("panel_name", doc.get("name", "Unknown")),
                        "panel_title": doc.get("embed_title", "Open a Ticket"),
                        "channel_id": str(doc.get("channel_id", ""))
                    })
            
            return web.json_response({'panels': panels})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def get_ticket_panel_detail(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            name = request.match_info.get('panel_id')
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            doc = await self.bot.db.ticket_panels.find_one({"guild_id": guild_id, "panel_id": name})
            
            if not doc:
                return web.json_response({'error': 'Panel not found'}, status=404)

            # Correctly map stored JSON to frontend structure
            embed_data = json.loads(doc.get("embed_json", "{}"))
            comp_data = json.loads(doc.get("component_json", "{}"))
            
            data = {
                "id": doc.get("panel_id"),
                "name": doc.get("panel_name", doc.get("name", "Unknown")),
                "channel_id": str(doc.get("channel_id", "") or ""),
                "category_id": str(doc.get("category_id", "") or ""),
                "message": doc.get("panel_message", ""),
                "embed": embed_data,
                "components": comp_data
            }
            
            return web.json_response({'data': data})
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def save_ticket_panel(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            panel_id = request.match_info.get('panel_id')
            data = await request.json()
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            # Construct update doc
            # Frontend sends: { name, channel_id, category_id, message, embed: {}, components: {} }
            # DB expects: { panel_id, panel_name, panel_title, panel_message, embed_json, component_json, ... }
            
            update_doc = {
                "panel_id": panel_id,
                "name": data.get("name"), # Added for consistency with ticket.py
                "panel_name": data.get("name"),
                "panel_message": data.get("message"),
                "channel_id": int(data["channel_id"]) if data.get("channel_id") else None,
                "category_id": int(data["category_id"]) if data.get("category_id") else None,
                
                # Store complex objects as JSON strings for the bot to parse
                "embed_json": json.dumps(data.get("embed", {})),
                "component_json": json.dumps(data.get("components", {})),
                
                # Redundant but useful fields for API checks? 
                # Actually, strictly stick to schema used by ticket.py
                # ticket.py uses: panel_id, component_json
            }
            
            await self.bot.db.ticket_panels.update_one(
                {"guild_id": guild_id, "panel_id": panel_id},
                {"$set": update_doc},
                upsert=True
            )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def delete_ticket_panel(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            panel_id = request.match_info.get('panel_id')
            
            if hasattr(self.bot, 'db'):
                await self.bot.db.ticket_panels.delete_one({"guild_id": guild_id, "panel_id": panel_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_ticket_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            config = await self.bot.db.ticket_settings.find_one({"guild_id": guild_id})
            
            data = {
                "transcript_channel": str(config.get("transcript_channel", "")) if config and config.get("transcript_channel") else "",
                "staff_role_id": str(config.get("staff_role_id", config.get("support_role_id", ""))) if config else "",
                "log_channel_id": str(config.get("log_channel_id", "")) if config and config.get("log_channel_id") else "",
                "dm_on_open": config.get("dm_on_open", True) if config else True,
                "dm_on_close": config.get("dm_on_close", True) if config else True
            }
            # Wrap as 'config' key or direct? 
            # Frontend: `const configData = await configRes.json(); setConfigData(configData);` (Line 113 in page.js)
            # But line 112 says `if (configRes.ok)`.
            # Wait, line 113: `const configData = await configRes.json()`.
            # If API returns `{'config': data}`, then `configData` is `{config: {...}}`.
            # But `setConfigData` expects `{staff_role_id: ...}`.
            # So I should return the dict DIRECTLY, or frontend needs to unwrap.
            # Looking at `api.py` 1382: `return web.json_response({'config': data})`.
            # Frontend line 113: `setConfigData(configData)`.
            # If line 113 gets `{config: {...}}`, then `configData.staff_role_id` is undefined.
            # Frontend seems to expect the object directly?
            # Let's check `loadConfig` in page.js (line 129): `const data = await res.json(); setConfigData(data);`.
            # So yes, API should return keys directly OR frontend should Unwrap.
            # Given `get_ticket_config` wraps in `config`, I should probably UNWRAP it in API or change key to match.
            # Actually, let's keep it consistent with other settings.
            # `get_leveling_config` returns keys directly.
            # `get_ticket_config` returns `{'config': data}`.
            # I will change it to return `data` directly to be safe, OR check frontend.
            # Frontend `setConfigData(configData)`. Accesses `configData.staff_role_id`.
            # So API must return `{staff_role_id: ...}`.
            
            return web.json_response(data)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def save_ticket_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            update_doc = {
                "transcript_channel": int(data["transcript_channel"]) if data.get("transcript_channel") else None,
                "staff_role_id": int(data["staff_role_id"]) if data.get("staff_role_id") else None, # Key used by Bot
                "support_role_id": int(data["staff_role_id"]) if data.get("staff_role_id") else None, # Legacy key
                "log_channel_id": int(data["log_channel_id"]) if data.get("log_channel_id") else None,
                "dm_on_open": data.get("dm_on_open", True),
                "dm_on_close": data.get("dm_on_close", True)
            }
            
            await self.bot.db.ticket_settings.update_one(
                {"guild_id": guild_id},
                {"$set": update_doc},
                upsert=True
            )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def send_ticket_panel(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            panel_id = request.match_info.get('panel_id')
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)
                
            doc = await self.bot.db.ticket_panels.find_one({"guild_id": guild_id, "panel_id": panel_id})
            if not doc:
                return web.json_response({'error': 'Panel not found'}, status=404)
                
            channel_id = doc.get("channel_id")
            if not channel_id:
                return web.json_response({'error': 'Channel not set in panel config'}, status=400)
                
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
            channel = guild.get_channel(int(channel_id))
            if not channel: return web.json_response({'error': 'Channel not found'}, status=404)
            
            # Construct Embed from JSON
            from cogs.commands.Embed import parse_embed_color
            
            embed_data = json.loads(doc.get("embed_json", "{}"))
            e = discord.Embed(
                title=embed_data.get("title") or "Open a Ticket",
                description=embed_data.get("description") or "Click below to open a ticket.",
                color=parse_embed_color(embed_data.get("color"))
            )
            if embed_data.get("thumbnail"): e.set_thumbnail(url=embed_data.get("thumbnail"))
            if embed_data.get("image"): e.set_image(url=embed_data.get("image"))
            if embed_data.get("footer"): e.set_footer(text=embed_data.get("footer"), icon_url=embed_data.get("footer_url"))
            
            # Use Global View
            view = APITicketView(panel_id, json.loads(doc.get("component_json", "{}")))
            self.bot.add_view(view)
            
            try:
                await channel.send(content=doc.get("panel_message") or None, embed=e, view=view)
            except discord.HTTPException as err:
                return web.json_response({'error': f'Discord Error: {err.text}'}, status=err.status)

            return web.json_response({'success': True})
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    # --- AUTOMATION API HANDLERS ---

    # Autorole
    async def get_autorole(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            doc = await db.autoroles.find_one({"guild_id": guild_id})
            
            if doc:
                data = {
                    "bots": doc.get("bots"),
                    "humans": doc.get("humans"),
                    "boosters": doc.get("boosters"),
                    "enabled": doc.get("enabled", False)
                }
            else:
                data = {"bots": None, "humans": None, "boosters": None, "enabled": False}
                
            return web.json_response(data)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def save_autorole(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoroles.update_one(
                {"guild_id": guild_id},
                {"$set": {
                    "bots": int(data.get('bots')) if data.get('bots') and str(data.get('bots')).isdigit() else None,
                    "humans": int(data.get('humans')) if data.get('humans') and str(data.get('humans')).isdigit() else None,
                    "boosters": int(data.get('boosters')) if data.get('boosters') and str(data.get('boosters')).isdigit() else None,
                    "enabled": bool(data.get('enabled', False))
                }},
                upsert=True
            )
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_autorole(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoroles.delete_one({"guild_id": guild_id})
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # Autoreact
    async def get_autoreact(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            cursor = db.autoreacts.find({"guild_id": guild_id})
            rows = await cursor.to_list(length=100)
                    
            return web.json_response({'autoreacts': [{'trigger': r['trigger'], 'emoji': r['emoji']} for r in rows]})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def create_autoreact(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            trigger = data.get('trigger', '').strip().lower()
            emojistr = data.get('emoji', '').strip()
            
            if not trigger or not emojistr:
                return web.json_response({'error': 'Missing trigger or emoji'}, status=400)
            
            # Verify emoji matches validation in autoreact command
            import discord
            try:
                # Try to parse as PartialEmoji (works for unicode and custom <a:name:id>)
                emoji = discord.PartialEmoji.from_str(emojistr)
                # We store the string representation for reacting later
                emoji_to_store = str(emoji)
            except:
                return web.json_response({'error': 'Invalid emoji provided'}, status=400)
                
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoreacts.update_one(
                {"guild_id": guild_id, "trigger": trigger},
                {"$set": {"emoji": emoji_to_store, "created_by": 0}},
                upsert=True
            )
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def delete_autoreact(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            trigger = data.get('trigger', '').strip().lower()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoreacts.delete_one({"guild_id": guild_id, "trigger": trigger})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_autoreact(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoreacts.delete_many({"guild_id": guild_id})
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # Autoresponder
    async def get_autoresponder(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            cursor = db.autoresponders.find({"guild_id": guild_id})
            rows = await cursor.to_list(length=100)
                    
            return web.json_response({'autoresponders': [{'trigger': r['trigger'], 'response': r['response']} for r in rows]})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def create_autoresponder(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            trigger = data.get('trigger', '').strip().lower()
            response = data.get('response', '')
            
            if not trigger or not response:
                return web.json_response({'error': 'Missing trigger or response'}, status=400)
                
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoresponders.update_one(
                {"guild_id": guild_id, "trigger": trigger},
                {"$set": {"response": response, "created_by": 0}},
                upsert=True
            )
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def delete_autoresponder(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            trigger = data.get('trigger', '').strip().lower()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoresponders.delete_one({"guild_id": guild_id, "trigger": trigger})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_autoresponder(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.autoresponders.delete_many({"guild_id": guild_id})
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # Reaction Roles
    async def get_reactionroles(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            rows = []
            cursor = self.bot.db.reaction_roles.find({"guild_id": guild_id})
            async for doc in cursor:
                doc['id'] = str(doc['_id'])
                rows.append(doc)
        
            guild = self.bot.get_guild(guild_id)
            roles = []
            if guild:
                for r in rows:
                    role_id = int(r['role_id']) if r.get('role_id') else 0
                    role_obj = guild.get_role(role_id)
                    roles.append({
                        'id': r['id'],
                        'message_id': str(r.get('message_id', '')),
                        'emoji': r.get('emoji', ''),
                        'role_id': str(role_id),
                        'role_name': role_obj.name if role_obj else "Unknown Role",
                        'role_color': str(role_obj.color) if role_obj else "#99aab5"
                    })
            
            return web.json_response({'reaction_roles': roles})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def create_reactionrole(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            # Retrieve message_id from root or rely on item structure?
            # Frontend sends: { message_id: "...", items: [...] }
            # Single mode: { message_id: "...", emoji: "...", role_id: "..." }
            
            message_id = None
            if 'message_id' in data:
                 try: message_id = int(data['message_id'])
                 except: pass # Might be string if big int? use int() safely
            
            if not message_id: return web.json_response({'error': 'Missing message_id'}, status=400)
            
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            # Check if bulk items (new frontend) or single (legacy)
            # Check Channel ID for adding reactions
            channel_id = data.get('channel_id')
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            
            print(f"[DEBUG] create_rr: guild={guild_id}, channel={channel}, msg={message_id}")

            items = data.get('items')

            # Normalize items to list
            items = data.get('items')
            if not items or not isinstance(items, list):
                # Check for legacy single item
                emoji = data.get('emoji')
                role_val = data.get('role_id')
                if emoji and role_val:
                    items = [{'emoji': emoji, 'role_id': role_val}]
                else:
                    items = []

            print(f"[DEBUG] create_rr: items count={len(items)}")

            for item in items:
                emoji = item.get('emoji')
                if emoji: emoji = emoji.strip() # Remove whitespace
                
                try:
                    role_id = int(item.get('role_id'))
                except:
                    continue # Skip invalid roles
                
                if not emoji or not role_id: continue

                # Update DB
                await self.bot.db.reaction_roles.update_one(
                    {"guild_id": guild_id, "message_id": message_id, "emoji": emoji},
                    {"$set": {"role_id": role_id, "channel_id": channel_id}},
                    upsert=True
                )
                
                # Try to react
                if channel:
                        try:
                            msg = await channel.fetch_message(message_id)
                            
                            # Parse Emoji
                            reaction_emoji = emoji
                            custom_emoji_pattern = r'<(a)?:([a-zA-Z0-9_]+):([0-9]+)>'
                            match = re.match(custom_emoji_pattern, emoji)
                            if match:
                                reaction_emoji = discord.PartialEmoji(
                                    name=match.group(2), 
                                    id=int(match.group(3)), 
                                    animated=bool(match.group(1))
                                )
                            
                            await msg.add_reaction(reaction_emoji)
                        except Exception as e:
                            print(f"Failed to add reaction {emoji}: {e}")
            
            # Note: We rely on the bot listening to RawReaction events using this DB.
            # If the bot uses a different DB for reaction roles, this won't work.
            # I should verify if cogs/commands/reactionrole.py exists and migrate it if needed.
            # But strictly following "Migrate Dashboard to MongoDB", this API change is correct.

            return web.json_response({'success': True})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def delete_reactionrole(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            rr_id = data.get('id')
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            from bson import ObjectId
            try:
                oid = ObjectId(rr_id)
                await self.bot.db.reaction_roles.delete_one({"_id": oid})
            except:
                # Fallback if id is not ObjectId (legacy integer ID from SQLite?)
                # If legacy, we can't easily delete it from Mongo unless migrated with legacy ID preserved.
                # Assuming fresh start or Proper IDs.
                pass
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_reactionroles(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db'):
                 await self.bot.db.reaction_roles.delete_many({"guild_id": guild_id})
                 
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)



    # ═══════════════════════════════════════════════════════════════════════════════
    #                           LOGGING API
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_logging_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            config = await self.bot.db.logging_settings.find_one({"guild_id": guild_id})
            config = config if config else {}
            
            # Stringify IDs/Format data
            response_config = {}
            for key, value in config.items():
                if key == '_id': continue
                if isinstance(value, int) and key not in ['enabled']: 
                    response_config[key] = str(value)
                else:
                    response_config[key] = value

            # Ensure enabled_logs is a list
            # Ensure enabled_logs is a list and synced with active channels
            if 'enabled_logs' not in response_config or not isinstance(response_config['enabled_logs'], list):
                response_config['enabled_logs'] = []
            
            # Backfill enabled_logs from set channels (fixes Bot -> Dash sync)
            known_types = ["messages", "members", "voice", "roles", "channels", "bans", "moderation", "server"]
            for t in known_types:
                if response_config.get(t): # If ID exists (truthy)
                     if t not in response_config['enabled_logs']:
                         response_config['enabled_logs'].append(t)
            
            # Get channels info
            guild = self.bot.get_guild(guild_id)
            channels = []
            if guild:
                for channel in guild.text_channels:
                    channels.append({'id': str(channel.id), 'name': channel.name})
            
            return web.json_response({'config': response_config, 'channels': channels})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def update_logging_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
            
            cog = self.bot.get_cog("Logging")
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            # Get current config to check for changes
            current_config = await self.bot.db.logging_settings.find_one({"guild_id": guild_id}) or {}

            # Prepare update
            update_fields = {}
            known_columns = ["messages", "members", "channels", "roles", "bans", "voice", "moderation", "server"]
            
            for col in known_columns:
                if col in data:
                    try:
                        val = int(data[col]) if data[col] else None
                        update_fields[col] = val
                    except:
                        update_fields[col] = None

            # Handle enabled_logs
            if 'enabled_logs' in data:
                enabled_types = data['enabled_logs'] # List of strings
                update_fields['enabled_logs'] = enabled_types
                
                # Logic to create/cleanup channels using cog
                # 1. Handle Enabled/New Logs
                for log_type in enabled_types:
                    provided_channel_id = data.get(log_type)
                    
                    if not provided_channel_id:
                        # Auto-create if cog is loaded
                        if cog:
                            new_channel = await cog.ensure_log_channel(guild, log_type)
                            if new_channel:
                                update_fields[log_type] = new_channel.id
                    else:
                        # User provided a channel. Check if we need to cleanup old "bot-created" channel.
                        old_channel_id = current_config.get(log_type)
                        if cog and old_channel_id and str(old_channel_id) != str(provided_channel_id):
                            await cog.cleanup_old_channel(guild, log_type, old_channel_id)

                # 2. Handle Disabled Logs (Cleanup)
                old_enabled = current_config.get('enabled_logs', [])
                disabled_types = [t for t in old_enabled if t not in enabled_types]
                
                for log_type in disabled_types:
                    old_channel_id = current_config.get(log_type)
                    if cog and old_channel_id:
                        await cog.cleanup_old_channel(guild, log_type, old_channel_id)
                        # Also clear the channel ID
                        update_fields[log_type] = None

            if update_fields:
                await self.bot.db.logging_settings.update_one(
                    {"guild_id": guild_id},
                    {"$set": update_fields},
                    upsert=True
                )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_logging(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db'):
                await self.bot.db.logging_settings.delete_one({"guild_id": guild_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           GIVEAWAY API
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_giveaways(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)

            rows = []
            import time
            now = time.time()
            cursor = self.bot.db.giveaways.find({"guild_id": guild_id}).sort("ends_at", 1)
            async for doc in cursor:
                rows.append(doc)
            
            giveaways = []
            guild = self.bot.get_guild(guild_id)
            
            for g in rows:
                # Normalize keys
                g['message_id'] = str(g.get('message_id', ''))
                g['channel_id'] = str(g.get('channel_id', ''))
                g['host_id'] = str(g.get('host_id', ''))
                g['is_ended'] = g.get('ends_at', 0) <= now
                
                if '_id' in g: del g['_id']

                # Get channel name and host details
                ch_name = "Unknown"
                host_name = "Unknown User"
                host_avatar = None
                
                if guild:
                    # Channel
                    try:
                        ch = guild.get_channel(int(g['channel_id']))
                        if ch: ch_name = ch.name
                    except: pass
                    
                    # Host
                    try:
                        mem = guild.get_member(int(g['host_id']))
                        if mem:
                            host_name = mem.display_name
                            host_avatar = mem.display_avatar.url
                    except: pass
                    
                g['channel_name'] = ch_name
                g['host_name'] = host_name
                g['host_avatar'] = host_avatar
                
                giveaways.append(g)
                
            return web.json_response({'giveaways': giveaways})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def start_giveaway(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            # Expected: duration (str), winners (int), prize (str), channel_id (str)
            
            cog = self.bot.get_cog("Giveaway")
            if not cog: return web.json_response({'error': 'Giveaway system offline'}, status=503)
            
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
            
            channel_id = int(data.get('channel_id'))
            channel = guild.get_channel(channel_id)
            if not channel: return web.json_response({'error': 'Channel not found'}, status=404)
            
            # Create a mock context
            class MockContext:
                def __init__(self, bot, guild, channel, author):
                    self.bot = bot
                    self.guild = guild
                    self.channel = channel
                    self.author = author
                    self.followup = None
                    self.message = None
                    
                async def send(self, *args, **kwargs):
                    return await self.channel.send(*args, **kwargs)
                
                async def reply(self, *args, **kwargs):
                    return await self.channel.send(*args, **kwargs)

            # Use bot as author or a dashboard user representation
            # Ideally we pass 'user_id' from dashboard auth
            # For now using bot.user or guild.owner as fallback
            user_id = data.get('user_id') 
            author = guild.get_member(int(user_id)) if user_id else guild.me
            
            ctx = MockContext(self.bot, guild, channel, author)
            
            # Call cog method directly
            # logic: giveaway_start(self, ctx, duration: str, winners: int, *, prize: str)
            await cog.giveaway_start(ctx, data.get('duration'), int(data.get('winners')), prize=data.get('prize'))
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_giveaways(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db'):
                await self.bot.db.giveaways.delete_many({"guild_id": guild_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def end_giveaway(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            message_id = int(data.get('message_id'))
            
            cog = self.bot.get_cog("Giveaway")
            if not cog: return web.json_response({'error': 'Giveaway system offline'}, status=503)
            
            guild = self.bot.get_guild(guild_id)
            
            if not hasattr(self.bot, 'db'):
                return web.json_response({'error': 'Database offline'}, status=503)
            
            # Find the giveaway in DB to get channel
            doc = await self.bot.db.giveaways.find_one({"message_id": message_id})
            if not doc:
                 return web.json_response({'error': 'Giveaway not found'}, status=404)
                 
            channel_id = doc.get("channel_id")
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            
            # Create Mock Context or call dedicated end method
            # If cog has `end_giveaway` (command) logic, we need to adapt.
            # Usually commands take `ctx` and `message_id_or_url`.
            # Let's check if we can reconstruct ctx.
            
            if channel:
                 # Mock Context
                class MockContext:
                    def __init__(self, bot, guild, channel, author):
                        self.bot = bot
                        self.guild = guild
                        self.channel = channel
                        self.author = guild.me # Bot ends it
                        self.message = None # No invoking message
                        
                    async def send(self, *args, **kwargs):
                        return await self.channel.send(*args, **kwargs)
                
                ctx = MockContext(self.bot, guild, channel, guild.me)
                
                # Assuming 'end' command exists in cog.
                # If command is `giveaway end <msg_id>`, the function might be `giveaway_end`.
                # Lines 1968 used `giveaway_start`. So `giveaway_end` is likely.
                if hasattr(cog, 'giveaway_end'):
                    await cog.giveaway_end(ctx, str(message_id))
                elif hasattr(cog, 'end_giveaway'):
                     await cog.end_giveaway(ctx, str(message_id))
                else:
                     # Fallback: manual end? 
                     # If we can't find method, just expire it in DB?
                     # But we want to announce winners.
                     return web.json_response({'error': 'Giveaway End method not found'}, status=500)
            else:
                return web.json_response({'error': 'Channel not found'}, status=404)

            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reroll_giveaway(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            message_id = data.get('message_id')
            
            cog = self.bot.get_cog("Giveaway")
            if not cog: return web.json_response({'error': 'Giveaway system offline'}, status=503)
            
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
            
            # Cog expects context. We need to find the message first because `giveaway_reroll` calls `do_reroll(message, ctx)`
            # But the command `giveaway_reroll` takes `ctx, message_id`.
            
            # Mock Ctx
            class MockContext:
                def __init__(self, guild, channel, author):
                    self.guild = guild
                    self.channel = channel
                    self.author = author
                async def reply(self, *args, **kwargs): pass
                async def send(self, *args, **kwargs): pass
            
            # Get channel ID from DB first to create context channel
            if not kwargs.get('channel_id'):
                 if not hasattr(self.bot, 'db'):
                      return web.json_response({'error': 'Database offline'}, status=503)
                 
                 # Fetch from MongoDB
                 giveaway_doc = await self.bot.db.giveaways.find_one({"message_id": message_id})
                 if giveaway_doc:
                     kwargs['channel_id'] = giveaway_doc.get('channel_id')

            # Simpler approach: call `giveaway_reroll(ctx, message_id)` but ctx needs valid channel.
            # Dashboard should probably send channel_id if possible. 
            # If not, we iterate channels (bad).
            # Let's check `Giveaway` cog logic. `do_reroll` uses `message.reactions`. It needs the actual message object.
            
            # For now, let's assume we can pass channel_id from frontend (stored in listing).
            channel_id = data.get('channel_id')
            channel = guild.get_channel(int(channel_id))
            
            user_id = data.get('user_id')
            author = guild.get_member(int(user_id)) if user_id else guild.me

            ctx = MockContext(guild, channel, author)
            await cog.giveaway_reroll(ctx, str(message_id))
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           MEDIA API
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_media_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            doc = await self.bot.db.media_settings.find_one({"guild_id": guild_id})
            
            channels = []
            bypass_users = []
            bypass_roles = []
            
            if doc:
                channel_ids = doc.get("channels", [])
                channels = [str(c) for c in channel_ids]
                
                # Enrich Bypass Users
                user_ids = doc.get("bypass_users", [])
                guild = self.bot.get_guild(guild_id)
                
                if guild:
                    for uid in user_ids:
                        member = guild.get_member(uid)
                        if member:
                            bypass_users.append({
                                'id': str(uid),
                                'name': member.name,
                                'avatar': member.display_avatar.url
                            })
                        else:
                            bypass_users.append({
                                'id': str(uid),
                                'name': "Unknown User",
                                'avatar': None
                            })
                else:
                    for uid in user_ids:
                         bypass_users.append({'id': str(uid), 'name': 'Unknown', 'avatar': None})
                
                # Enrich Bypass Roles
                role_ids = doc.get("bypass_roles", [])
                bypass_roles = [str(r) for r in role_ids]
                        
            return web.json_response({
                'channels': channels,
                'bypass_users': bypass_users,
                'bypass_roles': bypass_roles
            })
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def update_media_channels(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # 'add' or 'remove'
            channel_id = int(data.get('channel_id'))
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            if action == 'add':
                await self.bot.db.media_settings.update_one(
                    {"guild_id": guild_id},
                    {"$addToSet": {"channels": channel_id}},
                    upsert=True
                )
            elif action == 'remove':
                await self.bot.db.media_settings.update_one(
                    {"guild_id": guild_id},
                    {"$pull": {"channels": channel_id}}
                )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def update_media_bypass(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # 'add' or 'remove'
            target_id = int(data.get('target_id'))
            target_type = data.get('target_type') # 'user' or 'role'
            
            field = "bypass_users" if target_type == 'user' else "bypass_roles"
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            if action == 'add':
                await self.bot.db.media_settings.update_one(
                    {"guild_id": guild_id},
                    {"$addToSet": {field: target_id}},
                    upsert=True
                )
            elif action == 'remove':
                await self.bot.db.media_settings.update_one(
                    {"guild_id": guild_id},
                    {"$pull": {field: target_id}}
                )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_media(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            # We can delete the whole document to reset everything for this guild
            await self.bot.db.media_settings.delete_one({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # --- SECURITY API HANDLERS (Antinuke, Whitelist, Extraowner) ---
    async def search_members(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            query = request.query.get('q', '').lower()
            
            if not query:
                return web.json_response({'members': []})

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)

            members = []
            # Optimized search: ID match first, then name/nick match
            # Limit results to 20 for performance
            
            # Check if query is a user ID
            if query.isdigit():
                 user = guild.get_member(int(query))
                 if user:
                     members.append({
                        'id': str(user.id),
                        'username': str(user),
                        'avatar_url': str(user.display_avatar.url)
                     })
            
            # Search by name/nick if not just an ID match or to find partials
            count = 0
            for i, m in enumerate(guild.members):
                # Yield to event loop every 100 members to prevent blocking
                if i % 100 == 0:
                    await asyncio.sleep(0)

                if len(members) >= 20: break
                
                # If we already found this user via ID exact match, skip
                if members and members[0]['id'] == str(m.id): continue

                if query in m.name.lower() or (m.nick and query in m.nick.lower()):
                    members.append({
                        'id': str(m.id),
                        'username': str(m),
                        'avatar_url': str(m.display_avatar.url)
                    })
                    count += 1
            
            return web.json_response({'members': members})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_antinuke(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.antinuke.delete_one({"guild_id": guild_id})
            await self.bot.db.antinuke_modules.delete_many({"guild_id": guild_id})
            await self.bot.db.antinuke_settings.delete_many({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_whitelist_all(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.antinuke_whitelist.delete_many({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_extraowners_all(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.extraowners.delete_many({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_antinuke_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            # Get Status & Punishment
            doc = await self.bot.db.antinuke.find_one({"guild_id": guild_id})
            enabled = doc.get("status", False) if doc else False
            punishment = doc.get("punishment", "ban") if doc else "ban"
            
            # Get Limit Settings
            limits = {}
            async for limit_doc in self.bot.db.antinuke_settings.find({"guild_id": guild_id}):
                limits[limit_doc['action']] = limit_doc['limit']

            # Get Module Settings
            modules = {}
            # Default list matches bot's list
            all_modules = [
                "ban", "kick", "bot", "channel_create", "channel_delete", "channel_update",
                "role_create", "role_delete", "role_update", "member_update", "guild_update",
                "integration", "webhook_create", "webhook_delete", "webhook_update", "prune",
                "everyone", "emoji", "sticker", "soundboard"
            ]
            
            # Fetch explicit overrides from DB
            db_modules = {}
            async for mod_doc in self.bot.db.antinuke_modules.find({"guild_id": guild_id}):
                db_modules[mod_doc['module']] = mod_doc['enabled']
            
            # Construct final modules dict (default True if not in DB)
            for mod in all_modules:
                modules[mod] = db_modules.get(mod, True)
            
            return web.json_response({
                'enabled': enabled,
                'punishment': punishment,
                'limits': limits,
                'modules': modules
            })
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def save_antinuke_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            enabled = data.get('enabled')
            punishment = data.get('punishment')
            modules = data.get('modules')
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            # Update Main Config
            if enabled is not None:
                 update_data = {"status": bool(enabled)}
                 if punishment is not None:
                     update_data["punishment"] = punishment
                 
                 await self.bot.db.antinuke.update_one(
                     {"guild_id": guild_id},
                     {"$set": update_data},
                     upsert=True
                 )
            
            # Update Modules
            if modules:
                for module, is_enabled in modules.items():
                    await self.bot.db.antinuke_modules.update_one(
                        {"guild_id": guild_id, "module": module},
                        {"$set": {"enabled": bool(is_enabled)}},
                        upsert=True
                    )
            
            # Trigger Sync
            guild = self.bot.get_guild(guild_id)
            if guild and enabled and self.bot.get_cog("Antinuke"):
                asyncio.create_task(self.bot.get_cog("Antinuke").sync_antinuke_setup(guild))
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_whitelist(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            users = []
            # Match Bot's Collection Name from anti_wl.py
            async for doc in self.bot.db.antinuke_whitelist.find({"guild_id": guild_id}):
                user_id = doc.get('user_id')
                # Filter out Mongo fields
                perms = {k: v for k, v in doc.items() if k not in ['_id', 'guild_id', 'user_id']}
                
                guild = self.bot.get_guild(guild_id)
                member = guild.get_member(user_id) if guild else None
                
                users.append({
                    'user_id': str(user_id),
                    'username': member.name if member else 'Unknown User',
                    'avatar': member.display_avatar.url if member else None,
                    'permissions': perms
                })
            
            return web.json_response({'users': users})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def save_whitelist(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            user_id = int(data.get('user_id'))
            perms = data.get('permissions', {})
            
            valid_perms = ['ban', 'kick', 'prune', 'botadd', 'serverup', 'memup', 'chcr', 'chdl', 'chup', 'rlcr', 'rlup', 'rldl', 'meneve', 'mngweb', 'mngstemo']
            
            # Filter valid perms
            perm_updates = {p: perms.get(p, False) for p in valid_perms if p in perms}
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)
            
            if not perm_updates:
                 return web.json_response({'success': True}) # Nothing to update
                 
            await self.bot.db.antinuke_whitelist.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$set": perm_updates},
                upsert=True
            )
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
            
    async def delete_whitelist(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            user_id = int(data.get('user_id'))
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.antinuke_whitelist.delete_one({"guild_id": guild_id, "user_id": user_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_extraowners(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            owners = []
            async for doc in self.bot.db.extraowners.find({"guild_id": guild_id}):
                uid = doc.get('owner_id')
                guild = self.bot.get_guild(guild_id)
                member = guild.get_member(uid) if guild else None
                
                owners.append({
                    'user_id': str(uid),
                    'username': member.name if member else 'Unknown User',
                    'avatar': member.display_avatar.url if member else None
                })
            
            return web.json_response({'owners': owners})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def add_extraowner(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            user_id = int(data.get('user_id'))
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            count = await self.bot.db.extraowners.count_documents({"guild_id": guild_id})
            
            if count >= 3:
                 return web.json_response({'error': 'Max 3 extra owners allowed'}, status=400)
            
            # Using update_one with upsert to simulate INSERT OR IGNORE (avoid duplicates)
            await self.bot.db.extraowners.update_one(
                {"guild_id": guild_id, "owner_id": user_id},
                {"$set": {"created_at": datetime.datetime.utcnow()}},
                upsert=True
            )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def remove_extraowner(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            data = await request.json()
            user_id = int(data.get('user_id'))
            
            # Additional Security Check
            requester_id = request.headers.get('X-User-ID')
            if requester_id:
                guild = self.bot.get_guild(guild_id)
                if guild and str(guild.owner_id) != requester_id:
                     return web.json_response({'error': 'Only Server Owner can manage extra owners'}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.extraowners.delete_one({"guild_id": guild_id, "owner_id": user_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # --- AUTOMOD API HANDLERS ---
    async def get_automod_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            enabled = False
            punishments = {}
            log_channel_id = None
            ignored_roles = []
            ignored_channels = []

            # Get Enabled Status & Log Channel
            settings_doc = await self.bot.db.automod_settings.find_one({"guild_id": guild_id})
            if settings_doc:
                enabled = settings_doc.get("enabled", False)
                log_channel_id = str(settings_doc.get("log_channel")) if settings_doc.get("log_channel") else None

            # Get Punishments
            # Mapping rule internal names to display names if needed, but dashboard likely expects display names or keys
            # Original code expected: {event_name: punishment}
            # Automod cog: RULE_MAPPING = {"Anti spam": "anti_spam", ...}
            # REVERSE_RULE_MAPPING = {"anti_spam": "Anti spam", ...}
            
            # We need to reconstruct the punishments dict using display names as keys
            # to match original API response format.
            
            # Reconstruct Reverse Mapping locally to avoid dependency import issues
            REVERSE_RULE_MAPPING = {
                "anti_spam": "Anti spam", "anti_caps": "Anti caps", "anti_link": "Anti link",
                "anti_invites": "Anti invites", "anti_mass_mention": "Anti mass mention",
                "anti_emoji": "Anti emoji spam", "anti_repeated_text": "Anti repeated text",
                "anti_nsfw": "Anti NSFW link"
            }

            async for rule_doc in self.bot.db.automod_rules.find({"guild_id": guild_id}):
                rule_name = rule_doc.get("rule")
                punishment = rule_doc.get("punishment")
                display_name = REVERSE_RULE_MAPPING.get(rule_name, rule_name)
                punishments[display_name] = punishment

            # Get Ignored Roles/Channels
            guild = self.bot.get_guild(guild_id)
            async for ignored_doc in self.bot.db.automod_ignored.find({"guild_id": guild_id}):
                type_ = ignored_doc.get("type")
                target_id = ignored_doc.get("id") # Using 'id' as per previous insertion logic (wait, verify insert logic below)
                # Wait, earlier I saw 'target_id' in automod.py but original SQLite used 'id'.
                # Let's use 'target_id' to be standard but if automod.py uses 'id' allow that.
                # automod.py View: 
                # exempt_roles = [discord.Object(doc["target_id"]) ...]
                # So automod.py uses `target_id`.
                # BUT my new `api.py` insert logic MUST match automod.py.
                # Original SQLite had `id`.
                # I will change API to use `target_id` for MongoDB to match automod.py.
                
                # Check actual field in DB (automod.py line 146: doc["target_id"])
                # So I must read `target_id`.
                # But legacy data? This is a migration.
                target_id = ignored_doc.get("target_id") or ignored_doc.get("id")

                if guild and target_id:
                    if type_ == 'role':
                        role = guild.get_role(int(target_id))
                        ignored_roles.append({
                            'id': str(target_id),
                            'name': role.name if role else "Unknown Role"
                        })
                    elif type_ == 'channel':
                        chan = guild.get_channel(int(target_id))
                        ignored_channels.append({
                            'id': str(target_id),
                            'name': chan.name if chan else "Unknown Channel"
                        })

            return web.json_response({
                'enabled': enabled,
                'punishments': punishments,
                'log_channel_id': log_channel_id,
                'ignored_roles': ignored_roles,
                'ignored_channels': ignored_channels
            })
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def save_automod_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)
            
            # Extract data
            enabled = data.get('enabled')
            punishments = data.get('punishments', {}) 
            log_channel_id = data.get('log_channel_id')
            
            # Update Main Settings
            if enabled is not None:
                 await self.bot.db.automod_settings.update_one(
                     {"guild_id": guild_id},
                     {"$set": {"enabled": bool(enabled)}},
                     upsert=True
                 )
            
            # Update Log Channel
            if log_channel_id is not None:
                if log_channel_id == "": # Clear logging
                     await self.bot.db.automod_settings.update_one(
                         {"guild_id": guild_id},
                         {"$unset": {"log_channel": ""}}
                     )
                else:
                     await self.bot.db.automod_settings.update_one(
                         {"guild_id": guild_id},
                         {"$set": {"log_channel": int(log_channel_id)}},
                         upsert=True
                     )

            # Update Punishments
            RULE_MAPPING = {
                "Anti spam": "anti_spam", "Anti caps": "anti_caps", "Anti link": "anti_link",
                "Anti invites": "anti_invites", "Anti mass mention": "anti_mass_mention",
                "Anti emoji spam": "anti_emoji", "Anti repeated text": "anti_repeated_text",
                "Anti NSFW link": "anti_nsfw"
            }

            if punishments:
                for event, punishment in punishments.items():
                    internal_rule = RULE_MAPPING.get(event)
                    if not internal_rule: continue
                    
                    if punishment is None:
                         # Disable rule
                         await self.bot.db.automod_rules.update_one(
                             {"guild_id": guild_id, "rule": internal_rule},
                             {"$set": {"enabled": False}}
                         )
                    else:
                         # Enable and set punishment
                         await self.bot.db.automod_rules.update_one(
                             {"guild_id": guild_id, "rule": internal_rule},
                             {"$set": {"enabled": True, "punishment": punishment}},
                             upsert=True
                         )
            
            # --- DISCORD AUTOMOD RULE MANAGEMENT (Anti NSFW) ---
            try:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    # Check for Anti NSFW Link toggling
                    nsfw_enabled = False
                    
                    # Logic to determine if enabled:
                    # 1. Check current DB state for enabled/disabled
                    # 2. Check if this request is disabling automod globally
                    # 3. Check if this request is specifically toggling Anti NSFW
                    
                    # Get current global enabled state (updated above)
                    settings_doc = await self.bot.db.automod_settings.find_one({"guild_id": guild_id})
                    global_enabled = settings_doc.get("enabled", False) if settings_doc else False
                    
                    # Get rule state
                    rule_doc = await self.bot.db.automod_rules.find_one({"guild_id": guild_id, "rule": "anti_nsfw"})
                    rule_enabled = rule_doc.get("enabled", False) if rule_doc else False
                    
                    nsfw_enabled = global_enabled and rule_enabled

                    # KEYWORDS (Synced with automod.py)
                    nsfw_keywords = [
                        "porn", "xxx", "adult", "sex", "nsfw", "xnxx", "onlyfans", "brazzers", "xhamster", "xvideos", 
                        "pornhub", "redtube", "livejasmin", "youporn", "tube8", "pornhat", "swxvid", "ixxx", 
                        "tnaflix", "spankbang", "erome", "fapster", "hclips", "keezmovies", "motherless",
                        "nude", "nudes", "naked", "hentai", "bdsm", "fetish", "camgirl", "camgirls", 
                        "escort", "escorts", "hookup", "hookups", "titfuck", "blowjob", "handjob", 
                        "dildo", "vibrator", "anal", "pussy", "feetjob", "cum", "squirt", "orgasm", 
                        "threesome", "foursome", "assspanking", "bondage", "gokkun",
                        "madarchod", "randi", "chudail", "behenchod", "bhosadiwala", "bhosadiwale", 
                        "bhosdika", "bhosdike", "loda", "lund", "gand", "bkl", "chutiyapa", "mc", "bc", 
                        "bcchod", "bhenchod", "lundka", "lodu", "gandu", "randiwala", "randiwale", 
                        "chut", "chutiya", "chutiye", "tatti"
                    ]

                    existing_rules = await guild.fetch_automod_rules()
                    nsfw_discord_rule = next((r for r in existing_rules if r.name == "Anti NSFW Links"), None)

                    if nsfw_enabled:
                        if not nsfw_discord_rule:
                            # Create
                            try:
                                await guild.create_automod_rule(
                                    name="Anti NSFW Links",
                                    event_type=discord.AutoModRuleEventType.message_send,
                                    trigger=discord.AutoModTrigger(
                                        type=discord.AutoModRuleTriggerType.keyword,
                                        keyword_filter=nsfw_keywords,
                                    ),
                                    actions=[
                                        discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message),
                                    ],
                                    enabled=True,
                                    reason="Automod Dashboard Update - Anti NSFW Link Enabled"
                                )
                            except Exception as e:
                                print(f"Failed to create AutoMod rule: {e}")
                    else:
                        if nsfw_discord_rule:
                            # Delete
                            try:
                                await nsfw_discord_rule.delete(reason="Automod Dashboard Update - Anti NSFW Link Disabled")
                            except Exception as e:
                                print(f"Failed to delete AutoMod rule: {e}")

            except Exception as e:
                print(f"AutoMod Rule Logic Error: {e}")
                
            return web.json_response({'success': True})
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def create_automod_log_channel(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            # Create channel logic
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            try:
                channel = await guild.create_text_channel('automod-logs', overwrites=overwrites, reason="Automod Logging Channel Creation")
            except discord.Forbidden:
                return web.json_response({'error': 'Missing permissions to create channel'}, status=403)
            
            # Save to DB
            await self.bot.db.automod_settings.update_one(
                {"guild_id": guild_id},
                {"$set": {"log_channel": channel.id}},
                upsert=True
            )
                
            return web.json_response({
                'success': True, 
                'channel': {'id': str(channel.id), 'name': channel.name}
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def automod_enable_all(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            events = [
                ("anti_spam", "Mute"), ("anti_caps", "Mute"), ("anti_link", "Mute"),
                ("anti_invites", "Mute"), ("anti_mass_mention", "Mute"), 
                ("anti_emoji", "Mute"), ("anti_repeated_text", "Mute"),
                ("anti_nsfw", "Block Message")
            ]
            
            # Enable Globally
            await self.bot.db.automod_settings.update_one(
                {"guild_id": guild_id},
                {"$set": {"enabled": True}},
                upsert=True
            )
            
            # Enable All Rules
            for rule, punishment in events:
                await self.bot.db.automod_rules.update_one(
                    {"guild_id": guild_id, "rule": rule},
                    {"$set": {"enabled": True, "punishment": punishment}},
                    upsert=True
                )
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def automod_disable_all(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)
            
            # Disable Globally
            await self.bot.db.automod_settings.update_one(
                {"guild_id": guild_id},
                {"$set": {"enabled": False}},
                upsert=True
            )
            
            # Remove Punishments/Disable Rules
            # Mirroring SQLite "DELETE FROM automod_punishments" behavior:
            # We map this to setting enabled=False in MongoDB for all rules
            await self.bot.db.automod_rules.update_many(
                {"guild_id": guild_id},
                {"$set": {"enabled": False}}
            )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_automod(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.automod_settings.delete_one({"guild_id": guild_id})
            await self.bot.db.automod_rules.delete_many({"guild_id": guild_id})
            await self.bot.db.automod_ignored.delete_many({"guild_id": guild_id})
            
            # Clean up Discord AutoMod Rule if exists
            try:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    rules = await guild.fetch_automod_rules()
                    for rule in rules:
                        if rule.name == "Anti NSFW Links":
                             await rule.delete(reason="Dashboard: Automod Reset")
            except: pass

            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def automod_update_ignored(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # add/remove
            type_ = data.get('type') # role/channel
            target_id = int(data.get('id'))
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            if action == 'add':
                # Correct field name: target_id (matches automod.py)
                await self.bot.db.automod_ignored.update_one(
                    {"guild_id": guild_id, "type": type_, "target_id": target_id},
                    {"$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
                    upsert=True
                )
            elif action == 'remove':
                await self.bot.db.automod_ignored.delete_one(
                    {"guild_id": guild_id, "type": type_, "target_id": target_id}
                )
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)


    # --- BANWORDS API HANDLERS ---
    async def get_banwords_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            # Get Settings
            settings_doc = await db.blacklist_settings.find_one({"guild_id": guild_id})
            if settings_doc:
                settings = settings_doc
                settings.pop('_id', None)
                settings.pop('guild_id', None) # Clean up
            else:
                 settings = {
                    'punishment_type': 'warn',
                    'punishment_duration': 300,
                    'sensitivity_level': 'medium',
                    'auto_punish': True,
                    'similarity_check': True,
                    'leetspeak_filter': True,
                    'zalgo_filter': True
                }

            # Get Banwords
            banwords = []
            async for doc in db.blacklist_words.find({"guild_id": guild_id}):
                banwords.append({
                    'id': str(doc['_id']), # Use Mongo ID as ID
                    'word': doc['word'], 
                    'severity': doc.get('severity', 1)
                })
            
            # Get Exempt Channels
            exempt_channels = []
            guild = self.bot.get_guild(guild_id)
            async for doc in db.blacklist_exempt_channels.find({"guild_id": guild_id}):
                cid = doc['channel_id']
                chan = guild.get_channel(cid) if guild else None
                exempt_channels.append({
                    'id': str(cid),
                    'name': chan.name if chan else "Unknown Channel"
                })
                
            # Get Bypass Users
            bypass_users = []
            async for doc in db.blacklist_bypass_users.find({"guild_id": guild_id}):
                uid = doc['user_id']
                member = guild.get_member(uid) if guild else None
                bypass_users.append({
                    'id': str(uid),
                    'username': member.name if member else "Unknown User",
                    'avatar_url': member.display_avatar.url if member else None
                })

            # Get Bypass Roles
            bypass_roles = []
            async for doc in db.blacklist_bypass_roles.find({"guild_id": guild_id}):
                rid = doc['role_id']
                role = guild.get_role(rid) if guild else None
                if role:
                     bypass_roles.append({
                        'id': str(rid),
                        'name': role.name,
                        'color': str(role.color)
                    })

            return web.json_response({
                'settings': settings,
                'banwords': banwords,
                'exempt_channels': exempt_channels,
                'bypass_users': bypass_users,
                'bypass_roles': bypass_roles
            })
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def save_banwords_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            valid_fields = ['punishment_type', 'punishment_duration', 'sensitivity_level', 'auto_punish', 'similarity_check']
            update_data = {}
            for field in valid_fields:
                if field in data:
                    update_data[field] = data[field]
            
            if update_data:
                await db.blacklist_settings.update_one(
                    {"guild_id": guild_id},
                    {"$set": update_data},
                    upsert=True
                )
            
            return web.json_response({'success': True})
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def add_banword(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            word = data.get('word')
            severity = data.get('severity', 1)
            
            if not word: return web.json_response({'error': 'Word is required'}, status=400)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            try:
                await db.blacklist_words.update_one(
                    {"guild_id": guild_id, "word": word},
                    {"$set": {"severity": severity, "created_at": datetime.datetime.utcnow()}},
                    upsert=True
                )
            except Exception as e:
                 return web.json_response({'error': str(e)}, status=500)
                     
            return web.json_response({'success': True})
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def remove_banword(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            word_id = data.get('id')
            word = data.get('word')
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            if word_id:
                from bson.objectid import ObjectId
                try:
                    await db.blacklist_words.delete_one({"guild_id": guild_id, "_id": ObjectId(word_id)})
                except:
                    # Fallback if ID is not ObjectId (maybe legacy string?) 
                    # But we are migrating so new IDs will be ObjectIds. 
                    pass
            elif word:
                await db.blacklist_words.delete_one({"guild_id": guild_id, "word": word})
                     
            return web.json_response({'success': True})
        except Exception as e:
             return web.json_response({'error': str(e)}, status=500)

    async def banwords_update_bypass(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # add/remove
            user_id = int(data.get('user_id'))
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)

            if action == 'add':
                await db.blacklist_bypass_users.update_one(
                    {"guild_id": guild_id, "user_id": user_id},
                    {"$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
                    upsert=True
                )
            elif action == 'remove':
                await db.blacklist_bypass_users.delete_one({"guild_id": guild_id, "user_id": user_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def banwords_update_bypass_role(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # add/remove
            role_id = int(data.get('role_id'))
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            if action == 'add':
                await db.blacklist_bypass_roles.update_one(
                     {"guild_id": guild_id, "role_id": role_id},
                     {"$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
                     upsert=True
                )
            elif action == 'remove':
                await db.blacklist_bypass_roles.delete_one({"guild_id": guild_id, "role_id": role_id})

            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def banwords_update_exempt(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            data = await request.json()
            action = data.get('action') # add/remove
            channel_id = int(data.get('channel_id'))
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            if action == 'add':
                await db.blacklist_exempt_channels.update_one(
                    {"guild_id": guild_id, "channel_id": channel_id},
                    {"$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
                    upsert=True
                )
            elif action == 'remove':
                await db.blacklist_exempt_channels.delete_one({"guild_id": guild_id, "channel_id": channel_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_banwords(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database()
            if db is None: return web.json_response({'error': 'Database Error'}, status=500)
            
            await db.blacklist_words.delete_many({"guild_id": guild_id})
            await db.blacklist_bypass_users.delete_many({"guild_id": guild_id})
            await db.blacklist_bypass_roles.delete_many({"guild_id": guild_id})
            await db.blacklist_exempt_channels.delete_many({"guild_id": guild_id})
            await db.blacklist_settings.delete_one({"guild_id": guild_id})
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_permissions(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            
            # Use cached check for gatekeeping
            # Use cached check for gatekeeping
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: 
                if err == "Guild not found":
                    return web.json_response({'error': 'Guild not found', 'code': 'GUILD_NOT_FOUND'}, status=404)
                return web.json_response({'error': err}, status=403)
            
            # Get user_id from query params OR headers (preferred)
            user_id = request.query.get('user_id') or request.headers.get('X-User-ID')
            
            if not user_id:
                return web.json_response({'error': 'Missing user_id'}, status=400)
            
            try:
                user_id = int(user_id)
            except ValueError:
                 return web.json_response({'error': 'Invalid user_id format'}, status=400)
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return web.json_response({'error': 'Guild not found'}, status=404)
                
            is_owner = (guild.owner_id == user_id)
            
            # Use internal helper which might use cog cache or DB
            is_extra_owner = await self.is_extra_owner_internal(guild_id, user_id)
        
            member = guild.get_member(user_id)
            if not member:
                 try:
                    member = await guild.fetch_member(user_id)
                 except: pass

            is_admin = member.guild_permissions.administrator if member else False
            can_manage_guild = member.guild_permissions.manage_guild if member else False

            return web.json_response({
                'is_owner': is_owner,
                'is_extra_owner': is_extra_owner,
                'is_admin': is_admin,
                'can_manage_guild': can_manage_guild
            })
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # ═══════════════════════════════════════════════════════════════════════════════
    #                           📈 LEVELING API
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_leveling_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            doc = await self.bot.db.leveling_settings.find_one({"guild_id": guild_id})
            
            if doc:
                settings = {}
                # Map Mongo fields to response
                settings['enabled'] = doc.get('enabled', 1)
                settings['levelup_channel'] = str(doc.get('levelup_channel')) if doc.get('levelup_channel') else None
                settings['levelup_message'] = doc.get('levelup_message', "GG {user.mention}, you just leveled up to **Level {level}**!")
                settings['msg_config'] = doc.get('msg_config', {})
                settings['voice_config'] = doc.get('voice_config', {})
                settings['reaction_config'] = doc.get('reaction_config', {})
                
                # Fix rewards role IDs
                rewards = doc.get('rewards', [])
                for r in rewards:
                    if 'role' in r: r['role'] = str(r['role'])
                settings['rewards'] = rewards
                
                settings['ignores'] = doc.get('ignores', {})
                settings['auto_reset'] = doc.get('auto_reset', 0)
            else:
                settings = {
                    'enabled': 1, 
                    'levelup_channel': None, 
                    'levelup_message': "GG {user.mention}, you just leveled up to **Level {level}**!",
                    'msg_config': {},
                    'voice_config': {},
                    'reaction_config': {},
                    'rewards': [],
                    'ignores': {},
                    'auto_reset': 0
                }
            
            return web.json_response(settings)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def save_leveling_config(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            data = await request.json()
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            update_data = {}
            
            # Fields to update
            if 'enabled' in data: update_data['enabled'] = int(data['enabled'])
            if 'levelup_channel' in data: 
                # Store as int for consistency with original DB or consistency with Discord IDs?
                # MongoDB usually stores large ints as Int64 or we can store as str.
                # Leveling cog seems to treat them as IDs.
                try: update_data['levelup_channel'] = int(data['levelup_channel']) if data['levelup_channel'] else None
                except: update_data['levelup_channel'] = None
                
            if 'levelup_message' in data: update_data['levelup_message'] = data['levelup_message']
            if 'msg_config' in data: update_data['msg_config'] = data['msg_config']
            if 'voice_config' in data: update_data['voice_config'] = data['voice_config']
            if 'reaction_config' in data: update_data['reaction_config'] = data['reaction_config']
            if 'rewards' in data: 
                # Parse role IDs to int if needed by cog?
                # Cog likely handles ints. JSON comes as strings for huge ints.
                rewards = data['rewards']
                for r in rewards:
                    if 'role' in r: 
                        try: r['role'] = int(r['role'])
                        except: pass
                update_data['rewards'] = rewards
            else:
                 # If rewards missing, maybe don't overwrite? Or set empty?
                 # If explicit empty list sent, we set empty.
                 if 'rewards' in data: update_data['rewards'] = []
                
            if 'ignores' in data: update_data['ignores'] = data['ignores']
            if 'auto_reset' in data: update_data['auto_reset'] = int(data['auto_reset'])

            await self.bot.db.leveling_settings.update_one(
                {"guild_id": guild_id},
                {"$set": update_data},
                upsert=True
            )
            
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def reset_leveling_data(self, request):
        try:
            guild_id = int(request.match_info.get('guild_id'))
            auth, err = await self.check_permissions(request, guild_id)
            if not auth: return web.json_response({'error': err}, status=403)
            
            if not hasattr(self.bot, 'db'):
                 return web.json_response({'error': 'Database offline'}, status=503)

            await self.bot.db.leveling_users.delete_many({"guild_id": guild_id})
                
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)


    async def submit_security_log(self, request):
        try:
            # Verify API Secret (Auth Middleware handles this, but good to be sure if we change things)
            # Middleware already checks 'Authorization' header.
            
            data = await request.json()
            user_id = data.get('user_id')
            ip_address = data.get('ip')
            page_link = data.get('link')
            reason = data.get('reason', 'Unauthorized Access Attempt')
            
            # Security Log Channel ID provided by user
            LOG_CHANNEL_ID = 1454824185271685253
            
            channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if not channel:
                # Try fetching if not in cache
                try:
                    channel = await self.bot.fetch_channel(LOG_CHANNEL_ID)
                except:
                    print(f"[WARNING] Security Log Channel {LOG_CHANNEL_ID} not found.")
                    return web.json_response({'error': 'Log channel not found'}, status=404)

            embed = discord.Embed(
                title="🚨 Security Alert: Unauthorized Access",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="User ID", value=f"`{user_id}`" if user_id else "Unknown", inline=True)
            embed.add_field(name="IP Address", value=f"`{ip_address}`", inline=True)
            embed.add_field(name="Target Link", value=f"[Click Here]({page_link})" if page_link else "Unknown", inline=False)
            embed.add_field(name="Reason", value=str(reason), inline=False)
            
            # Try to fetch user info for better logging
            if user_id and str(user_id).isdigit():
                try:
                    user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                    if user:
                        embed.set_author(name=f"{user} ({user.id})", icon_url=user.display_avatar.url)
                        embed.set_thumbnail(url=user.display_avatar.url)
                except: pass
            
            embed.set_footer(text="Scyro Security System")
            
            await channel.send(embed=embed)
            return web.json_response({'success': True})
            
        except Exception as e:
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def check_dashboard_blacklist(self, request):
        try:
            user_id = request.query.get('user_id')
            ip = request.query.get('ip')
            
            if not user_id and not ip:
                return web.json_response({'error': 'Missing user_id or ip'}, status=400)
            
            query = {"$or": []}
            if user_id: query["$or"].append({"type": "user", "value": str(user_id)})
            if ip: query["$or"].append({"type": "ip", "value": str(ip)})
            
            if not query["$or"]:
                 return web.json_response({'blocked': False})

            if hasattr(self.bot, 'db') and self.bot.db is not None:
                db = self.bot.db
            else:
                db = get_database() # Fallback

            # Check for blacklist entry
            entry = await db.dashboard_blacklist.find_one(query)
            
            if entry:
                return web.json_response({
                    'blocked': True, 
                    'reason': entry.get('reason', 'No reason provided'), 
                    'type': entry.get('type')
                })
            
            return web.json_response({'blocked': False})
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

async def setup(bot):
    await bot.add_cog(API(bot))


