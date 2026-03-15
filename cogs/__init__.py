from __future__ import annotations
from core import Scyro
from colorama import Fore, Style, init
import datetime


#----------Commands---------#
from .commands.general import General
from .commands.automod import Automod
from .commands.welcome import Welcomer
from .commands.fun import Fun
from .commands.extra import Extra
from .commands.owner import Owner
from .commands.afk import afk
from .commands.ignore import Ignore
from .commands.Media import Media
from .commands.Invc import Invcrole
from .commands.giveaway import Giveaway
from .commands.Embed import Embed
from .commands.blacklist import Blacklist
from .commands.block import Block
from .commands.nightmode import Nightmode
from .commands.owner import Badges
from .commands.autoresponder import AutoResponder
from .commands.customrole import Customrole
from .commands.customprofile import CustomProfile
from .commands.autorole import AutoRole
from .commands.reactionrole import ReactionRole
from .commands.tempvc import TempVC
from .commands.emote import Emoji
from .commands.help import Help
from .commands.antinuke import Antinuke
from .commands.extraown import Extraowner
from .commands.anti_wl import Whitelist
from .commands.anti_unwl import Unwhitelist
from .commands.emergency import Emergency
from .commands.notify import NotifCommands
from .commands.status import Status
from .commands.np import NoPrefix
from .commands.owner2 import Global
from .commands.ticket import TicketSetup
from .commands.automodrule import AutoModRule
# from .commands.activity import Activity
from .commands.logging import Logging
from .commands.premium import Premium
# from .commands.help import Help
from .commands.music import Music
from .commands.verify import Verification
from .commands.tracker import Tracker
from .commands.autoreact import Autoreact
from .commands.leveling import Leveling
from .commands.sticky import Sticky
from .stats import Stats
from .api import API


#____________ Events _____________

from .events.autoblacklist import AutoBlacklist
from .events.Errors import Errors
from .events.on_guild import Guild
from .events.auto import Autorole
from .events.mention import Mention
#from .events.topgg import TopGG
# from .commands.ticket import TicketCreationView,TicketManagementView

########-------HELP-------########
from .Scyro.security import _antinuke
from .Scyro.extra import _extra
from .Scyro.general import _general
from .Scyro.automod import _automod 
from .Scyro.moderation import _moderation
from .Scyro.fun import _fun
from .Scyro.ignore import _ignore
from .Scyro.management import _server
from .Scyro.welcome import _welcome 
from .Scyro.giveaway import _giveaway
from .Scyro.logging import _logs
from .Scyro.ticket import _ticket
from .Scyro.media import _media


#########ANTINUKE#########

from .antinuke.anti_member_update import AntiMemberUpdate
from .antinuke.antiban import AntiBan
from .antinuke.antibotadd import AntiBotAdd
from .antinuke.antichcr import AntiChannelCreate
from .antinuke.antichdl import AntiChannelDelete
from .antinuke.antichup import AntiChannelUpdate
from .antinuke.antieveryone import AntiEveryone
from .antinuke.antiguild import AntiGuildUpdate
from .antinuke.antiIntegration import AntiIntegration
from .antinuke.antikick import AntiKick
from .antinuke.antiprune import AntiPrune
from .antinuke.antirlcr import AntiRoleCreate
from .antinuke.antirldl import AntiRoleDelete
from .antinuke.antirlup import AntiRoleUpdate
from .antinuke.antiwebhook import AntiWebhookUpdate
from .antinuke.antiwebhookcr import AntiWebhookCreate
from .antinuke.antiwebhookdl import AntiWebhookDelete

#Extra Optional Events 

#from .antinuke.antiemocr import AntiEmojiCreate
#from .antinuke.antiemodl import AntiEmojiDelete
#from .antinuke.antiemoup import AntiEmojiUpdate
from .antinuke.antiemoji import AntiEmoji
from .antinuke.antisticker import AntiSticker
from .antinuke.antisoundboard import AntiSoundboard
from .antinuke.antiunban import AntiUnban

