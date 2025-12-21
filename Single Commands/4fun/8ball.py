import discord
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

responses = [
    "🎱 Tak, zdecydowanie!",
    "🎱 Na pewno!",
    "🎱 Bez wątpienia!",
    "🎱 Zdecydowanie tak!",
    "🎱 Możesz na to liczyć!",
    "🎱 Według mnie - tak",
    "🎱 Prawdopodobnie",
    "🎱 Dobre perspektywy",
    "🎱 Znaki wskazują na tak",
    "🎱 Nie wiem, spróbuj ponownie",
    "🎱 Zapytaj później",
    "🎱 Lepiej ci nie mówić",
    "🎱 Nie teraz",
    "🎱 Nie mogę tego przewidzieć",
    "🎱 Skup się i zapytaj ponownie",
    "🎱 Nie licz na to",
    "🎱 Moja odpowiedź brzmi: nie",
    "🎱 Źródła mówią nie",
    "🎱 Perspektywy nie są dobre",
    "🎱 Bardzo wątpliwe"
]

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='8ball', aliases=['magicball', 'kula'])
async def eight_ball(ctx, *, question):
    if not question.endswith('?'):
        question = question + '?'
    
    answer = random.choice(responses)
    
    embed = discord.Embed(
        title="🎱 Magiczna Kula",
        color=discord.Color.dark_blue()
    )
    embed.add_field(name="❓ Pytanie", value=question, inline=False)
    embed.add_field(name="💭 Odpowiedź", value=answer, inline=False)
    embed.set_footer(text=f"Zapytał: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)

TOKEN = ""
bot.run(TOKEN)