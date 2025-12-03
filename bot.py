import discord
import os
import asyncio
import sqlite3
import random
import traceback
import sys
import re
from discord.ext import commands
from discord.ui import Button, View, Select
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
TOKEN = os.getenv('DISCORD_TOKEN')
MOD_CHANNEL_ID = os.getenv('MOD_CHANNEL_ID')
DB_NAME = os.getenv('DB_PATH', 'trg.db')

# --- CONSTANTS ---
TARGET_CATEGORY_NAME = "🔊 VOICE LOBBY"
TRIGGER_CHANNEL_NAME = "➕ Create Channel"
AFK_CHANNEL_NAME = "💤 AFK"
FOREVER_ALONE_NAME = "Forever Alone"
LONELY_TIMEOUT = 60

# --- DATABASE SETUP (ISOLATED PER GUILD) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS active_channels
                 (channel_id INTEGER PRIMARY KEY, guild_id INTEGER, original_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_prefs
                 (user_id INTEGER, guild_id INTEGER, custom_name TEXT,
                 PRIMARY KEY (user_id, guild_id))''')
    conn.commit()
    conn.close()

def db_save_channel(channel_id, guild_id, name):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR REPLACE INTO active_channels VALUES (?, ?, ?)", (channel_id, guild_id, name))
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

def db_get_user_name(user_id, guild_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT custom_name FROM user_prefs WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def db_set_user_name(user_id, guild_id, name):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR REPLACE INTO user_prefs VALUES (?, ?, ?)", (user_id, guild_id, name))
    conn.commit()
    conn.close()

def db_delete_user_name(user_id, guild_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM user_prefs WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    conn.commit()
    conn.close()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

channel_tasks = {}

# --- ERROR HANDLING ---
async def log_error(error, ctx=None, extra_info=None):
    if not MOD_CHANNEL_ID: return
    try:
        channel = bot.get_channel(int(MOD_CHANNEL_ID))
        if not channel: return

        embed = discord.Embed(title="⚠️ Bot Error", color=discord.Color.red())
        if ctx:
            embed.add_field(name="Command", value=ctx.command.name if ctx.command else "Unknown", inline=True)
            embed.add_field(name="User", value=f"{ctx.author} ({ctx.author.id})", inline=True)
            embed.add_field(name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})", inline=True)
        if extra_info:
            embed.add_field(name="Context", value=extra_info, inline=False)

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        if len(tb) > 1000: tb = tb[:1000] + "..."
        embed.description = f"```python\n{tb}\n```"
        await channel.send(embed=embed)
    except Exception as e:
        print(f"❌ Failed to log error: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to do that.", delete_after=5)
        return
    await ctx.send("❌ Something went wrong.", delete_after=5)
    await log_error(error, ctx)
    print(f"Command Error: {error}")

# --- UI CLASSES ---
class RoleSelect(Select):
    def __init__(self, channel, bot_member):
        self.target_channel = channel
        roles = channel.guild.roles
        valid_roles = [r for r in roles if r.name != "@everyone" and not r.managed and r.position < bot_member.top_role.position]
        valid_roles.sort(key=lambda r: r.position, reverse=True)
        valid_roles = valid_roles[:25]
        options = [discord.SelectOption(label=role.name, value=str(role.id), emoji="👥") for role in valid_roles]
        if not options: options = [discord.SelectOption(label="No valid roles found", value="0")]
        super().__init__(placeholder="Select a role to limit access...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        if role_id == 0: return await interaction.response.send_message("No role selected.", ephemeral=True)
        role = interaction.guild.get_role(role_id)
        if not role: return await interaction.response.send_message("Role not found!", ephemeral=True)
        try:
            await self.target_channel.set_permissions(interaction.guild.default_role, connect=False)
            await self.target_channel.set_permissions(role, connect=True)
            await interaction.response.send_message(f"🔒 Channel limited to **{role.name}** only!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Failed to update permissions.", ephemeral=True)

class RoleSelectView(View):
    def __init__(self, channel, bot_member):
        super().__init__()
        self.add_item(RoleSelect(channel, bot_member))

class VoiceControlView(View):
    def __init__(self, voice_channel):
        super().__init__(timeout=None)
        self.voice_channel = voice_channel

    @discord.ui.button(label="🔒 Lock", style=discord.ButtonStyle.danger, custom_id="lock_vc")
    async def lock_button(self, interaction: discord.Interaction, button: Button):
        await self.voice_channel.edit(user_limit=len(self.voice_channel.members))
        await interaction.response.send_message("🔒 **Locked!**", ephemeral=True)

    @discord.ui.button(label="🔓 Unlock", style=discord.ButtonStyle.success, custom_id="unlock_vc")
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        await self.voice_channel.edit(user_limit=0)
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

# --- ADMIN COMMANDS ---
@bot.command()
@commands.has_permissions(administrator=True)
async def create_lobby(ctx, category_name: str, role: discord.Role = None):
    """Creates a new Voice Lobby."""
    guild = ctx.guild
    overwrites = {}
    if role:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            role: discord.PermissionOverwrite(view_channel=True, connect=True)
        }
        msg = f"✅ Created Private Lobby **{category_name}** restricted to {role.mention}!"
    else:
        msg = f"✅ Created Public Lobby **{category_name}**!"

    try:
        category = await guild.create_category(category_name, overwrites=overwrites)
        await guild.create_voice_channel(TRIGGER_CHANNEL_NAME, category=category)
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ Failed to create lobby.")
        await log_error(e, ctx)

# --- USER PREFERENCE COMMANDS (FIXED) ---

@bot.command()
async def setname(ctx, *, user_input: str):
    """
    Sets a custom VC name.
    Usage: !setname My Cool Room
    Admin Usage: !setname @User User's Room
    """
    target = ctx.author
    name_to_set = user_input

    # 1. Admin Override Check (Mention Detection)
    if ctx.message.mentions:
        if ctx.author.guild_permissions.administrator:
            target = ctx.message.mentions[0]
            # Remove the mention from the string to get the actual name
            name_to_set = re.sub(r'<@!?\d+>', '', user_input).strip()
        else:
            return await ctx.send("❌ Only Admins can set names for other users.")

    # 2. Quote Cleanup: "Name" -> Name
    if name_to_set.startswith('"') and name_to_set.endswith('"'):
        name_to_set = name_to_set[1:-1].strip()

    # 3. Validation
    if len(name_to_set) > 30:
        return await ctx.send(f"❌ Name is too long! ({len(name_to_set)}/30 chars)")
    if len(name_to_set) == 0:
        return await ctx.send("❌ Please provide a name!")

    # 4. Save
    db_set_user_name(target.id, ctx.guild.id, name_to_set)
    await ctx.send(f"✅ Set **{target.display_name}'s** channel name to: **🔊 {name_to_set}**")

@bot.command()
async def resetname(ctx, member: discord.Member = None):
    """Resets custom VC name."""
    target = ctx.author
    if member and ctx.author.guild_permissions.administrator:
        target = member

    db_delete_user_name(target.id, ctx.guild.id)
    await ctx.send(f"✅ Reset custom name for **{target.display_name}**.")

# --- CHAOS COMMANDS ---
@bot.command()
async def roulette(ctx):
    if not ctx.author.voice: return await ctx.send("❌ Join voice first!")
    await ctx.send("🔫 *Spinning...*")
    await asyncio.sleep(1.5)
    if random.randint(1, 6) == 1:
        try:
            await ctx.author.move_to(None)
            await ctx.send(f"💥 **BANG!** {ctx.author.mention} dead.")
        except: await ctx.send("❌ Gun jammed.")
    else: await ctx.send(f"😰 *Click.* Safe.")

@bot.command()
async def flip(ctx):
    await ctx.send(random.choice(["🪙 **Heads!**", "🦅 **Tails!**"]))

@bot.command()
async def bonk(ctx, member: discord.Member):
    try: await ctx.message.delete()
    except: pass
    if not member.voice: return await ctx.send("Target not in voice!", delete_after=5)
    afk = ctx.guild.afk_channel
    if not afk: return await ctx.send("No AFK channel!", delete_after=5)
    original = member.voice.channel
    await ctx.send(f"🔨 **BONK!** {member.mention}")
    try:
        await member.move_to(afk)
        await asyncio.sleep(0.5)
        await member.move_to(original)
    except: await ctx.send("❌ Permission Error.", delete_after=5)

@bot.command()
async def ride(ctx, member: discord.Member):
    try: await ctx.message.delete()
    except: pass
    if not member.voice: return await ctx.send("Target not in voice!", delete_after=5)
    original = member.voice.channel
    channels = [c for c in ctx.guild.voice_channels if c != original and c != ctx.guild.afk_channel]
    if len(channels) < 3: return await ctx.send("Not enough channels!", delete_after=5)
    await ctx.send(f"🎢 Buckle up {member.mention}!")
    for _ in range(3):
        try:
            await member.move_to(random.choice(channels))
            await asyncio.sleep(0.5)
        except: break
    await member.move_to(original)
    await ctx.send(f"🤢 Done.")

@bot.command()
async def mimic(ctx, member: discord.Member):
    try: await ctx.message.delete()
    except: pass
    try:
        original_name = member.display_name
        await ctx.guild.me.edit(nick=original_name)
        await ctx.send(f"👀 Look at me, I am the real {member.mention} now.")
        await asyncio.sleep(120)
        await ctx.guild.me.edit(nick=None)
    except: await ctx.send("❌ I can't change my nickname.", delete_after=5)

@bot.command()
async def lag(ctx, member: discord.Member):
    try: await ctx.message.delete()
    except: pass
    if not member.voice: return await ctx.send("Target not in voice!", delete_after=5)
    afk = ctx.guild.afk_channel
    if not afk: return await ctx.send("No AFK channel!", delete_after=5)
    original = member.voice.channel
    await ctx.send(f"📶 Creating artificial lag for {member.mention}...")
    for _ in range(3):
        try:
            await member.move_to(afk)
            await asyncio.sleep(0.2)
            await member.move_to(original)
            await asyncio.sleep(0.2)
        except: break
    await ctx.send("📶 Connection restored... mostly.")

@bot.command()
async def mute_roulette(ctx):
    try: await ctx.message.delete()
    except: pass
    if not ctx.author.voice: return await ctx.send("❌ Join voice first!", delete_after=5)
    victims = [m for m in ctx.author.voice.channel.members if not m.bot]
    if not victims: return await ctx.send("No valid targets!", delete_after=5)
    victim = random.choice(victims)
    try:
        await victim.edit(mute=True)
        await ctx.send(f"🙊 **MUTE ROULETTE!** {victim.mention} silenced for 30s.")
        await asyncio.sleep(30)
        await victim.edit(mute=False)
        await ctx.send(f"🗣️ {victim.mention} can speak.")
    except: await ctx.send("❌ I need Mute permissions.", delete_after=5)

# --- CORE LOGIC ---
async def lonely_task(channel):
    try:
        await asyncio.sleep(LONELY_TIMEOUT)
        channel = channel.guild.get_channel(channel.id)
        if not channel: return
        if len(channel.members) == 1 and channel.name != FOREVER_ALONE_NAME:
            await channel.edit(name=FOREVER_ALONE_NAME)
            print(f"😢 {channel.id} Forever Alone")
    except asyncio.CancelledError: pass
    except Exception as e: await log_error(e, extra_info=f"Lonely Task {channel.id}")

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
    try:
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
    except Exception as e:
        print(f"Failed setup {guild.name}: {e}")
        await log_error(e, extra_info=f"Setup {guild.name}")

@bot.event
async def on_ready():
    init_db()
    print(f'Logged in as {bot.user}')
    for guild in bot.guilds: await ensure_voice_setup(guild)
    print('--- TRG Manager Ready ---')

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    if after.channel and after.channel.name == TRIGGER_CHANNEL_NAME:
        try:
            category = after.channel.category
            custom_name = db_get_user_name(member.id, guild.id)
            channel_name = f"🔊 {custom_name}" if custom_name else f"🔊 {member.display_name}'s VC"
            overwrites = {member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)}
            new_channel = await guild.create_voice_channel(channel_name, category=category, overwrites=overwrites)
            await member.move_to(new_channel)
            db_save_channel(new_channel.id, guild.id, channel_name)
            await handle_loneliness(new_channel, 1)
            view = VoiceControlView(new_channel)
            await new_channel.send(f"Welcome, {member.mention}!", view=view)
        except Exception as e:
            print(f"Create Error: {e}")
            await log_error(e, extra_info=f"Voice Create {member.name}")

    if before.channel:
        try:
            if db_is_temp_channel(before.channel.id):
                if len(before.channel.members) == 0:
                    if before.channel.id in channel_tasks:
                        channel_tasks[before.channel.id].cancel()
                        del channel_tasks[before.channel.id]
                    db_delete_channel(before.channel.id)
                    await before.channel.delete()
                else:
                    await handle_loneliness(before.channel, len(before.channel.members))
        except: pass

bot.run(TOKEN)