############ AUTOMOD ############
from .automod.antispam import AntiSpam
from .automod.anticaps import AntiCaps
from .automod.antilink import AntiLink
from .automod.anti_invites import AntiInvite
from .automod.anti_mass_mention import AntiMassMention
from .automod.anti_emoji_spam import AntiEmojiSpam


from .moderation.ban import Ban
from .moderation.unban import Unban
from .moderation.timeout import Mute
from .moderation.unmute import Unmute
from .moderation.lock import Lock
from .moderation.unlock import Unlock
from .moderation.hide import Hide
from .moderation.unhide import Unhide
from .moderation.kick import Kick
from .moderation.warn import Warn
from .moderation.role import Role
from .moderation.message import Message
from .moderation.moderation import Moderation
from .moderation.topcheck import TopCheck
from .moderation.snipe import Snipe


async def setup(bot: Scyro):
  cogs_to_load = [
        General, Moderation, Automod, Welcomer, Fun, Extra,
         Owner, Customrole, afk, Embed, Media, Ignore,
        Invcrole, Logging,
        Blacklist, Block, Nightmode,  Badges, Antinuke, Whitelist, 
        Unwhitelist, Extraowner,
        AutoBlacklist, Guild, Errors, Autorole, AutoResponder,
        Mention, AutoRole, AntiMemberUpdate, AntiBan, AntiBotAdd,
        AntiChannelCreate, AntiChannelDelete, AntiChannelUpdate, AntiEveryone, AntiGuildUpdate,
        AntiIntegration, AntiKick, AntiPrune, AntiRoleCreate, AntiRoleDelete,
        AntiRoleUpdate, AntiWebhookUpdate, AntiWebhookCreate,
        AntiWebhookDelete, AntiSpam, AntiCaps, AntiLink, AntiInvite, AntiMassMention, Emergency, Status, NoPrefix, Ban, Unban, Mute, Unmute, Lock, Unlock, Hide, Unhide, Kick, Warn, Role, Message, Moderation, TopCheck, Snipe, Global, TicketSetup, Premium, TempVC, Emoji, Music, Verification, Tracker, AutoModRule
    ]

  await bot.add_cog(Tracker(bot))
  await bot.add_cog(Autoreact(bot))
  await bot.add_cog(API(bot))
  await bot.add_cog(Stats(bot))


  await bot.add_cog(General(bot))
  await bot.add_cog(Automod(bot))
  await bot.add_cog(Welcomer(bot))
  await bot.add_cog(Fun(bot))
  await bot.add_cog(Extra(bot))
  await bot.add_cog(Owner(bot))
  await bot.add_cog(Customrole(bot))
  await bot.add_cog(CustomProfile(bot))
  await bot.add_cog(afk(bot))
  await bot.add_cog(Embed(bot))
  await bot.add_cog(Media(bot))
  await bot.add_cog(Ignore(bot))
  await bot.add_cog(Invcrole(bot))
  await bot.add_cog(Giveaway(bot))
  await bot.add_cog(Blacklist(bot))
  await bot.add_cog(Block(bot))
  await bot.add_cog(Nightmode(bot))
  await bot.add_cog(Badges(bot))
  await bot.add_cog(Antinuke(bot))
  await bot.add_cog(Whitelist(bot))
  await bot.add_cog(Unwhitelist(bot))
  await bot.add_cog(Extraowner(bot))
  await bot.add_cog(Emergency(bot))
  await bot.add_cog(Status(bot))
  await bot.add_cog(NoPrefix(bot))
  await bot.add_cog(Global(bot))
  await bot.add_cog(TicketSetup(bot))
  await bot.add_cog(AutoModRule(bot))
  #await bot.add_cog(Activity(bot))
  await bot.add_cog(Logging(bot))
  await bot.add_cog(Premium(bot))
  await bot.add_cog(ReactionRole(bot))
  await bot.add_cog(Help(bot))
  await bot.add_cog(TempVC(bot))
  await bot.add_cog(Emoji(bot))
  await bot.add_cog(Music(bot))
  await bot.add_cog(_antinuke(bot))
  await bot.add_cog(_extra(bot))
  await bot.add_cog(_media(bot))
  await bot.add_cog(_general(bot))
  await bot.add_cog(_automod(bot))  
  await bot.add_cog(_moderation(bot))
  await bot.add_cog(_fun(bot))
  await bot.add_cog(_ignore(bot))
  await bot.add_cog(_server(bot))
  await bot.add_cog(_welcome(bot))
  await bot.add_cog(_giveaway(bot))
  await bot.add_cog(_logs(bot))
  await bot.add_cog(_ticket(bot))

  




  
  await bot.add_cog(AutoBlacklist(bot))
  await bot.add_cog(Guild(bot))
  await bot.add_cog(Errors(bot))
  await bot.add_cog(Autorole(bot))
  # await bot.add_cog(greet(bot))  # Removed to prevent duplicate welcome messages
  await bot.add_cog(AutoResponder(bot))
  await bot.add_cog(Mention(bot))
  await bot.add_cog(AutoRole(bot))
  await bot.add_cog(NotifCommands(bot))


  await bot.add_cog(AntiMemberUpdate(bot))
  await bot.add_cog(AntiBan(bot))
  await bot.add_cog(AntiBotAdd(bot))
  await bot.add_cog(AntiChannelCreate(bot))
  await bot.add_cog(AntiChannelDelete(bot))
  await bot.add_cog(AntiChannelUpdate(bot))
  await bot.add_cog(AntiEveryone(bot))
  await bot.add_cog(AntiGuildUpdate(bot))
  await bot.add_cog(AntiIntegration(bot))
  await bot.add_cog(AntiKick(bot))
  await bot.add_cog(AntiPrune(bot))
  await bot.add_cog(AntiRoleCreate(bot))
  await bot.add_cog(AntiRoleDelete(bot))
  await bot.add_cog(AntiRoleUpdate(bot))
  await bot.add_cog(AntiWebhookUpdate(bot))
  await bot.add_cog(AntiWebhookCreate(bot))
  await bot.add_cog(AntiWebhookDelete(bot))
  
  # await bot.add_cog(TicketCreationView(bot))
  # await bot.add_cog(TicketManagementView(bot))

