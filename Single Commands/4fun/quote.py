import discord
import aiohttp
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

polish_quotes = [
    {"quote": "Kto czyta książki, żyje podwójnie.", "author": "Umberto Eco"},
    {"quote": "Nadzieja matką głupich.", "author": "Przysłowie polskie"},
    {"quote": "Gdzie drwa rąbią, tam wióry lecą.", "author": "Przysłowie polskie"},
    {"quote": "Lepiej zapobiegać niż leczyć.", "author": "Przysłowie polskie"},
    {"quote": "Co ma wisieć, nie utonie.", "author": "Przysłowie polskie"},
    {"quote": "Bez pracy nie ma kołaczy.", "author": "Przysłowie polskie"},
    {"quote": "Nie od razu Rzym zbudowano.", "author": "Przysłowie polskie"},
    {"quote": "Czym skorupka za młodu nasiąknie, tym na starość trąci.", "author": "Ignacy Krasicki"},
    {"quote": "Szlachetne zdrowie, nikt się nie dowie, jako smakujesz, aż się zepsujesz.", "author": "Jan Kochanowski"},
    {"quote": "Mądry Polak po szkodzie.", "author": "Przysłowie polskie"}
]

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='cytat', aliases=['quote', 'inspiracja'])
async def quote_command(ctx, category: str = None):
    categories = {
        "polski": "Cytaty polskie",
        "motywacja": "Cytaty motywacyjne",
        "filozofia": "Cytaty filozoficzne",
        "losowy": "Losowy cytat z internetu"
    }
    
    if category is None:
        embed = discord.Embed(
            title="📜 System cytatów",
            description="Użyj: `!cytat <kategoria>`",
            color=discord.Color.dark_gold()
        )
        
        for key, value in categories.items():
            embed.add_field(name=key.capitalize(), value=value, inline=True)
        
        embed.add_field(name="Przykład", value="!cytat polski", inline=False)
        embed.set_footer(text="Aliasy: !quote, !inspiracja")
        
        await ctx.send(embed=embed)
        return
    
    category = category.lower()
    
    if category == "polski":
        quote_data = random.choice(polish_quotes)
        quote = quote_data["quote"]
        author = quote_data["author"]
        source = "🇵🇱 Polska kolekcja"
        
    elif category == "motywacja":
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get('https://api.quotable.io/random?tags=motivational') as response:
                    data = await response.json()
                    quote = data['content']
                    author = data['author']
                    source = "💪 Cytat motywacyjny"
            except:
                quote = "Wiara to ptak, który czuje światło i śpiewa, gdy jeszcze jest ciemno."
                author = "Rabindranath Tagore"
                source = "💪 Cytat motywacyjny"
    
    elif category == "filozofia":
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get('https://api.quotable.io/random?tags=philosophy') as response:
                    data = await response.json()
                    quote = data['content']
                    author = data['author']
                    source = "🤔 Cytat filozoficzny"
            except:
                quote = "Myślę, więc jestem."
                author = "Kartezjusz"
                source = "🤔 Cytat filozoficzny"
    
    elif category == "losowy":
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get('https://api.quotable.io/random') as response:
                    data = await response.json()
                    quote = data['content']
                    author = data['author']
                    source = "🎲 Losowy cytat"
            except:
                quote_data = random.choice(polish_quotes)
                quote = quote_data["quote"]
                author = quote_data["author"]
                source = "🎲 Losowy cytat"
    
    else:
        await ctx.send(f"❌ Nieznana kategoria: `{category}`\n📋 Dostępne: {', '.join(categories.keys())}")
        return
    
    embed = discord.Embed(
        title="📜 Cytat",
        description=f"*{quote}*",
        color=discord.Color.dark_gold()
    )
    embed.add_field(name="✍️ Autor", value=author, inline=True)
    embed.add_field(name="📁 Kategoria", value=source, inline=True)
    embed.set_footer(text=f"Dla: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)

@bot.command(name='cytat_dnia', aliases=['qotd'])
async def quote_of_the_day(ctx):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://api.quotable.io/quotes/random') as response:
                data = await response.json()
                quote = data[0]['content']
                author = data[0]['author']
                
                embed = discord.Embed(
                    title="🌟 Cytat Dnia",
                    description=f"*{quote}*",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Autor", value=author, inline=False)
                embed.set_footer(text=f"Dla: {ctx.author.display_name} | Data: {ctx.message.created_at.strftime('%Y-%m-%d')}")
                
                await ctx.send(embed=embed)
                
        except:
            quote_data = random.choice(polish_quotes)
            embed = discord.Embed(
                title="🌟 Cytat Dnia",
                description=f"*{quote_data['quote']}*",
                color=discord.Color.gold()
            )
            embed.add_field(name="Autor", value=quote_data['author'], inline=False)
            embed.set_footer(text=f"Dla: {ctx.author.display_name}")
            await ctx.send(embed=embed)

TOKEN = ""
bot.run(TOKEN)