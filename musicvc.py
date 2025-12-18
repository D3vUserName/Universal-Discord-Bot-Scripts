import os
import asyncio
import discord
from discord import Intents, Interaction, app_commands
from discord.ext import commands
from discord.ui import Button, View
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Dict, Optional, List
import re
from collections import deque
from datetime import datetime, timedelta
import json
from enum import Enum

TOKEN = ""
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': False,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn -filter:a "volume=0.8"'
}

class PlayerState(Enum):
    PLAYING = "▶️ Odtwarzanie"
    PAUSED = "⏸️ Wstrzymane"
    STOPPED = "⏹️ Zatrzymane"

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.now_playing = None
        self.loop = False
        self.loop_queue = False
        self.history = deque(maxlen=10)
    
    def add(self, track):
        self.queue.append(track)
    
    def add_next(self, track):
        self.queue.appendleft(track)
    
    def get_next(self):
        if self.loop and self.now_playing:
            return self.now_playing.copy()
        
        if self.queue:
            track = self.queue.popleft()
            self.now_playing = track

            self.history.append(track)
            
            if self.loop_queue:
                self.queue.append(track)
            
            return track
        return None
    
    def clear(self):
        self.queue.clear()
    
    def remove(self, index):
        if 0 <= index < len(self.queue):
            del self.queue[index]
            return True
        return False
    
    def get_queue_list(self):
        return list(self.queue)
    
    def shuffle(self):
        import random
        if len(self.queue) >= 2:
            queue_list = list(self.queue)
            random.shuffle(queue_list)
            self.queue = deque(queue_list)
    
    def is_empty(self):
        return not self.queue and not self.loop and not self.loop_queue
    
    @property
    def size(self):
        return len(self.queue)