#Extra Optional Events 

  await bot.add_cog(AntiEmoji(bot))
  #await bot.add_cog(AntiEmojiDelete(bot))
  #await bot.add_cog(AntiEmojiUpdate(bot))
  await bot.add_cog(AntiSticker(bot))
  await bot.add_cog(AntiSoundboard(bot))
  await bot.add_cog(AntiUnban(bot))


  await bot.add_cog(AntiSpam(bot))
  await bot.add_cog(AntiCaps(bot))
  await bot.add_cog(AntiInvite(bot))
  await bot.add_cog(AntiLink(bot))
  await bot.add_cog(AntiMassMention(bot))
  await bot.add_cog(AntiEmojiSpam(bot))






  await bot.add_cog(Ban(bot))
  await bot.add_cog(Unban(bot))
  await bot.add_cog(Mute(bot))
  await bot.add_cog(Unmute(bot))
  await bot.add_cog(Lock(bot))
  await bot.add_cog(Unlock(bot))
  await bot.add_cog(Hide(bot))
  await bot.add_cog(Unhide(bot))
  await bot.add_cog(Kick(bot))
  await bot.add_cog(Warn(bot))
  await bot.add_cog(Role(bot))
  await bot.add_cog(Message(bot))
  await bot.add_cog(Moderation(bot))
  await bot.add_cog(TopCheck(bot))
  await bot.add_cog(Snipe(bot))
  await bot.add_cog(Verification(bot))
  await bot.add_cog(Leveling(bot))
  await bot.add_cog(Sticky(bot))


  print(Fore.GREEN + Style.BRIGHT + "All Cogs Loaded Successfully.")

