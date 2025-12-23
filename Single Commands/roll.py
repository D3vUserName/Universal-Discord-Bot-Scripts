import discord
from discord.ext import commands
import random
import json
import os
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from typing import Optional, List, Dict, Tuple
import re
from collections import defaultdict

TOKEN = ""

class DiceType(Enum):
    D4 = 4
    D6 = 6
    D8 = 8
    D10 = 10
    D12 = 12
    D20 = 20
    D100 = 100
    CUSTOM = 0

class RollBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.roll_data_file = 'roll_stats.json'
        self.load_data()
        
        self.session_rolls = []
        self.user_cooldowns = {}
        self.cooldown_time = timedelta(seconds=5)
        
        self.dice_art = {
            1: [
                "┌───────┐",
                "│       │",
                "│   ●   │",
                "│       │",
                "└───────┘"
            ],
            2: [
                "┌───────┐",
                "│ ●     │",
                "│       │",
                "│     ● │",
                "└───────┘"
            ],
            3: [
                "┌───────┐",
                "│ ●     │",
                "│   ●   │",
                "│     ● │",
                "└───────┘"
            ],
            4: [
                "┌───────┐",
                "│ ●   ● │",
                "│       │",
                "│ ●   ● │",
                "└───────┘"
            ],
            5: [
                "┌───────┐",
                "│ ●   ● │",
                "│   ●   │",
                "│ ●   ● │",
                "└───────┘"
            ],
            6: [
                "┌───────┐",
                "│ ●   ● │",
                "│ ●   ● │",
                "│ ●   ● │",
                "└───────┘"
            ]
        }
        
        self.critical_messages = {
            "success": {
                "D20": [
                    "🎯 **KRYTYCZNY SUKCES!** 🎯",
                    "🌟 **NATURALNE 20!** 🌟",
                    "💫 **PERFEKCYJNY RZUT!** 💫",
                    "🔥 **ABSOLUTNA DOSKONAŁOŚĆ!** 🔥"
                ],
                "general": [
                    "✨ Niezwykły rzut!",
                    "✅ Doskonale!",
                    "🏆 Mistrzowski!",
                    "🎖 Wspaniale!"
                ]
            },
            "failure": {
                "D20": [
                    "💀 **KRYTYCZNA PORAŻKA!** 💀",
                    "☠️ **NATURALNE 1!** ☠️",
                    "😭 **KATASTROFA!** 😭",
                    "💥 **ABSURDALNIE ŹLE!** 💥"
                ],
                "general": [
                    "😬 Prawie...",
                    "📉 Słabiutko...",
                    "🎭 Dramat...",
                    "🌀 Fatalny dzień..."
                ]
            }
        }

        self.dice_colors = {
            4: discord.Color.blue(),
            6: discord.Color.green(),
            8: discord.Color.orange(),
            10: discord.Color.purple(),
            12: discord.Color.gold(),
            20: discord.Color.red(),
            100: discord.Color.teal(),
            0: discord.Color.dark_grey()
        }

        self.modifiers = {
            "advantage": "🎲 Przewaga",
            "disadvantage": "⚠️  Utrudnienie",
            "double": "⚡ Podwójny rzut",
            "exploding": "💣 Wybuchające kości",
            "reroll": "🔄 Ponowny rzut",
            "drop_lowest": "⬇️ Odrzuć najniższy",
            "drop_highest": "⬆️ Odrzuć najwyższy"
        }
        
        self.achievements = {
            "first_roll": "🎲 Pierwszy rzut",
            "natural_20": "🌟 Naturalne 20",
            "natural_1": "💀 Naturalne 1",
            "triple_six": "👿 Potrójna szóstka",
            "lucky_streak": "🍀 3 dobre rzuty z rzędu",
            "unlucky_streak": "☂️ 3 złe rzuty z rzędu",
            "perfect_100": "💯 Idealne 100",
            "dice_master": "🏆 1000 rzutów",
            "variety": "🎭 Wszystkie typy kości",
            "gambler": "🎰 50 rzutów w sesji"
        }

    def load_data(self):
        if os.path.exists(self.roll_data_file):
            with open(self.roll_data_file, 'r', encoding='utf-8') as f:
                self.roll_data = json.load(f)
        else:
            self.roll_data = {
                "global_stats": {
                    "total_rolls": 0,
                    "total_sum": 0,
                    "average_roll": 0,
                    "highest_roll": 0,
                    "lowest_roll": float('inf'),
                    "critical_successes": 0,
                    "critical_failures": 0
                },
                "user_stats": {},
                "achievements": {},
                "dice_usage": defaultdict(int),
                "session_history": [],
                "streaks": {}
            }
            self.save_data()

    def save_data(self):
        with open(self.roll_data_file, 'w', encoding='utf-8') as f:
            json.dump(self.roll_data, f, indent=2, ensure_ascii=False)

    def parse_dice_notation(self, notation: str) -> Tuple[List[Tuple[int, int]], List[int], str]:
        notation = notation.lower().strip()
        
        if not notation:
            return [(1, 20)], [0], ""
        
        effect = ""
        if "advantage" in notation:
            effect = "advantage"
            notation = notation.replace("advantage", "").strip()
        elif "disadvantage" in notation:
            effect = "disadvantage"
            notation = notation.replace("disadvantage", "").strip()
        elif "double" in notation:
            effect = "double"
            notation = notation.replace("double", "").strip()
        elif "explode" in notation:
            effect = "exploding"
            notation = notation.replace("explode", "").strip()
        
        dice_list = []
        modifiers = [0]
        
        if notation.startswith("d"):
            notation = "1" + notation
        
        match = re.match(r'(\d+)d(\d+)(?:([+-]\d+))?', notation)
        if match:
            count = int(match.group(1))
            sides = int(match.group(2))
            mod = int(match.group(3) or 0)
            dice_list.append((count, sides))
            modifiers = [mod]
        else:
            parts = notation.split()
            for part in parts:
                if 'd' in part:
                    if part.startswith('d'):
                        part = '1' + part
                    match = re.match(r'(\d+)d(\d+)', part)
                    if match:
                        dice_list.append((int(match.group(1)), int(match.group(2))))
                elif part.startswith(('+', '-')):
                    modifiers.append(int(part))
        
        return dice_list, modifiers, effect

    def roll_dice(self, count: int, sides: int, effect: str = "") -> List[Dict]:
        rolls = []
        
        for _ in range(count):
            if effect == "advantage":
                roll1 = random.randint(1, sides)
                roll2 = random.randint(1, sides)
                result = max(roll1, roll2)
                rolls.append({
                    "value": result,
                    "details": [roll1, roll2],
                    "effect": effect
                })
            elif effect == "disadvantage":
                roll1 = random.randint(1, sides)
                roll2 = random.randint(1, sides)
                result = min(roll1, roll2)
                rolls.append({
                    "value": result,
                    "details": [roll1, roll2],
                    "effect": effect
                })
            elif effect == "double":
                result = random.randint(1, sides) * 2
                rolls.append({
                    "value": result,
                    "details": [result // 2, result // 2],
                    "effect": effect
                })
            elif effect == "exploding":
                result = random.randint(1, sides)
                extra_rolls = []
                while result == sides:
                    extra_rolls.append(result)
                    result = random.randint(1, sides)
                rolls.append({
                    "value": sum(extra_rolls) + result,
                    "details": extra_rolls + [result],
                    "effect": effect
                })
            else:
                result = random.randint(1, sides)
                rolls.append({
                    "value": result,
                    "details": [result],
                    "effect": ""
                })
        
        return rolls

    def update_stats(self, user_id: str, rolls: List[Dict], total: int, dice_type: str):
        now = datetime.now().isoformat()
        
        self.roll_data["global_stats"]["total_rolls"] += 1
        self.roll_data["global_stats"]["total_sum"] += total
        
        for roll in rolls:
            for detail in roll["details"]:
                if "20" in dice_type and detail == 20:
                    self.roll_data["global_stats"]["critical_successes"] += 1
                elif "20" in dice_type and detail == 1:
                    self.roll_data["global_stats"]["critical_failures"] += 1
                
                if detail > self.roll_data["global_stats"]["highest_roll"]:
                    self.roll_data["global_stats"]["highest_roll"] = detail
                if detail < self.roll_data["global_stats"]["lowest_roll"]:
                    self.roll_data["global_stats"]["lowest_roll"] = detail
        
        total_rolls = self.roll_data["global_stats"]["total_rolls"]
        total_sum = self.roll_data["global_stats"]["total_sum"]
        if total_rolls > 0:
            self.roll_data["global_stats"]["average_roll"] = round(total_sum / total_rolls, 2)

        if user_id not in self.roll_data["user_stats"]:
            self.roll_data["user_stats"][user_id] = {
                "total_rolls": 0,
                "total_sum": 0,
                "average": 0,
                "highest_roll": 0,
                "lowest_roll": float('inf'),
                "critical_successes": 0,
                "critical_failures": 0,
                "favorite_dice": {},
                "last_roll": now,
                "roll_history": [],
                "daily_rolls": 0,
                "weekly_rolls": 0
            }
        
        user_stats = self.roll_data["user_stats"][user_id]
        user_stats["total_rolls"] += 1
        user_stats["total_sum"] += total
        user_stats["last_roll"] = now

        roll_entry = {
            "timestamp": now,
            "total": total,
            "dice_type": dice_type,
            "rolls": rolls
        }
        user_stats["roll_history"].append(roll_entry)
        if len(user_stats["roll_history"]) > 100:
            user_stats["roll_history"].pop(0)
        
        dice_key = dice_type
        user_stats["favorite_dice"][dice_key] = user_stats["favorite_dice"].get(dice_key, 0) + 1
        self.roll_data["dice_usage"][dice_key] += 1
        
        self.check_achievements(user_id, rolls, total)
        
        self.save_data()

    def check_achievements(self, user_id: str, rolls: List[Dict], total: int):
        if user_id not in self.roll_data["achievements"]:
            self.roll_data["achievements"][user_id] = []
        
        achievements = self.roll_data["achievements"][user_id]
        user_stats = self.roll_data["user_stats"][user_id]

        if user_stats["total_rolls"] == 1 and "first_roll" not in achievements:
            achievements.append("first_roll")

        for roll in rolls:
            for detail in roll["details"]:
                if detail == 20 and "natural_20" not in achievements:
                    achievements.append("natural_20")
                elif detail == 1 and "natural_1" not in achievements:
                    achievements.append("natural_1")

        if len(rolls) >= 3:
            six_count = sum(1 for roll in rolls for detail in roll["details"] if detail == 6)
            if six_count >= 3 and "triple_six" not in achievements:
                achievements.append("triple_six")

        if total == 100 and "perfect_100" not in achievements:
            achievements.append("perfect_100")

        if user_stats["total_rolls"] >= 1000 and "dice_master" not in achievements:
            achievements.append("dice_master")

        dice_types = set()
        for dice_key in user_stats["favorite_dice"].keys():
            if "d20" in dice_key:
                dice_types.add("D20")
            elif "d6" in dice_key:
                dice_types.add("D6")
            elif "d100" in dice_key:
                dice_types.add("D100")

        if len(dice_types) >= 5 and "variety" not in achievements:
            achievements.append("variety")

    def generate_dice_art(self, value: int) -> str:
        if 1 <= value <= 6:
            return "\n".join(self.dice_art[value])
        else:
            return f"[ {value} ]"

    def calculate_probability(self, target: int, sides: int) -> float:
        if target > sides:
            return 0.0
        success_outcomes = sides - target + 1
        return round((success_outcomes / sides) * 100, 2)

    def check_cooldown(self, user_id: str) -> bool:
        if user_id in self.user_cooldowns:
            elapsed = datetime.now() - self.user_cooldowns[user_id]
            if elapsed < self.cooldown_time:
                return False
        self.user_cooldowns[user_id] = datetime.now()
        return True

    async def create_roll_embed(self, user: discord.User, dice_notation: str, 
                               dice_list: List[Tuple[int, int]], modifiers: List[int],
                               effect: str, rolls: List[Dict], total: int) -> discord.Embed:
        
        main_dice = dice_list[0][1] if dice_list else 20
        color = self.dice_colors.get(main_dice, discord.Color.blue())
        
        embed = discord.Embed(
            title="🎲 **RZUT KOŚCIĄ** 🎲",
            color=color,
            timestamp=datetime.now()
        )

        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        
        notation_text = dice_notation if dice_notation else "1d20"
        embed.description = f"**Notacja:** `{notation_text}`\n"
        
        if effect:
            effect_name = self.modifiers.get(effect, effect.capitalize())
            embed.description += f"**Efekt:** {effect_name}\n"
        
        roll_details = []
        total_before_mods = 0
        
        for i, roll in enumerate(rolls):
            if len(roll["details"]) > 1:
                details = " + ".join(str(r) for r in roll["details"])
                roll_details.append(f"K{dice_list[i][1]}: `{details}` = **{roll['value']}**")
            else:
                roll_details.append(f"K{dice_list[i][1]}: **{roll['value']}**")
            
            total_before_mods += roll['value']
        
        embed.add_field(
            name="🎯 Wyniki rzutów",
            value="\n".join(roll_details) or "Brak rzutów",
            inline=False
        )
        
        mod_sum = sum(modifiers)
        if mod_sum != 0:
            mod_text = " + ".join(f"`{m:+d}`" for m in modifiers if m != 0)
            embed.add_field(
                name="📊 Modyfikatory",
                value=f"{mod_text} = `{mod_sum:+d}`",
                inline=True
            )

        embed.add_field(
            name="💰 **SUMA**",
            value=f"**`{total_before_mods}`** + `{mod_sum}` = **`{total}`**",
            inline=True
        )
        
        if main_dice == 20:
            for roll in rolls:
                for detail in roll["details"]:
                    if detail == 20:
                        crit_msg = random.choice(self.critical_messages["success"]["D20"])
                        embed.add_field(
                            name="🌟 **KRYTYCZNY SUKCES!**",
                            value=crit_msg,
                            inline=False
                        )
                        embed.color = discord.Color.gold()
                    elif detail == 1:
                        crit_msg = random.choice(self.critical_messages["failure"]["D20"])
                        embed.add_field(
                            name="💀 **KRYTYCZNA PORAŻKA!**",
                            value=crit_msg,
                            inline=False
                        )
                        embed.color = discord.Color.dark_grey()

        if len(dice_list) == 1 and len(rolls) == 1:
            sides = dice_list[0][1]
            roll_value = rolls[0]["value"]
            prob = self.calculate_probability(roll_value, sides)
            
            if prob > 0:
                success_chance = f"{prob}%"
                if prob >= 75:
                    rating = "🎯 Łatwe"
                elif prob >= 50:
                    rating = "👍 Średnie"
                elif prob >= 25:
                    rating = "⚠️ Trudne"
                else:
                    rating = "💀 Bardzo trudne"
                
                embed.add_field(
                    name="📈 Prawdopodobieństwo",
                    value=f"Aby uzyskać ≥{roll_value} na K{sides}:\n**{success_chance}**\n{rating}",
                    inline=True
                )
        
        if main_dice == 6 and len(rolls) == 1:
            dice_art = self.generate_dice_art(rolls[0]["value"])
            embed.add_field(
                name="🎨 Wizualizacja",
                value=f"```{dice_art}```",
                inline=True
            )

        self.session_rolls.append({
            "user": user.id,
            "total": total,
            "time": datetime.now().isoformat()
        })
        
        session_avg = sum(r["total"] for r in self.session_rolls[-10:]) / min(len(self.session_rolls), 10)
        embed.add_field(
            name="📊 Sesja",
            value=f"Rzutów w sesji: **{len(self.session_rolls)}**\nŚrednia (10 ost.): **{session_avg:.1f}**",
            inline=True
        )
        
        user_id = str(user.id)
        if user_id in self.roll_data["user_stats"]:
            user_stats = self.roll_data["user_stats"][user_id]
            embed.add_field(
                name="👤 Twoje statystyki",
                value=f"Łącznie rzutów: **{user_stats['total_rolls']}**\nŚrednia: **{user_stats.get('average', 0):.1f}**",
                inline=True
            )

        embed.set_footer(text=f"ID: {random.randint(1000, 9999)} • {datetime.now().strftime('%H:%M:%S')}")
        
        return embed
    
bot = RollBot()

@bot.tree.command(name="roll", description="Rzuć kośćmi!")
@discord.app_commands.describe(
    dice="Notacja kości (np. 2d20+5, d6, 3d6 advantage)",
    secret="Czy rzut ma być prywatny? (tylko dla ciebie)"
)
async def roll_command(
    interaction: discord.Interaction,
    dice: Optional[str] = None,
    secret: bool = False
):
    
    if not bot.check_cooldown(str(interaction.user.id)):
        await interaction.response.send_message(
            "⏳ Za szybko! Poczekaj chwilę przed kolejnym rzutem.",
            ephemeral=True
        )
        return
    
    dice_notation = dice or "1d20"
    dice_list, modifiers, effect = bot.parse_dice_notation(dice_notation)

    total_dice = sum(count for count, _ in dice_list)
    if total_dice > 20:
        await interaction.response.send_message(
            "❌ Za dużo kości! Maksymalnie 20 na raz.",
            ephemeral=True
        )
        return

    all_rolls = []
    for count, sides in dice_list:
        if sides > 1000:
            await interaction.response.send_message(
                "❌ Kości mają za dużo ścianek! Maksymalnie 1000.",
                ephemeral=True
            )
            return
        
        rolls = bot.roll_dice(count, sides, effect if not all_rolls else "")
        all_rolls.extend(rolls)
    
    total_rolls = sum(roll["value"] for roll in all_rolls)
    total = total_rolls + sum(modifiers)

    dice_type = f"{dice_list[0][1]}" if dice_list else "20"
    bot.update_stats(str(interaction.user.id), all_rolls, total, f"d{dice_type}")

    embed = await bot.create_roll_embed(
        user=interaction.user,
        dice_notation=dice_notation,
        dice_list=dice_list,
        modifiers=modifiers,
        effect=effect,
        rolls=all_rolls,
        total=total
    )

    if secret:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed)
        
        try:
            message = await interaction.original_response()

            if total >= 15:
                await message.add_reaction("🎲")
                await message.add_reaction("✨")
            elif total <= 5:
                await message.add_reaction("🎲")
                await message.add_reaction("😅")
            else:
                await message.add_reaction("🎲")
        except:
            pass

