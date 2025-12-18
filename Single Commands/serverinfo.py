import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

TOKEN = ""

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.tree.command(name="serverinfo", description="Wyświetla informacje o serwerze")
async def serverinfo(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild

    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    category_channels = len(guild.categories)

    total_members = guild.member_count
    online_members = sum(1 for member in guild.members if member.status != discord.Status.offline)
    bots = sum(1 for member in guild.members if member.bot)
    humans = total_members - bots
    
    verification_levels = {
        discord.VerificationLevel.none: "Brak",
        discord.VerificationLevel.low: "Niski",
        discord.VerificationLevel.medium: "Średni",
        discord.VerificationLevel.high: "Wysoki",
        discord.VerificationLevel.highest: "Najwyższy"
    }
    
    content_filter_levels = {
        discord.ContentFilter.disabled: "Wyłączony",
        discord.ContentFilter.no_role: "Bez roli",
        discord.ContentFilter.all_members: "Wszyscy"
    }
    
    boost_tier = guild.premium_tier
    boost_count = guild.premium_subscription_count
    boost_emojis = ["⚪", "🟣", "🟢", "🟠"]

    emoji_count = len(guild.emojis)
    sticker_count = len(guild.stickers)
    
    embed = discord.Embed(
        title=f"ℹ️ Informacje o {guild.name}",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="📋 Podstawowe informacje",
        value=f"**Nazwa:** {guild.name}\n"
              f"**ID:** {guild.id}\n"
              f"**Właściciel:** {guild.owner.mention}\n"
              f"**Utworzono:** <t:{int(guild.created_at.timestamp())}:R>\n"
              f"**Region:** {str(guild.preferred_locale).title()}",
        inline=True
    )

    embed.add_field(
        name="📊 Statystyki",
        value=f"**Członkowie:** {total_members}\n"
              f"• 👥 Ludzie: {humans}\n"
              f"• 🤖 Boty: {bots}\n"
              f"• 🟢 Online: {online_members}\n\n"
              f"**Kanały:** {text_channels + voice_channels + category_channels}\n"
              f"• 💬 Tekstowe: {text_channels}\n"
              f"• 🔊 Głosowe: {voice_channels}\n"
              f"• 📁 Kategorie: {category_channels}",
        inline=True
    )

    embed.add_field(
        name="✨ Boosty",
        value=f"**Poziom:** {boost_emojis[boost_tier if boost_tier < 4 else 3]} Tier {boost_tier}\n"
              f"**Liczba boostów:** {boost_count}\n\n"
              f"**Emoji:** {emoji_count}/50\n"
              f"**Naklejki:** {sticker_count}/60",
        inline=True
    )

    features = []
    if "COMMUNITY" in guild.features:
        features.append("🏘️ Community")
    if "PARTNERED" in guild.features:
        features.append("🤝 Partner")
    if "VERIFIED" in guild.features:
        features.append("✅ Zweryfikowany")
    if "INVITE_SPLASH" in guild.features:
        features.append("🎨 Invite Splash")
    if "BANNER" in guild.features:
        features.append("🖼️ Banner")
    if "VANITY_URL" in guild.features:
        features.append("🔗 Własny link")
    
    features_text = " ".join(features) if features else "Brak specjalnych funkcji"
    
    embed.add_field(
        name="⚙️ Funkcje",
        value=features_text,
        inline=False
    )

    embed.add_field(
        name="🔐 Ustawienia",
        value=f"**Weryfikacja:** {verification_levels.get(guild.verification_level, 'Nieznany')}\n"
              f"**Filtr treści:** {content_filter_levels.get(guild.explicit_content_filter, 'Nieznany')}\n"
              f"**AFK timeout:** {guild.afk_timeout // 60} min",
        inline=True
    )
    
    system_channels = []
    if guild.rules_channel:
        system_channels.append(f"**Rules:** {guild.rules_channel.mention}")
    if guild.system_channel:
        system_channels.append(f"**System:** {guild.system_channel.mention}")
    
    embed.add_field(
        name="📢 Kanały systemowe",
        value="\n".join(system_channels) if system_channels else "Brak",
        inline=True
    )
    
    embed.set_footer(text=f"Wywołane przez {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.followup.send(embed=embed)

bot.run(TOKEN)