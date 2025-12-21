import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime

TOKEN = ""

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

BIRTHDAYS_FILE = "birthdays.json"
BIRTHDAY_CHANNEL_ID = None

def load_birthdays():
    try:
        with open(BIRTHDAYS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_birthdays(birthdays):
    with open(BIRTHDAYS_FILE, 'w') as f:
        json.dump(birthdays, f, indent=4)

@bot.event
async def on_ready():
    print(f'✅ Bot zalogowany jako {bot.user}')
    print(f'🎂 Wiadomości będą wysyłane na kanał o ID: {BIRTHDAY_CHANNEL_ID}')
    check_birthdays.start()

@bot.command(name='setbirthday')
async def set_birthday(ctx, day: int, month: int):
    if month < 1 or month > 12:
        await ctx.send("❌ Miesiąc musi być między 1 a 12")
        return
    
    if day < 1 or day > 31:
        await ctx.send("❌ Dzień musi być między 1 a 31")
        return
    
    birthdays = load_birthdays()
    
    user_id = str(ctx.author.id)
    birthdays[user_id] = {
        'day': day,
        'month': month,
        'username': ctx.author.name,
        'display_name': ctx.author.display_name
    }
    
    save_birthdays(birthdays)
    
    await ctx.send(f"🎉 Ustawiono datę urodzin na: **{day}.{month}**")

@bot.command(name='birthday')
async def show_birthday(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    birthdays = load_birthdays()
    user_id = str(member.id)
    
    if user_id in birthdays:
        bday = birthdays[user_id]
        await ctx.send(f"🎂 **{member.display_name}** ma urodziny **{bday['day']}.{bday['month']}**")
    else:
        await ctx.send(f"❌ {member.display_name} nie ustawił jeszcze urodzin")

@bot.command(name='birthdays')
async def list_birthdays(ctx):
    birthdays = load_birthdays()
    
    if not birthdays:
        await ctx.send("🎈 Nikt jeszcze nie ustawił urodzin!")
        return
    
    sorted_bdays = []
    for user_id, data in birthdays.items():
        sorted_bdays.append((data['month'], data['day'], data['display_name']))
    
    sorted_bdays.sort()
    
    embed = discord.Embed(
        title="🎂 Lista urodzin",
        color=discord.Color.pink()
    )
    
    current_month = None
    bday_list = ""
    
    for month, day, name in sorted_bdays:
        if month != current_month:
            if bday_list:
                embed.add_field(name=f"Miesiąc {current_month}", value=bday_list, inline=True)
            current_month = month
            bday_list = ""
        
        bday_list += f"**{day}.{month}** - {name}\n"
    
    if bday_list:
        embed.add_field(name=f"Miesiąc {current_month}", value=bday_list, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='testbirthday')
@commands.has_permissions(administrator=True)
async def test_birthday(ctx):
    channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
    
    if channel:
        message = f"Wszystkiego najlepszego! °°, {ctx.author.mention}"
        await channel.send(message)
        await ctx.send(f"✅ Wysłano testową wiadomość na {channel.mention}")
    else:
        await ctx.send(f"❌ Nie znaleziono kanału o ID: {BIRTHDAY_CHANNEL_ID}")

@bot.command(name='setchannel')
@commands.has_permissions(administrator=True)
async def set_channel(ctx, channel_id: int):
    global BIRTHDAY_CHANNEL_ID
    BIRTHDAY_CHANNEL_ID = channel_id
    
    channel = bot.get_channel(channel_id)
    if channel:
        await ctx.send(f"✅ Ustawiono kanał urodzinowy na: {channel.mention}")
    else:
        await ctx.send(f"✅ Ustawiono ID kanału na: {channel_id}")

@tasks.loop(hours=24)
async def check_birthdays():
    birthdays = load_birthdays()
    
    if not birthdays or not BIRTHDAY_CHANNEL_ID:
        return
    
    today = datetime.now()
    channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
    
    if not channel:
        print(f"❌ Nie znaleziono kanału o ID: {BIRTHDAY_CHANNEL_ID}")
        return
    
    for user_id, data in birthdays.items():
        if data['day'] == today.day and data['month'] == today.month:
            member = None
            for guild in bot.guilds:
                member = guild.get_member(int(user_id))
                if member:
                    break
            
            if member:
                birthday_message = f"Wszystkiego najlepszego! °°, {member.mention}"
                birthday_message += " 🎂🎈🎉"
                
                await channel.send(birthday_message)

                embed = discord.Embed(
                    description=f"**{data['display_name']}** obchodzi dziś urodziny! 🥳\n"
                              f"Data urodzin: {data['day']}.{data['month']}",
                    color=discord.Color.gold()
                )
                if member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)
                
                await channel.send(embed=embed)

@check_birthdays.before_loop
async def before_check_birthdays():
    await bot.wait_until_ready()

bot.run(TOKEN)