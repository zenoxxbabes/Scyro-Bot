# --- AUTOMATION API HANDLERS ---

# Autorole
async def get_autorole(self, request):
    try:
        guild_id = int(request.match_info.get('guild_id'))
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)

        doc = await self.bot.db.autoroles.find_one({"guild_id": guild_id})
        
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
        
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        await self.bot.db.autoroles.update_one(
            {"guild_id": guild_id},
            {"$set": {
                "bots": data.get('bots'),
                "humans": data.get('humans'),
                "boosters": data.get('boosters'),
                "enabled": bool(data.get('enabled', False))
            }},
            upsert=True
        )
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

# Autoreact
async def get_autoreact(self, request):
    try:
        guild_id = int(request.match_info.get('guild_id'))
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        cursor = self.bot.db.autoreacts.find({"guild_id": guild_id})
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
            emoji = discord.PartialEmoji.from_str(emojistr)
            emoji_to_store = str(emoji)
        except:
            return web.json_response({'error': 'Invalid emoji provided'}, status=400)
            
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        await self.bot.db.autoreacts.update_one(
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
        data = await request.json()
        trigger = data.get('trigger', '').strip().lower()
        
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        await self.bot.db.autoreacts.delete_one({"guild_id": guild_id, "trigger": trigger})
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

# Autoresponder
async def get_autoresponder(self, request):
    try:
        guild_id = int(request.match_info.get('guild_id'))
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        cursor = self.bot.db.autoresponders.find({"guild_id": guild_id})
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
            
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        await self.bot.db.autoresponders.update_one(
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
        data = await request.json()
        trigger = data.get('trigger', '').strip().lower()
        
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)
        
        await self.bot.db.autoresponders.delete_one({"guild_id": guild_id, "trigger": trigger})
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
        message_id = int(data.get('message_id'))
        emoji = data.get('emoji')
        role_id = int(data.get('role_id'))
        
        guild = self.bot.get_guild(guild_id)
        if not guild: return web.json_response({'error': 'Guild not found'}, status=404)
        
        if not hasattr(self.bot, 'db'):
            return web.json_response({'error': 'Database offline'}, status=503)

        await self.bot.db.reaction_roles.update_one(
            {"guild_id": guild_id, "message_id": message_id, "emoji": emoji},
            {"$set": {"role_id": role_id}},
            upsert=True
        )
        return web.json_response({'success': True})
    except Exception as e:
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
            pass
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)
