import discord
import os
import asyncio
import sqlite3
import random
from discord.ext import commands
from discord.ui import Button, View, Select
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
TOKEN = os.getenv('DISCORD_TOKEN')

# --- DATABASE SETUP ---
DB_NAME = os.getenv('DB_PATH', 'trg.db')

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS active_channels
                 (channel_id INTEGER PRIMARY KEY, original_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_prefs
                 (user_id INTEGER PRIMARY KEY, custom_name TEXT)''')
    conn.commit()
    conn.close()

def db_save_channel(channel_id, name):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR REPLACE INTO active_channels VALUES (?, ?)", (channel_id, name))
    conn.commit()
    conn.close()

def db_get_original_name(channel_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT original_name FROM active_channels WHERE channel_id=?", (channel_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "Active VC"

def db_delete_channel(channel_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM active_channels WHERE channel_id=?", (channel_id,))
    conn.commit()
    conn.close()

def db_is_temp_channel(channel_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT 1 FROM active_channels WHERE channel_id=?", (channel_id,))
    exists = cursor.fetchone()
    conn.close()
    return exists is not None

def db_get_user_name(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT custom_name FROM user_prefs WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def db_set_user_name(user_id, name):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR REPLACE INTO user_prefs VALUES (?, ?)", (user_id, name))
    conn.commit()
    conn.close()

def db_delete_user_name(user_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM user_prefs WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# --- BOT SETUP ---
TARGET_CATEGORY_NAME = "🔊 VOICE LOBBY"
TRIGGER_CHANNEL_NAME = "➕ Create Channel"
AFK_CHANNEL_NAME = "💤 AFK"
FOREVER_ALONE_NAME = "Forever Alone"
LONELY_TIMEOUT = 60

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Memory
server_configs = {}
channel_tasks = {}

# --- UI: ROLE SELECTOR ---
class RoleSelect(Select):
    def __init__(self, channel, bot_member):
        self.target_channel = channel
        roles = channel.guild.roles

        valid_roles = [
            r for r in roles
            if r.name != "@everyone"
            and not r.managed
            and r.position < bot_member.top_role.position
        ]
        valid_roles.sort(key=lambda r: r.position, reverse=True)
        valid_roles = valid_roles[:25]

        options = [
            discord.SelectOption(label=role.name, value=str(role.id), emoji="👥")
            for role in valid_roles
        ]

        if not options:
            options = [discord.SelectOption(label="No valid roles found", value="0")]

        super().__init__(placeholder="Select a role to limit access...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        if role_id == 0:
            return await interaction.response.send_message("No role selected.", ephemeral=True)

        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message("Role not found!", ephemeral=True)

        await self.target_channel.set_permissions(interaction.guild.default_role, connect=False)
        await self.target_channel.set_permissions(role, connect=True)

        await interaction.response.send_message(f"🔒 Channel limited to **{role.name}** only!", ephemeral=True)

class RoleSelectView(View):
    def __init__(self, channel, bot_member):
        super().__init__()
        self.add_item(RoleSelect(channel, bot_member))

# --- UI: MAIN CONTROL PANEL ---
class VoiceControlView(View):
    def __init__(self, voice_channel):
        super().__init__(timeout=None)
        self.voice_channel = voice_channel

    @discord.ui.button(label="🔒 Lock", style=discord.ButtonStyle.danger, custom_id="lock_vc")
    async def lock_button(self, interaction: discord.Interaction, button: Button):
        await self.voice_channel.edit(user_limit=len(self.voice_channel.members))
        await interaction.response.send_message("🔒 **Locked!** (User limit applied)", ephemeral=True)

    @discord.ui.button(label="🔓 Unlock", style=discord.ButtonStyle.success, custom_id="unlock_vc")
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        await self.voice_channel.edit(user_limit=0)
        # We also reset specific overwrites to ensure inheritance restores (optional)
        await self.voice_channel.set_permissions(interaction.guild.default_role, connect=None)
        await interaction.response.send_message("🔓 **Unlocked!**", ephemeral=True)

    @discord.ui.button(label="👥 Role Limit", style=discord.ButtonStyle.primary, custom_id="role_limit_vc")
    async def role_limit_button(self, interaction: discord.Interaction, button: Button):
        bot_member = interaction.guild.get_member(bot.user.id)
        view = RoleSelectView(self.voice_channel, bot_member)
        await interaction.response.send_message("Select a role to allow:", view=view, ephemeral=True)

    @discord.ui.button(label="✏️ Rename", style=discord.ButtonStyle.secondary, custom_id="rename_vc")
    async def rename_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("ℹ️ Right Click channel > Edit Channel!", ephemeral=True)

# --- NEW: ADMIN COMMANDS ---

@bot.command()
@commands.has_permissions(administrator=True)
async def create_lobby(ctx, category_name: str, role: discord.Role = None):
    """
    Creates a new Voice Lobby.
    Usage: !create_lobby "VIP Lounge" @VIP
    If a role is provided, the lobby is private to that role.
    """
    guild = ctx.guild

    # 1. Define Permissions
    overwrites = {}
    if role:
        # Private Lobby Logic: Deny everyone, Allow Role
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            role: discord.PermissionOverwrite(view_channel=True, connect=True)
        }
        msg = f"✅ Created Private Lobby **{category_name}** restricted to {role.mention}!"
    else:
        # Public Lobby Logic
        msg = f"✅ Created Public Lobby **{category_name}**!"

    # 2. Create Category
    category = await guild.create_category(category_name, overwrites=overwrites)

    # 3. Create Trigger Channel
    await guild.create_voice_channel(TRIGGER_CHANNEL_NAME, category=category)

    await ctx.send(msg)

# --- USER PREFERENCE COMMANDS ---

@bot.command()
async def setname(ctx, *, name: str):
    """
    Sets your permanent custom voice channel name.
    Usage: !setname The Batcave
    """
    if len(name) > 30:
        return await ctx.send("❌ Name is too long! (Max 30 chars)")

    db_set_user_name(ctx.author.id, name)
    await ctx.send(f"✅ Your channel name is now set to: **🔊 {name}**\n(It will appear next time you create a channel)")

@bot.command()
async def resetname(ctx):
    """Resets your voice channel name to default (User's VC)."""
    db_delete_user_name(ctx.author.id)
    await ctx.send("✅ Custom name removed. Back to default!")

# --- CHAOS COMMANDS ---
@bot.command()
async def roulette(ctx):
    if not ctx.author.voice: return await ctx.send("❌ Join voice first!")
    await ctx.send("🔫 *Spinning...*")
    await asyncio.sleep(1.5)
    if random.randint(1, 6) == 1:
        await ctx.author.move_to(None)
        await ctx.send(f"💥 **BANG!** {ctx.author.mention} dead.")
    else:
        await ctx.send(f"😰 *Click.* Safe.")

@bot.command()
async def flip(ctx):
    await ctx.send(random.choice(["🪙 **Heads!**", "🦅 **Tails!**"]))

@bot.command()
async def bonk(ctx, member: discord.Member):
    if not member.voice: return await ctx.send("Target not in voice!")
    afk = ctx.guild.afk_channel
    if not afk: return await ctx.send("No AFK channel!")
    original = member.voice.channel
    await ctx.send(f"🔨 **BONK!** {member.mention}")
    try:
        await member.move_to(afk)
        await asyncio.sleep(0.5)
        await member.move_to(original)
    except: await ctx.send("❌ Permission Error.")

@bot.command()
async def ride(ctx, member: discord.Member):
    if not member.voice: return await ctx.send("Target not in voice!")
    original = member.voice.channel
    channels = [c for c in ctx.guild.voice_channels if c != original and c != ctx.guild.afk_channel]
    if len(channels) < 3: return await ctx.send("Not enough channels!")
    await ctx.send(f"🎢 Buckle up {member.mention}!")
    for _ in range(3):
        try:
            await member.move_to(random.choice(channels))
            await asyncio.sleep(0.5)
        except: break
    await member.move_to(original)
    await ctx.send(f"🤢 Done.")

# --- CORE LOGIC ---
async def lonely_task(channel):
    try:
        await asyncio.sleep(LONELY_TIMEOUT)
        channel = channel.guild.get_channel(channel.id)
        if not channel: return
        if len(channel.members) == 1 and channel.name != FOREVER_ALONE_NAME:
            await channel.edit(name=FOREVER_ALONE_NAME)
            print(f"😢 {channel.id} Forever Alone")
    except asyncio.CancelledError:
        pass

async def handle_loneliness(channel, member_count):
    cid = channel.id
    if cid in channel_tasks:
        channel_tasks[cid].cancel()
        del channel_tasks[cid]

    if member_count == 1:
        task = asyncio.create_task(lonely_task(channel))
        channel_tasks[cid] = task
    elif member_count > 1:
        if channel.name == FOREVER_ALONE_NAME:
            original_name = db_get_original_name(cid)
            await channel.edit(name=original_name)

async def ensure_voice_setup(guild):
    """
    Ensures the Default 'VOICE LOBBY' exists.
    (This is just the default public one).
    """
    category = discord.utils.get(guild.categories, name=TARGET_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(TARGET_CATEGORY_NAME)
        print(f"🛠️  Created Default Category '{TARGET_CATEGORY_NAME}'")

    trigger = discord.utils.get(category.voice_channels, name=TRIGGER_CHANNEL_NAME)
    if not trigger:
        trigger = await guild.create_voice_channel(TRIGGER_CHANNEL_NAME, category=category)

    afk_c = discord.utils.get(guild.voice_channels, name=AFK_CHANNEL_NAME)
    if not afk_c:
        afk_c = await guild.create_voice_channel(AFK_CHANNEL_NAME, category=category)
        try: await guild.edit(afk_channel=afk_c, afk_timeout=300)
        except: pass

@bot.event
async def on_ready():
    init_db()
    print(f'Logged in as {bot.user}')
    for guild in bot.guilds:
        await ensure_voice_setup(guild)
    print('--- TRG Manager Ready ---')

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild

    # --- 1. JOIN ANY TRIGGER CHANNEL ---
    # We now detect by NAME, so it works in ANY category (Public, VIP, etc.)
    if after.channel and after.channel.name == TRIGGER_CHANNEL_NAME:

        category = after.channel.category
        custom_name = db_get_user_name(member.id)
        channel_name = f"🔊 {custom_name}" if custom_name else f"🔊 {member.display_name}'s VC"

        # INHERITANCE:
        # We add the Creator, but we do NOT add @everyone overwrites.
        # This means the channel acts like a chameleon:
        # - If created in "VIP Lounge" (Private), new channel is Private.
        # - If created in "Voice Lobby" (Public), new channel is Public.
        overwrites = {
            member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)
        }

        new_channel = await guild.create_voice_channel(channel_name, category=category, overwrites=overwrites)
        await member.move_to(new_channel)

        db_save_channel(new_channel.id, channel_name)
        await handle_loneliness(new_channel, 1)

        view = VoiceControlView(new_channel)
        await new_channel.send(f"Welcome, {member.mention}!", view=view)

    # --- 2. CLEANUP ---
    if before.channel:
        # We rely on the DB to tell us if this channel was created by the bot
        if db_is_temp_channel(before.channel.id):
            if len(before.channel.members) == 0:
                # Cleanup Tasks
                if before.channel.id in channel_tasks:
                    channel_tasks[before.channel.id].cancel()
                    del channel_tasks[before.channel.id]

                db_delete_channel(before.channel.id)
                await before.channel.delete()
            else:
                await handle_loneliness(before.channel, len(before.channel.members))

bot.run(TOKEN)
