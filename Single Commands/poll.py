import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import os
from typing import Optional
import json
from enum import Enum

TOKEN = ""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


class PollStatus(Enum):
    ACTIVE = "🔵 AKTYWNA"
    ENDED = "🔴 ZAKOŃCZONA"
    TIED = "⚖️ REMIS"


class PollView(discord.ui.View):
    def __init__(self, poll_id: str, duration_seconds: int):
        super().__init__(timeout=duration_seconds)
        self.poll_id = poll_id
        self.yes_votes = 0
        self.no_votes = 0
        self.voters = {}
        self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(seconds=duration_seconds)
        self.is_active = True

    def _progress_bar(self, percentage: float) -> str:
        filled = int(percentage / 5)
        return "█" * filled + "░" * (20 - filled)

    def _calculate_percentages(self) -> tuple:
        total = self.yes_votes + self.no_votes
        if total == 0:
            return 0.0, 0.0
        yes_percent = (self.yes_votes / total) * 100
        no_percent = (self.no_votes / total) * 100
        return round(yes_percent, 1), round(no_percent, 1)

    def _get_status(self) -> PollStatus:
        if self.yes_votes > self.no_votes:
            return PollStatus.ACTIVE
        elif self.no_votes > self.yes_votes:
            return PollStatus.ACTIVE
        else:
            return PollStatus.TIED

    def _get_time_remaining(self) -> str:
        remaining = self.end_time - datetime.utcnow()
        if remaining.total_seconds() <= 0:
            return "Zakończona"
        
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def update_embed(self, embed: discord.Embed, ended: bool = False):
        yes_percent, no_percent = self._calculate_percentages()
        total = self.yes_votes + self.no_votes
        status = PollStatus.ENDED if ended else self._get_status()
        
        embed.clear_fields()
        
        embed.add_field(
            name=f"✅ TAK — {self.yes_votes} ({yes_percent}%)",
            value=f"```{self._progress_bar(yes_percent)}```",
            inline=False
        )
        
        embed.add_field(
            name=f"❌ NIE — {self.no_votes} ({no_percent}%)",
            value=f"```{self._progress_bar(no_percent)}```",
            inline=False
        )

        status_text = status.value if ended else f"{status.value} | ⏱️ {self._get_time_remaining()}"
        embed.add_field(
            name="📊 STATYSTYKI",
            value=f"**Łącznie głosów:** {total}\n"
                  f"**Status:** {status_text}\n"
                  f"**ID ankiety:** `{self.poll_id}`",
            inline=False
        )
        
        embed.timestamp = datetime.utcnow()
        
        if ended:
            embed.color = discord.Color.dark_gray()
            embed.set_footer(text="⛔ Ankieta zakończona")
        else:
            embed.color = discord.Color.blue()
            embed.set_footer(text=f"Koniec: {self.end_time.strftime('%H:%M:%S')} UTC")

    async def vote(self, interaction: discord.Interaction, vote_type: bool):
        user = interaction.user
        
        if user.id in self.voters:
            old_vote = self.voters[user.id][0]
            if old_vote == vote_type:
                await interaction.response.send_message(
                    "❌ Już oddałeś taki sam głos!", 
                    ephemeral=True
                )
                return
            
            if old_vote:
                self.yes_votes -= 1
                self.no_votes += 1
            else:
                self.no_votes -= 1
                self.yes_votes += 1
            
            self.voters[user.id] = (vote_type, datetime.utcnow())
            action = "zmieniony na"
        else:
            if vote_type:
                self.yes_votes += 1
            else:
                self.no_votes += 1
            
            self.voters[user.id] = (vote_type, datetime.utcnow())
            action = "oddany"
        
        vote_str = "TAK" if vote_type else "NIE"
        await interaction.response.send_message(
            f"✅ Twój głos ({vote_str}) został {action}!",
            ephemeral=True
        )
        
        embed = interaction.message.embeds[0]
        self.update_embed(embed)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="TAK", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.vote(interaction, True)

    @discord.ui.button(label="NIE", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.vote(interaction, False)

    async def on_timeout(self):
        self.is_active = False

        for child in self.children:
            child.disabled = True
        
        if hasattr(self, 'message'):
            embed = self.message.embeds[0]
            self.update_embed(embed, ended=True)
            await self.message.edit(embed=embed, view=self)


class PollManager:
    _instance = None
    _polls = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PollManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def generate_poll_id(cls) -> str:
        import uuid
        return str(uuid.uuid4())[:8]
    
    @classmethod
    def register_poll(cls, poll: PollView):
        cls._polls[poll.poll_id] = poll
    
    @classmethod
    def get_poll(cls, poll_id: str) -> Optional[PollView]:
        return cls._polls.get(poll_id)
    
    @classmethod
    def get_active_polls(cls) -> dict:
        return {pid: poll for pid, poll in cls._polls.items() if poll.is_active}


@bot.tree.command(
    name="ankieta",
    description="Tworzy ankietę TAK/NIE z limitem czasu"
)
async def create_poll(
    interaction: discord.Interaction,
    pytanie: str,
    czas_minuty: int = 60
):
    if czas_minuty < 1 or czas_minuty > 10080:
        await interaction.response.send_message(
            "❌ Czas musi być w zakresie **1-10080** minut (7 dni).",
            ephemeral=True
        )
        return
    
    if len(pytanie) > 1000:
        await interaction.response.send_message(
            "❌ Pytanie jest zbyt długie! Maksymalnie 1000 znaków.",
            ephemeral=True
        )
        return
    
    duration_seconds = czas_minuty * 60
    poll_id = PollManager.generate_poll_id()
    
    embed = discord.Embed(
        title="📊 ANKIETA",
        description=f"**Pytanie:**\n{pytanie}",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    embed.set_author(
        name=f"Ankieta utworzona przez {interaction.user.display_name}",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    view = PollView(poll_id, duration_seconds)
    PollManager.register_poll(view)
    
    view.update_embed(embed)
    
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()


@bot.tree.command(
    name="ankieta_zakończ",
    description="Przedwcześnie kończy ankietę"
)
async def end_poll(
    interaction: discord.Interaction,
    poll_id: str
):
    poll = PollManager.get_poll(poll_id)
    
    if not poll:
        await interaction.response.send_message(
            "❌ Nie znaleziono ankiety o podanym ID!",
            ephemeral=True
        )
        return
    
    if not poll.is_active:
        await interaction.response.send_message(
            "ℹ️ Ta ankieta już została zakończona.",
            ephemeral=True
        )
        return
    
    if interaction.user != poll.message.author and not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ Nie masz uprawnień do zakończenia tej ankiety!",
            ephemeral=True
        )
        return
    
    poll.is_active = False
    poll.stop()
    
    await interaction.response.send_message(
        f"✅ Ankieta `{poll_id}` została przedwcześnie zakończona!",
        ephemeral=True
    )


@bot.tree.command(
    name="ankieta_statystyki",
    description="Pokazuje szczegółowe statystyki ankiety"
)
async def poll_stats(
    interaction: discord.Interaction,
    poll_id: str
):
    poll = PollManager.get_poll(poll_id)
    
    if not poll:
        await interaction.response.send_message(
            "❌ Nie znaleziono ankiety o podanym ID!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"📈 SZCZEGÓŁOWE STATYSTYKI - {poll_id}",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    
    yes_percent, no_percent = poll._calculate_percentages()
    total_votes = poll.yes_votes + poll.no_votes
    
    embed.add_field(
        name="📊 Wyniki",
        value=f"✅ **TAK:** {poll.yes_votes} ({yes_percent}%)\n"
              f"❌ **NIE:** {poll.no_votes} ({no_percent}%)\n"
              f"👥 **Łącznie:** {total_votes}",
        inline=False
    )
    
    embed.add_field(
        name="⏱️ Czas",
        value=f"**Rozpoczęcie:** {poll.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
              f"**Zakończenie:** {poll.end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
              f"**Status:** {'Aktywna' if poll.is_active else 'Zakończona'}",
        inline=False
    )
    
    embed.add_field(
        name="👥 Uczestnicy",
        value=f"**Liczba głosujących:** {len(poll.voters)}\n"
              f"**Unikalni głosujący:** {len(set(poll.voters.keys()))}",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="ankiety_aktywne",
    description="Pokazuje listę aktywnych ankiet"
)
async def active_polls(interaction: discord.Interaction):
    active = PollManager.get_active_polls()
    
    if not active:
        await interaction.response.send_message(
            "ℹ️ Nie ma obecnie aktywnych ankiet.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="📋 AKTYWNE ANKIETY",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    
    for poll_id, poll in list(active.items())[:10]:
        time_left = poll._get_time_remaining()
        embed.add_field(
            name=f"ID: `{poll_id}`",
            value=f"**Głosy:** {poll.yes_votes + poll.no_votes}\n"
                  f"**Pozostały czas:** {time_left}\n"
                  f"[Przejdź do ankiety]({poll.message.jump_url})",
            inline=False
        )
    
    embed.set_footer(text=f"Łącznie aktywnych ankiet: {len(active)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="pomoc",
    description="Pokazuje wszystkie dostępne komendy"
)
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Pomoc - Bot Ankietowy",
        description="Komendy do zarządzania ankietami TAK/NIE",
        color=discord.Color.blue()
    )
    
    commands_list = [
        ("`/ankieta <pytanie> [czas_minuty=60]`", "Tworzy nową ankietę"),
        ("`/ankieta_zakończ <poll_id>`", "Przedwcześnie kończy ankietę"),
        ("`/ankieta_statystyki <poll_id>`", "Pokazuje statystyki ankiety"),
        ("`/ankiety_aktywne`", "Lista aktywnych ankiet"),
        ("`/pomoc`", "Ta wiadomość"),
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="📝 Uwagi",
        value="• Czas minimalny: 1 minuta\n"
              "• Czas maksymalny: 7 dni\n"
              "• Można zmienić swój głos\n"
              "• Wyniki aktualizują się na żywo",
        inline=False
    )
    
    embed.set_footer(text="ID ankiety znajdziesz w stopce wiadomości z ankietą")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    start_time = datetime.utcnow()

    try:
        synced = await bot.tree.sync()
        sync_status = f"✅ Zsynchronizowano {len(synced)} komend"
    except Exception as e:
        sync_status = f"⚠️ Błąd synchronizacji: {e}"
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="/ankieta | /pomoc"
        )
    )

    print("=" * 50)
    print(f"🤖 Bot: {bot.user.name} (ID: {bot.user.id})")
    print(f"📅 Uruchomiono: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"🌐 Serwery: {len(bot.guilds)}")
    print(f"👥 Użytkownicy: {sum(g.member_count for g in bot.guilds)}")
    print(f"🔄 {sync_status}")
    print("=" * 50)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Nieznana komenda. Użyj `/pomoc` aby zobaczyć listę komend.", delete_after=10)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Nie masz wymaganych uprawnień!", delete_after=10)
    else:
        print(f"Błąd: {error}")
        await ctx.send("❌ Wystąpił nieoczekiwany błąd!", delete_after=10)


if __name__ == "__main__":
    print("🚀 Uruchamianie bota ankietowego...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Błąd logowania: Nieprawidłowy token!")
    except KeyboardInterrupt:
        print("\n👋 Zatrzymywanie bota...")
    except Exception as e:
        print(f"❌ Nieoczekiwany błąd: {e}")