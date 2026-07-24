import os
import random
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Status: Operational"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web_server)
    t.start()

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

user_profiles = {}

LOCALIZATION = {
    False: {
        "invalid_die": "Execution error: A valid die must possess at least 2 sides.",
        "die_result": "🎲 Rolled a **{sides}**-sided die. Result: **{result}**",
        "pong": "🏓 Pong! Network Latency: **{latency}ms**",
        "avatar_title": "{name}'s Avatar",
        "lang_updated": "Language preference toggled to **English**.",
        "coin_heads": "Heads",
        "coin_tails": "Tails",
        "coin_result": "🪙 Algorithmic determination result: **{outcome}**",
        "pet_matrix": "Processing affection matrix for {name}",
        "rng_error": "Execution error: Lower bound must be strictly less than upper bound.",
        "rng_result": "🔢 Random Integer Generation result [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Operational limit exceeded: Value must range strictly between 1 and 100.",
        "purge_success": "Operation successful: Terminated {count} message entries.",
        "guild_spec": "Guild Specifications: {name}",
        "guild_id": "Identification Key",
        "guild_owner": "Administrative Owner",
        "guild_members": "Total Membership",
        "ball_title": "🔮 Matrix Response:",
        "user_analysis": "User Analysis: {name}",
        "account_class": "Account Classification",
        "registry_date": "Registry Date",
        "session_init": "Guild Session Initiation"
    },
    True: {
        "invalid_die": "Error de ejecución: Un dado válido debe poseer al menos 2 lados.",
        "die_result": "🎲 Lanzaste un dado de **{sides}** lados. Resultado: **{result}**",
        "pong": "🏓 ¡Pong! Latencia de Red: **{latency}ms**",
        "avatar_title": "Avatar de {name}",
        "lang_updated": "Preferencia de idioma cambiada a **Español**.",
        "coin_heads": "Cara",
        "coin_tails": "Cruz",
        "coin_result": "🪙 Resultado de la determinación algorítmica: **{outcome}**",
        "pet_matrix": "Procesando matriz de afecto para {name}",
        "rng_error": "Error de ejecución: El límite inferior debe ser estrictamente menor que el superior.",
        "rng_result": "🔢 Resultado de la generación de entero aleatorio [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Límite operacional excedido: El valor debe oscilar estrictamente entre 1 y 100.",
        "purge_success": "Operación exitosa: Se terminaron {count} entradas de mensajes.",
        "guild_spec": "Especificaciones del Servidor: {name}",
        "guild_id": "Clave de Identificación",
        "guild_owner": "Propietario Administrativo",
        "guild_members": "Membresía Total",
        "ball_title": "🔮 Respuesta de la Matriz:",
        "user_analysis": "Análisis de Usuario: {name}",
        "account_class": "Clasificación de la Cuenta",
        "registry_date": "Fecha de Registro",
        "session_init": "Inicio de Sesión en el Servidor"
    }
}

def get_string(user_id: int, key: str) -> str:
    is_spanish = user_profiles.get(user_id, False)
    return LOCALIZATION[is_spanish][key]

@bot.event
async def on_ready():
    print(f'Logged in successfully as {bot.user.name}')
    try:
        activity = discord.Activity(type=discord.ActivityType.watching, name="System Performance")
        await bot.change_presence(status=discord.Status.online, activity=activity)
        synced = await bot.tree.sync()
        print(f"Successfully synchronized {len(synced)} application command(s)")
    except Exception as e:
        print(f"Synchronization failure: {e}")
@bot.tree.command(name="switchengesp", description="Toggles your account interaction profile language between English and Español")
async def switchengesp(interaction: discord.Interaction):
    uid = interaction.user.id
    user_profiles[uid] = not user_profiles.get(uid, False)
    response = get_string(uid, "lang_updated")
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name="say", description="Echoes back the specified message text")
@app_commands.describe(message="The message string to be replicated by the bot")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(name="ping", description="Retrieves the current network latency of the application")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    response = get_string(interaction.user.id, "pong").format(latency=latency)
    await interaction.response.send_message(response)

@bot.tree.command(name="roll", description="Simulates rolling a standard or custom multi-sided die")
@app_commands.describe(sides="The total number of sides for the die execution")
async def roll(interaction: discord.Interaction, sides: int = 6):
    uid = interaction.user.id
    if sides < 2:
        await interaction.response.send_message(get_string(uid, "invalid_die"), ephemeral=True)
        return
    result = random.randint(1, sides)
    response = get_string(uid, "die_result").format(sides=sides, result=result)
    await interaction.response.send_message(response)