@bot.tree.command(name="rollstats", description="Pokaż statystyki rzutów")
async def roll_stats(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.roll_data["user_stats"]:
        await interaction.response.send_message(
            "📊 Nie masz jeszcze statystyk rzutów. Użyj `/roll`!",
            ephemeral=True
        )
        return
    
    user_stats = bot.roll_data["user_stats"][user_id]
    global_stats = bot.roll_data["global_stats"]
    achievements = bot.roll_data["achievements"].get(user_id, [])
    
    user_avg = user_stats["total_sum"] / user_stats["total_rolls"] if user_stats["total_rolls"] > 0 else 0
    
    embed = discord.Embed(
        title="📊 **STATYSTYKI RZUTÓW** 📊",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    
    embed.add_field(
        name="👤 Twoje statystyki",
        value=(
            f"**Rzuty:** {user_stats['total_rolls']}\n"
            f"**Średnia:** {user_avg:.2f}\n"
            f"**Najwyższy:** {user_stats.get('highest_roll', 'N/A')}\n"
            f"**Najniższy:** {user_stats.get('lowest_roll', 'N/A')}\n"
            f"**Krytyczne sukcesy:** {user_stats.get('critical_successes', 0)}\n"
            f"**Krytyczne porażki:** {user_stats.get('critical_failures', 0)}"
        ),
        inline=True
    )

    embed.add_field(
        name="🌍 Statystyki globalne",
        value=(
            f"**Wszystkich rzutów:** {global_stats['total_rolls']}\n"
            f"**Średnia globalna:** {global_stats['average_roll']:.2f}\n"
            f"**Najwyższy rzut:** {global_stats['highest_roll']}\n"
            f"**Najniższy rzut:** {global_stats['lowest_roll']}\n"
            f"**Krytycznych sukcesów:** {global_stats['critical_successes']}\n"
            f"**Krytycznych porażek:** {global_stats['critical_failures']}"
        ),
        inline=True
    )

    if user_stats.get("favorite_dice"):
        sorted_dice = sorted(user_stats["favorite_dice"].items(), key=lambda x: x[1], reverse=True)[:3]
        dice_text = "\n".join([f"**{dice}:** {count}" for dice, count in sorted_dice])
        embed.add_field(
            name="🎭 Ulubione kości",
            value=dice_text or "Brak danych",
            inline=False
        )

    if achievements:
        recent_achievements = achievements[-5:]
        achievements_text = "\n".join([f"🏆 {ach}" for ach in recent_achievements])
        embed.add_field(
            name="🎖 Osiągnięcia",
            value=achievements_text,
            inline=False
        )

    user_session_rolls = [r for r in bot.session_rolls if r["user"] == interaction.user.id]
    if user_session_rolls:
        session_avg = sum(r["total"] for r in user_session_rolls) / len(user_session_rolls)
        embed.add_field(
            name="📈 Dzisiejsza sesja",
            value=f"Rzutów: **{len(user_session_rolls)}**\nŚrednia: **{session_avg:.1f}**",
            inline=True
        )
    
    embed.set_footer(text=f"ID: {interaction.user.id}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} jest gotowy!')
    print(f'✅ Główna komenda: /roll')
    print(f'✅ Dodatkowe: /roll_stats, /roll_help')

    try:
        synced = await bot.tree.sync()
        print(f"✅ Zsynchonizowano {len(synced)} komend(y)")
    except Exception as e:
        print(f"❌ Błąd synchronizacji: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)