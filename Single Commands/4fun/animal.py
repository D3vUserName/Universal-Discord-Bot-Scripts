import discord
import aiohttp
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

animal_apis = {
    "kot": "https://api.thecatapi.com/v1/images/search",
    "pies": "https://dog.ceo/api/breeds/image/random",
    "lis": "https://randomfox.ca/floof/",
    "ptak": "https://some-random-api.com/img/bird",
    "panda": "https://some-random-api.com/img/panda",
    "koala": "https://some-random-api.com/img/koala"
}

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='zwierzę', aliases=['animal', 'zwierze'])
async def animal_command(ctx, animal_type: str = None):
    if animal_type is None:
        embed = discord.Embed(
            title="🐾 Losowe zdjęcia zwierząt",
            description="Użyj: `!zwierzę <typ>`",
            color=discord.Color.green()
        )
        
        animals_list = ""
        for animal in animal_apis.keys():
            animals_list += f"• {animal.capitalize()}\n"
        
        embed.add_field(name="Dostępne zwierzęta", value=animals_list, inline=False)
        embed.add_field(name="Przykład", value="!zwierzę kot", inline=False)
        embed.add_field(name="Losowe zwierzę", value="!zwierzę losowe", inline=False)
        embed.set_footer(text="Aliasy: !animal, !zwierze")
        
        await ctx.send(embed=embed)
        return
    
    animal_type = animal_type.lower()
    
    if animal_type == "losowe" or animal_type == "random":
        animal_type = random.choice(list(animal_apis.keys()))
    
    if animal_type not in animal_apis:
        await ctx.send(f"❌ Nie znaleziono zwierzęcia: `{animal_type}`\n📋 Dostępne: {', '.join(animal_apis.keys())}")
        return
    
    api_url = animal_apis[animal_type]
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url) as response:
                data = await response.json()

                if animal_type == "kot":
                    image_url = data[0]['url']
                elif animal_type == "pies":
                    image_url = data['message']
                elif animal_type == "lis":
                    image_url = data['image']
                else:
                    image_url = data['link']

                embed = discord.Embed(
                    title=f"🐾 {animal_type.capitalize()}",
                    color=discord.Color.green()
                )
                embed.set_image(url=image_url)
                embed.set_footer(text=f"Żądane przez: {ctx.author.display_name}")
                
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ctx.send(f"❌ Nie udało się pobrać zdjęcia {animal_type}. Spróbuj ponownie!")

@bot.command(name='zwierzęta', aliases=['animals'])
async def animals_list(ctx):
    embed = discord.Embed(
        title="🐾 Lista zwierząt",
        description="Kliknij reakcję aby zobaczyć zdjęcie!",
        color=discord.Color.green()
    )
    
    for animal in animal_apis.keys():
        embed.add_field(
            name=animal.capitalize(),
            value=f"`!zwierzę {animal}`",
            inline=True
        )
    
    await ctx.send(embed=embed)

TOKEN = ""
bot.run(TOKEN)