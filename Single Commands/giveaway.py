import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import random
import json
import os
from typing import Optional, List
from enum import Enum

TOKEN = ""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


class GiveawayStatus(Enum):
    ACTIVE = "🟢 AKTYWNY"
    ENDED = "🔴 ZAKOŃCZONY"
    CANCELLED = "⚫ ANULOWANY"


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: str, duration_seconds: int, winners_count: int, prize: str):
        super().__init__(timeout=duration_seconds)
        self.giveaway_id = giveaway_id
        self.participants = set()
        self.winners = []
        self.prize = prize
        self.winners_count = winners_count
        self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(seconds=duration_seconds)
        self.is_active = True
        self.creator_id = None
        self.message_id = None

    def _get_time_remaining(self) -> str:
        remaining = self.end_time - datetime.utcnow()
        if remaining.total_seconds() <= 0:
            return "Zakończony"
        
        days, remainder = divmod(int(remaining.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def update_embed(self, embed: discord.Embed, status: GiveawayStatus = None):
        if not status:
            status = GiveawayStatus.ACTIVE if self.is_active else GiveawayStatus.ENDED
        
        embed.clear_fields()
        
        embed.add_field(
            name="🎁 Nagroda",
            value=f"```{self.prize}```",
            inline=False
        )
        
        embed.add_field(
            name="👥 Uczestnicy",
            value=f"**{len(self.participants)}** osób",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Wygrywa",
            value=f"**{self.winners_count}** osoba(y)",
            inline=True
        )
        
        time_text = f"⏰ {self._get_time_remaining()}" if self.is_active else f"⏰ Zakończono"
        status_text = f"{status.value} | {time_text}"
        
        embed.add_field(
            name="📊 Informacje",
            value=f"**Status:** {status_text}\n"
                  f"**ID Giveaway:** `{self.giveaway_id}`\n"
                  f"**Zakończenie:** {self.end_time.strftime('%d.%m.%Y %H:%M:%S')} UTC",
            inline=False
        )
        
        if self.winners:
            winners_mentions = ", ".join([f"<@{winner}>" for winner in self.winners[:5]])
            if len(self.winners) > 5:
                winners_mentions += f" (+{len(self.winners) - 5} więcej)"
            embed.add_field(
                name="🏆 Zwycięzcy",
                value=winners_mentions,
                inline=False
            )
        
        embed.timestamp = datetime.utcnow()
        
        if status == GiveawayStatus.ACTIVE:
            embed.color = discord.Color.green()
            embed.set_footer(text="🎉 Weź udział klikając poniżej!")
        elif status == GiveawayStatus.ENDED:
            embed.color = discord.Color.gold()
            embed.set_footer(text="🏆 Giveaway zakończony!")
        else:
            embed.color = discord.Color.dark_gray()
            embed.set_footer(text="❌ Giveaway anulowany!")

    async def join_giveaway(self, interaction: discord.Interaction):
        user = interaction.user
        
        if user.id in self.participants:
            await interaction.response.send_message(
                "❌ Już bierzesz udział w tym giveaway!",
                ephemeral=True
            )
            return
        
        self.participants.add(user.id)
        
        embed = interaction.message.embeds[0]
        self.update_embed(embed)
        await interaction.message.edit(embed=embed, view=self)
        
        await interaction.response.send_message(
            f"✅ Dołączyłeś do giveaway'u: **{self.prize}**!",
            ephemeral=True
        )

    async def draw_winners(self) -> List[int]:
        if len(self.participants) < self.winners_count:
            self.winners = list(self.participants)
        else:
            self.winners = random.sample(list(self.participants), self.winners_count)
        return self.winners

    @discord.ui.button(label="DOŁĄCZ DO GIVEAWAY", style=discord.ButtonStyle.primary, emoji="🎉", custom_id="join_giveaway")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.join_giveaway(interaction)

    async def on_timeout(self):
        self.is_active = False
        await self.end_giveaway()

    async def end_giveaway(self):
        for child in self.children:
            child.disabled = True
        
        if hasattr(self, 'message'):
            await self.draw_winners()
            embed = self.message.embeds[0]
            self.update_embed(embed, GiveawayStatus.ENDED)
            await self.message.edit(embed=embed, view=self)
            
            if self.winners:
                winners_mentions = " ".join([f"<@{winner}>" for winner in self.winners])
                await self.message.channel.send(
                    f"🎉 **GIVEAWAY ZAKOŃCZONY!** 🎉\n"
                    f"**Nagroda:** {self.prize}\n"
                    f"**Zwycięzcy:** {winners_mentions}\n"
                    f"Gratulacje! Skontaktuj się z organizatorem aby odebrać nagrodę!"
                )


class GiveawayManager:
    _instance = None
    _giveaways = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GiveawayManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def generate_id(cls) -> str:
        import uuid
        return str(uuid.uuid4())[:8].upper()
    
    @classmethod
    def register_giveaway(cls, giveaway: GiveawayView):
        cls._giveaways[giveaway.giveaway_id] = giveaway
    
    @classmethod
    def get_giveaway(cls, giveaway_id: str) -> Optional[GiveawayView]:
        return cls._giveaways.get(giveaway_id)
    
    @classmethod
    def get_active_giveaways(cls) -> dict:
        return {gid: g for gid, g in cls._giveaways.items() if g.is_active}
    
    @classmethod
    def get_giveaways_by_creator(cls, creator_id: int) -> dict:
        return {gid: g for gid, g in cls._giveaways.items() if g.creator_id == creator_id}


@bot.tree.command(
    name="giveaway",
    description="Tworzy nowy giveaway"
)
async def create_giveaway(
    interaction: discord.Interaction,
    nagroda: str,
    czas_minuty: int,
    wygrani: int = 1
):
    if czas_minuty < 1 or czas_minuty > 10080:
        await interaction.response.send_message(
            "❌ Czas musi być w zakresie **1-10080** minut (7 dni).",
            ephemeral=True
        )
        return
    
    if wygrani < 1 or wygrani > 20:
        await interaction.response.send_message(
            "❌ Liczba wygranych musi być w zakresie **1-20**.",
            ephemeral=True
        )
        return
    
    if len(nagroda) > 500:
        await interaction.response.send_message(
            "❌ Opis nagrody jest zbyt długi! Maksymalnie 500 znaków.",
            ephemeral=True
        )
        return
    
    duration_seconds = czas_minuty * 60
    giveaway_id = GiveawayManager.generate_id()
    
    embed = discord.Embed(
        title="🎉 GIVEAWAY",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    
    embed.set_author(
        name=f"Giveaway utworzony przez {interaction.user.display_name}",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    view = GiveawayView(giveaway_id, duration_seconds, wygrani, nagroda)
    view.creator_id = interaction.user.id
    GiveawayManager.register_giveaway(view)
    
    view.update_embed(embed)
    
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()
    view.message_id = view.message.id


@bot.tree.command(
    name="giveawayzakończ",
    description="Przedwcześnie kończy giveaway i losuje zwycięzców"
)
async def end_giveaway(
    interaction: discord.Interaction,
    giveaway_id: str
):
    giveaway = GiveawayManager.get_giveaway(giveaway_id)
    
    if not giveaway:
        await interaction.response.send_message(
            "❌ Nie znaleziono giveaway'u o podanym ID!",
            ephemeral=True
        )
        return
    
    if not giveaway.is_active:
        await interaction.response.send_message(
            "ℹ️ Ten giveaway już został zakończony.",
            ephemeral=True
        )
        return
    
    if interaction.user.id != giveaway.creator_id and not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ Tylko twórca giveaway'u lub moderator może go zakończyć!",
            ephemeral=True
        )
        return
    
    giveaway.is_active = False
    giveaway.stop()
    await giveaway.end_giveaway()
    
    await interaction.response.send_message(
        f"✅ Giveaway `{giveaway_id}` został przedwcześnie zakończony!",
        ephemeral=True
    )


@bot.tree.command(
    name="giveawayanuluj",
    description="Anuluje giveaway bez losowania zwycięzców"
)
async def cancel_giveaway(
    interaction: discord.Interaction,
    giveaway_id: str
):
    giveaway = GiveawayManager.get_giveaway(giveaway_id)
    
    if not giveaway:
        await interaction.response.send_message(
            "❌ Nie znaleziono giveaway'u o podanym ID!",
            ephemeral=True
        )
        return
    
    if not giveaway.is_active:
        await interaction.response.send_message(
            "ℹ️ Ten giveaway już został zakończony.",
            ephemeral=True
        )
        return
    
    if interaction.user.id != giveaway.creator_id and not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ Tylko twórca giveaway'u lub moderator może go anulować!",
            ephemeral=True
        )
        return
    
    giveaway.is_active = False
    giveaway.stop()
    
    for child in giveaway.children:
        child.disabled = True
    
    embed = giveaway.message.embeds[0]
    giveaway.update_embed(embed, GiveawayStatus.CANCELLED)
    await giveaway.message.edit(embed=embed, view=giveaway)
    
    await interaction.response.send_message(
        f"✅ Giveaway `{giveaway_id}` został anulowany!",
        ephemeral=True
    )


@bot.tree.command(
    name="giveawayponów",
    description="Ponawia zakończony giveaway z nowym czasem"
)
async def reroll_giveaway(
    interaction: discord.Interaction,
    giveaway_id: str,
    nowy_czas_minuty: int
):
    original_giveaway = GiveawayManager.get_giveaway(giveaway_id)
    
    if not original_giveaway:
        await interaction.response.send_message(
            "❌ Nie znaleziono giveaway'u o podanym ID!",
            ephemeral=True
        )
        return
    
    if interaction.user.id != original_giveaway.creator_id and not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ Tylko twórca giveaway'u lub moderator może go ponowić!",
            ephemeral=True
        )
        return
    
    if nowy_czas_minuty < 1 or nowy_czas_minuty > 10080:
        await interaction.response.send_message(
            "❌ Czas musi być w zakresie **1-10080** minut.",
            ephemeral=True
        )
        return
    
    duration_seconds = nowy_czas_minuty * 60
    new_giveaway_id = GiveawayManager.generate_id()
    
    embed = discord.Embed(
        title="🎉 GIVEAWAY (PONOWIONY)",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    
    embed.set_author(
        name=f"Giveaway ponowiony przez {interaction.user.display_name}",
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    
    view = GiveawayView(new_giveaway_id, duration_seconds, original_giveaway.winners_count, original_giveaway.prize)
    view.creator_id = interaction.user.id
    GiveawayManager.register_giveaway(view)
    
    view.update_embed(embed)
    
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()
    view.message_id = view.message.id


@bot.tree.command(
    name="giveawayreroll",
    description="Losuje nowych zwycięzców dla zakończonego giveaway'u"
)
async def reroll_winners(
    interaction: discord.Interaction,
    giveaway_id: str,
    ilość_wygranych: int = None
):
    giveaway = GiveawayManager.get_giveaway(giveaway_id)
    
    if not giveaway:
        await interaction.response.send_message(
            "❌ Nie znaleziono giveaway'u o podanym ID!",
            ephemeral=True
        )
        return
    
    if giveaway.is_active:
        await interaction.response.send_message(
            "❌ Giveaway jest jeszcze aktywny! Najpierw go zakończ.",
            ephemeral=True
        )
        return
    
    if not giveaway.participants:
        await interaction.response.send_message(
            "❌ W tym giveaway'u nie było uczestników!",
            ephemeral=True
        )
        return
    
    if ilość_wygranych:
        if ilość_wygranych < 1 or ilość_wygranych > 20:
            await interaction.response.send_message(
                "❌ Liczba wygranych musi być w zakresie **1-20**.",
                ephemeral=True
            )
            return
        giveaway.winners_count = ilość_wygranych
    
    await giveaway.draw_winners()
    
    winners_mentions = " ".join([f"<@{winner}>" for winner in giveaway.winners])
    
    embed = giveaway.message.embeds[0]
    giveaway.update_embed(embed, GiveawayStatus.ENDED)
    await giveaway.message.edit(embed=embed, view=giveaway)
    
    await interaction.response.send_message(
        f"🎉 **NOWI ZWYCIĘZCY!** 🎉\n"
        f"**Nagroda:** {giveaway.prize}\n"
        f"**Nowi zwycięzcy:** {winners_mentions}\n"
        f"Gratulacje!"
    )


@bot.tree.command(
    name="giveawaystatystyki",
    description="Pokazuje szczegółowe statystyki giveaway'u"
)
async def giveaway_stats(
    interaction: discord.Interaction,
    giveaway_id: str
):
    giveaway = GiveawayManager.get_giveaway(giveaway_id)
    
    if not giveaway:
        await interaction.response.send_message(
            "❌ Nie znaleziono giveaway'u o podanym ID!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"📈 STATYSTYKI GIVEAWAY - {giveaway_id}",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(
        name="🎁 Nagroda",
        value=giveaway.prize,
        inline=False
    )
    
    embed.add_field(
        name="👥 Uczestnicy",
        value=f"**Łącznie:** {len(giveaway.participants)}\n"
              f"**Wygrywa:** {giveaway.winners_count}",
        inline=True
    )
    
    embed.add_field(
        name="⏱️ Czas",
        value=f"**Rozpoczęcie:** {giveaway.start_time.strftime('%d.%m.%Y %H:%M:%S')} UTC\n"
              f"**Zakończenie:** {giveaway.end_time.strftime('%d.%m.%Y %H:%M:%S')} UTC\n"
              f"**Status:** {'Aktywny' if giveaway.is_active else 'Zakończony'}",
        inline=True
    )
    
    if giveaway.winners:
        winners_list = "\n".join([f"<@{winner}>" for winner in giveaway.winners[:10]])
        if len(giveaway.winners) > 10:
            winners_list += f"\n... (+{len(giveaway.winners) - 10} więcej)"
        embed.add_field(
            name="🏆 Zwycięzcy",
            value=winners_list,
            inline=False
        )
    
    creator = await bot.fetch_user(giveaway.creator_id) if giveaway.creator_id else "Nieznany"
    embed.set_footer(text=f"Twórca: {creator.display_name if hasattr(creator, 'display_name') else creator}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="giveawaylista",
    description="Pokazuje listę aktywnych giveaway'ów"
)
async def giveaway_list(
    interaction: discord.Interaction,
    pokaż_zakończone: bool = False
):
    if pokaż_zakończone:
        giveaways = GiveawayManager._giveaways
        title = "📋 WSZYSTKIE GIVEAWAY'E"
        color = discord.Color.dark_gray()
    else:
        giveaways = GiveawayManager.get_active_giveaways()
        title = "📋 AKTYWNE GIVEAWAY'E"
        color = discord.Color.green()
    
    if not giveaways:
        status = "zakończonych" if pokaż_zakończone else "aktywnych"
        await interaction.response.send_message(
            f"ℹ️ Nie ma obecnie {status} giveaway'ów.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.utcnow()
    )
    
    for giveaway_id, giveaway in list(giveaways.items())[:15]:
        time_left = giveaway._get_time_remaining() if giveaway.is_active else "Zakończony"
        status = "🟢" if giveaway.is_active else "🔴"
        
        embed.add_field(
            name=f"{status} ID: `{giveaway_id}`",
            value=f"**Nagroda:** {giveaway.prize[:50]}{'...' if len(giveaway.prize) > 50 else ''}\n"
                  f"**Uczestnicy:** {len(giveaway.participants)}\n"
                  f"**Pozostały czas:** {time_left}\n"
                  f"[Przejdź do giveaway'u]({giveaway.message.jump_url})",
            inline=False
        )
    
    embed.set_footer(text=f"Łącznie giveaway'ów: {len(giveaways)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    start_time = datetime.utcnow()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Zsynchronizowano {len(synced)} komend")
    except Exception as e:
        (f"⚠️ Błąd synchronizacji: {e}")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="/giveaway | /giveaway_pomoc"
        )
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Nieznana komenda. Użyj `/giveaway_pomoc` aby zobaczyć listę komend.", delete_after=10)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Nie masz wymaganych uprawnień!", delete_after=10)
    else:
        print(f"Błąd: {error}")
        await ctx.send("❌ Wystąpił nieoczekiwany błąd!", delete_after=10)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get('custom_id', '')
        if custom_id == 'join_giveaway':
            for giveaway in GiveawayManager._giveaways.values():
                if hasattr(giveaway, 'message_id') and giveaway.message_id == interaction.message.id:
                    if giveaway.is_active:
                        await giveaway.join_giveaway(interaction)
                    else:
                        await interaction.response.send_message(
                            "❌ Ten giveaway już się zakończył!",
                            ephemeral=True
                        )
                    return
    
    await bot.process_application_commands(interaction)


if __name__ == "__main__":
    print("🚀 Uruchamianie bota giveaway...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Błąd logowania: Nieprawidłowy token!")
    except KeyboardInterrupt:
        print("\n👋 Zatrzymywanie bota...")
    except Exception as e:
        print(f"❌ Nieoczekiwany błąd: {e}")