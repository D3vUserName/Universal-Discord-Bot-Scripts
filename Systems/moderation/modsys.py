import discord
from discord.ext import commands, tasks
import json
import os
import aiofiles
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union

CONFIG = {
    "token": "",
    "prefix": "!",
    "admin_roles": [123456789012345678],
    "log_channel_id": None,
    "automod": {
        "max_caps_percentage": 70,
        "max_message_length": 500,
        "max_messages_per_second": 3,
        "max_mentions": 5,
        "blocked_links": ["discord.gg/", "discord.com/invite/", "bit.ly/"],
        "allowed_domains": ["discord.com", "github.com", "youtube.com"],
        "anti_spam": {
            "enabled": True,
            "message_limit": 5,
            "timeframe": 5,
            "mute_duration": 300
        },
        "anti_caps": {
            "enabled": True,
            "min_length": 10,
            "action": "delete"
        },
        "anti_links": {
            "enabled": True,
            "whitelist_channels": [],
            "action": "warn"
        }
    },
    "warnings": {
        "max_warnings": 3,
        "punishments": [
            {"warnings": 1, "action": "mute", "duration": 300},
            {"warnings": 2, "action": "mute", "duration": 1800},
            {"warnings": 3, "action": "kick"},
            {"warnings": 4, "action": "ban", "duration": 86400}
        ]
    },
    "temp_punishments_check_interval": 60
}

if not os.path.exists('config.json'):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(CONFIG, f, indent=4, ensure_ascii=False)

try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = CONFIG

class JSONDatabase:
    def __init__(self, file_path: str = "data/database.json"):
        self.file_path = file_path
        self.data = {
            "warnings": {},
            "mutes": {},
            "bans": {},
            "guild_settings": {},
            "user_stats": {},
            "message_history": {}
        }
        self.lock = asyncio.Lock()
        self._ensure_directory()
        self.load()
    
    def _ensure_directory(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
    
    def load(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.save()
    
    def save(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
    
    async def async_save(self):
        async with self.lock:
            async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self.data, indent=4, ensure_ascii=False))
    
    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> str:
        if str(guild_id) not in self.data["warnings"]:
            self.data["warnings"][str(guild_id)] = {}
        
        if str(user_id) not in self.data["warnings"][str(guild_id)]:
            self.data["warnings"][str(guild_id)][str(user_id)] = []
        
        warning_id = f"WARN_{datetime.now().timestamp()}_{user_id}"
        warning = {
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "warning_id": warning_id
        }
        
        self.data["warnings"][str(guild_id)][str(user_id)].append(warning)
        self.save()
        return warning_id
    
    def get_warnings(self, guild_id: int, user_id: int) -> List[dict]:
        guild_warnings = self.data["warnings"].get(str(guild_id), {})
        user_warnings = guild_warnings.get(str(user_id), [])
        return user_warnings
    
    def remove_warning(self, guild_id: int, user_id: int, warning_id: str) -> bool:
        warnings = self.get_warnings(guild_id, user_id)
        for i, warning in enumerate(warnings):
            if warning["warning_id"] == warning_id:
                self.data["warnings"][str(guild_id)][str(user_id)].pop(i)
                self.save()
                return True
        return False
    
    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        count = len(self.get_warnings(guild_id, user_id))
        if str(guild_id) in self.data["warnings"]:
            self.data["warnings"][str(guild_id)].pop(str(user_id), None)
        self.save()
        return count
    
    def add_mute(self, guild_id: int, user_id: int, moderator_id: int, reason: str, duration: int) -> dict:
        if str(guild_id) not in self.data["mutes"]:
            self.data["mutes"][str(guild_id)] = {}
        
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration)
        
        mute = {
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "guild_id": guild_id
        }
        
        self.data["mutes"][str(guild_id)][str(user_id)] = mute
        self.save()
        return mute
    
    def get_mute(self, guild_id: int, user_id: int) -> Optional[dict]:
        guild_mutes = self.data["mutes"].get(str(guild_id), {})
        return guild_mutes.get(str(user_id))
    
    def remove_mute(self, guild_id: int, user_id: int) -> bool:
        if str(guild_id) in self.data["mutes"]:
            if str(user_id) in self.data["mutes"][str(guild_id)]:
                del self.data["mutes"][str(guild_id)][str(user_id)]
                self.save()
                return True
        return False
    
    def get_expired_mutes(self) -> List[dict]:
        expired = []
        now = datetime.now()
        
        for guild_id, users in self.data["mutes"].items():
            for user_id, mute_data in users.items():
                end_time = datetime.fromisoformat(mute_data["end_time"])
                if end_time < now:
                    expired.append(mute_data)
        
        return expired
    
    def add_ban(self, guild_id: int, user_id: int, moderator_id: int, reason: str, duration: Optional[int] = None) -> dict:
        if str(guild_id) not in self.data["bans"]:
            self.data["bans"][str(guild_id)] = {}
        
        start_time = datetime.now()
        end_time = None
        if duration:
            end_time = start_time + timedelta(seconds=duration)
        
        ban = {
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat() if end_time else None,
            "guild_id": guild_id
        }
        
        self.data["bans"][str(guild_id)][str(user_id)] = ban
        self.save()
        return ban
    
    def get_ban(self, guild_id: int, user_id: int) -> Optional[dict]:
        guild_bans = self.data["bans"].get(str(guild_id), {})
        return guild_bans.get(str(user_id))
    
    def remove_ban(self, guild_id: int, user_id: int) -> bool:
        if str(guild_id) in self.data["bans"]:
            if str(user_id) in self.data["bans"][str(guild_id)]:
                del self.data["bans"][str(guild_id)][str(user_id)]
                self.save()
                return True
        return False
    
    def get_expired_bans(self) -> List[dict]:
        expired = []
        now = datetime.now()
        
        for guild_id, users in self.data["bans"].items():
            for user_id, ban_data in users.items():
                if ban_data["end_time"]:
                    end_time = datetime.fromisoformat(ban_data["end_time"])
                    if end_time < now:
                        expired.append(ban_data)
        
        return expired
    
    def add_message(self, guild_id: int, user_id: int, message_id: int, timestamp: float):
        if str(guild_id) not in self.data["message_history"]:
            self.data["message_history"][str(guild_id)] = {}
        
        if str(user_id) not in self.data["message_history"][str(guild_id)]:
            self.data["message_history"][str(guild_id)][str(user_id)] = []
        
        self.data["message_history"][str(guild_id)][str(user_id)].append({
            "message_id": message_id,
            "timestamp": timestamp
        })
        
        if len(self.data["message_history"][str(guild_id)][str(user_id)]) > 20:
            self.data["message_history"][str(guild_id)][str(user_id)] = \
                self.data["message_history"][str(guild_id)][str(user_id)][-20:]
        
        self.save()
    
    def get_recent_messages(self, guild_id: int, user_id: int, timeframe: int) -> List[dict]:
        messages = self.data["message_history"].get(str(guild_id), {}).get(str(user_id), [])
        now = datetime.now().timestamp()
        return [msg for msg in messages if now - msg["timestamp"] <= timeframe]
    
    def cleanup_old_messages(self, max_age: int = 300):
        now = datetime.now().timestamp()
        for guild_id, users in list(self.data["message_history"].items()):
            for user_id, messages in list(users.items()):
                filtered = [msg for msg in messages if now - msg["timestamp"] <= max_age]
                if filtered:
                    self.data["message_history"][guild_id][user_id] = filtered
                else:
                    del self.data["message_history"][guild_id][user_id]
        self.save()

