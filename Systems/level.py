import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import random
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

TOKEN = ""
PREFIX = "!"
LEVEL_UP_CHANNEL_ID = None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@dataclass
class LevelingConfig:
    xp_per_message_min: int = 15
    xp_per_message_max: int = 25
    cooldown_seconds: int = 60
    level_base: int = 100
    level_multiplier: float = 1.5
    level_roles: Dict[int, int] = None
    level_up_channel_id: int = LEVEL_UP_CHANNEL_ID
    
    def __post_init__(self):
        if self.level_roles is None:
            self.level_roles = {
                1: 123456789012345690,
                5: 123456789012345678,
                10: 123456789012345679,
                15: 123456789012345680,
                20: 123456789012345681,
                25: 123456789012345682,
                30: 123456789012345683,
                35: 123456789012345684,
                40: 123456789012345685,
                45: 123456789012345686,
                50: 123456789012345687,
                55: 123456789012345688,
                60: 123456789012345689,
                65: 123456789012345690,
                70: 123456789012345691,
                75: 123456789012345692,
                80: 123456789012345693,
                85: 123456789012345694,
                90: 123456789012345695,
                95: 123456789012345696,
                100: 123456789012345697
            }

config = LevelingConfig()

class LevelingDatabase:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.filename = "leveling_data.json"
            self.data = self._load_data()
            self.cooldowns = defaultdict(dict)
            self._save_lock = asyncio.Lock()
            self._initialized = True
    
    def _load_data(self) -> Dict:
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Błąd ładowania danych: {e}")
            backup_files = [f for f in os.listdir('.') if f.startswith('leveling_data.json.backup')]
            if backup_files:
                latest_backup = max(backup_files)
                try:
                    with open(latest_backup, 'r', encoding='utf-8') as f:
                        print(f"Ładowanie kopii zapasowej: {latest_backup}")
                        return json.load(f)
                except Exception:
                    pass
        return {"users": {}, "last_save": datetime.now().isoformat()}
    
    def _save_data(self):
        self.data["last_save"] = datetime.now().isoformat()
        try:
            temp_filename = f"{self.filename}.tmp"
            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            if os.path.exists(self.filename):
                backup_name = f"{self.filename}.backup"
                os.replace(self.filename, backup_name)
            
            os.replace(temp_filename, self.filename)
        except Exception as e:
            print(f"Błąd zapisu danych: {e}")
    
    async def save_all_async(self):
        async with self._save_lock:
            await asyncio.get_event_loop().run_in_executor(None, self._save_data)
    
    def get_user_key(self, user_id: int, guild_id: int) -> str:
        return f"{guild_id}:{user_id}"
    
    def get_user_data(self, user_id: int, guild_id: int) -> Dict:
        key = self.get_user_key(user_id, guild_id)
        
        if key not in self.data.setdefault("users", {}):
            self.data["users"][key] = {
                "xp": 0,
                "level": 1,
                "messages": 0,
                "total_xp": 0,
                "last_active": None,
                "created_at": datetime.now().isoformat()
            }
        
        return self.data["users"][key]
    
    def update_user(self, user_id: int, guild_id: int, data: Dict):
        key = self.get_user_key(user_id, guild_id)
        self.data.setdefault("users", {})[key] = data
    
    def get_guild_leaderboard(self, guild_id: int, limit: int = 10) -> List[Tuple[int, Dict]]:
        guild_users = []
        
        for key, user_data in self.data.get("users", {}).items():
            try:
                stored_guild_id = int(key.split(':')[0])
                if stored_guild_id == guild_id:
                    user_id = int(key.split(':')[1])
                    guild_users.append((user_id, user_data))
            except (ValueError, IndexError):
                continue
        
        guild_users.sort(key=lambda x: x[1].get("xp", 0), reverse=True)
        return guild_users[:limit]
    
    def get_user_rank(self, user_id: int, guild_id: int) -> Optional[int]:
        all_users = []
        
        for key, user_data in self.data.get("users", {}).items():
            try:
                stored_guild_id = int(key.split(':')[0])
                if stored_guild_id == guild_id:
                    stored_user_id = int(key.split(':')[1])
                    all_users.append((stored_user_id, user_data))
            except (ValueError, IndexError):
                continue
        
        all_users.sort(key=lambda x: x[1].get("xp", 0), reverse=True)
        
        for i, (uid, _) in enumerate(all_users):
            if uid == user_id:
                return i + 1
        return None
    
    def add_cooldown(self, user_id: int, guild_id: int):
        self.cooldowns[guild_id][user_id] = datetime.now()
    
    def is_on_cooldown(self, user_id: int, guild_id: int) -> bool:
        if guild_id in self.cooldowns and user_id in self.cooldowns[guild_id]:
            elapsed = (datetime.now() - self.cooldowns[guild_id][user_id]).total_seconds()
            if elapsed < config.cooldown_seconds:
                return True
            else:
                del self.cooldowns[guild_id][user_id]
        return False

