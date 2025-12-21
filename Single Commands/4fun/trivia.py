import discord
import aiohttp
import random
import os
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

categories = {
    "ogólna": 9,
    "książki": 10,
    "filmy": 11,
    "muzyka": 12,
    "nauka": 17,
    "komputery": 18,
    "matematyka": 19,
    "geografia": 22,
    "historia": 23
}

@bot.event
async def on_ready():
    print(f'Bot {bot.user} jest gotowy!')

@bot.command(name='quiz', aliases=['trivia', 'pytanie'])
async def quiz_command(ctx, category: str = "ogólna"):
    category = category.lower()
    
    if category not in categories:
        embed = discord.Embed(
            title="❓ Dostępne kategorie quizu",
            description="Użyj: `!quiz <kategoria>`",
            color=discord.Color.blue()
        )
        for cat in categories.keys():
            embed.add_field(name=cat.capitalize(), value="✓", inline=True)
        embed.set_footer(text="Przykład: !quiz nauka")
        await ctx.send(embed=embed)
        return
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f'https://opentdb.com/api.php?amount=1&category={categories[category]}&type=multiple&encode=url3986'
            async with session.get(url) as response:
                data = await response.json()
                
                if data['response_code'] == 0:
                    question = data['results'][0]

                    import urllib.parse
                    q_text = urllib.parse.unquote(question['question'])
                    correct_answer = urllib.parse.unquote(question['correct_answer'])
                    incorrect_answers = [urllib.parse.unquote(ans) for ans in question['incorrect_answers']]

                    all_answers = incorrect_answers + [correct_answer]
                    random.shuffle(all_answers)
                    
                    embed = discord.Embed(
                        title="🧠 Quiz Time!",
                        description=f"**Kategoria:** {category.capitalize()}\n**Trudność:** {question['difficulty'].capitalize()}",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="❓ Pytanie", value=q_text, inline=False)

                    answers_text = ""
                    letters = ["🇦", "🇧", "🇨", "🇩"]
                    for i, answer in enumerate(all_answers[:4]):
                        answers_text += f"{letters[i]} {answer}\n"
                    
                    embed.add_field(name="📝 Odpowiedzi", value=answers_text, inline=False)
                    embed.set_footer(text="Odpowiedz reakcją w ciągu 30 sekund!")
                    
                    msg = await ctx.send(embed=embed)

                    for i in range(len(all_answers[:4])):
                        await msg.add_reaction(letters[i])

                    def check(reaction, user):
                        return user == ctx.author and str(reaction.emoji) in letters
                    
                    try:
                        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
                        
                        index = letters.index(str(reaction.emoji))
                        user_answer = all_answers[index]
                        
                        if user_answer == correct_answer:
                            result_embed = discord.Embed(
                                title="✅ Poprawna odpowiedź!",
                                description=f"Brawo {ctx.author.mention}!",
                                color=discord.Color.green()
                            )
                        else:
                            result_embed = discord.Embed(
                                title="❌ Błędna odpowiedź",
                                description=f"Prawidłowa odpowiedź to: **{correct_answer}**",
                                color=discord.Color.red()
                            )
                        
                        await ctx.send(embed=result_embed)
                        
                    except TimeoutError:
                        await ctx.send(f"⏰ Czas minął! Prawidłowa odpowiedź to: **{correct_answer}**")
                    
                else:
                    await ctx.send("❌ Nie udało się pobrać pytania. Spróbuj ponownie!")
                    
        except Exception as e:
            await ctx.send(f"❌ Wystąpił błąd: {str(e)}")


TOKEN = "TWÓJ_TOKEN_DISCORD_TUTAJ"
bot.run(TOKEN)