import discord
import aiohttp
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def get_meme():
    subreddits = ['memes', 'dankmemes', 'polishmemes', 'ProgrammerHumor']
    subreddit = random.choice(subreddits)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f'https://www.reddit.com/r/{subreddit}/hot.json?limit=50') as response:
                data = await response.json()
                posts = [post for post in data['data']['children'] 
                        if not post['data']['over_18'] 
                        and post['data']['url'].endswith(('.jpg', '.png', '.gif'))]
                
                if posts:
                    post = random.choice(posts)['data']
                    return {
                        'title': post['title'],
                        'url': post['url'],
                        'upvotes': post['ups'],
                        'subreddit': subreddit
                    }
        except:
            return None

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='mem', aliases=['meme'])
async def meme_command(ctx):
    meme = await get_meme()
    
    if meme:
        embed = discord.Embed(
            title=meme['title'],
            color=discord.Color.purple()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text=f"👍 {meme['upvotes']} | r/{meme['subreddit']}")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Nie udało się pobrać mema 😅")

TOKEN = "TWÓJ_TOKEN_DISCORD_TUTAJ"
bot.run(TOKEN)