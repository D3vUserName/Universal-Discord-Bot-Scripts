import discord
from discord.ext import commands
import json
import os
from datetime import datetime

TOKEN = ""

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

SUGGESTIONS_FILE = "suggestions.json"
SUGGESTIONS_CHANNEL_ID = 1450149343536484403

def load_suggestions():
    try:
        with open(SUGGESTIONS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_suggestions(suggestions):
    with open(SUGGESTIONS_FILE, 'w') as f:
        json.dump(suggestions, f, indent=4)

@bot.event
async def on_ready():
    print(f'✅ bot zalogowany jako {bot.user}')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if SUGGESTIONS_CHANNEL_ID and message.channel.id == SUGGESTIONS_CHANNEL_ID:
        await message.delete()

        suggestions = load_suggestions()
        suggestion_id = len(suggestions) + 1
        
        embed = discord.Embed(
            title=f"💡 Sugestia #{suggestion_id}",
            description=message.content,
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url)
        embed.set_footer(text=f"ID: {suggestion_id} | Reakcje do głosowania")

        embed_msg = await message.channel.send(embed=embed)
        
        await embed_msg.add_reaction("👍")
        await embed_msg.add_reaction("👎")

        thread_name = f"Sugestia #{suggestion_id} - {message.author.display_name}"
        thread = await embed_msg.create_thread(
            name=thread_name[:250],
        )
        
        suggestions.append({
            'id': suggestion_id,
            'user_id': str(message.author.id),
            'user_name': message.author.name,
            'user_display_name': message.author.display_name,
            'suggestion': message.content,
            'message_id': str(embed_msg.id),
            'channel_id': str(message.channel.id),
            'thread_id': str(thread.id),
            'timestamp': datetime.now().isoformat(),
            'embed_message_id': str(embed_msg.id)
        })
        
        save_suggestions(suggestions)
        
    
    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    suggestions = load_suggestions()
    
    for suggestion in suggestions:
        if str(reaction.message.id) == suggestion.get('embed_message_id'):
            try:
                channel = bot.get_channel(int(suggestion['channel_id']))
                if channel:
                    msg = await channel.fetch_message(int(suggestion['embed_message_id']))
                    
                    upvotes = 0
                    downvotes = 0
                    
                    for react in msg.reactions:
                        if str(react.emoji) == "👍":
                            upvotes = react.count - 1
                        elif str(react.emoji) == "👎":
                            downvotes = react.count - 1
                    
                    embed = msg.embeds[0]

                    votes_text = f"👍 {upvotes} | 👎 {downvotes}"
                    embed.set_footer(text=f"ID: {suggestion['id']} • {votes_text}")
                    
                    if upvotes - downvotes >= 5:
                        embed.color = discord.Color.gold()
                    elif upvotes - downvotes <= -3:
                        embed.color = discord.Color.red()
                    else:
                        embed.color = discord.Color.green()
                    
                    await msg.edit(embed=embed)
                    break
            except:
                pass

@bot.command(name='setsuggestchannel')
@commands.has_permissions(administrator=True)
async def set_suggest_channel(ctx):
    global SUGGESTIONS_CHANNEL_ID
    SUGGESTIONS_CHANNEL_ID = ctx.channel.id
    
    await ctx.send(f"✅ Ustawiono ten kanał jako kanał sugestii!\n"
                   f"Od teraz każda wiadomość tutaj zostanie zamieniona w sugestię z embed i wątkiem.")

bot.run(TOKEN)