import discord
import aiohttp
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def get_joke():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,religious,political,racist,sexist,explicit') as response:
                data = await response.json()
                if data['type'] == 'single':
                    return data['joke']
                elif data['type'] == 'twopart':
                    return f"**{data['setup']}**\n\n||{data['delivery']}||"
        except:
            return "Nie udało się pobrać żartu 😔"

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='żart', aliases=['joke'])
async def joke_command(ctx):
    joke = await get_joke()
    embed = discord.Embed(
        title="😂 Losowy żart",
        description=joke,
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Żądane przez: {ctx.author.display_name}")
    await ctx.send(embed=embed)


TOKEN = ""
bot.run(TOKEN)