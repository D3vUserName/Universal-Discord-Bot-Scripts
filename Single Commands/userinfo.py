import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

TOKEN = ""

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.tree.command(name="userinfo", description="Wyświetla informacje o użytkowniku")
@app_commands.describe(user="Użytkownik, o którym chcesz uzyskać informacje")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer()
    
    target = user or interaction.user

    status_emojis = {
        "online": "🟢",
        "idle": "🟡",
        "dnd": "🔴",
        "offline": "⚫"
    }
    
    status_texts = {
        "online": "Online",
        "idle": "Nieaktywny",
        "dnd": "Nie przeszkadzać",
        "offline": "Offline"
    }
    
    status = str(target.status)
    status_display = f"{status_emojis.get(status, '⚫')} {status_texts.get(status, 'Offline')}"
    
    flags = []
    if target.public_flags.staff:
        flags.append("👨‍💼 Pracownik Discord")
    if target.public_flags.partner:
        flags.append("🤝 Partner Discord")
    if target.public_flags.hypesquad:
        flags.append("🏠 HypeSquad")
    if target.public_flags.bug_hunter:
        flags.append("🐛 Bug Hunter")
    if target.public_flags.bug_hunter_level_2:
        flags.append("🐛 Bug Hunter Level 2")
    if target.public_flags.hypesquad_bravery:
        flags.append("⚔️ HypeSquad Bravery")
    if target.public_flags.hypesquad_brilliance:
        flags.append("🎓 HypeSquad Brilliance")
    if target.public_flags.hypesquad_balance:
        flags.append("⚖️ HypeSquad Balance")
    if target.public_flags.early_supporter:
        flags.append("🕐 Early Supporter")
    if target.public_flags.verified_bot_developer:
        flags.append("🤖 Developer bota")
        
    flags_text = "\n".join(flags) if flags else "Brak"

    roles = [role.mention for role in target.roles[1:]]
    if roles:
        roles_text = " ".join(roles[:10]) + (f" ... (+{len(roles)-10})" if len(roles) > 10 else "")
    else:
        roles_text = "Brak ról"
    
    embed = discord.Embed(
        title=f"ℹ️ Informacje o {target.name}",
        color=target.color if target.color.value != 0 else discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    
    embed.add_field(
        name="👤 Podstawowe informacje",
        value=f"**Nazwa:** {target.name}\n"
              f"**Tag:** {target.discriminator}\n"
              f"**ID:** {target.id}\n"
              f"**Status:** {status_display}\n"
              f"**Bot:** {'Tak 🤖' if target.bot else 'Nie 👤'}",
        inline=True
    )
    
    embed.add_field(
        name="📊 Na serwerze",
        value=f"**Pseudonim:** {target.nick or 'Brak'}\n"
              f"**Dołączył:** <t:{int(target.joined_at.timestamp())}:R>\n"
              f"**Utworzono konto:** <t:{int(target.created_at.timestamp())}:R>\n"
              f"**Najwyższa rola:** {target.top_role.mention}",
        inline=True
    )
    
    embed.add_field(
        name=f"🎭 Role ({len(roles)})",
        value=roles_text[:1024] if len(roles_text) > 1024 else roles_text,
        inline=False
    )
    
    embed.add_field(
        name="🏆 Oznaczenia",
        value=flags_text,
        inline=True
    )
    
    activities = []
    if target.activity:
        activity_type = str(target.activity.type).split(".")[-1].title()
        activities.append(f"{activity_type}: **{target.activity.name}**")
    
    embed.add_field(
        name="🎮 Aktywności",
        value="\n".join(activities) if activities else "Brak aktywności",
        inline=True
    )
    
    embed.set_footer(text=f"Wywołane przez {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.followup.send(embed=embed)


bot.run(TOKEN)