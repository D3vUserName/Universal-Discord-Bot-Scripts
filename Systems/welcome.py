import discord
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime

TOKEN = ""

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

CONFIG_FILE = "welcome_config.json"

DEFAULT_CONFIG = {
    'enabled': True,
    'channel_id': None,
    'welcome_message': "Witaj {member.mention} na serwerze **{guild.name}**! 🎉",
    'welcome_embed': True,
    'goodbye_enabled': True,
    'goodbye_message': "**{member.name}** opuścił serwer. 😢",
    'goodbye_embed': True,
    'auto_role': None,
    'dm_welcome': False,
    'dm_message': "Witaj na {guild.name}! Miłego pobytu!",
    'join_dm': False,
    'leave_dm': False,
    'embed_color': "#00FF00",
    'goodbye_color': "#FF0000"
}

class WelcomeSystem:
    def __init__(self):
        self.config_cache = {}
        self.load_config()
    
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config_cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.config_cache = {}
        return self.config_cache
    
    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config_cache, f, indent=4, ensure_ascii=False)
    
    def get_guild_config(self, guild_id):
        guild_id = str(guild_id)
        if guild_id not in self.config_cache:
            self.config_cache[guild_id] = DEFAULT_CONFIG.copy()
        return self.config_cache[guild_id]
    
    def update_guild_config(self, guild_id, updates):
        guild_id = str(guild_id)
        config = self.get_guild_config(guild_id)
        config.update(updates)
        self.config_cache[guild_id] = config
        self.save_config()
    
    def delete_guild_config(self, guild_id):
        guild_id = str(guild_id)
        if guild_id in self.config_cache:
            del self.config_cache[guild_id]
            self.save_config()
            return True
        return False

welcome_system = WelcomeSystem()

@bot.event
async def on_ready():
    print(f'✅ Bot zalogowany jako {bot.user}')

async def send_welcome_message(member):
    config = welcome_system.get_guild_config(member.guild.id)
    
    if not config.get('enabled', True):
        return
    
    channel_id = config.get('channel_id')
    if not channel_id:
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel or not channel.permissions_for(member.guild.me).send_messages:
        return
    
    welcome_message = config.get('welcome_message', DEFAULT_CONFIG['welcome_message'])
    try:
        formatted_message = welcome_message.format(
            member=member,
            user=member,
            guild=member.guild,
            server=member.guild,
            count=member.guild.member_count
        )
    except Exception:
        formatted_message = welcome_message
    
    if not config.get('welcome_embed', True):
        await channel.send(formatted_message)
    else:
        embed_color = config.get('embed_color', "#00FF00")
        try:
            color = int(embed_color.replace("#", ""), 16)
        except ValueError:
            color = discord.Color.green()
        
        embed = discord.Embed(
            title="👋 Witamy na serwerze!",
            description=formatted_message,
            color=color,
            timestamp=datetime.now()
        )
        
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(
            name="📅 Data dołączenia",
            value=f"<t:{int(member.joined_at.timestamp())}:F>",
            inline=True
        )
        embed.add_field(
            name="👥 Numer członka",
            value=f"#{member.guild.member_count}",
            inline=True
        )
        
        embed.set_footer(
            text=f"{member.guild.name}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        
        await channel.send(embed=embed)
    
    role_id = config.get('auto_role')
    if role_id:
        try:
            role = member.guild.get_role(int(role_id))
            if role and role < member.guild.me.top_role:
                await member.add_roles(role, reason="Auto-rola powitalna")
        except Exception as e:
            print(f"❌ Błąd przy nadawaniu roli: {e}")
    
    if config.get('dm_welcome', False):
        dm_message = config.get('dm_message', DEFAULT_CONFIG['dm_message'])
        try:
            formatted_dm = dm_message.format(
                member=member,
                user=member,
                guild=member.guild,
                server=member.guild
            )
            await member.send(formatted_dm)
        except Exception:
            pass

async def send_goodbye_message(member):
    config = welcome_system.get_guild_config(member.guild.id)
    
    if not config.get('enabled', True) or not config.get('goodbye_enabled', True):
        return
    
    channel_id = config.get('channel_id')
    if not channel_id:
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel or not channel.permissions_for(member.guild.me).send_messages:
        return
    
    goodbye_message = config.get('goodbye_message', DEFAULT_CONFIG['goodbye_message'])
    try:
        formatted_message = goodbye_message.format(
            member=member,
            user=member,
            guild=member.guild,
            server=member.guild,
            count=member.guild.member_count
        )
    except Exception:
        formatted_message = goodbye_message
    
    if not config.get('goodbye_embed', True):
        await channel.send(formatted_message)
    else:
        goodbye_color = config.get('goodbye_color', "#FF0000")
        try:
            color = int(goodbye_color.replace("#", ""), 16)
        except ValueError:
            color = discord.Color.red()
        
        embed = discord.Embed(
            title="👋 Opuszczono serwer",
            description=formatted_message,
            color=color,
            timestamp=datetime.now()
        )
        
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_thumbnail(url=avatar_url)

        if member.joined_at:
            duration = datetime.now() - member.joined_at
            days = duration.days
            hours = duration.seconds // 3600
            
            time_info = []
            if days > 0:
                time_info.append(f"{days} dni")
            if hours > 0:
                time_info.append(f"{hours} godzin")
            
            time_str = ", ".join(time_info) if time_info else "Mniej niż godzinę"
            
            embed.add_field(
                name="⏱️ Czas na serwerze",
                value=time_str,
                inline=True
            )
        
        embed.add_field(
            name="👥 Pozostało członków",
            value=member.guild.member_count,
            inline=True
        )

        embed.set_footer(
            text=f"{member.guild.name}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        
        await channel.send(embed=embed)

@bot.event
async def on_member_join(member):
    try:
        await send_welcome_message(member)
    except Exception as e:
        print(f"❌ Błąd w on_member_join: {e}")

@bot.event
async def on_member_remove(member):
    try:
        await send_goodbye_message(member)
    except Exception as e:
        print(f"❌ Błąd w on_member_remove: {e}")

async def setup_guild_welcome(guild, channel=None):
    if not channel:
        for potential_channel in guild.text_channels:
            if potential_channel.name in ['powitania', 'welcome', 'general', 'witamy']:
                if potential_channel.permissions_for(guild.me).send_messages:
                    channel = potential_channel
                    break

        if not channel:
            for potential_channel in guild.text_channels:
                if potential_channel.permissions_for(guild.me).send_messages:
                    channel = potential_channel
                    break
    
    if channel:
        welcome_system.update_guild_config(guild.id, {
            'channel_id': str(channel.id),
            'enabled': True
        })
        return True
    
    return False

@bot.event
async def on_connect():
    for guild in bot.guilds:
        config = welcome_system.get_guild_config(guild.id)
        if not config.get('channel_id'):
            await setup_guild_welcome(guild)

def main():
    try:
        bot.run(TOKEN)
    except discord.LoginError:
        print("❌ Błąd logowania: Nieprawidłowy token")
    except Exception as e:
        print(f"❌ Nieoczekiwany błąd: {e}")

if __name__ == "__main__":
    main()