db = LevelingDatabase()

class XPCalculator:
    @staticmethod
    def xp_for_level(level: int) -> int:
        return int(config.level_base * (config.level_multiplier ** (level - 1)))
    
    @staticmethod
    def level_from_xp(xp: int) -> Tuple[int, int, int]:
        level = 1
        xp_needed = XPCalculator.xp_for_level(level)
        
        while xp >= xp_needed:
            xp -= xp_needed
            level += 1
            xp_needed = XPCalculator.xp_for_level(level)
            
            if level > 1000:
                break
        
        return level, xp, XPCalculator.xp_for_level(level)
    
    @staticmethod
    def calculate_progress_bar(current: int, needed: int, length: int = 20) -> str:
        if needed <= 0:
            return "█" * length
        percentage = min(current / needed, 1.0)
        filled = int(length * percentage)
        return "█" * filled + "░" * (length - filled)

class RoleManager:
    @staticmethod
    async def assign_level_roles(member: discord.Member, new_level: int, old_level: int):
        roles_to_add = []
        
        for required_level, role_id in config.level_roles.items():
            if old_level < required_level <= new_level:
                role = member.guild.get_role(role_id)
                if role and role not in member.roles:
                    roles_to_add.append(role)
        
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason=f"Awans na poziom {new_level}")
            except discord.Forbidden:
                print(f"Brak uprawnień do dodania ról dla {member}")
            except Exception as e:
                print(f"Błąd dodawania ról: {e}")
    
    @staticmethod
    async def remove_all_level_roles(member: discord.Member):
        roles_to_remove = []
        
        for role_id in config.level_roles.values():
            role = member.guild.get_role(role_id)
            if role and role in member.roles:
                roles_to_remove.append(role)
        
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason="Reset statystyk")
            except discord.Forbidden:
                print(f"Brak uprawnień do usunięcia ról dla {member}")
            except Exception as e:
                print(f"Błąd usuwania ról: {e}")

