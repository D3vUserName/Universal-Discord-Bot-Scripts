import discord
from discord.ext import commands, tasks
import asyncio
import json
import uuid
import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import timedelta
import io
import os

CONFIG = {
    "token": "",
    "prefix": "!",
    "ticket_category_id": 0,                
    "archive_category_id": 0,               
    "panel_channel_id": 0,                  
    "log_channel_id": 0,                    
    "transcript_channel_id": 0,             
    "support_role_ids": [],
    "admin_role_ids": [],
    "auto_close_days": 7,
    "sla_warning_hours": 1,
    "max_tickets_per_user": 5,
    "panel_channel_name": "pomoc"
}

class TicketStatus(str, Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_USER = "WAITING_USER"
    WAITING_SUPPORT = "WAITING_SUPPORT"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"

class TicketType(str, Enum):
    SUPPORT = "support"
    REPORT = "report"
    APPEAL = "appeal"
    PURCHASE = "purchase"
    PARTNERSHIP = "partnership"
    CUSTOM = "custom"

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class StatusChange:
    timestamp: datetime.datetime
    user_id: int
    from_status: TicketStatus
    to_status: TicketStatus
    reason: Optional[str] = None

@dataclass
class Message:
    message_id: int
    timestamp: datetime.datetime
    user_id: int
    content: str
    attachments: List[str] = field(default_factory=list)

@dataclass
class SLA:
    response_time_hours: int = 24
    resolution_time_hours: int = 72

@dataclass
class Template:
    id: str
    name: str
    ticket_type: TicketType
    channel_name: str
    categories: List[str]
    required_questions: List[Dict[str, Any]]
    support_roles: List[int]
    color: int = 0x3498db
    emoji: str = "🎫"
    sla: SLA = field(default_factory=SLA)
    welcome_message: str = "Dziękujemy za utworzenie ticketu!"

class Ticket:
    def __init__(
        self,
        user_id: int,
        template: Template,
        title: str,
        initial_message: str,
        priority: Priority = Priority.MEDIUM,
        answers: Optional[Dict[str, Any]] = None
    ):
        self.id = f"TICKET-{uuid.uuid4().hex[:8].upper()}"
        self.user_id = user_id
        self.template = template
        self.title = title
        self.priority = priority
        
        self.channel_id: Optional[int] = None
        self.panel_message_id: Optional[int] = None
        
        self.status_history: List[StatusChange] = []
        self.current_status = TicketStatus.NEW
        
        self.messages: List[Message] = []
        self.assigned_to: Optional[int] = None
        self.assignments_history: List[Dict] = []
        
        self.created_at = datetime.datetime.now()
        self.updated_at = self.created_at
        self.closed_at: Optional[datetime.datetime] = None
        self.sla_deadline = self._calculate_sla_deadline()
        
        self.answers = answers or {}
        
        self.add_message(0, user_id, initial_message, [])
        self.change_status(TicketStatus.NEW, user_id, "Ticket utworzony")
    
    def _calculate_sla_deadline(self) -> datetime.datetime:
        return self.created_at + timedelta(hours=self.template.sla.response_time_hours)
    
    def change_status(self, new_status: TicketStatus, user_id: int, reason: Optional[str] = None):
        change = StatusChange(
            timestamp=datetime.datetime.now(),
            user_id=user_id,
            from_status=self.current_status,
            to_status=new_status,
            reason=reason
        )
        self.status_history.append(change)
        self.current_status = new_status
        self.updated_at = datetime.datetime.now()
        
        if new_status in [TicketStatus.CLOSED, TicketStatus.ARCHIVED]:
            self.closed_at = datetime.datetime.now()
    
    def add_message(self, message_id: int, user_id: int, content: str, attachments: List[str]):
        message = Message(
            message_id=message_id,
            timestamp=datetime.datetime.now(),
            user_id=user_id,
            content=content,
            attachments=attachments
        )
        self.messages.append(message)
        self.updated_at = message.timestamp

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=CONFIG["prefix"], intents=intents, help_command=None)