class ControlPanel(View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.message = None
    
    async def update_buttons(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        queue = self.bot.get_queue(self.guild_id)
        
        if voice_client and voice_client.is_paused():
            self.children[0].emoji = "▶️"
            self.children[0].label = "Wznów"
        else:
            self.children[0].emoji = "⏸️"
            self.children[0].label = "Pauza"
        
        self.children[3].style = discord.ButtonStyle.green if queue.loop else discord.ButtonStyle.grey
        self.children[4].style = discord.ButtonStyle.green if queue.loop_queue else discord.ButtonStyle.grey
        
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
    
    @discord.ui.button(emoji="⏸️", label="Pauza", style=discord.ButtonStyle.blurple)
    async def pause_resume_button(self, interaction: Interaction, button: Button):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        
        if not voice_client:
            await interaction.response.send_message("Bot nie jest podłączony do kanału głosowego!", ephemeral=True)
            return
        
        if voice_client.is_playing():
            voice_client.pause()
            button.emoji = "▶️"
            button.label = "Wznów"
        elif voice_client.is_paused():
            voice_client.resume()
            button.emoji = "⏸️"
            button.label = "Pauza"
        
        await self.update_buttons()
        await interaction.response.defer()
    
    @discord.ui.button(emoji="⏭️", label="Skip", style=discord.ButtonStyle.blurple)
    async def skip_button(self, interaction: Interaction, button: Button):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message("Nic nie jest odtwarzane!", ephemeral=True)
            return
        
        voice_client.stop()
        await interaction.response.defer()
    
    @discord.ui.button(emoji="⏹️", label="Stop", style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: Interaction, button: Button):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        
        if not voice_client:
            await interaction.response.send_message("Bot nie jest podłączony do kanału głosowego!", ephemeral=True)
            return

        queue = self.bot.get_queue(self.guild_id)
        queue.clear()

        voice_client.stop()

        await voice_client.disconnect()

        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        if self.guild_id in self.bot.bot_messages:
            self.bot.bot_messages[self.guild_id] = []
        
        await interaction.response.send_message("⏹️ Zatrzymano odtwarzanie i wyczyszczono kolejkę")
    
    @discord.ui.button(emoji="🔁", label="Loop", style=discord.ButtonStyle.grey)
    async def loop_button(self, interaction: Interaction, button: Button):
        queue = self.bot.get_queue(self.guild_id)
        queue.loop = not queue.loop
        queue.loop_queue = False
        
        status = "włączone" if queue.loop else "wyłączone"
        button.style = discord.ButtonStyle.green if queue.loop else discord.ButtonStyle.grey
        
        await self.update_buttons()
        await interaction.response.send_message(f"🔁 Zapętlanie utworu: **{status}**", ephemeral=True)
    
    @discord.ui.button(emoji="🔂", label="Loop Queue", style=discord.ButtonStyle.grey)
    async def loop_queue_button(self, interaction: Interaction, button: Button):
        queue = self.bot.get_queue(self.guild_id)
        queue.loop_queue = not queue.loop_queue
        queue.loop = False
        
        status = "włączone" if queue.loop_queue else "wyłączone"
        button.style = discord.ButtonStyle.green if queue.loop_queue else discord.ButtonStyle.grey
        
        await self.update_buttons()
        await interaction.response.send_message(f"🔂 Zapętlanie kolejki: **{status}**", ephemeral=True)
    
    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.blurple)
    async def shuffle_button(self, interaction: Interaction, button: Button):
        queue = self.bot.get_queue(self.guild_id)
        
        if len(queue.queue) < 2:
            await interaction.response.send_message("Za mało utworów w kolejce do wymieszania!", ephemeral=True)
            return
        
        queue.shuffle()
        await interaction.response.send_message("🔀 Wymieszano kolejkę!", ephemeral=True)
    
    @discord.ui.button(emoji="📋", label="Kolejka", style=discord.ButtonStyle.green)
    async def queue_button(self, interaction: Interaction, button: Button):
        queue = self.bot.get_queue(self.guild_id)
        queue_list = queue.get_queue_list()
        
        if not queue_list and not queue.now_playing:
            await interaction.response.send_message("Kolejka jest pusta!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Kolejka odtwarzania",
            color=discord.Color.blurple(),
            timestamp=datetime.now()
        )
        
        if queue.now_playing:
            embed.add_field(
                name="🎶 Teraz odtwarzane",
                value=f"**{queue.now_playing.get('title', 'Nieznany tytuł')[:80]}**",
                inline=False
            )
        
        if queue_list:
            queue_text = ""
            for i, track in enumerate(queue_list[:10], 1):
                title = track.get('title', 'Nieznany tytuł')[:60]
                queue_text += f"`{i}.` {title}\n"
            
            if len(queue_list) > 10:
                queue_text += f"\n...i {len(queue_list) - 10} więcej"
            
            embed.add_field(name="⏭️ W kolejce", value=queue_text, inline=False)
        
        embed.set_footer(text=f"🔁: {'✅' if queue.loop else '❌'} | 🔂: {'✅' if queue.loop_queue else '❌'}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(emoji="🔊", label="+10%", style=discord.ButtonStyle.grey)
    async def volume_up_button(self, interaction: Interaction, button: Button):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        
        if not voice_client or not voice_client.source:
            await interaction.response.send_message("Nic nie jest odtwarzane!", ephemeral=True)
            return
        
        current_volume = voice_client.source.volume * 100
        new_volume = min(100, current_volume + 10)
        voice_client.source.volume = new_volume / 100
        
        await interaction.response.send_message(f"🔊 Głośność: **{new_volume:.0f}%**", ephemeral=True)
    
    @discord.ui.button(emoji="🔉", label="-10%", style=discord.ButtonStyle.grey)
    async def volume_down_button(self, interaction: Interaction, button: Button):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        
        if not voice_client or not voice_client.source:
            await interaction.response.send_message("Nic nie jest odtwarzane!", ephemeral=True)
            return
        
        current_volume = voice_client.source.volume * 100
        new_volume = max(0, current_volume - 10)
        voice_client.source.volume = new_volume / 100
        
        await interaction.response.send_message(f"🔉 Głośność: **{new_volume:.0f}%**", ephemeral=True)
    
    @discord.ui.button(emoji="❌", label="Disconnect", style=discord.ButtonStyle.red, row=1)
    async def disconnect_button(self, interaction: Interaction, button: Button):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        voice_client = guild.voice_client
        
        if not voice_client:
            await interaction.response.send_message("Bot nie jest podłączony do kanału głosowego!", ephemeral=True)
            return
        
        queue = self.bot.get_queue(self.guild_id)
        queue.clear()

        await voice_client.disconnect()
        
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        if self.guild_id in self.bot.bot_messages:
            self.bot.bot_messages[self.guild_id] = []
        
        await interaction.response.send_message("👋 Rozłączono z kanału głosowego")

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Nieznany tytuł')
        self.url = data.get('url', '')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail', '')
        self.uploader = data.get('uploader', 'Nieznany artysta')
        self.views = data.get('view_count', 0)
        self.likes = data.get('like_count', 0)
    
    @classmethod
    async def create_source(cls, search: str, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        if not cls.is_url(search):
            search = f"ytsearch:{search}"
        
        ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
            
            if not data:
                return None
            
            if 'url' in data:
                filename = data['url']
            else:
                formats = data.get('formats', [])
                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_formats:
                    filename = audio_formats[0]['url']
                else:
                    for f in formats:
                        if f.get('acodec') != 'none':
                            filename = f['url']
                            break
                    else:
                        filename = data.get('webpage_url', '')
            
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except Exception as e:
            print(f"Błąd podczas pobierania: {e}")
            return None
    
    @staticmethod
    def is_url(string: str) -> bool:
        regex = re.compile(
            r'^(?:http|ftp)s?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return re.match(regex, string) is not None

class SpotifyHandler:
    def __init__(self, client_id, client_secret):
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
    
    def extract_track_info(self, url):
        try:
            if 'track' in url:
                track = self.sp.track(url)
                return {
                    'title': f"{track['name']} - {', '.join([artist['name'] for artist in track['artists']])}",
                    'artists': [artist['name'] for artist in track['artists']],
                    'duration_ms': track['duration_ms'],
                    'album': track['album']['name'],
                    'cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'url': track['external_urls']['spotify']
                }
            elif 'playlist' in url:
                playlist = self.sp.playlist(url, fields='name,tracks(items(track(name,artists(name),duration_ms,external_urls)))')
                tracks = []
                for item in playlist['tracks']['items']:
                    track = item['track']
                    tracks.append({
                        'title': f"{track['name']} - {', '.join([artist['name'] for artist in track['artists']])}",
                        'artists': [artist['name'] for artist in track['artists']],
                        'duration_ms': track['duration_ms'],
                        'url': track['external_urls']['spotify']
                    })
                return {'playlist': True, 'tracks': tracks, 'name': playlist['name']}
            elif 'album' in url:
                album = self.sp.album(url)
                tracks = []
                for track in album['tracks']['items']:
                    tracks.append({
                        'title': f"{track['name']} - {', '.join([artist['name'] for artist in track['artists']])}",
                        'artists': [artist['name'] for artist in track['artists']],
                        'duration_ms': track['duration_ms'],
                        'url': f"https://open.spotify.com/track/{track['id']}"
                    })
                return {'album': True, 'tracks': tracks, 'name': album['name']}
        except Exception as e:
            print(f"Błąd Spotify: {e}")
            return None

class MusicBot(commands.Bot):
    def __init__(self):
        intents = Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.queues: Dict[int, MusicQueue] = {}
        self.control_panels: Dict[int, ControlPanel] = {}
        self.bot_messages: Dict[int, List[discord.Message]] = {}
        self.spotify_handler = None
        
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            try:
                self.spotify_handler = SpotifyHandler(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
            except Exception as e:
                print(f"Błąd inicjalizacji Spotify: {e}")

        self.on_ready = self.on_ready_handler
        self.tree.on_error = self.on_app_command_error
    
    async def on_ready_handler(self):
        print(f'{self.user} został uruchomiony!')
        print(f'Zaproszenie bota: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=8&scope=bot%20applications.commands')
        
        try:
            synced = await self.tree.sync()
            print(f"Zsynchronizowano {len(synced)} komend slash")
        except Exception as e:
            print(f"Błąd synchronizacji komend: {e}")
    
    async def on_app_command_error(self, interaction: Interaction, error):
        print(f"Błąd komendy: {error}")
        
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ Komenda jest na cooldownie! Spróbuj za {error.retry_after:.1f}s.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Wystąpił błąd: {str(error)}",
                ephemeral=True
            )
    
    def get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]
    
    async def join_voice_channel(self, interaction: Interaction):
        if not interaction.user.voice:
            await interaction.response.send_message("🎧 Musisz być na kanale głosowym!", ephemeral=True)
            return None
        
        voice_channel = interaction.user.voice.channel
        
        if not voice_channel.permissions_for(interaction.guild.me).connect:
            await interaction.response.send_message("❌ Nie mam uprawnień do dołączenia na ten kanał!", ephemeral=True)
            return None
        
        if not voice_channel.permissions_for(interaction.guild.me).speak:
            await interaction.response.send_message("❌ Nie mam uprawnień do mówienia na tym kanale!", ephemeral=True)
            return None
        
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.channel != voice_channel:
                await interaction.guild.voice_client.move_to(voice_channel)
        else:
            await voice_channel.connect()
        
        return interaction.guild.voice_client
    
    async def create_control_panel(self, interaction: Interaction):
        guild_id = interaction.guild_id
        
        if guild_id in self.control_panels:
            old_panel = self.control_panels[guild_id]
            if old_panel.message:
                try:
                    await old_panel.message.delete()
                except:
                    pass
        
        panel = ControlPanel(self, guild_id)
        self.control_panels[guild_id] = panel
        
        return panel
    
    async def send_now_playing_embed(self, interaction: Interaction, track_info: dict, source: YTDLSource = None):
        queue = self.get_queue(interaction.guild_id)
        
        embed = discord.Embed(
            title="🎵 Teraz odtwarzane",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )

        title = track_info.get('title', 'Nieznany tytuł')
        embed.add_field(name="Tytuł", value=title, inline=False)
        
        if source:
            if source.duration > 0:
                minutes, seconds = divmod(source.duration, 60)
                hours, minutes = divmod(minutes, 60)
                
                if hours > 0:
                    duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = f"{minutes}:{seconds:02d}"
                
                embed.add_field(name="⏱️ Czas trwania", value=duration_str, inline=True)
            
            if source.uploader and source.uploader != 'Nieznany artysta':
                embed.add_field(name="👤 Artysta", value=source.uploader, inline=True)
            
            if source.thumbnail:
                embed.set_thumbnail(url=source.thumbnail)
            
            embed.url = source.url
        
        queue_size = len(queue.queue)
        if queue_size > 0:
            embed.add_field(name="📊 Kolejka", value=f"{queue_size} utwór(ów) w kolejce", inline=True)
        
        loop_status = []
        if queue.loop:
            loop_status.append("🔁 Utwór")
        if queue.loop_queue:
            loop_status.append("🔂 Kolejka")
        
        if loop_status:
            embed.add_field(name="Zapętlenie", value=" | ".join(loop_status), inline=True)
        
        if source and source.duration > 0:
            end_time = datetime.now() + timedelta(seconds=source.duration)
            embed.add_field(name="⏰ Zakończenie", value=end_time.strftime("%H:%M"), inline=True)
        
        embed.set_footer(text=f"Żądane przez {interaction.user.display_name}", icon_url=interaction.user.avatar.url)
        
        return embed
    
    async def process_spotify_url(self, url: str, interaction: Interaction):
        if not self.spotify_handler:
            await interaction.followup.send("❌ Integracja ze Spotify nie jest skonfigurowana!")
            return []
        
        spotify_data = self.spotify_handler.extract_track_info(url)
        
        if not spotify_data:
            await interaction.followup.send("❌ Nie udało się pobrać informacji z Spotify!")
            return []
        
        tracks = []
        
        if 'playlist' in spotify_data or 'album' in spotify_data:
            count = len(spotify_data['tracks'])
            name = spotify_data['name']
            
            for track in spotify_data['tracks']:
                tracks.append({
                    'title': track['title'],
                    'query': track['title'],
                    'type': 'spotify',
                    'url': track.get('url', '')
                })
            
            await interaction.followup.send(f"✅ Dodano **{count}** utworów z **{name}** do kolejki!")
            
        else:
            tracks.append({
                'title': spotify_data['title'],
                'query': spotify_data['title'],
                'type': 'spotify',
                'url': spotify_data.get('url', '')
            })
            
            await interaction.followup.send(f"✅ Dodano do kolejki: **{spotify_data['title']}**")
        
        return tracks
    
    async def cleanup_voice_channel_chat(self, voice_channel_id: int, guild_id: int):
        try:
            voice_channel = self.get_channel(voice_channel_id)
            if not voice_channel:
                return
            
            if guild_id in self.bot_messages:
                for msg in self.bot_messages[guild_id]:
                    try:
                        await msg.delete()
                    except:
                        pass
                self.bot_messages[guild_id] = []
            
            try:
                async for message in voice_channel.history(limit=50):
                    if message.author.id == self.user.id:
                        try:
                            await message.delete()
                            await asyncio.sleep(0.1)
                        except:
                            pass
            except discord.Forbidden:
                print("Brak uprawnień do czytania historii VCC")
            except Exception as e:
                print(f"Błąd podczas czyszczenia VCC: {e}")
                
        except Exception as e:
            print(f"Błąd w cleanup_voice_channel_chat: {e}")
    
    async def send_to_voice_channel_chat(self, voice_channel_id: int, guild_id: int, 
                                         content: str = None, embed: discord.Embed = None, 
                                         view: View = None, cleanup: bool = True):
        try:
            voice_channel = self.get_channel(voice_channel_id)
            if not voice_channel:
                print(f"Nie znaleziono kanału głosowego o ID: {voice_channel_id}")
                return None
        
            if cleanup:
                await self.cleanup_voice_channel_chat(voice_channel_id, guild_id)
            
            message = await voice_channel.send(content=content, embed=embed, view=view)

            if guild_id not in self.bot_messages:
                self.bot_messages[guild_id] = []
            
            self.bot_messages[guild_id].append(message)
            
            if len(self.bot_messages[guild_id]) > 5:
                self.bot_messages[guild_id] = self.bot_messages[guild_id][-5:]
            
            return message
            
        except discord.Forbidden:
            print("Brak uprawnień do wysyłania wiadomości na Voice Channel Chat")
            return None
        except discord.HTTPException as e:
            print(f"Błąd HTTP przy wysyłaniu do Voice Channel Chat: {e}")
            return None
        except Exception as e:
            print(f"Nieoczekiwany błąd w send_to_voice_channel_chat: {e}")
            return None
    
    async def play_next(self, guild_id: int, interaction: Interaction = None):
        queue = self.get_queue(guild_id)
        guild = self.get_guild(guild_id)
        
        if not guild or not guild.voice_client:
            return
        
        next_track = queue.get_next()
        
        if not next_track:
            if guild.voice_client and guild.voice_client.is_connected():
                await guild.voice_client.disconnect()

                if guild_id in self.bot_messages:
                    self.bot_messages[guild_id] = []
                
                if interaction and interaction.channel:
                    await interaction.channel.send("✅ Kolejka zakończona! Bot rozłączył się z kanału głosowego.")
            return
        
        try:
            search_query = next_track.get('url') or next_track['query']
            source = await YTDLSource.create_source(search_query)
            
            if not source:
                if interaction and interaction.channel:
                    await interaction.channel.send(f"❌ Nie udało się znaleźć: {next_track['title']}")
                await asyncio.sleep(1)
                await self.play_next(guild_id, interaction)
                return
            
            source.volume = 0.5
            
            panel = await self.create_control_panel(interaction)
            
            embed = await self.send_now_playing_embed(interaction, next_track, source)
            
            panel_message = await self.send_to_voice_channel_chat(
                guild.voice_client.channel.id,
                guild_id,
                embed=embed,
                view=panel,
                cleanup=True
            )
            
            if panel_message:
                panel.message = panel_message
            
            def after_playback(error):
                if error:
                    print(f"Błąd podczas odtwarzania: {error}")
                
                self.loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self.play_next(guild_id, interaction)
                )
            
            guild.voice_client.play(source, after=after_playback)
            
            print(f"🎶 Odtwarzam: {source.title}")
            
        except Exception as e:
            print(f"❌ Błąd odtwarzania: {e}")
            if interaction and interaction.channel:
                await interaction.channel.send(f"❌ Błąd podczas odtwarzania: {str(e)}")
            await asyncio.sleep(1)
            await self.play_next(guild_id, interaction)

bot = MusicBot()

@bot.tree.command(name="play", description="Odtwarzaj muzykę z YouTube lub Spotify")
@app_commands.describe(query="Nazwa utworu, artysty lub URL (YouTube/Spotify)")
@app_commands.checks.cooldown(1, 5.0)
async def play_command(interaction: Interaction, query: str):
    await interaction.response.defer()

    voice_client = await bot.join_voice_channel(interaction)
    if not voice_client:
        return
    
    queue = bot.get_queue(interaction.guild_id)

    is_spotify = 'spotify.com' in query and bot.spotify_handler

    was_queue_empty = queue.is_empty()
    
    if is_spotify:
        tracks = await bot.process_spotify_url(query, interaction)
        if not tracks:
            return

        for track in tracks:
            queue.add(track)
    else:
        try:
            ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

            if not YTDLSource.is_url(query):
                search_query = f"ytsearch:{query}"
            else:
                search_query = query
            
            data = await bot.loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(search_query, download=False)
            )
            
            if 'entries' in data:
                data = data['entries'][0]
            
            if not data:
                await interaction.followup.send("❌ Nie znaleziono utworu!")
                return
            
            track = {
                'title': data.get('title', query),
                'query': data.get('webpage_url', query),
                'type': 'youtube',
                'url': data.get('webpage_url', '')
            }
            
            queue.add(track)
            
            await interaction.followup.send(f"✅ Dodano do kolejki: **{track['title']}**")
            
        except Exception as e:
            print(f"❌ Błąd wyszukiwania: {e}")
            await interaction.followup.send("❌ Wystąpił błąd podczas wyszukiwania utworu!")
            return
        
    if (not voice_client.is_playing() and not voice_client.is_paused()) or was_queue_empty:
        await bot.play_next(interaction.guild_id, interaction)
    else:
        if interaction.guild_id in bot.control_panels:
            panel = bot.control_panels[interaction.guild_id]
            await panel.update_buttons()

@play_command.error
async def play_command_error(interaction: Interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Poczekaj {error.retry_after:.1f} sekund przed kolejnym użyciem!",
            ephemeral=True
        )

if __name__ == "__main__":
    if not TOKEN:
        print("\n🌐 Pobierz token bota: https://discord.com/developers/applications")
        print("🎵 Spotify Developer: https://developer.spotify.com/dashboard")
        exit(1)
    
    try:
        import subprocess
        subprocess.run(['ffmpeg', '-version'], capture_output=True)
        print("✅ FFmpeg jest zainstalowany")
    except:
        print("⚠️  UWAGA: FFmpeg nie jest zainstalowany!")
        print("\n📥 Zainstaluj FFmpeg:")
        print("• Windows: Pobierz z ffmpeg.org i dodaj do PATH")
        print("• Ubuntu/Debian: sudo apt install ffmpeg")
        print("• macOS: brew install ffmpeg")
        print("\n🔄 Uruchom ponownie po instalacji")
    
    print("\n🚀 Uruchamianie bota muzycznego...")
    print("=" * 50)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ BŁĄD: Nieprawidłowy token Discord!")
    except Exception as e:
        print(f"❌ BŁĄD: {type(e).__name__}: {e}")