async def send_level_up_message(message: discord.Message, new_level: int):
    try:
        level_up_channel = bot.get_channel(config.level_up_channel_id)
        if level_up_channel:
            embed = discord.Embed(
                title="🎉 AWANS POZIOMU! 🎉",
                description=f"{message.author.mention} awansował na **poziom {new_level}!**",
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )

            user_data = db.get_user_data(message.author.id, message.guild.id)
            level, current_xp, xp_needed = XPCalculator.level_from_xp(user_data.get("xp", 0))
            progress_bar = XPCalculator.calculate_progress_bar(current_xp, xp_needed)
                
            embed.add_field(
                name="📊 Postęp",
                value=f"```{progress_bar}```\n{current_xp}/{xp_needed} XP ({current_xp/xp_needed*100:.1f}%)",
                inline=False
            )

            if new_level in config.level_roles:
                role_id = config.level_roles[new_level]
                role = message.guild.get_role(role_id)
                if role:
                    embed.add_field(
                        name="🎖️ Nowa rola",
                        value=f"Otrzymałeś rolę {role.mention}!",
                        inline=False
                    )

            rank_pos = db.get_user_rank(message.author.id, message.guild.id)
            if rank_pos:
                embed.add_field(
                    name="🏆 Ranking",
                    value=f"#{rank_pos} w rankingu serwera",
                    inline=True
                )
                
            embed.add_field(
                name="💬 Wiadomości",
                value=f"**{user_data.get('messages', 0)}**",
                inline=True
            )
                
            embed.add_field(
                name="⭐ Całkowite XP",
                value=f"**{user_data.get('total_xp', 0)}**",
                inline=True
            )
                
            if message.author.avatar:
                embed.set_thumbnail(url=message.author.avatar.url)
                
            embed.set_footer(text=f"ID: {message.author.id}")

            await level_up_channel.send(embed=embed)
    except Exception as e:
        print(f"Błąd wysyłania wiadomości o awansie: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot zalogowany jako {bot.user}")
    print(f"📊 Serwery: {len(bot.guilds)}")

    auto_save.start()
    
    try:
        await bot.tree.sync()
        print("✅ Komendy slash zsynchronizowane")
    except Exception as e:
        print(f"❌ Błąd synchronizacji komend: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    
    if db.is_on_cooldown(message.author.id, message.guild.id):
        await bot.process_commands(message)
        return
    
    xp_gained = random.randint(config.xp_per_message_min, config.xp_per_message_max)
    user_data = db.get_user_data(message.author.id, message.guild.id)
    old_xp = user_data.get("xp", 0)
    
    user_data["xp"] = user_data.get("xp", 0) + xp_gained
    user_data["total_xp"] = user_data.get("total_xp", 0) + xp_gained
    user_data["messages"] = user_data.get("messages", 0) + 1
    user_data["last_active"] = datetime.now().isoformat()
    user_data.setdefault("created_at", datetime.now().isoformat())
    
    old_level, _, _ = XPCalculator.level_from_xp(old_xp)
    new_level, current_xp, xp_needed = XPCalculator.level_from_xp(user_data["xp"])
    
    if new_level > old_level:
        user_data["level"] = new_level
        await RoleManager.assign_level_roles(message.author, new_level, old_level)
        await send_level_up_message(message, new_level)
    
    db.update_user(message.author.id, message.guild.id, user_data)
    db.add_cooldown(message.author.id, message.guild.id)
    await bot.process_commands(message)

@bot.command(name="rank")
async def rank_command(ctx, member: discord.Member = None):
    """Sprawdź swój poziom i statystyki"""
    target = member or ctx.author
    user_data = db.get_user_data(target.id, ctx.guild.id)
    
    level, current_xp, xp_needed = XPCalculator.level_from_xp(user_data.get("xp", 0))
    rank_pos = db.get_user_rank(target.id, ctx.guild.id)
    progress_bar = XPCalculator.calculate_progress_bar(current_xp, xp_needed)
    
    embed = discord.Embed(
        title=f"📊 Statystyki {target.display_name}",
        color=discord.Color.blue()
    )
    
    if target.avatar:
        embed.set_thumbnail(url=target.avatar.url)
    
    embed.add_field(name="🎯 Poziom", value=f"**{level}**", inline=True)
    embed.add_field(name="⭐ XP", value=f"**{user_data.get('xp', 0)}**", inline=True)
    
    if rank_pos:
        embed.add_field(name="🏆 Ranking", value=f"**#{rank_pos}**", inline=True)
    
    embed.add_field(
        name=f"📈 Postęp do poziomu {level + 1}",
        value=f"```{progress_bar}```\n{current_xp}/{xp_needed} XP ({current_xp/xp_needed*100:.1f}%)",
        inline=False
    )
    
    embed.add_field(name="💬 Wiadomości", value=f"**{user_data.get('messages', 0)}**", inline=True)
    embed.add_field(name="📦 Total XP", value=f"**{user_data.get('total_xp', 0)}**", inline=True)
    
    if user_data.get("last_active"):
        try:
            last_active = datetime.fromisoformat(user_data["last_active"])
            embed.add_field(
                name="🕐 Ostatnia aktywność",
                value=f"<t:{int(last_active.timestamp())}:R>",
                inline=False
            )
        except (ValueError, KeyError):
            pass
    
    embed.set_footer(text=f"ID: {target.id}")
    await ctx.send(embed=embed)

@bot.command(name="leaderboard")
async def leaderboard_command(ctx):
    """Top 10 najaktywniejszych użytkowników"""
    top_users = db.get_guild_leaderboard(ctx.guild.id, 10)
    
    if not top_users:
        await ctx.send("📭 Brak danych w rankingu!")
        return
    
    embed = discord.Embed(
        title="🏆 TOP 10 RANKING",
        description=f"Ranking aktywności w {ctx.guild.name}",
        color=discord.Color.gold()
    )
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    leaderboard_text = ""
    
    for i, (user_id, user_data) in enumerate(top_users):
        try:
            member = ctx.guild.get_member(user_id)
            if member:
                name = member.display_name
                mention = member.mention
            else:
                name = f"Użytkownik {user_id}"
                mention = f"`{user_id}`"
        except:
            name = f"Użytkownik {user_id}"
            mention = f"`{user_id}`"
        
        level, _, _ = XPCalculator.level_from_xp(user_data.get("xp", 0))
        medal = medals[i] if i < len(medals) else f"{i+1}."
        
        leaderboard_text += f"{medal} {mention} **{name}**\n"
        leaderboard_text += f"   └ Poziom **{level}** | **{user_data.get('xp', 0)}** XP | **{user_data.get('messages', 0)}** wiadomości\n\n"
    
    embed.description = leaderboard_text
    
    total_messages = sum(data.get("messages", 0) for _, data in top_users)
    embed.set_footer(text=f"Łącznie wiadomości w TOP10: {total_messages}")
    
    await ctx.send(embed=embed)

@bot.tree.command(name="xpadd", description="Dodaj XP użytkownikowi (tylko admin)")
@commands.has_permissions(administrator=True)
async def xp_add(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer()
    
    if amount <= 0:
        await interaction.followup.send("❌ Ilość XP musi być większa od 0!")
        return
    
    user_data = db.get_user_data(member.id, interaction.guild.id)
    old_xp = user_data.get("xp", 0)
    old_level, _, _ = XPCalculator.level_from_xp(old_xp)
    
    user_data["xp"] = user_data.get("xp", 0) + amount
    user_data["total_xp"] = user_data.get("total_xp", 0) + amount
    
    new_level, _, _ = XPCalculator.level_from_xp(user_data["xp"])
    db.update_user(member.id, interaction.guild.id, user_data)
    
    if new_level > old_level:
        await RoleManager.assign_level_roles(member, new_level, old_level)
    
    embed = discord.Embed(
        title="✅ XP dodane pomyślnie",
        color=discord.Color.green()
    )
    embed.add_field(name="Użytkownik", value=member.mention, inline=True)
    embed.add_field(name="Dodano XP", value=f"**+{amount}**", inline=True)
    embed.add_field(name="Nowe XP", value=f"**{user_data['xp']}**", inline=True)
    embed.add_field(name="Poziom", value=f"**{old_level} → {new_level}**", inline=True)
    embed.add_field(name="Total XP", value=f"**{user_data['total_xp']}**", inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="xpremove", description="Odejmij XP użytkownikowi (tylko admin)")
@commands.has_permissions(administrator=True)
async def xp_remove(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer()
    
    if amount <= 0:
        await interaction.followup.send("❌ Ilość XP musi być większa od 0!")
        return
    
    user_data = db.get_user_data(member.id, interaction.guild.id)
    old_xp = user_data.get("xp", 0)
    old_level, _, _ = XPCalculator.level_from_xp(old_xp)
    
    user_data["xp"] = max(0, user_data.get("xp", 0) - amount)
    new_level, _, _ = XPCalculator.level_from_xp(user_data["xp"])
    db.update_user(member.id, interaction.guild.id, user_data)
    
    if new_level < old_level:
        await RoleManager.remove_all_level_roles(member)
        if new_level > 0:
            await RoleManager.assign_level_roles(member, new_level, 0)
    
    embed = discord.Embed(
        title="✅ XP odjęte pomyślnie",
        color=discord.Color.orange()
    )
    embed.add_field(name="Użytkownik", value=member.mention, inline=True)
    embed.add_field(name="Odjęto XP", value=f"**-{amount}**", inline=True)
    embed.add_field(name="Nowe XP", value=f"**{user_data['xp']}**", inline=True)
    embed.add_field(name="Poziom", value=f"**{old_level} → {new_level}**", inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="xpreset", description="Zresetuj statystyki użytkownika (tylko admin)")
@commands.has_permissions(administrator=True)
async def xp_reset(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    
    user_data = {
        "xp": 0,
        "level": 1,
        "messages": 0,
        "total_xp": 0,
        "last_active": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat()
    }
    
    db.update_user(member.id, interaction.guild.id, user_data)
    await RoleManager.remove_all_level_roles(member)
    
    embed = discord.Embed(
        title="🔄 Statystyki zresetowane",
        description=f"Statystyki {member.mention} zostały zresetowane!",
        color=discord.Color.red()
    )
    embed.add_field(name="Poziom", value="**1**", inline=True)
    embed.add_field(name="XP", value="**0**", inline=True)
    embed.add_field(name="Wiadomości", value="**0**", inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="setlevelchannel", description="Ustaw kanał do wiadomości o awansach (admin)")
@commands.has_permissions(administrator=True)
async def set_level_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer()
    
    config.level_up_channel_id = channel.id
    
    embed = discord.Embed(
        title="✅ Kanał ustawiony",
        description=f"Kanał do wiadomości o awansach został ustawiony na {channel.mention}",
        color=discord.Color.green()
    )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="testlevelup", description="Testuj wiadomość o awansie (admin)")
@commands.has_permissions(administrator=True)
async def test_level_up(interaction: discord.Interaction, level: int = 5):
    await interaction.response.defer()
    
    try:
        embed = discord.Embed(
            title="🎉 TEST: AWANS POZIOMU! 🎉",
            description=f"{interaction.user.mention} awansował na **poziom {level}!**",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📊 Postęp",
            value=f"```{'█' * 15 + '░' * 5}```\n750/1000 XP (75.0%)",
            inline=False
        )
        
        embed.add_field(
            name="🏆 Ranking",
            value=f"#1 w rankingu serwera",
            inline=True
        )
        
        embed.add_field(
            name="💬 Wiadomości",
            value=f"**500**",
            inline=True
        )
        
        embed.add_field(
            name="⭐ Całkowite XP",
            value=f"**12500**",
            inline=True
        )
        
        if interaction.user.avatar:
            embed.set_thumbnail(url=interaction.user.avatar.url)
        
        embed.set_footer(text=f"ID: {interaction.user.id} | To jest testowa wiadomość")
        
        channel = bot.get_channel(config.level_up_channel_id)
        if channel:
            await channel.send(embed=embed)
            await interaction.followup.send(f"✅ Wysłano testową wiadomość o awansie na {level} poziom do {channel.mention}")
        else:
            await interaction.followup.send("❌ Nie znaleziono kanału! Użyj `/setlevelchannel` najpierw.")
            
    except Exception as e:
        await interaction.followup.send(f"❌ Błąd: {e}")

@tasks.loop(minutes=5)
async def auto_save():
    await db.save_all_async()

@bot.event
async def on_disconnect():
    await db.save_all_async()

@auto_save.before_loop
async def before_auto_save():
    await bot.wait_until_ready()

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("Zamykanie bota...")
    except Exception as e:
        print(f"Błąd uruchamiania bota: {e}")