class LoggingSystem:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
    
    async def get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        channel_id = config["log_channel_id"]
        if not channel_id:
            for channel in guild.text_channels:
                if "log" in channel.name.lower() or "mod-log" in channel.name.lower():
                    config["log_channel_id"] = channel.id
                    return channel
            return None
        
        channel = guild.get_channel(channel_id)
        if channel:
            return channel
        
        config["log_channel_id"] = None
        return None
    
    async def setup_log_channel(self, guild: discord.Guild) -> discord.TextChannel:
        existing = await self.get_log_channel(guild)
        if existing:
            return existing
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for role_id in config["admin_roles"]:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        
        channel = await guild.create_text_channel(
            "mod-logs",
            overwrites=overwrites,
            reason="Kanał do logowania moderacji"
        )
        
        config["log_channel_id"] = channel.id
        return channel
    
    async def log_ban(self, guild: discord.Guild, user: discord.User, moderator: discord.User, 
                     reason: str, duration: Optional[int] = None):
        embed = discord.Embed(
            title="🔨 Użytkownik Zbanowany",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Powód", value=reason, inline=False)
        if duration:
            embed.add_field(name="Czas trwania", value=f"{duration}s", inline=True)
        embed.set_footer(text=f"Akcja wykonana")
        
        await self._send_log(guild, embed)
    
    async def log_unban(self, guild: discord.Guild, user: discord.User, moderator: discord.User, reason: str):
        embed = discord.Embed(
            title="🔓 Użytkownik Odbanowany",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Powód", value=reason, inline=False)
        embed.set_footer(text=f"Akcja wykonana")
        
        await self._send_log(guild, embed)
    
    async def log_kick(self, guild: discord.Guild, user: discord.User, moderator: discord.User, reason: str):
        embed = discord.Embed(
            title="👢 Użytkownik Wyrzucony",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Powód", value=reason, inline=False)
        embed.set_footer(text=f"Akcja wykonana")
        
        await self._send_log(guild, embed)
    
    async def log_mute(self, guild: discord.Guild, user: discord.User, moderator: discord.User, 
                      reason: str, duration: int):
        embed = discord.Embed(
            title="🔇 Użytkownik Wyciszony",
            color=discord.Color.dark_gray(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Powód", value=reason, inline=False)
        embed.add_field(name="Czas trwania", value=f"{duration}s", inline=True)
        embed.set_footer(text=f"Akcja wykonana")
        
        await self._send_log(guild, embed)
    
    async def log_unmute(self, guild: discord.Guild, user: Union[discord.User, int], 
                        moderator: discord.User, reason: str):
        if isinstance(user, int):
            user_str = f"`{user}`"
        else:
            user_str = f"{user.mention}\n`{user.id}`"
        
        embed = discord.Embed(
            title="🔊 Zdjęto Wyciszenie",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=user_str, inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Powód", value=reason, inline=False)
        embed.set_footer(text=f"Akcja wykonana")
        
        await self._send_log(guild, embed)
    
    async def log_warn(self, guild: discord.Guild, user: discord.User, moderator: discord.User, 
                      reason: str, warning_id: str, warning_count: int):
        embed = discord.Embed(
            title="⚠️ Nowe Ostrzeżenie",
            color=discord.Color.yellow(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.add_field(name="Powód", value=reason, inline=False)
        embed.add_field(name="ID Ostrzeżenia", value=warning_id, inline=True)
        embed.add_field(name="Łączna liczba", value=str(warning_count), inline=True)
        embed.set_footer(text=f"Akcja wykonana")
        
        await self._send_log(guild, embed)
    
    async def log_automod(self, message: discord.Message, violation_data: dict, action: str):
        embed = discord.Embed(
            title="🤖 AutoMod Działanie",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Użytkownik", value=f"{message.author.mention}\n`{message.author.id}`", inline=True)
        embed.add_field(name="Kanał", value=message.channel.mention, inline=True)
        
        violations_text = "\n".join([v["message"] for v in violation_data["violations"][:3]])
        if len(violation_data["violations"]) > 3:
            violations_text += f"\n...i {len(violation_data['violations']) - 3} więcej"
        
        embed.add_field(name="Naruszenia", value=violations_text, inline=False)
        embed.add_field(name="Podjęta akcja", value=action, inline=True)
        
        if len(message.content) < 500:
            embed.add_field(name="Wiadomość", value=f"```{message.content[:200]}...```", inline=False)
        
        embed.set_footer(text=f"ID: {message.id}")
        
        await self._send_log(message.guild, embed)
    
    async def log_message_delete(self, message: discord.Message, moderator: Optional[discord.User] = None):
        embed = discord.Embed(
            title="🗑️ Wiadomość Usunięta",
            color=discord.Color.dark_gray(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Autor", value=f"{message.author.mention}\n`{message.author.id}`", inline=True)
        embed.add_field(name="Kanał", value=message.channel.mention, inline=True)
        
        if moderator:
            embed.add_field(name="Usunięta przez", value=moderator.mention, inline=True)
        
        if message.content:
            content_preview = message.content[:400]
            if len(message.content) > 400:
                content_preview += "..."
            embed.add_field(name="Treść", value=f"```{content_preview}```", inline=False)
        
        if message.attachments:
            attachments = "\n".join([f"📎 {att.filename}" for att in message.attachments[:3]])
            if len(message.attachments) > 3:
                attachments += f"\n...i {len(message.attachments) - 3} więcej"
            embed.add_field(name="Załączniki", value=attachments, inline=False)
        
        embed.set_footer(text=f"ID: {message.id}")
        
        await self._send_log(message.guild, embed)
    
    async def _send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self.get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except:
                pass

class PunishmentSystem:
    def __init__(self, bot, db, logs):
        self.bot = bot
        self.db = db
        self.logs = logs
    
    async def ban_user(self, guild: discord.Guild, user: discord.User, moderator: discord.User, 
                       reason: str, duration: Optional[int] = None):
        try:
            ban = self.db.add_ban(guild.id, user.id, moderator.id, reason, duration)
            
            audit_reason = f"{moderator} | {reason}"
            if duration:
                audit_reason += f" | {duration}s"
            
            await guild.ban(user, reason=audit_reason, delete_message_days=1)
            
            await self.logs.log_ban(guild, user, moderator, reason, duration)
            
            try:
                embed = discord.Embed(
                    title="🔨 Zostałeś zbanowany",
                    description=f"**Serwer:** {guild.name}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Moderator", value=moderator.mention, inline=True)
                embed.add_field(name="Powód", value=reason, inline=True)
                if duration:
                    embed.add_field(name="Czas trwania", value=f"{duration}s", inline=True)
                embed.set_footer(text=f"ID: {user.id}")
                
                await user.send(embed=embed)
            except:
                pass
            
            return True, f"✅ Pomyślnie zbanowano {user.mention}"
            
        except discord.Forbidden:
            return False, "❌ Bot nie ma uprawnień do banowania"
        except discord.HTTPException as e:
            return False, f"❌ Błąd HTTP: {e}"
    
    async def unban_user(self, guild: discord.Guild, user_id: int, moderator: discord.User, reason: str):
        try:
            user = await self.bot.fetch_user(user_id)
            await guild.unban(user, reason=f"{moderator} | {reason}")
            
            self.db.remove_ban(guild.id, user_id)
            
            await self.logs.log_unban(guild, user, moderator, reason)
            return True, f"✅ Pomyślnie odbanowano użytkownika"
            
        except discord.NotFound:
            return False, "❌ Użytkownik nie jest zbanowany"
        except discord.Forbidden:
            return False, "❌ Bot nie ma uprawnień do odbanowywania"
        except discord.HTTPException as e:
            return False, f"❌ Błąd HTTP: {e}"
    
    async def tempban_user(self, guild: discord.Guild, user: discord.User, moderator: discord.User, 
                          duration: int, reason: str):
        return await self.ban_user(guild, user, moderator, reason, duration)
    
    async def kick_user(self, guild: discord.Guild, user: discord.User, moderator: discord.User, reason: str):
        try:
            audit_reason = f"{moderator} | {reason}"
            
            await guild.kick(user, reason=audit_reason)
            
            await self.logs.log_kick(guild, user, moderator, reason)
            
            try:
                embed = discord.Embed(
                    title="👢 Zostałeś wyrzucony",
                    description=f"**Serwer:** {guild.name}",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Moderator", value=moderator.mention, inline=True)
                embed.add_field(name="Powód", value=reason, inline=True)
                embed.set_footer(text=f"ID: {user.id}")
                
                await user.send(embed=embed)
            except:
                pass
            
            return True, f"✅ Pomyślnie wyrzucono {user.mention}"
            
        except discord.Forbidden:
            return False, "❌ Bot nie ma uprawnień do wyrzucania"
        except discord.HTTPException as e:
            return False, f"❌ Błąd HTTP: {e}"
    
    async def mute_user(self, guild: discord.Guild, user: discord.User, moderator: discord.User, 
                       duration: int, reason: str):
        try:
            member = guild.get_member(user.id)
            if not member:
                return False, "❌ Użytkownik nie jest na serwerze"
            
            if duration > 2419200:
                return False, "❌ Maksymalny czas timeoutu to 28 dni (2419200 sekund)"
            
            timeout_until = datetime.now() + timedelta(seconds=duration)
            
            await member.timeout(timeout_until, reason=f"{moderator} | {reason}")
            
            mute = self.db.add_mute(guild.id, user.id, moderator.id, reason, duration)
            
            await self.logs.log_mute(guild, user, moderator, reason, duration)
            
            try:
                embed = discord.Embed(
                    title="🔇 Zostałeś wyciszony (timeout)",
                    description=f"**Serwer:** {guild.name}",
                    color=discord.Color.dark_gray(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Moderator", value=moderator.mention, inline=True)
                embed.add_field(name="Powód", value=reason, inline=True)
                embed.add_field(name="Czas trwania", value=f"{duration}s", inline=True)
                embed.set_footer(text=f"ID: {user.id}")
                
                await user.send(embed=embed)
            except:
                pass
            
            return True, f"✅ Pomyślnie wyciszono {user.mention} na {duration}s"
            
        except discord.Forbidden:
            return False, "❌ Bot nie ma uprawnień do timeoutów"
        except discord.HTTPException as e:
            return False, f"❌ Błąd HTTP: {e}"
    
    async def unmute_user(self, guild: discord.Guild, user_id: int, moderator: discord.User, reason: str):
        try:
            member = guild.get_member(user_id)
            if not member:
                return False, "❌ Użytkownik nie jest na serwerze"
            
            await member.timeout(None, reason=f"{moderator} | {reason}")
            
            self.db.remove_mute(guild.id, user_id)
            
            await self.logs.log_unmute(guild, member, moderator, reason)
            return True, f"✅ Pomyślnie zdjęto timeout"
            
        except discord.Forbidden:
            return False, "❌ Bot nie ma uprawnień do timeoutów"
        except discord.HTTPException as e:
            return False, f"❌ Błąd HTTP: {e}"
    
    async def warn_user(self, guild: discord.Guild, user: discord.User, moderator: discord.User, reason: str):
        warning_id = self.db.add_warning(guild.id, user.id, moderator.id, reason)
        
        warnings = self.db.get_warnings(guild.id, user.id)
        warning_count = len(warnings)
        
        punishment_applied = await self._check_automatic_punishments(guild, user, warning_count)
        
        await self.logs.log_warn(guild, user, moderator, reason, warning_id, warning_count)
        
        try:
            embed = discord.Embed(
                title="⚠️ Otrzymałeś ostrzeżenie",
                description=f"**Serwer:** {guild.name}",
                color=discord.Color.yellow(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
            embed.add_field(name="Powód", value=reason, inline=True)
            embed.add_field(name="ID Ostrzeżenia", value=warning_id, inline=True)
            embed.add_field(name="Łączna liczba ostrzeżeń", value=str(warning_count), inline=True)
            if punishment_applied:
                embed.add_field(name="Zastosowana kara", value=punishment_applied, inline=True)
            embed.set_footer(text=f"ID: {user.id}")
            
            await user.send(embed=embed)
        except:
            pass
        
        return True, f"✅ Pomyślnie ostrzeżono {user.mention} (ID: {warning_id[-8:]})"
    
    async def _check_automatic_punishments(self, guild: discord.Guild, user: discord.User, warning_count: int) -> Optional[str]:
        for punishment in config["warnings"]["punishments"]:
            if warning_count == punishment["warnings"]:
                action = punishment["action"]
                duration = punishment.get("duration")
                
                if action == "mute" and duration:
                    await self.mute_user(guild, user, self.bot.user, duration, 
                                       f"Automatyczna kara za {warning_count} ostrzeżeń")
                    return f"Timeout na {duration}s"
                
                elif action == "kick":
                    await self.kick_user(guild, user, self.bot.user, 
                                       f"Automatyczna kara za {warning_count} ostrzeżeń")
                    return "Wyrzucenie"
                
                elif action == "ban":
                    ban_duration = duration if duration else None
                    await self.ban_user(guild, user, self.bot.user, 
                                      f"Automatyczna kara za {warning_count} ostrzeżeń",
                                      ban_duration)
                    return "Ban" + (f" na {ban_duration}s" if ban_duration else "")
        
        return None
    
    async def check_expired_punishments(self):
        expired_mutes = self.db.get_expired_mutes()
        for mute in expired_mutes:
            guild = self.bot.get_guild(mute["guild_id"])
            if guild:
                await self.unmute_user(guild, mute["user_id"], self.bot.user, "Kara wygasła")
        
        expired_bans = self.db.get_expired_bans()
        for ban in expired_bans:
            guild = self.bot.get_guild(ban["guild_id"])
            if guild:
                await self.unban_user(guild, ban["user_id"], self.bot.user, "Ban wygasł")

class AutoMod:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.user_cooldowns = {}
        
    async def check_message(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        if message.author.bot or message.author.guild_permissions.administrator:
            return None
        
        violations = []
        
        if config["automod"]["anti_caps"]["enabled"]:
            caps_violation = await self._check_caps(message)
            if caps_violation:
                violations.append(caps_violation)
        
        if config["automod"]["anti_spam"]["enabled"]:
            spam_violation = await self._check_spam(message)
            if spam_violation:
                violations.append(spam_violation)
        
        if config["automod"]["anti_links"]["enabled"]:
            link_violation = await self._check_links(message)
            if link_violation:
                violations.append(link_violation)
        
        mention_violation = await self._check_mentions(message)
        if mention_violation:
            violations.append(mention_violation)
        
        length_violation = await self._check_length(message)
        if length_violation:
            violations.append(length_violation)
        
        if violations:
            return {
                "violations": violations,
                "action_required": any(v.get("action") != "log" for v in violations),
                "highest_action": self._get_highest_action(violations)
            }
        
        return None
    
    async def _check_caps(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        content = message.content
        if len(content) < config["automod"]["anti_caps"]["min_length"]:
            return None
        
        letters = sum(c.isalpha() for c in content)
        if letters == 0:
            return None
        
        caps = sum(c.isupper() for c in content)
        caps_percentage = (caps / letters) * 100
        
        if caps_percentage > config["automod"]["max_caps_percentage"]:
            return {
                "type": "caps",
                "percentage": caps_percentage,
                "action": config["automod"]["anti_caps"]["action"],
                "message": f"Zbyt dużo wielkich liter ({caps_percentage:.1f}%)"
            }
        return None
    
    async def _check_spam(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        guild_id = message.guild.id
        user_id = message.author.id
        
        self.db.add_message(guild_id, user_id, message.id, datetime.now().timestamp())
        
        timeframe = config["automod"]["anti_spam"]["timeframe"]
        limit = config["automod"]["anti_spam"]["message_limit"]
        
        recent_messages = self.db.get_recent_messages(guild_id, user_id, timeframe)
        
        if len(recent_messages) > limit:
            return {
                "type": "spam",
                "count": len(recent_messages),
                "timeframe": timeframe,
                "action": "mute",
                "duration": config["automod"]["anti_spam"]["mute_duration"],
                "message": f"Zbyt wiele wiadomości ({len(recent_messages)} w {timeframe}s)"
            }
        return None
    
    async def _check_links(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        if message.channel.id in config["automod"]["anti_links"]["whitelist_channels"]:
            return None
        
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.\-?=&%#+]*'
        urls = re.findall(url_pattern, message.content)
        
        if not urls:
            return None
        
        blocked_links = []
        for url in urls:
            if any(blocked in url.lower() for blocked in config["automod"]["blocked_links"]):
                domain = re.search(r'https?://([^/]+)', url)
                if domain and domain.group(1) not in config["automod"]["allowed_domains"]:
                    blocked_links.append(url)
        
        if blocked_links:
            return {
                "type": "links",
                "urls": blocked_links,
                "action": config["automod"]["anti_links"]["action"],
                "message": f"Znaleziono zablokowane linki: {', '.join(blocked_links[:3])}"
            }
        return None
    
    async def _check_mentions(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        mentions = len(message.mentions) + len(message.role_mentions)
        max_mentions = config["automod"]["max_mentions"]
        
        if mentions > max_mentions:
            return {
                "type": "mentions",
                "count": mentions,
                "max_allowed": max_mentions,
                "action": "warn",
                "message": f"Zbyt wiele oznaczeń ({mentions} > {max_mentions})"
            }
        return None
    
    async def _check_length(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        max_length = config["automod"]["max_message_length"]
        
        if len(message.content) > max_length:
            return {
                "type": "length",
                "length": len(message.content),
                "max_allowed": max_length,
                "action": "warn",
                "message": f"Wiadomość zbyt długa ({len(message.content)} > {max_length})"
            }
        return None
    
    def _get_highest_action(self, violations: List[Dict[str, Any]]) -> str:
        action_priority = {
            "delete": 1,
            "warn": 2,
            "mute": 3,
            "kick": 4,
            "ban": 5
        }
        
        highest_action = "delete"
        for violation in violations:
            action = violation.get("action", "delete")
            if action_priority.get(action, 0) > action_priority.get(highest_action, 0):
                highest_action = action
        
        return highest_action
    
    async def handle_violation(self, message: discord.Message, violation_data: Dict[str, Any], logs):
        action = violation_data["highest_action"]
        
        if action == "delete":
            try:
                await message.delete()
                await logs.log_automod(message, violation_data, action="Usunięto wiadomość")
            except:
                pass
        
        elif action == "warn":
            try:
                await message.delete()
            except:
                pass
            warning_id = self.db.add_warning(
                message.guild.id,
                message.author.id,
                self.bot.user.id,
                f"AutoMod: {violation_data['violations'][0]['message']}"
            )
            await logs.log_automod(message, violation_data, action=f"Ostrzeżenie #{warning_id[-8:]}")
        
        elif action == "mute":
            try:
                await message.delete()
            except:
                pass
            
            duration = 300
            for violation in violation_data["violations"]:
                if violation.get("duration"):
                    duration = violation["duration"]
                    break
            
            punishment_system = PunishmentSystem(self.bot, self.db, logs)
            await punishment_system.mute_user(
                message.guild,
                message.author,
                self.bot.user,
                duration,
                f"AutoMod: {violation_data['violations'][0]['message']}"
            )
            await logs.log_automod(message, violation_data, action=f"Timeout na {duration}s")

class ModerationSystem:
    def __init__(self, bot, db, punishment_system, logs):
        self.bot = bot
        self.db = db
        self.punishment_system = punishment_system
        self.logs = logs
    
    async def check_permissions(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        
        for role_id in config["admin_roles"]:
            role = discord.utils.get(member.roles, id=role_id)
            if role:
                return True
        
        return False
    
    async def command_ban(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 2:
            return await ctx.send("❌ Użycie: `!ban <@użytkownik/id> <powód> [czas w sekundach]`")
        
        user = await self._parse_user(ctx.guild, args[0])
        if not user:
            return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        duration = None
        if len(args) >= 3 and args[-1].isdigit():
            duration = int(args[-1])
            reason = ' '.join(args[1:-1])
        else:
            reason = ' '.join(args[1:])
        
        if not reason:
            reason = "Nie podano powodu"
        
        success, result = await self.punishment_system.ban_user(
            ctx.guild, user, ctx.author, reason, duration
        )
        
        await ctx.send(result)
    
    async def command_tempban(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 3:
            return await ctx.send("❌ Użycie: `!tempban <@użytkownik/id> <czas w sekundach> <powód>`")
        
        user = await self._parse_user(ctx.guild, args[0])
        if not user:
            return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        if not args[1].isdigit():
            return await ctx.send("❌ Czas musi być liczbą sekund.")
        
        duration = int(args[1])
        reason = ' '.join(args[2:])
        
        success, result = await self.punishment_system.tempban_user(
            ctx.guild, user, ctx.author, duration, reason
        )
        
        await ctx.send(result)
    
    async def command_kick(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 2:
            return await ctx.send("❌ Użycie: `!kick <@użytkownik/id> <powód>`")
        
        user = await self._parse_user(ctx.guild, args[0])
        if not user:
            return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        reason = ' '.join(args[1:])
        
        success, result = await self.punishment_system.kick_user(
            ctx.guild, user, ctx.author, reason
        )
        
        await ctx.send(result)
    
    async def command_mute(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 3:
            return await ctx.send("❌ Użycie: `!mute <@użytkownik/id> <czas w sekundach> <powód>`")
        
        user = await self._parse_user(ctx.guild, args[0])
        if not user:
            return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        if not args[1].isdigit():
            return await ctx.send("❌ Czas musi być liczbą sekund.")
        
        duration = int(args[1])
        if duration > 2419200:
            return await ctx.send("❌ Maksymalny czas timeoutu to 28 dni (2419200 sekund)")
        
        reason = ' '.join(args[2:])
        
        success, result = await self.punishment_system.mute_user(
            ctx.guild, user, ctx.author, duration, reason
        )
        
        await ctx.send(result)
    
    async def command_unmute(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 2:
            return await ctx.send("❌ Użycie: `!unmute <@użytkownik/id> <powód>`")
        
        user_id = await self._parse_user_id(args[0])
        if not user_id:
            return await ctx.send("❌ Nieprawidłowy ID użytkownika.")
        
        reason = ' '.join(args[1:])
        
        success, result = await self.punishment_system.unmute_user(
            ctx.guild, user_id, ctx.author, reason
        )
        
        await ctx.send(result)
    
    async def command_warn(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 2:
            return await ctx.send("❌ Użycie: `!warn <@użytkownik/id> <powód>`")
        
        user = await self._parse_user(ctx.guild, args[0])
        if not user:
            return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        reason = ' '.join(args[1:])
        
        success, result = await self.punishment_system.warn_user(
            ctx.guild, user, ctx.author, reason
        )
        
        await ctx.send(result)
    
    async def command_warnings(self, ctx, args_str: str):
        args = args_str.split()
        if len(args) < 1:
            user = ctx.author
        else:
            user = await self._parse_user(ctx.guild, args[0])
            if not user:
                return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        warnings = self.db.get_warnings(ctx.guild.id, user.id)
        
        if not warnings:
            embed = discord.Embed(
                title=f"⚠️ Ostrzeżenia - {user}",
                description="✅ Brak ostrzeżeń",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title=f"⚠️ Ostrzeżenia - {user}",
                description=f"Łącznie: **{len(warnings)}**",
                color=discord.Color.yellow()
            )
            
            for i, warning in enumerate(warnings[:10], 1):
                moderator = ctx.guild.get_member(warning["moderator_id"]) or warning["moderator_id"]
                time = datetime.fromisoformat(warning["timestamp"]).strftime("%Y-%m-%d %H:%M")
                embed.add_field(
                    name=f"#{i} | ID: {warning['warning_id'][-8:]}",
                    value=f"**Moderator:** {moderator}\n**Powód:** {warning['reason']}\n**Data:** {time}",
                    inline=False
                )
            
            if len(warnings) > 10:
                embed.set_footer(text=f"I {len(warnings) - 10} więcej ostrzeżeń...")
        
        await ctx.send(embed=embed)
    
    async def command_clearwarnings(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 1:
            return await ctx.send("❌ Użycie: `!clearwarnings <@użytkownik/id>`")
        
        user = await self._parse_user(ctx.guild, args[0])
        if not user:
            return await ctx.send("❌ Nie znaleziono użytkownika.")
        
        count = self.db.clear_warnings(ctx.guild.id, user.id)
        
        embed = discord.Embed(
            title="✅ Wyczyszczono ostrzeżenia",
            description=f"Usunięto **{count}** ostrzeżeń użytkownika {user.mention}",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
    
    async def command_purge(self, ctx, args_str: str):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        args = args_str.split()
        if len(args) < 1 or not args[0].isdigit():
            return await ctx.send("❌ Użycie: `!purge <liczba> [@użytkownik]`")
        
        limit = int(args[0])
        if limit > 100:
            return await ctx.send("❌ Maksymalnie 100 wiadomości na raz.")
        
        user = None
        if len(args) > 1:
            user = await self._parse_user(ctx.guild, args[1])
        
        def check(msg):
            if user:
                return msg.author.id == user.id
            return True
        
        try:
            deleted = await ctx.channel.purge(limit=limit + 1, check=check, before=ctx.message)
            
            embed = discord.Embed(
                title="🗑️ Wyczyszczono wiadomości",
                description=f"Usunięto **{len(deleted) - 1}** wiadomości",
                color=discord.Color.green()
            )
            if user:
                embed.add_field(name="Filtr", value=f"Tylko od {user.mention}")
            
            await ctx.send(embed=embed, delete_after=5)
            
        except discord.Forbidden:
            await ctx.send("❌ Bot nie ma uprawnień do usuwania wiadomości.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Błąd HTTP: {e}")
    
    async def command_setup(self, ctx):
        if not await self.check_permissions(ctx.author):
            return await ctx.send("❌ Nie masz uprawnień do tej komendy.")
        
        channel = await self.logs.setup_log_channel(ctx.guild)
        
        embed = discord.Embed(
            title="✅ Konfiguracja zakończona",
            color=discord.Color.green()
        )
        embed.add_field(name="Kanał logów", value=channel.mention, inline=True)
        embed.add_field(name="AutoMod", value="Aktywny", inline=True)
        
        await ctx.send(embed=embed)
    
    async def _parse_user(self, guild: discord.Guild, user_input: str) -> Optional[discord.User]:
        if user_input.startswith('<@') and user_input.endswith('>'):
            user_id = user_input[2:-1].replace('!', '')
            if user_id.isdigit():
                try:
                    return await guild.fetch_member(int(user_id))
                except:
                    try:
                        return await self.bot.fetch_user(int(user_id))
                    except:
                        return None
        
        if user_input.isdigit():
            try:
                return await guild.fetch_member(int(user_input))
            except:
                try:
                    return await self.bot.fetch_user(int(user_input))
                except:
                    return None
        
        return None
    
    async def _parse_user_id(self, user_input: str) -> Optional[int]:
        if user_input.startswith('<@') and user_input.endswith('>'):
            user_id = user_input[2:-1].replace('!', '')
            if user_id.isdigit():
                return int(user_id)
        
        if user_input.isdigit():
            return int(user_input)
        
        return None

class AdvancedModerationBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.members = True
        intents.message_content = True
        
        super().__init__(command_prefix=config["prefix"], intents=intents, help_command=None)
        
        self.db = JSONDatabase()
        self.logs = LoggingSystem(self, self.db)
        self.punishment_system = PunishmentSystem(self, self.db, self.logs)
        self.automod = AutoMod(self, self.db)
        self.mod_system = ModerationSystem(self, self.db, self.punishment_system, self.logs)
    
    async def on_ready(self):
        print(f'✅ Zalogowano jako {self.user}')
        print(f'🏠 Serwery: {len(self.guilds)}')
        print(f'⚙️ Prefix: {config["prefix"]}')
        
        if not self.check_punishments.is_running():
            self.check_punishments.start()
        
        if not self.cleanup_messages.is_running():
            self.cleanup_messages.start()
    
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        
        violation_data = await self.automod.check_message(message)
        if violation_data and violation_data["action_required"]:
            await self.automod.handle_violation(message, violation_data, self.logs)
        
        self.db.add_message(
            message.guild.id,
            message.author.id,
            message.id,
            datetime.now().timestamp()
        )
        
        await self.process_commands(message)
    
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        await self.logs.log_message_delete(message)
    
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content or not before.guild:
            return
        
        violation_data = await self.automod.check_message(after)
        if violation_data and violation_data["action_required"]:
            await self.automod.handle_violation(after, violation_data, self.logs)
    
    async def on_member_join(self, member):
        mute = self.db.get_mute(member.guild.id, member.id)
        if mute:
            end_time = datetime.fromisoformat(mute["end_time"])
            if end_time > datetime.now():
                timeout_until = end_time
                try:
                    await member.timeout(timeout_until, reason="Przywrócenie timeoutu po powrocie")
                except:
                    pass
    
    @commands.command(name='ban')
    async def ban_command(self, ctx, *, args):
        await self.mod_system.command_ban(ctx, args)
    
    @commands.command(name='tempban')
    async def tempban_command(self, ctx, *, args):
        await self.mod_system.command_tempban(ctx, args)
    
    @commands.command(name='kick')
    async def kick_command(self, ctx, *, args):
        await self.mod_system.command_kick(ctx, args)
    
    @commands.command(name='mute')
    async def mute_command(self, ctx, *, args):
        await self.mod_system.command_mute(ctx, args)
    
    @commands.command(name='unmute')
    async def unmute_command(self, ctx, *, args):
        await self.mod_system.command_unmute(ctx, args)
    
    @commands.command(name='warn')
    async def warn_command(self, ctx, *, args):
        await self.mod_system.command_warn(ctx, args)
    
    @commands.command(name='warnings')
    async def warnings_command(self, ctx, *, args=None):
        await self.mod_system.command_warnings(ctx, args or "")
    
    @commands.command(name='clearwarnings')
    async def clearwarnings_command(self, ctx, *, args):
        await self.mod_system.command_clearwarnings(ctx, args)
    
    @commands.command(name='purge')
    async def purge_command(self, ctx, *, args):
        await self.mod_system.command_purge(ctx, args)
    
    @commands.command(name='setup')
    async def setup_command(self, ctx):
        await self.mod_system.command_setup(ctx)
    
    @commands.command(name='help', aliases=['h', 'pomoc'])
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="🤖 Pomoc - System Moderacji",
            description="Lista dostępnych komend:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎯 Podstawowe",
            value="```"
                  "!ban <użytkownik> <powód> [czas]\n"
                  "!tempban <użytkownik> <czas> <powód>\n"
                  "!kick <użytkownik> <powód>\n"
                  "!mute <użytkownik> <czas> <powód>\n"
                  "!unmute <użytkownik> <powód>\n"
                  "```",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Ostrzeżenia",
            value="```"
                  "!warn <użytkownik> <powód>\n"
                  "!warnings [użytkownik]\n"
                  "!clearwarnings <użytkownik>\n"
                  "```",
            inline=False
        )
        
        embed.add_field(
            name="🧹 Narzędzia",
            value="```"
                  "!purge <liczba> [użytkownik]\n"
                  "!setup - Konfiguruje bota\n"
                  "```",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ AutoMod",
            value="Automatycznie wykrywa:\n"
                  "• Spam\n• Caps lock\n• Linki\n• Zbyt długie wiadomości\n"
                  "• Zbyt wiele oznaczeń",
            inline=False
        )
        
        embed.set_footer(text=f"Prefix: {config['prefix']} | Wpisz !help <komenda> po szczegóły")
        await ctx.send(embed=embed)
    
    @tasks.loop(seconds=60)
    async def check_punishments(self):
        await self.punishment_system.check_expired_punishments()
    
    @tasks.loop(minutes=5)
    async def cleanup_messages(self):
        self.db.cleanup_old_messages()
    
    @check_punishments.before_loop
    async def before_check_punishments(self):
        await self.wait_until_ready()
    
    @cleanup_messages.before_loop
    async def before_cleanup_messages(self):
        await self.wait_until_ready()

if __name__ == "__main__":
    print("🚀 Uruchamianie systemu moderacji...")
    os.makedirs("data", exist_ok=True)
    
    if not os.path.exists('config.json'):
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, indent=4, ensure_ascii=False)
        print("📝 Utworzono plik config.json")
        print("⚠️ Uzupełnij token bota w config.json przed uruchomieniem!")
        exit()
    
    if config["token"] == "":
        exit()
    
    print("✅ Konfiguracja załadowana")
    print("🤖 Rozpoczynanie pracy bota...")
    
    bot = AdvancedModerationBot()
    bot.run(config["token"])