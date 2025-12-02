import discord
import os
import asyncio
import sqlite3
from discord.ext import commands
from discord.ui import Button, View
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
TOKEN = os.getenv('DISCORD_TOKEN')

# --- DATABASE SETUP ---
DB_NAME = os.getenv('DB_PATH', 'trg.db')

def init_db():
    """Initializes the SQLite database with necessary tables."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Table 1: Stores active temp channels and their original names (for Forever Alone logic)
    c.execute('''CREATE TABLE IF NOT EXISTS active_channels
                 (channel_id INTEGER PRIMARY KEY, original_name TEXT)''')

    # Table 2: Stores user preferences (Custom Names)
    c.execute('''CREATE TABLE IF NOT EXISTS user_prefs
                 (user_id INTEGER PRIMARY KEY, custom_name TEXT)''')

    conn.commit()
    conn.close()

# Database Helpers
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

def db_get_user_name(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT custom_name FROM user_prefs WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# Seed initial data (Optional: for your manual mapping)
def seed_custom_names():
    # You can move your hardcoded map here once, or add a command !setname later
    initial_map = {
       # 123456789012345678: "Moro's Den",
    }
    conn = sqlite3.connect(DB_NAME)
    for uid, name in initial_map.items():
        conn.execute("INSERT OR IGNORE INTO user_prefs VALUES (?, ?)", (uid, name))
    conn.commit()
    conn.close()


# --- BOT SETUP ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Memory (Still used for tasks, as tasks are transient)
server_configs = {}
channel_tasks = {}

# Constants
TARGET_CATEGORY_NAME = "🔊 VOICE LOBBY"
TRIGGER_CHANNEL_NAME = "➕ Create Channel"
AFK_CHANNEL_NAME = "💤 AFK"
FOREVER_ALONE_NAME = "Forever Alone"
LONELY_TIMEOUT = 60

# --- BUTTONS ---
class VoiceControlView(View):
    def __init__(self, voice_channel):
        super().__init__(timeout=None)
        self.voice_channel = voice_channel

    @discord.ui.button(label="🔒 Lock", style=discord.ButtonStyle.danger, custom_id="lock_vc")
    async def lock_button(self, interaction: discord.Interaction, button: Button):
        await self.voice_channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 **Locked!**", ephemeral=True)

    @discord.ui.button(label="🔓 Unlock", style=discord.ButtonStyle.success, custom_id="unlock_vc")
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        await self.voice_channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 **Unlocked!**", ephemeral=True)

    @discord.ui.button(label="✏️ Rename", style=discord.ButtonStyle.secondary, custom_id="rename_vc")
    async def rename_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("ℹ️ Right Click channel > Edit Channel!", ephemeral=True)

# --- LOGIC ---
async def lonely_task(channel):
    try:
        await asyncio.sleep(LONELY_TIMEOUT)
        channel = channel.guild.get_channel(channel.id)
        if not channel: return

        if len(channel.members) == 1 and channel.name != FOREVER_ALONE_NAME:
            # We don't need to save name here, it was saved on creation
            await channel.edit(name=FOREVER_ALONE_NAME)
            print(f"😢 {channel.id} is now Forever Alone")

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
            # RESTORE FROM DB (Safe against restarts)
            original_name = db_get_original_name(cid)
            await channel.edit(name=original_name)
            print(f"🥳 {original_name} restored from DB!")

async def ensure_voice_setup(guild):
    category = discord.utils.get(guild.categories, name=TARGET_CATEGORY_NAME)
    if not category: category = await guild.create_category(TARGET_CATEGORY_NAME)

    trigger = discord.utils.get(category.voice_channels, name=TRIGGER_CHANNEL_NAME)
    if not trigger: trigger = await guild.create_voice_channel(TRIGGER_CHANNEL_NAME, category=category)

    afk_c = discord.utils.get(guild.voice_channels, name=AFK_CHANNEL_NAME)
    if not afk_c:
        afk_c = await guild.create_voice_channel(AFK_CHANNEL_NAME, category=category)
        try: await guild.edit(afk_channel=afk_c, afk_timeout=300)
        except: pass

    server_configs[guild.id] = {'category_id': category.id, 'trigger_id': trigger.id}
    return server_configs[guild.id]

# --- EVENTS ---
@bot.event
async def on_ready():
    init_db()
    seed_custom_names()
    print(f'Logged in as {bot.user}')

    for guild in bot.guilds:
        await ensure_voice_setup(guild)

        # Crash Recovery: Check for stuck "Forever Alone" channels
        # If bot crashed while timer was running, we restart the logic for any existing channels
        config = server_configs[guild.id]
        category = guild.get_channel(config['category_id'])
        if category:
            for channel in category.voice_channels:
                if channel.id != config['trigger_id'] and channel.name != AFK_CHANNEL_NAME:
                    # It's a temp channel, resume monitoring
                    if len(channel.members) == 1:
                        await handle_loneliness(channel, 1)

    print('--- TRG Manager Ready & DB Connected ---')

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    if guild.id not in server_configs: await ensure_voice_setup(guild)

    config = server_configs[guild.id]
    trigger_id = config['trigger_id']
    category_id = config['category_id']

    # JOIN TRIGGER
    if after.channel and after.channel.id == trigger_id:
        category = guild.get_channel(category_id)

        # Check DB for custom name
        custom_name = db_get_user_name(member.id)
        if custom_name:
            channel_name = f"🔊 {custom_name}"
        else:
            channel_name = f"🔊 {member.display_name}'s VC"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)
        }

        new_channel = await guild.create_voice_channel(channel_name, category=category, overwrites=overwrites)
        await member.move_to(new_channel)

        # SAVE TO DB
        db_save_channel(new_channel.id, channel_name)

        await handle_loneliness(new_channel, 1)
        view = VoiceControlView(new_channel)
        await new_channel.send(f"Welcome, {member.mention}!", view=view)

    # UPDATE EXISTING
    if after.channel and after.channel.category_id == category_id and after.channel.id != trigger_id:
        await handle_loneliness(after.channel, len(after.channel.members))

    if before.channel and before.channel.category_id == category_id and before.channel.id != trigger_id:
        if len(before.channel.members) == 0:
            if before.channel.id in channel_tasks:
                channel_tasks[before.channel.id].cancel()
                del channel_tasks[before.channel.id]

            # REMOVE FROM DB
            db_delete_channel(before.channel.id)
            await before.channel.delete()
        else:
            await handle_loneliness(before.channel, len(before.channel.members))

bot.run(TOKEN)