@bot.tree.command(name="avatar", description="Fetches and displays the profile asset of a designated user")
@app_commands.describe(user="The target user whose profile asset is to be retrieved")
async def avatar(interaction: discord.Interaction, user: discord.User = None):
    target_user = user or interaction.user
    title_str = get_string(interaction.user.id, "avatar_title").format(name=target_user.name)
    embed = discord.Embed(title=title_str, color=0x00a8fc)
    embed.set_image(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Executes a binary randomized determination algorithm")
async def coinflip(interaction: discord.Interaction):
    uid = interaction.user.id
    sides_list = [get_string(uid, "coin_heads"), get_string(uid, "coin_tails")]
    outcome = random.choice(sides_list)
    response = get_string(uid, "coin_result").format(outcome=outcome)
    await interaction.response.send_message(response)

@bot.tree.command(name="petpet", description="Generates a customized petpet animation overlay for a user asset")
@app_commands.describe(user="The targeted user to receive the petpet animation asset")
async def petpet(interaction: discord.Interaction, user: discord.User = None):
    target_user = user or interaction.user
    avatar_url = target_user.display_avatar.with_format("png").url
    petpet_url = f"https://vacefron.nl{avatar_url}"
    title_str = get_string(interaction.user.id, "pet_matrix").format(name=target_user.name)
    embed = discord.Embed(title=title_str, color=0x00a8fc)
    embed.set_image(url=petpet_url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rng", description="Generates a random numerical integer within a specified bound")
@app_commands.describe(min_val="Minimum bound value", max_val="Maximum bound value")
async def rng(interaction: discord.Interaction, min_val: int = 1, max_val: int = 100):
    uid = interaction.user.id
    if min_val >= max_val:
        await interaction.response.send_message(get_string(uid, "rng_error"), ephemeral=True)
        return
    result = random.randint(min_val, max_val)
    response = get_string(uid, "rng_result").format(min_val=min_val, max_val=max_val, result=result)
    await interaction.response.send_message(response)

@bot.tree.command(name="purge", description="Executes a bulk deletion of a specified quantity of recent messages")
@app_commands.describe(limit="The explicit quantity of messages to terminate from the channel history")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, limit: int):
    uid = interaction.user.id
    if limit < 1 or limit > 100:
        await interaction.response.send_message(get_string(uid, "purge_limit"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=limit)
    response = get_string(uid, "purge_success").format(count=len(deleted))
    await interaction.followup.send(response)

@bot.tree.command(name="serverinfo", description="Retrieves comprehensive analytical data regarding the current guild")
async def serverinfo(interaction: discord.Interaction):
    uid = interaction.user.id
    guild = interaction.guild
    embed = discord.Embed(title=get_string(uid, "guild_spec").format(name=guild.name), color=0x00a8fc)
    embed.add_field(name=get_string(uid, "guild_id"), value=guild.id, inline=True)
    embed.add_field(name=get_string(uid, "guild_owner"), value=guild.owner, inline=True)
    embed.add_field(name=get_string(uid, "guild_members"), value=guild.member_count, inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="8ball", description="Queries the algorithmic matrix for a definitive response to a binary query")
@app_commands.describe(question="The explicit query string directed to the application core")
async def eightball(interaction: discord.Interaction, question: str):
    uid = interaction.user.id
    responses = [
        "It is certain.", "Without a doubt.", "You may rely on it.", 
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", 
        "Don't count on it.", "My sources say no.", "Outlook not so good."
    ]
    outcome = random.choice(responses)
    await interaction.response.send_message(f"❓ **Query:** {question}\n{get_string(uid, 'ball_title')} {outcome}")

@bot.tree.command(name="userinfo", description="Extracts structured identity profile analytics of a guild member")
@app_commands.describe(user="The specific member asset to analyze")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    uid = interaction.user.id
    target_user = user or interaction.user
    embed = discord.Embed(title=get_string(uid, "user_analysis").format(name=target_user.name), color=0x00a8fc)
    embed.add_field(name=get_string(uid, "account_class"), value=f"ID: {target_user.id}", inline=False)
    embed.add_field(name=get_string(uid, "registry_date"), value=target_user.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name=get_string(uid, "session_init"), value=target_user.joined_at.strftime("%Y-%m-%d") if target_user.joined_at else "N/A", inline=True)
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

keep_alive()
bot.run(TOKEN)

