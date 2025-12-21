import discord
from discord.ext import commands
import aiohttp
import os

TOKEN = ""

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ bot zalogowany jako {bot.user}')

@bot.command(name='anime')
async def anime(ctx, *, title):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.jikan.moe/v4/anime?q={title}&limit=5"
        
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if not data['data']:
                        await ctx.send(f"❌ Nie znaleziono anime: `{title}`")
                        return
                    
                    anime_data = data['data'][0]
                    embed = discord.Embed(
                        title=f"🎬 {anime_data['title']}",
                        description=anime_data.get('synopsis', 'Brak opisu')[:300] + "...",
                        color=discord.Color.purple(),
                        url=anime_data['url']
                    )
                    
                    embed.add_field(name="📺 Typ", value=anime_data.get('type', 'Nieznany'), inline=True)
                    embed.add_field(name="📅 Rok", value=anime_data.get('year', 'Nieznany'), inline=True)
                    embed.add_field(name="🎬 Odcinki", value=anime_data.get('episodes', 'Nieznany'), inline=True)
                    embed.add_field(name="⭐ Ocena", value=anime_data.get('score', 'Nieznany'), inline=True)
                    embed.add_field(name="📊 Status", value=anime_data.get('status', 'Nieznany'), inline=True)
                    embed.add_field(name="👥 Popularność", value=f"#{anime_data.get('popularity', '?')}", inline=True)

                    genres = ", ".join([g['name'] for g in anime_data.get('genres', [])[:3]])
                    if genres:
                        embed.add_field(name="🏷️ Gatunki", value=genres, inline=False)
                    
                    if anime_data.get('images', {}).get('jpg', {}).get('image_url'):
                        embed.set_thumbnail(url=anime_data['images']['jpg']['image_url'])
                    
                    embed.set_footer(text="Źródło: MyAnimeList")
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Błąd połączenia z API. Spróbuj później.")
        except Exception as e:
            await ctx.send(f"❌ Wystąpił błąd: {str(e)}")

@bot.command(name='character')
async def character(ctx, *, name):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.jikan.moe/v4/characters?q={name}&limit=1"
        
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if not data['data']:
                        await ctx.send(f"❌ Nie znaleziono postaci: `{name}`")
                        return
                    
                    char_data = data['data'][0]
                    
                    embed = discord.Embed(
                        title=f"👤 {char_data['name']}",
                        color=discord.Color.blue()
                    )
                    
                    if char_data.get('about'):
                        embed.description = char_data['about'][:250] + "..."
                    
                    if char_data.get('anime'):
                        anime_names = [a['anime']['title'] for a in char_data['anime'][:3]]
                        embed.add_field(name="📺 Występuje w", value="\n".join(anime_names), inline=False)

                    if char_data.get('images', {}).get('jpg', {}).get('image_url'):
                        embed.set_image(url=char_data['images']['jpg']['image_url'])
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Błąd API.")
        except Exception as e:
            await ctx.send(f"❌ Błąd: {str(e)}")

bot.run(TOKEN)