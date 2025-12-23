import discord
from discord.ext import commands
import random
import json
import os
from datetime import datetime
from enum import Enum

TOKEN = ""

class HugType(Enum):
    NORMAL = "normal"
    ROMANTIC = "romantic"
    FRIENDLY = "friendly"
    BEAR = "bear"
    SURPRISE = "surprise"
    GHOST = "ghost"

class HugBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.hug_data = {}
        self.load_data()
        
        self.hug_database = {
            HugType.NORMAL: [
                "czule przytula", "obejmuje z uczuciem", "delikatnie ściska",
                "otula ramionami", "przytula z ciepłem", "ściska mocno"
            ],
            HugType.ROMANTIC: [
                "obejmuje miłośnie i szepcze do ucha", "przytula namiętnie",
                "całuje w policzek i mocno przytula", "otula w romantycznym uścisku"
            ],
            HugType.FRIENDLY: [
                "klepie po plecach i przytula", "ściska jak przyjaciel",
                "przytula z uśmiechem", "obejmuje w przyjacielskim geście"
            ],
            HugType.BEAR: [
                "chwyta w niedźwiedzi uścisk", "podnosi i kręci w powietrzu",
                "ściska tak mocno, że trzeszczą kości", "obejmuje całym ciałem"
            ],
            HugType.SURPRISE: [
                "zaskakuje nagłym przytuleniem", "podbiega i obejmuje z zaskoczenia",
                "przytula od tyłu niespodziewanie", "chwyta w uścisk z ukrycia"
            ],
            HugType.GHOST: [
                "próbuje przytulić ducha", "obejmuje powietrze",
                "przytula niewidzialną osobę", "ściska przezroczystą istotę"
            ]
        }
        
        self.hug_gifs = {
            "default": [

            ],
            "romantic": [

            ],
            "bear": [

            ]
        }
    
    def load_data(self):
        if os.path.exists('hugs.json'):
            with open('hugs.json', 'r', encoding='utf-8') as f:
                self.hug_data = json.load(f)
    
    def save_data(self):
        with open('hugs.json', 'w', encoding='utf-8') as f:
            json.dump(self.hug_data, f, indent=2, ensure_ascii=False)
    
    def update_stats(self, giver_id: str, receiver_id: str, hug_type: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if giver_id not in self.hug_data:
            self.hug_data[giver_id] = {"given": 0, "received": 0, "history": []}
        if receiver_id not in self.hug_data:
            self.hug_data[receiver_id] = {"given": 0, "received": 0, "history": []}
        
        self.hug_data[giver_id]["given"] += 1
        self.hug_data[giver_id]["history"].append({
            "action": "given",
            "to": receiver_id,
            "type": hug_type,
            "time": now
        })

        self.hug_data[receiver_id]["received"] += 1
        self.hug_data[receiver_id]["history"].append({
            "action": "received",
            "from": giver_id,
            "type": hug_type,
            "time": now
        })
        
        self.save_data()
    
    def get_hug_count(self, user_id: str) -> dict:
        return self.hug_data.get(user_id, {"given": 0, "received": 0})
    
    def generate_embed(self, giver: discord.User, receiver: discord.User, 
                      hug_type: HugType, intensity: int = 1) -> discord.Embed:

        description = random.choice(self.hug_database[hug_type])

        if giver == receiver:
            description = "próbuje przytulić sam siebie... trochę smutne"
            hug_type = HugType.GHOST

        color_map = {
            HugType.NORMAL: discord.Color.blue(),
            HugType.ROMANTIC: discord.Color.pink(),
            HugType.FRIENDLY: discord.Color.green(),
            HugType.BEAR: discord.Color.orange(),
            HugType.SURPRISE: discord.Color.purple(),
            HugType.GHOST: discord.Color.light_grey()
        }
        
        embed = discord.Embed(
            title="🤗 PRZYTULAS! 🤗",
            description=f"**{giver.display_name}** {description} **{receiver.display_name}**!",
            color=color_map[hug_type],
            timestamp=datetime.now()
        )

        embed.set_author(name=giver.display_name, icon_url=giver.display_avatar.url)
        
        embed.set_thumbnail(url=receiver.display_avatar.url)

        gif_category = "bear" if hug_type == HugType.BEAR else "romantic" if hug_type == HugType.ROMANTIC else "default"
        embed.set_image(url=random.choice(self.hug_gifs[gif_category]))

        giver_stats = self.get_hug_count(str(giver.id))
        receiver_stats = self.get_hug_count(str(receiver.id))
        
        embed.add_field(
            name="📊 Statystyki przytulającego",
            value=f"Przytulił: **{giver_stats['given']}**\nOtrzymał: **{giver_stats['received']}**",
            inline=True
        )
        
        embed.add_field(
            name="📊 Statystyki przytulanego",
            value=f"Otrzymał: **{receiver_stats['received']}**\nPrzytulił: **{receiver_stats['given']}**",
            inline=True
        )

        if intensity > 1:
            intensity_emojis = {2: "✨", 3: "💫", 4: "🌟", 5: "💥"}
            if intensity in intensity_emojis:
                embed.add_field(
                    name=f"Intensywność: {intensity_emojis[intensity]}",
                    value=f"Moc przytulenia: {'⭐' * intensity}",
                    inline=False
                )

        embed.set_footer(text=f"Typ: {hug_type.value.upper()} • {datetime.now().strftime('%H:%M:%S')}")
        
        return embed

bot = HugBot()

@bot.tree.command(name="hug", description="Przytul inną osobę!")
@discord.app_commands.describe(
    user="Kogo chcesz przytulić?",
    type="Typ przytulenia (normal/romantic/friendly/bear/surprise)",
    intensity="Moc przytulenia (1-5)"
)
async def hug_command(
    interaction: discord.Interaction,
    user: discord.User,
    type: str = "normal",
    intensity: int = 1
):
    intensity = max(1, min(5, intensity))
    
    try:
        hug_type = HugType(type.lower())
    except:
        hug_type = HugType.NORMAL
    
    bot.update_stats(str(interaction.user.id), str(user.id), hug_type.value)
    
    embed = bot.generate_embed(
        giver=interaction.user,
        receiver=user,
        hug_type=hug_type,
        intensity=intensity
    )
    
    await interaction.response.send_message(embed=embed)
    
    try:
        message = await interaction.original_response()
        
        reaction_map = {
            HugType.NORMAL: ["🤗", "❤️"],
            HugType.ROMANTIC: ["🥰", "💕", "😘"],
            HugType.FRIENDLY: ["😊", "👍"],
            HugType.BEAR: ["💪", "🔥"],
            HugType.SURPRISE: ["😲", "🎉"],
            HugType.GHOST: ["👻", "😅"]
        }
        
        reactions = reaction_map.get(hug_type, ["🤗"])
        for reaction in reactions[:intensity]:
            await message.add_reaction(reaction)
    except:
        pass

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} jest gotowy!')
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Zsynchonizowano {len(synced)} komendę")
    except Exception as e:
        print(f"❌ Błąd synchronizacji: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)