class TicketSystem:
    def __init__(self, bot):
        self.bot = bot
        self.tickets: Dict[str, Ticket] = {}
        self.user_tickets: Dict[int, List[str]] = {}
        self.staff_tickets: Dict[int, List[str]] = {}
        self.templates: Dict[str, Template] = {}
        self._load_templates()
    
    def _load_templates(self):
        templates = [
            Template(
                id="SUPPORT",
                name="Wsparcie Techniczne",
                ticket_type=TicketType.SUPPORT,
                channel_name="wsparcie",
                categories=["techniczne", "pomoc"],
                required_questions=[
                    {"question": "Opisz swój problem", "field": "problem", "required": True},
                    {"question": "Co już próbowałeś?", "field": "proby", "required": False, "long": True},
                ],
                support_roles=CONFIG["support_role_ids"],
                color=0x3498db,
                emoji="🔧",
                sla=SLA(response_time_hours=12, resolution_time_hours=48),
                welcome_message="Dziękujemy za utworzenie ticketu wsparcia! Nasz zespół pomoże Ci w krótkim czasie.\n\n**Prosimy o cierpliwość - odpowiemy najszybciej jak to możliwe!**"
            ),
            Template(
                id="REPORT",
                name="Zgłoszenie Błędu",
                ticket_type=TicketType.REPORT,
                channel_name="blad",
                categories=["bug", "problem"],
                required_questions=[
                    {"question": "Opis błędu", "field": "opis", "required": True, "long": True},
                    {"question": "Kroki do odtworzenia", "field": "kroki", "required": True, "long": True},
                ],
                support_roles=CONFIG["support_role_ids"],
                color=0xe74c3c,
                emoji="🐛",
                sla=SLA(response_time_hours=6, resolution_time_hours=24),
                welcome_message="Dziękujemy za zgłoszenie błędu! Przeanalizujemy ten problem.\n\n**Aby pomóc nam w diagnozie, podaj jak najwięcej szczegółów!**"
            ),
            Template(
                id="APPEAL",
                name="Odwołanie",
                ticket_type=TicketType.APPEAL,
                channel_name="odwolanie",
                categories=["moderacja", "odwolanie"],
                required_questions=[
                    {"question": "Od czego się odwołujesz?", "field": "co", "required": True},
                    {"question": "Dlaczego powinniśmy rozważyć?", "field": "powod", "required": True, "long": True},
                ],
                support_roles=CONFIG["support_role_ids"] + CONFIG["admin_role_ids"],
                color=0xf1c40f,
                emoji="⚖️",
                sla=SLA(response_time_hours=48, resolution_time_hours=168),
                welcome_message="Twoje odwołanie zostało złożone. Zespół moderacyjny je przeanalizuje.\n\n**Odwołania są rozpatrywane indywidualnie, prosimy o cierpliwość.**"
            ),
            Template(
                id="PURCHASE",
                name="Pomoc z Zakupem",
                ticket_type=TicketType.PURCHASE,
                channel_name="zakup",
                categories=["płatności", "zakupy"],
                required_questions=[
                    {"question": "ID zamówienia/transakcji", "field": "zamowienie_id", "required": True},
                    {"question": "Opis problemu", "field": "problem", "required": True, "long": True}
                ],
                support_roles=CONFIG["support_role_ids"],
                color=0x2ecc71,
                emoji="💳",
                sla=SLA(response_time_hours=4, resolution_time_hours=12),
                welcome_message="Dziękujemy za kontakt w sprawie zakupu!\n\n**Dla szybszej pomocy podaj wszystkie szczegóły transakcji.**"
            ),
            Template(
                id="PARTNERSHIP",
                name="Współpraca",
                ticket_type=TicketType.PARTNERSHIP,
                channel_name="wspolpraca",
                categories=["business", "partnership"],
                required_questions=[
                    {"question": "Firma/Organizacja", "field": "firma", "required": True},
                    {"question": "Propozycja współpracy", "field": "propozycja", "required": True, "long": True},
                ],
                support_roles=CONFIG["admin_role_ids"],
                color=0x9b59b6,
                emoji="🤝",
                sla=SLA(response_time_hours=24, resolution_time_hours=72),
                welcome_message="Dziękujemy za zainteresowanie współpracą!\n\n**Nasz zespół biznesowy skontaktuje się z Tobą w ciągu 24 godzin.**"
            )
        ]
        
        for template in templates:
            self.templates[template.id] = template
    
    async def start_tasks(self):
        if not self._cleanup_task.is_running():
            self._cleanup_task.start()
        if not self._sla_check_task.is_running():
            self._sla_check_task.start()
    
    async def create_ticket(self, user_id: int, template_id: str, title: str, 
                           description: str, priority: Priority, answers: Dict[str, Any]) -> Optional[Ticket]:
        if len(self.user_tickets.get(user_id, [])) >= CONFIG["max_tickets_per_user"]:
            return None
        
        template = self.templates.get(template_id)
        if not template:
            return None
        
        ticket = Ticket(
            user_id=user_id,
            template=template,
            title=title,
            initial_message=description,
            priority=priority,
            answers=answers
        )
        
        self.tickets[ticket.id] = ticket
        if user_id not in self.user_tickets:
            self.user_tickets[user_id] = []
        self.user_tickets[user_id].append(ticket.id)
        
        return ticket
    
    async def create_ticket_channel(self, guild: discord.Guild, ticket: Ticket) -> Optional[discord.TextChannel]:
        category = None
        if CONFIG["ticket_category_id"]:
            category = guild.get_channel(CONFIG["ticket_category_id"])
        
        if not category:
            await self.send_log(f"❌ Nie znaleziono kategorii ticketów (ID: {CONFIG['ticket_category_id']})")
            return None
        
        channel_name = f"{ticket.template.channel_name}-{ticket.id.lower()}"
        try:
            channel = await category.create_text_channel(
                name=channel_name,
                topic=f"Ticket {ticket.id} - {ticket.title}"
            )
            
            await channel.set_permissions(guild.default_role, read_messages=False)
            
            user = guild.get_member(ticket.user_id)
            if user:
                await channel.set_permissions(user, read_messages=True, send_messages=True, 
                                             embed_links=True, attach_files=True)
            
            for role_id in ticket.template.support_roles:
                role = guild.get_role(role_id)
                if role:
                    await channel.set_permissions(role, read_messages=True, send_messages=True, 
                                                 manage_messages=True, embed_links=True, 
                                                 attach_files=True)
            
            await channel.set_permissions(guild.me, read_messages=True, send_messages=True, 
                                         manage_channels=True, manage_messages=True,
                                         embed_links=True, attach_files=True)
            
            ticket.channel_id = channel.id
            return channel
            
        except discord.Forbidden as e:
            await self.send_log(f"❌ Brak uprawnień do tworzenia kanału: {e}")
            return None
        except Exception as e:
            await self.send_log(f"❌ Błąd tworzenia kanału: {e}")
            return None
    
    async def send_ticket_panel(self, channel: discord.TextChannel, ticket: Ticket):
        embed = discord.Embed(
            title=f"🎫 PANEL TICKETU - {ticket.id}",
            description=f"**Status:** `{ticket.current_status.value}`\n**Priorytet:** `{ticket.priority.value.upper()}`",
            color=ticket.template.color,
            timestamp=ticket.created_at
        )
        
        user = self.bot.get_user(ticket.user_id)
        embed.add_field(name="👤 Twórca", value=user.mention if user else f"<@{ticket.user_id}>", inline=True)
        
        if ticket.assigned_to:
            staff = self.bot.get_user(ticket.assigned_to)
            embed.add_field(name="🛠️ Przypisany do", value=staff.mention if staff else f"<@{ticket.assigned_to}>", inline=True)
        else:
            embed.add_field(name="🛠️ Przypisany do", value="❌ Nieprzypisany", inline=True)
        
        embed.add_field(name="📅 Utworzony", value=f"<t:{int(ticket.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="⏰ Termin SLA", value=f"<t:{int(ticket.sla_deadline.timestamp())}:R>", inline=True)
        
        if ticket.answers:
            answers_text = "\n".join([f"• **{k}:** {v[:100]}{'...' if len(str(v)) > 100 else ''}" for k, v in ticket.answers.items()])
            embed.add_field(name="📝 Informacje", value=answers_text[:500], inline=False)
        
        embed.add_field(
            name="⚡ Akcje",
            value="• **👥 Przypisz** - Przypisz ticket\n"
                  "• **📋 Status** - Zmień status\n"
                  "• **📄 Transkrypt** - Pobierz transkrypt\n"
                  "• **🔒 Zamknij** - Zamknij ticket\n"
                  "• **ℹ️ Info** - Informacje o tickecie",
            inline=False
        )
        
        embed.set_footer(text=f"Typ: {ticket.template.name}")
        
        view = TicketPanelView(ticket)
        message = await channel.send(embed=embed, view=view)
        ticket.panel_message_id = message.id
        
        await message.add_reaction("👥")
        await message.add_reaction("📋")
        await message.add_reaction("📄")
        await message.add_reaction("🔒")
        await message.add_reaction("ℹ️")
    
    async def auto_assign_ticket(self, ticket: Ticket, guild: discord.Guild):
        support_members = []
        for role_id in ticket.template.support_roles:
            role = guild.get_role(role_id)
            if role:
                support_members.extend([member for member in role.members if not member.bot])
        
        if not support_members:
            await self.send_log(f"⚠️ Brak członków supportu dla ticketu {ticket.id}")
            return
        
        unique_members = []
        seen_ids = set()
        for member in support_members:
            if member.id not in seen_ids:
                unique_members.append(member)
                seen_ids.add(member.id)
        
        if not unique_members:
            return
        
        member_load = {}
        for member in unique_members:
            member_load[member.id] = len(self.staff_tickets.get(member.id, []))
        
        min_member_id = min(member_load, key=member_load.get)
        ticket.assigned_to = min_member_id
        
        if min_member_id not in self.staff_tickets:
            self.staff_tickets[min_member_id] = []
        self.staff_tickets[min_member_id].append(ticket.id)
        
        channel = self.bot.get_channel(ticket.channel_id)
        if channel:
            member = guild.get_member(min_member_id)
            if member:
                await channel.set_permissions(member, read_messages=True, send_messages=True, 
                                             embed_links=True, attach_files=True)
                
                embed = discord.Embed(
                    description=f"✅ Ticket automatycznie przypisany do {member.mention}",
                    color=0x2ecc71
                )
                await channel.send(embed=embed)
                
                await self.send_log(f"✅ Ticket {ticket.id} przypisany do {member.name}")
    
    async def close_ticket(self, ticket_id: str, closer_id: int, reason: Optional[str] = None) -> bool:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return False
        
        ticket.change_status(TicketStatus.CLOSED, closer_id, reason or "Ręcznie zamknięty")

        transcript = await self.generate_transcript(ticket)
        
        if CONFIG["transcript_channel_id"]:
            log_channel = self.bot.get_channel(CONFIG["transcript_channel_id"])
            if log_channel:
                try:
                    file = discord.File(
                        io.BytesIO(transcript.encode('utf-8')),
                        filename=f"transcript-{ticket.id}.txt"
                    )
                    embed = discord.Embed(
                        title=f"📄 Transkrypt Ticketu {ticket.id}",
                        description=f"**Tytuł:** {ticket.title}\n**Twórca:** <@{ticket.user_id}>\n**Zamknięty przez:** <@{closer_id}>",
                        color=0x95a5a6,
                        timestamp=datetime.datetime.now()
                    )
                    if reason:
                        embed.add_field(name="Powód zamknięcia", value=reason, inline=False)
                    
                    await log_channel.send(embed=embed, file=file)
                except Exception as e:
                    await self.send_log(f"❌ Błąd wysyłania transkryptu: {e}")

        channel = self.bot.get_channel(ticket.channel_id)
        if channel:
            try:
                await channel.edit(name=f"closed-{ticket.id.lower()}")

                if CONFIG["archive_category_id"]:
                    archive_category = self.bot.get_channel(CONFIG["archive_category_id"])
                    if archive_category:
                        await channel.edit(category=archive_category)

                await channel.set_permissions(channel.guild.default_role, read_messages=False, send_messages=False)
                
                for role_id in ticket.template.support_roles + CONFIG["admin_role_ids"]:
                    role = channel.guild.get_role(role_id)
                    if role:
                        await channel.set_permissions(role, read_messages=True, send_messages=False)
                
                closer = self.bot.get_user(closer_id)
                embed = discord.Embed(
                    title="🔒 TICKET ZAMKNIĘTY",
                    description=f"**ID:** {ticket.id}\n**Tytuł:** {ticket.title}",
                    color=0x95a5a6,
                    timestamp=datetime.datetime.now()
                )
                
                embed.add_field(name="👤 Twórca", value=f"<@{ticket.user_id}>", inline=True)
                embed.add_field(name="🔧 Zamknięty przez", value=closer.mention if closer else f"<@{closer_id}>", inline=True)
                
                if ticket.assigned_to:
                    staff = self.bot.get_user(ticket.assigned_to)
                    embed.add_field(name="🛠️ Ostatnio przypisany", value=staff.mention if staff else f"<@{ticket.assigned_to}>", inline=True)
                
                duration = (datetime.datetime.now() - ticket.created_at)
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                embed.add_field(name="⏱️ Czas trwania", value=f"{duration.days}d {hours}h {minutes}m", inline=True)
                embed.add_field(name="💬 Wiadomości", value=str(len(ticket.messages)), inline=True)
                embed.add_field(name="🔄 Zmiany statusu", value=str(len(ticket.status_history)), inline=True)
                
                if reason:
                    embed.add_field(name="📝 Powód zamknięcia", value=reason, inline=False)
                
                await channel.send(embed=embed)
                
            except Exception as e:
                await self.send_log(f"❌ Błąd zamykania kanału: {e}")
        
        await self.send_log(f"🔒 Ticket {ticket.id} zamknięty przez <@{closer_id}>")
        return True
    
    async def generate_transcript(self, ticket: Ticket) -> str:
        transcript = f"=== TRANSKRYPT TICKETU ===\n"
        transcript += f"ID: {ticket.id}\n"
        transcript += f"Tytuł: {ticket.title}\n"
        transcript += f"Twórca: {ticket.user_id}\n"
        transcript += f"Typ: {ticket.template.name}\n"
        transcript += f"Priorytet: {ticket.priority.value}\n"
        transcript += f"Status końcowy: {ticket.current_status.value}\n"
        transcript += f"Utworzony: {ticket.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        transcript += f"Ostatnia aktywność: {ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if ticket.assigned_to:
            transcript += f"Przypisany do: {ticket.assigned_to}\n"
        
        if ticket.answers:
            transcript += f"\n=== ODPOWIEDZI ===\n"
            for key, value in ticket.answers.items():
                transcript += f"{key}: {value}\n"
        
        transcript += f"\n=== HISTORIA STATUSÓW ===\n"
        for change in ticket.status_history:
            user = self.bot.get_user(change.user_id)
            user_name = user.name if user else f"User_{change.user_id}"
            transcript += f"[{change.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {change.from_status} → {change.to_status} przez {user_name}"
            if change.reason:
                transcript += f" - {change.reason}"
            transcript += "\n"
        
        transcript += f"\n=== WIADOMOŚCI ({len(ticket.messages)}) ===\n"
        for msg in ticket.messages:
            if msg.message_id == 0:
                transcript += f"[{msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] SYSTEM: Ticket utworzony z wiadomością: {msg.content}\n"
                continue
                
            user = self.bot.get_user(msg.user_id)
            user_name = user.name if user else f"User_{msg.user_id}"
            transcript += f"[{msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {user_name}: {msg.content}\n"
            if msg.attachments:
                transcript += f"  Załączniki: {', '.join(msg.attachments)}\n"
        
        transcript += f"\n=== PRZYPISANIA ({len(ticket.assignments_history)}) ===\n"
        for assignment in ticket.assignments_history:
            staff = self.bot.get_user(assignment['staff_id'])
            staff_name = staff.name if staff else f"User_{assignment['staff_id']}"
            by = self.bot.get_user(assignment['assigned_by'])
            by_name = by.name if by else f"User_{assignment['assigned_by']}"
            transcript += f"[{assignment['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}] Przypisany do {staff_name} przez {by_name}"
            if assignment['reason']:
                transcript += f" - {assignment['reason']}"
            transcript += "\n"
        
        transcript += f"\n=== KONIEC TRANSKRYPTU ===\n"
        return transcript
    
    async def send_log(self, message: str):
        if CONFIG["log_channel_id"]:
            log_channel = self.bot.get_channel(CONFIG["log_channel_id"])
            if log_channel:
                try:
                    await log_channel.send(message)
                except:
                    pass
    
    @tasks.loop(hours=1)
    async def _cleanup_task(self):
        await self.bot.wait_until_ready()
        
        cutoff = datetime.datetime.now() - timedelta(days=CONFIG["auto_close_days"])
        
        tickets_to_close = []
        for ticket_id, ticket in self.tickets.items():
            if (ticket.current_status == TicketStatus.RESOLVED and 
                ticket.updated_at < cutoff):
                tickets_to_close.append(ticket_id)
        
        for ticket_id in tickets_to_close:
            await self.close_ticket(ticket_id, self.bot.user.id, "Automatycznie zamknięty po okresie rozwiązywania")
    
    @tasks.loop(minutes=30)
    async def _sla_check_task(self):
        await self.bot.wait_until_ready()
        
        for ticket_id, ticket in self.tickets.items():
            if ticket.current_status not in [TicketStatus.CLOSED, TicketStatus.ARCHIVED]:
                if datetime.datetime.now() > ticket.sla_deadline:
                    channel = self.bot.get_channel(ticket.channel_id)
                    if channel:
                        embed = discord.Embed(
                            title="⚠️ OSTRZEŻENIE SLA",
                            description=f"Ticket {ticket.id} przekroczył czas odpowiedzi SLA!",
                            color=0xe74c3c
                        )
                        embed.add_field(name="Termin SLA", value=f"<t:{int(ticket.sla_deadline.timestamp())}:R>", inline=True)
                        embed.add_field(name="Bieżący czas", value=f"<t:{int(datetime.datetime.now().timestamp())}:R>", inline=True)
                        
                        role_mentions = " ".join([f"<@&{role_id}>" for role_id in ticket.template.support_roles])
                        await channel.send(f"{role_mentions}\n**UWAGA: PRZEKROCZENIE SLA!**", embed=embed)

class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.select(
        placeholder="🎫 Wybierz typ ticketu...",
        custom_id="main_panel_select",
        options=[
            discord.SelectOption(label="🔧 Wsparcie Techniczne", value="SUPPORT", description="Pomoc z problemami technicznymi"),
            discord.SelectOption(label="🐛 Zgłoszenie Błędu", value="REPORT", description="Zgłoś błąd lub problem"),
            discord.SelectOption(label="⚖️ Odwołanie", value="APPEAL", description="Odwołaj się od decyzji moderacji"),
            discord.SelectOption(label="💳 Pomoc z Zakupem", value="PURCHASE", description="Problemy z płatnościami i zakupami"),
            discord.SelectOption(label="🤝 Współpraca", value="PARTNERSHIP", description="Propozycje biznesowe"),
        ]
    )
    async def ticket_type_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        template = ticket_system.templates.get(select.values[0])
        if not template:
            await interaction.response.send_message("❌ Nieprawidłowy typ ticketu!", ephemeral=True)
            return
        
        modal = TicketCreationModal(template)
        await interaction.response.send_modal(modal)

class TicketCreationModal(discord.ui.Modal):
    def __init__(self, template: Template):
        super().__init__(title=f"🎫 {template.name}")
        self.template = template

        self.title_input = discord.ui.TextInput(
            label="Tytuł Ticketu (max 100 znaków)",
            placeholder="Krótki opis problemu/pytania...",
            max_length=100,
            required=True
        )
        self.add_item(self.title_input)
        
        self.desc_input = discord.ui.TextInput(
            label="Szczegółowy Opis (max 1000 znaków)",
            style=discord.TextStyle.paragraph,
            placeholder="Opisz swój problem/pytanie szczegółowo...",
            max_length=1000,
            required=True
        )
        self.add_item(self.desc_input)
        
        self.priority_select = discord.ui.TextInput(
            label="Priorytet (niski/średni/wysoki/krytyczny)",
            placeholder="średni",
            default="średni",
            required=False,
            max_length=20
        )
        self.add_item(self.priority_select)
        
        self.answer_inputs = {}
        questions_to_add = template.required_questions[:2]
        
        for question in questions_to_add:
            style = discord.TextStyle.paragraph if question.get("long", False) else discord.TextStyle.short
            max_length = 1000 if question.get("long", False) else 200
            
            input_field = discord.ui.TextInput(
                label=question["question"][:40] + ("..." if len(question["question"]) > 40 else ""),
                style=style,
                required=question.get("required", True),
                placeholder="Twoja odpowiedź...",
                max_length=max_length
            )
            self.add_item(input_field)
            self.answer_inputs[question["field"]] = input_field
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        priority_text = self.priority_select.value.lower() if self.priority_select.value else "średni"
        priority_map = {
            "niski": Priority.LOW,
            "niskie": Priority.LOW,
            "low": Priority.LOW,
            "średni": Priority.MEDIUM,
            "sredni": Priority.MEDIUM,
            "medium": Priority.MEDIUM,
            "wysoki": Priority.HIGH,
            "high": Priority.HIGH,
            "krytyczny": Priority.CRITICAL,
            "critical": Priority.CRITICAL
        }
        priority = priority_map.get(priority_text, Priority.MEDIUM)
        
        answers = {}
        for field_name, input_field in self.answer_inputs.items():
            answers[field_name] = input_field.value
        
        ticket = await ticket_system.create_ticket(
            user_id=interaction.user.id,
            template_id=self.template.id,
            title=self.title_input.value,
            description=self.desc_input.value,
            priority=priority,
            answers=answers
        )
        
        if not ticket:
            await interaction.followup.send(
                "❌ Osiągnąłeś maksymalną liczbę otwartych ticketów! Zamknij któryś z istniejących przed utworzeniem nowego.",
                ephemeral=True
            )
            return
        
        channel = await ticket_system.create_ticket_channel(interaction.guild, ticket)
        
        if channel:
            await ticket_system.send_ticket_panel(channel, ticket)
            
            embed = discord.Embed(
                title="✅ TICKET UTWORZONY POMYŚLNIE!",
                description=f"**ID Ticketu:** `{ticket.id}`",
                color=0x2ecc71
            )
            
            embed.add_field(name="📁 Typ", value=ticket.template.name, inline=True)
            embed.add_field(name="⚡ Priorytet", value=ticket.priority.value.upper(), inline=True)
            embed.add_field(name="📅 Utworzony", value=f"<t:{int(ticket.created_at.timestamp())}:R>", inline=True)
            embed.add_field(name="🔗 Kanał", value=channel.mention, inline=False)
            embed.add_field(name="⏰ Termin odpowiedzi", value=f"<t:{int(ticket.sla_deadline.timestamp())}:R>", inline=True)
            
            embed.set_footer(text="Nasz zespół skontaktuje się z Tobą najszybciej jak to możliwe!")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            await ticket_system.auto_assign_ticket(ticket, interaction.guild)
            await ticket_system.send_log(f"🎫 Nowy ticket `{ticket.id}` utworzony przez <@{interaction.user.id}>")
        else:
            await interaction.followup.send(
                "❌ Nie udało się utworzyć kanału ticketu! Sprawdź:\n"
                "1. Czy bot ma uprawnienia do tworzenia kanałów\n"
                "2. Czy kategoria ticketów istnieje\n"
                "3. Skontaktuj się z administratorem",
                ephemeral=True
            )

class TicketPanelView(discord.ui.View):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=None)
        self.ticket = ticket
    
    def _check_permissions(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ticket.user_id:
            return True
        
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        
        for role in member.roles:
            if role.id in self.ticket.template.support_roles or role.id in CONFIG["admin_role_ids"]:
                return True
        
        return False
    
    @discord.ui.button(label="Przypisz", emoji="👥", style=discord.ButtonStyle.primary, custom_id="assign_btn")
    async def assign_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permissions(interaction):
            await interaction.response.send_message("❌ Nie masz uprawnień do zarządzania tym ticketem!", ephemeral=True)
            return
        
        await interaction.response.send_modal(AssignModal(self.ticket))
    
    @discord.ui.button(label="Status", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="status_btn")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permissions(interaction):
            await interaction.response.send_message("❌ Nie masz uprawnień do zmiany statusu!", ephemeral=True)
            return
        
        view = StatusSelectView(self.ticket)
        embed = discord.Embed(
            title="📋 Zmień Status Ticketu",
            description="Wybierz nowy status z listy poniżej:",
            color=0x3498db
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Transkrypt", emoji="📄", style=discord.ButtonStyle.secondary, custom_id="transcript_btn")
    async def transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permissions(interaction):
            await interaction.response.send_message("❌ Nie masz uprawnień do pobierania transkryptu!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        transcript = await ticket_system.generate_transcript(self.ticket)
        file = discord.File(
            io.BytesIO(transcript.encode('utf-8')),
            filename=f"transcript-{self.ticket.id}.txt"
        )
        
        embed = discord.Embed(
            title=f"📄 Transkrypt Ticketu {self.ticket.id}",
            description=f"Pobrano: <t:{int(datetime.datetime.now().timestamp())}:R>",
            color=0x3498db
        )
        embed.set_footer(text="Zachowaj ten plik dla celów archiwalnych")
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)
    
    @discord.ui.button(label="Zamknij", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close_btn")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permissions(interaction):
            await interaction.response.send_message("❌ Nie masz uprawnień do zamykania ticketu!", ephemeral=True)
            return
        
        await interaction.response.send_modal(CloseModal(self.ticket))
    
    @discord.ui.button(label="Info", emoji="ℹ️", style=discord.ButtonStyle.success, custom_id="info_btn")
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.create_info_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def create_info_embed(self) -> discord.Embed:
        """Tworzy embed z informacjami o tickecie"""
        embed = discord.Embed(
            title=f"ℹ️ SZCZEGÓŁY TICKETU - {self.ticket.id}",
            color=self.ticket.template.color,
            timestamp=self.ticket.created_at
        )

        user = ticket_system.bot.get_user(self.ticket.user_id)
        embed.add_field(name="👤 Twórca", value=user.mention if user else f"<@{self.ticket.user_id}>", inline=True)
        
        if self.ticket.assigned_to:
            staff = ticket_system.bot.get_user(self.ticket.assigned_to)
            embed.add_field(name="🛠️ Przypisany do", value=staff.mention if staff else f"<@{self.ticket.assigned_to}>", inline=True)
        else:
            embed.add_field(name="🛠️ Przypisany do", value="❌ Nieprzypisany", inline=True)
        
        embed.add_field(name="📊 Status", value=f"`{self.ticket.current_status.value}`", inline=True)
        embed.add_field(name="⚡ Priorytet", value=f"`{self.ticket.priority.value.upper()}`", inline=True)
        embed.add_field(name="📝 Typ", value=self.ticket.template.name, inline=True)
        embed.add_field(name="📅 Utworzony", value=f"<t:{int(self.ticket.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="🔄 Ostatnia aktywność", value=f"<t:{int(self.ticket.updated_at.timestamp())}:R>", inline=True)
        embed.add_field(name="⏰ Termin SLA", value=f"<t:{int(self.ticket.sla_deadline.timestamp())}:R>", inline=True)
        embed.add_field(name="💬 Wiadomości", value=str(len(self.ticket.messages)), inline=True)
        embed.add_field(name="🔄 Zmiany statusu", value=str(len(self.ticket.status_history)), inline=True)
        
        if self.ticket.status_history:
            recent_changes = self.ticket.status_history[-3:]
            changes_text = ""
            for change in reversed(recent_changes):
                user = ticket_system.bot.get_user(change.user_id)
                user_name = user.name if user else f"User_{change.user_id}"
                time_ago = f"<t:{int(change.timestamp.timestamp())}:R>"
                changes_text += f"• `{change.from_status}` → `{change.to_status}` przez **{user_name}** {time_ago}\n"
                if change.reason:
                    changes_text += f"  *Powód: {change.reason}*\n"
            
            embed.add_field(name="📈 Ostatnie zmiany", value=changes_text[:500] + ("..." if len(changes_text) > 500 else ""), inline=False)
        
        embed.set_footer(text=f"ID: {self.ticket.id}")
        return embed

class StatusSelectView(discord.ui.View):
    def __init__(self, ticket: Ticket):
        super().__init__(timeout=60)
        self.ticket = ticket
    
    @discord.ui.select(
        placeholder="Wybierz nowy status...",
        options=[
            discord.SelectOption(label="🆕 Nowy", value="NEW", description="Ticket właśnie utworzony"),
            discord.SelectOption(label="📂 Otwarty", value="OPEN", description="Ticket otwarty, oczekuje na przypisanie"),
            discord.SelectOption(label="🔄 W trakcie", value="IN_PROGRESS", description="Ticket w trakcie rozwiązywania"),
            discord.SelectOption(label="⏳ Czeka na użytkownika", value="WAITING_USER", description="Oczekiwanie na odpowiedź użytkownika"),
            discord.SelectOption(label="⏳ Czeka na support", value="WAITING_SUPPORT", description="Oczekiwanie na odpowiedź supportu"),
            discord.SelectOption(label="✅ Rozwiązany", value="RESOLVED", description="Problem rozwiązany"),
            discord.SelectOption(label="🔒 Zamknięty", value="CLOSED", description="Ticket zamknięty"),
        ]
    )
    async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        new_status = TicketStatus(select.values[0])
        self.ticket.change_status(new_status, interaction.user.id, f"Zmieniony przez {interaction.user.name}")
        
        await update_ticket_panel(self.ticket)
        
        embed = discord.Embed(
            description=f"✅ Status zmieniony na **{new_status.value}**",
            color=0x2ecc71
        )
        await interaction.response.edit_message(embed=embed, view=None)

class AssignModal(discord.ui.Modal):
    def __init__(self, ticket: Ticket):
        super().__init__(title="👥 Przypisz Ticket")
        self.ticket = ticket
        
        self.user_input = discord.ui.TextInput(
            label="ID użytkownika lub @wzmianka",
            placeholder="np. 123456789012345678 lub @username",
            required=True,
            max_length=100
        )
        self.add_item(self.user_input)
        
        self.reason_input = discord.ui.TextInput(
            label="Powód przypisania (opcjonalnie)",
            placeholder="Dlaczego przypisujesz tego użytkownika?",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        user_input = self.user_input.value.strip()
        user_id = None
        
        try:
            if user_input.startswith("<@") and user_input.endswith(">"):
                user_id = int(user_input[2:-1].replace("!", ""))
            elif user_input.isdigit() and len(user_input) >= 17:
                user_id = int(user_input)
            else:
                member = discord.utils.get(interaction.guild.members, name=user_input)
                if member:
                    user_id = member.id
        except:
            pass
        
        if not user_id:
            await interaction.followup.send("❌ Nieprawidłowy format użytkownika! Użyj ID lub @wzmianki.", ephemeral=True)
            return
        
        member = interaction.guild.get_member(user_id)
        if not member:
            await interaction.followup.send("❌ Użytkownik nie znaleziony na serwerze!", ephemeral=True)
            return
        
        if member.bot:
            await interaction.followup.send("❌ Nie możesz przypisać ticketu do bota!", ephemeral=True)
            return
        
        has_permission = False
        for role in member.roles:
            if role.id in self.ticket.template.support_roles:
                has_permission = True
                break
        
        if not has_permission:
            await interaction.followup.send(
                f"❌ {member.mention} nie ma wymaganej roli support do obsługi tego typu ticketu!",
                ephemeral=True
            )
            return
        
        self.ticket.assigned_to = user_id
        self.ticket.assignments_history.append({
            "timestamp": datetime.datetime.now(),
            "staff_id": user_id,
            "assigned_by": interaction.user.id,
            "reason": self.reason_input.value
        })

        channel = ticket_system.bot.get_channel(self.ticket.channel_id)
        if channel:
            await channel.set_permissions(member, read_messages=True, send_messages=True, 
                                         embed_links=True, attach_files=True)
        
        await update_ticket_panel(self.ticket)
        
        embed = discord.Embed(
            description=f"✅ Ticket przypisany do {member.mention}",
            color=0x2ecc71,
            timestamp=datetime.datetime.now()
        )
        
        if self.reason_input.value:
            embed.add_field(name="📝 Powód przypisania", value=self.reason_input.value, inline=False)
        
        embed.add_field(name="🛠️ Przypisany przez", value=interaction.user.mention, inline=True)
        embed.add_field(name="📅 Data", value=f"<t:{int(datetime.datetime.now().timestamp())}:R>", inline=True)
        
        await channel.send(embed=embed)
        await interaction.followup.send(f"✅ Ticket przypisany pomyślnie do {member.mention}!", ephemeral=True)
        await ticket_system.send_log(f"👥 Ticket `{self.ticket.id}` przypisany do {member.name} przez {interaction.user.name}")

class CloseModal(discord.ui.Modal):
    def __init__(self, ticket: Ticket):
        super().__init__(title="🔒 Zamknij Ticket")
        self.ticket = ticket
        
        self.reason_input = discord.ui.TextInput(
            label="Powód zamknięcia",
            placeholder="Podaj powód zamknięcia ticketu...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        await ticket_system.close_ticket(self.ticket.id, interaction.user.id, self.reason_input.value)
        
        embed = discord.Embed(
            title="✅ TICKET ZAMKNIĘTY",
            description=f"Ticket `{self.ticket.id}` został zamknięty pomyślnie.",
            color=0x2ecc71
        )
        embed.add_field(name="📝 Powód", value=self.reason_input.value, inline=False)
        embed.add_field(name="👤 Zamknięty przez", value=interaction.user.mention, inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def update_ticket_panel(ticket: Ticket):
    channel = ticket_system.bot.get_channel(ticket.channel_id)
    if not channel or not ticket.panel_message_id:
        return
    
    try:
        message = await channel.fetch_message(ticket.panel_message_id)
        
        embed = discord.Embed(
            title=f"🎫 PANEL TICKETU - {ticket.id}",
            description=f"**Status:** `{ticket.current_status.value}`\n**Priorytet:** `{ticket.priority.value.upper()}`",
            color=ticket.template.color,
            timestamp=ticket.updated_at
        )
        
        user = ticket_system.bot.get_user(ticket.user_id)
        embed.add_field(name="👤 Twórca", value=user.mention if user else f"<@{ticket.user_id}>", inline=True)
        
        if ticket.assigned_to:
            staff = ticket_system.bot.get_user(ticket.assigned_to)
            embed.add_field(name="🛠️ Przypisany do", value=staff.mention if staff else f"<@{ticket.assigned_to}>", inline=True)
        else:
            embed.add_field(name="🛠️ Przypisany do", value="❌ Nieprzypisany", inline=True)
        
        embed.add_field(name="📅 Utworzony", value=f"<t:{int(ticket.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="⏰ Termin SLA", value=f"<t:{int(ticket.sla_deadline.timestamp())}:R>", inline=True)
        
        if ticket.answers:
            answers_text = "\n".join([f"• **{k}:** {v[:100]}{'...' if len(str(v)) > 100 else ''}" for k, v in ticket.answers.items()])
            embed.add_field(name="📝 Informacje", value=answers_text[:500], inline=False)
        
        embed.add_field(
            name="⚡ Akcje",
            value="• **👥 Przypisz** - Przypisz ticket\n"
                  "• **📋 Status** - Zmień status\n"
                  "• **📄 Transkrypt** - Pobierz transkrypt\n"
                  "• **🔒 Zamknij** - Zamknij ticket\n"
                  "• **ℹ️ Info** - Informacje o tickecie",
            inline=False
        )
        
        embed.set_footer(text=f"Typ: {ticket.template.name} | Ostatnia aktualizacja")
        
        view = TicketPanelView(ticket)
        await message.edit(embed=embed, view=view)
    except discord.NotFound:
        await ticket_system.send_ticket_panel(channel, ticket)
    except Exception as e:
        print(f"Błąd aktualizacji panelu: {e}")

ticket_system = TicketSystem(bot)

@bot.event
async def on_ready():
    print(f"✅ Bot gotowy jako {bot.user}")
    print(f"🎫 System ticketów zainicjalizowany z {len(ticket_system.templates)} szablonami")
    print(f"📁 Konfiguracja:")
    print(f"   • Kategoria ticketów: {CONFIG['ticket_category_id']}")
    print(f"   • Kategoria archiwum: {CONFIG['archive_category_id']}")
    print(f"   • Kanał panelu: {CONFIG['panel_channel_id']}")
    print(f"   • Kanał logów: {CONFIG['log_channel_id']}")
    print(f"   • Kanał transkryptów: {CONFIG['transcript_channel_id']}")

    await ticket_system.start_tasks()

    bot.add_view(MainPanelView())

    for guild in bot.guilds:
        await create_or_update_panel(guild)

async def create_or_update_panel(guild: discord.Guild):
    panel_channel = None

    if CONFIG["panel_channel_id"]:
        panel_channel = guild.get_channel(CONFIG["panel_channel_id"])
    
    if not panel_channel:
        for channel in guild.text_channels:
            if channel.name == CONFIG["panel_channel_name"]:
                panel_channel = channel
                CONFIG["panel_channel_id"] = channel.id
                break
    
    if not panel_channel:
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True),
                guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True)
            }
            
            category = None
            if CONFIG["ticket_category_id"]:
                category = guild.get_channel(CONFIG["ticket_category_id"])
            
            panel_channel = await guild.create_text_channel(
                CONFIG["panel_channel_name"],
                topic="🎫 Utwórz ticket używając menu poniżej",
                overwrites=overwrites,
                category=category
            )
            CONFIG["panel_channel_id"] = panel_channel.id
            print(f"✅ Utworzono nowy kanał panelu: {panel_channel.name}")
        except Exception as e:
            print(f"❌ Nie udało się utworzyć kanału panelu: {e}")
            return
    
    try:
        def is_bot_message(m):
            return m.author == bot.user or (m.author.bot and m.content)
        
        await panel_channel.purge(limit=100, check=is_bot_message)
    except:
        pass
    
    embed = discord.Embed(
        title="🎫 SYSTEM TICKETÓW",
        description="**Wybierz typ ticketu z menu poniżej:**\n\n"
                   "Utwórz ticket w odpowiedniej kategorii, aby uzyskać szybką i profesjonalną pomoc.",
        color=0x3498db,
        timestamp=datetime.datetime.now()
    )

    templates_list = []
    for template_id, template in ticket_system.templates.items():
        role_names = []
        for role_id in template.support_roles:
            role = guild.get_role(role_id)
            if role:
                role_names.append(role.name)
        
        templates_list.append(f"• **{template.emoji} {template.name}** - {template.welcome_message.split('.')[0]}")
    
    embed.add_field(
        name="📋 Dostępne Typy Ticketów",
        value="\n".join(templates_list),
        inline=False
    )
    
    
    embed.set_footer(text="System zarządzania ticketami v3.0 | Wsparcie dostępne 24/7")
    
    view = MainPanelView()
    await panel_channel.send(embed=embed, view=view)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    await bot.process_commands(message)
    

    for ticket in ticket_system.tickets.values():
        if ticket.channel_id == message.channel.id:
            attachments = [att.url for att in message.attachments]
            ticket.add_message(message.id, message.author.id, message.content, attachments)
            
            await update_ticket_panel(ticket)
            break

@bot.command(name="ticketsetup")
@commands.has_permissions(administrator=True)
async def ticketsetup_command(ctx):
    embed = discord.Embed(
        title="⚙️ KONFIGURACJA SYSTEMU TICKETÓW",
        description="Konfiguruję system ticketów...",
        color=0x9b59b6
    )
    
    msg = await ctx.send(embed=embed)
    
    guild = ctx.guild
    
    if not CONFIG["ticket_category_id"]:
        category = discord.utils.get(guild.categories, name="🎫 Tickety")
        if not category:
            category = await guild.create_category("🎫 Tickety")
        CONFIG["ticket_category_id"] = category.id
        embed.add_field(name="✅ Kategoria ticketów", value=f"ID: `{category.id}`", inline=True)
    
    if not CONFIG["archive_category_id"]:
        category = discord.utils.get(guild.categories, name="📁 Zamknięte Tickety")
        if not category:
            category = await guild.create_category("📁 Zamknięte Tickety")
        CONFIG["archive_category_id"] = category.id
        embed.add_field(name="✅ Kategoria archiwum", value=f"ID: `{category.id}`", inline=True)
    
    channels_created = []
    
    if not CONFIG["log_channel_id"]:
        channel = discord.utils.get(guild.text_channels, name="📋-logi-ticketów")
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            for role_id in CONFIG["support_role_ids"] + CONFIG["admin_role_ids"]:
                role = guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await guild.create_text_channel("📋-logi-ticketów", overwrites=overwrites)
            channels_created.append(channel.name)
        CONFIG["log_channel_id"] = channel.id
    
    if not CONFIG["transcript_channel_id"]:
        channel = discord.utils.get(guild.text_channels, name="📄-transkrypty")
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            for role_id in CONFIG["support_role_ids"] + CONFIG["admin_role_ids"]:
                role = guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await guild.create_text_channel("📄-transkrypty", overwrites=overwrites)
            channels_created.append(channel.name)
        CONFIG["transcript_channel_id"] = channel.id
    
    if channels_created:
        embed.add_field(name="✅ Utworzone kanały", value=", ".join(channels_created), inline=False)

    if not CONFIG["support_role_ids"]:
        embed.add_field(
            name="⚠️ Uwaga", 
            value="Nie ustawiono ID roli support. Ustaw `CONFIG['support_role_ids']` w kodzie.",
            inline=False
        )
    
    if not CONFIG["admin_role_ids"]:
        embed.add_field(
            name="⚠️ Uwaga", 
            value="Nie ustawiono ID roli admin. Ustaw `CONFIG['admin_role_ids']` w kodzie.",
            inline=False
        )
    
    embed.description = "✅ Konfiguracja zakończona pomyślnie!"
    await msg.edit(embed=embed)

    await create_or_update_panel(guild)

    config_embed = discord.Embed(
        title="📋 Twoja konfiguracja",
        description="Skopiuj te ID do pliku konfiguracyjnego:",
        color=0x3498db
    )
    
    config_embed.add_field(name="Kategoria ticketów", value=f"`{CONFIG['ticket_category_id']}`", inline=True)
    config_embed.add_field(name="Kategoria archiwum", value=f"`{CONFIG['archive_category_id']}`", inline=True)
    config_embed.add_field(name="Kanał panelu", value=f"`{CONFIG['panel_channel_id']}`", inline=True)
    config_embed.add_field(name="Kanał logów", value=f"`{CONFIG['log_channel_id']}`", inline=True)
    config_embed.add_field(name="Kanał transkryptów", value=f"`{CONFIG['transcript_channel_id']}`", inline=True)
    
    await ctx.send(embed=config_embed)

@bot.command(name="ticket")
async def ticket_info(ctx, ticket_id: str = None):
    if ticket_id:
        ticket = ticket_system.tickets.get(ticket_id)
    else:
        ticket = None
        for t in ticket_system.tickets.values():
            if t.channel_id == ctx.channel.id:
                ticket = t
                break
    
    if not ticket:
        await ctx.send("❌ Ticket nie znaleziony!", delete_after=10)
        return
    
    embed = discord.Embed(
        title=f"ℹ️ INFORMACJE O TICKECIE - {ticket.id}",
        color=ticket.template.color
    )
    
    user = bot.get_user(ticket.user_id)
    embed.add_field(name="👤 Twórca", value=user.mention if user else f"<@{ticket.user_id}>", inline=True)
    
    if ticket.assigned_to:
        staff = bot.get_user(ticket.assigned_to)
        embed.add_field(name="🛠️ Przypisany do", value=staff.mention if staff else f"<@{ticket.assigned_to}>", inline=True)
    
    embed.add_field(name="📊 Status", value=f"`{ticket.current_status.value}`", inline=True)
    embed.add_field(name="⚡ Priorytet", value=f"`{ticket.priority.value.upper()}`", inline=True)
    embed.add_field(name="📅 Utworzony", value=f"<t:{int(ticket.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="🔄 Ostatnia aktywność", value=f"<t:{int(ticket.updated_at.timestamp())}:R>", inline=True)
    
    embed.add_field(name="📝 Typ", value=ticket.template.name, inline=True)
    embed.add_field(name="💬 Wiadomości", value=str(len(ticket.messages)), inline=True)
    embed.add_field(name="🔄 Zmiany statusu", value=str(len(ticket.status_history)), inline=True)
    
    if ticket.sla_deadline:
        embed.add_field(name="⏰ Termin SLA", value=f"<t:{int(ticket.sla_deadline.timestamp())}:R>", inline=True)
    
    await ctx.send(embed=embed, delete_after=30)

@bot.command(name="tickets")
async def list_tickets(ctx):
    user_tickets = ticket_system.user_tickets.get(ctx.author.id, [])
    
    if not user_tickets:
        embed = discord.Embed(
            title="📭 Twoje Tickety",
            description="Nie masz żadnych otwartych ticketów.",
            color=0x95a5a6
        )
        await ctx.send(embed=embed, delete_after=30)
        return
    
    embed = discord.Embed(
        title=f"📋 Twoje Tickety ({len(user_tickets)})",
        color=0x3498db
    )
    
    for i, ticket_id in enumerate(user_tickets[:10], 1):
        ticket = ticket_system.tickets.get(ticket_id)
        if ticket:
            channel_mention = f"<{ticket.channel_id}>" if ticket.channel_id else "Brak kanału"
            status_emoji = {
                "NEW": "🆕", "OPEN": "📂", "IN_PROGRESS": "🔄",
                "WAITING_USER": "⏳", "WAITING_SUPPORT": "⏳",
                "RESOLVED": "✅", "CLOSED": "🔒", "ARCHIVED": "📁"
            }.get(ticket.current_status.value, "❓")
            
            embed.add_field(
                name=f"{i}. {status_emoji} {ticket.id}",
                value=f"**{ticket.title}**\n"
                      f"Status: `{ticket.current_status.value}`\n"
                      f"Kanał: {channel_mention}\n"
                      f"Typ: {ticket.template.name}",
                inline=False
            )
    
    if len(user_tickets) > 10:
        embed.set_footer(text=f"Pokazano 10 z {len(user_tickets)} ticketów")
    
    await ctx.send(embed=embed, delete_after=60)

@bot.command(name="ticketstats")
@commands.has_permissions(administrator=True)
async def ticket_stats(ctx):
    total_tickets = len(ticket_system.tickets)
    open_tickets = len([t for t in ticket_system.tickets.values() if t.current_status not in [TicketStatus.CLOSED, TicketStatus.ARCHIVED]])
    closed_tickets = len([t for t in ticket_system.tickets.values() if t.current_status in [TicketStatus.CLOSED, TicketStatus.ARCHIVED]])
    
    status_counts = {}
    for ticket in ticket_system.tickets.values():
        status = ticket.current_status.value
        status_counts[status] = status_counts.get(status, 0) + 1
    
    type_counts = {}
    for ticket in ticket_system.tickets.values():
        ticket_type = ticket.template.name
        type_counts[ticket_type] = type_counts.get(ticket_type, 0) + 1
    
    embed = discord.Embed(
        title="📊 STATYSTYKI SYSTEMU TICKETÓW",
        color=0x9b59b6,
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(name="🎫 Wszystkie tickety", value=str(total_tickets), inline=True)
    embed.add_field(name="📂 Otwarte", value=str(open_tickets), inline=True)
    embed.add_field(name="🔒 Zamknięte", value=str(closed_tickets), inline=True)
    
    status_text = "\n".join([f"• **{status}:** {count}" for status, count in sorted(status_counts.items())])
    embed.add_field(name="📈 Statusy", value=status_text if status_text else "Brak danych", inline=False)
    
    type_text = "\n".join([f"• **{ttype}:** {count}" for ttype, count in sorted(type_counts.items())])
    embed.add_field(name="📋 Typy", value=type_text if type_text else "Brak danych", inline=False)

    recent_tickets = sorted(ticket_system.tickets.values(), key=lambda x: x.created_at, reverse=True)[:5]
    if recent_tickets:
        recent_text = ""
        for ticket in recent_tickets:
            user = bot.get_user(ticket.user_id)
            user_name = user.name if user else f"User_{ticket.user_id}"
            time_ago = f"<t:{int(ticket.created_at.timestamp())}:R>"
            recent_text += f"• `{ticket.id}` - **{user_name}** - {ticket.template.name} {time_ago}\n"
        embed.add_field(name="🕒 Ostatnie tickety", value=recent_text, inline=False)
    
    embed.set_footer(text=f"System zarządzania ticketami v3.0")
    
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if CONFIG["token"] == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Ustaw token bota w CONFIG['token']!")
        exit(1)
    

    required_configs = [
        ("ticket_category_id", "ID kategorii ticketów"),
        ("archive_category_id", "ID kategorii archiwum"),
        ("panel_channel_id", "ID kanału panelu"),
        ("support_role_ids", "ID roli support"),
        ("admin_role_ids", "ID roli admin")
    ]
    
    missing = []
    for config_key, config_name in required_configs:
        if not CONFIG[config_key]:
            missing.append(config_name)
    
    if missing:
        print("⚠️ Uwaga: Nie ustawiono następujących konfiguracji:")
        for item in missing:
            print(f"   • {item}")
        print("\nUżyj komendy `!ticketsetup` na serwerze Discord aby skonfigurować system.")
    
    print("🚀 Uruchamianie bota...")
    bot.run(CONFIG["token"])