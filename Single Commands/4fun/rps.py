import discord
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

choices = {
    "kamień": "🗿",
    "papier": "📄",
    "nożyce": "✂️"
}

win_conditions = {
    "kamień": "nożyce",
    "papier": "kamień",
    "nożyce": "papier"
}

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='rps', aliases=['pkn', 'kamieńpapiernożyce'])
async def rock_paper_scissors(ctx, user_choice: str = None):
    if user_choice is None:
        embed = discord.Embed(
            title="✂️ Kamień, Papier, Nożyce",
            description="Użyj: `!rps <kamień/papier/nożyce>`",
            color=discord.Color.red()
        )
        embed.add_field(name="Przykład", value="!rps kamień", inline=False)
        embed.add_field(name="Aliasy", value="!pkn, !kamieńpapiernożyce", inline=False)
        await ctx.send(embed=embed)
        return
    
    user_choice = user_choice.lower()
    
    if user_choice not in choices:
        await ctx.send("❌ Nieprawidłowy wybór! Wybierz: kamień, papier lub nożyce")
        return
    
    bot_choice = random.choice(list(choices.keys()))
    
    if user_choice == bot_choice:
        result = "🤝 Remis!"
        color = discord.Color.gold()
    elif win_conditions[user_choice] == bot_choice:
        result = "🎉 Wygrałeś!"
        color = discord.Color.green()
    else:
        result = "😔 Przegrałeś!"
        color = discord.Color.red()
    
    embed = discord.Embed(
        title="✂️ Kamień, Papier, Nożyce",
        color=color
    )
    embed.add_field(
        name="Twoj wybór",
        value=f"{choices[user_choice]} {user_choice.capitalize()}",
        inline=True
    )
    embed.add_field(
        name="Wybór bota",
        value=f"{choices[bot_choice]} {bot_choice.capitalize()}",
        inline=True
    )
    embed.add_field(
        name="Wynik",
        value=f"**{result}**",
        inline=False
    )
    embed.set_footer(text=f"Gracz: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)

TOKEN = ""
bot.run(TOKEN)