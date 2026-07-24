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

user_languages = {}

LOCALIZATION = {
    "en": {
        "invalid_die": "Execution error: A valid die must possess at least 2 sides.",
        "die_result": "🎲 Rolled a **{sides}**-sided die. Result: **{result}**",
        "pong": "🏓 Pong! Network Latency: **{latency}ms**",
        "avatar_title": "{name}'s Avatar",
        "lang_updated": "Language preference updated successfully to **English**.",
        "coin_heads": "Heads",
        "coin_tails": "Tails",
        "coin_result": "🪙 Algorithmic determination result: **{outcome}**",
        "pet_matrix": "Processing affection matrix for {name}",
        "rng_error": "Execution error: Lower bound must be strictly less than upper bound.",
        "rng_result": "🔢 Random Integer Generation result [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Operational limit exceeded: Value must range strictly between 1 and 100.",
        "purge_success": "Operation successful: Terminated {count} message entries."
    },
    "es": {
        "invalid_die": "Error de ejecución: Un dado válido debe poseer al menos 2 lados.",
        "die_result": "🎲 Lanzaste un dado de **{sides}** lados. Resultado: **{result}**",
        "pong": "🏓 ¡Pong! Latencia de Red: **{latency}ms**",
        "avatar_title": "Avatar de {name}",
        "lang_updated": "Preferencia de idioma actualizada correctamente a **Español**.",
        "coin_heads": "Cara",
        "coin_tails": "Cruz",
        "coin_result": "🪙 Resultado de la determinación algorítmica: **{outcome}**",
        "pet_matrix": "Procesando matriz de afecto para {name}",
        "rng_error": "Error de ejecución: El límite inferior debe ser estrictamente menor que el superior.",
        "rng_result": "🔢 Resultado de la generación de entero aleatorio [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Límite operacional excedido: El valor debe oscilar estrictamente entre 1 y 100.",
        "purge_success": "Operación exitosa: Se terminaron {count} entradas de mensajes."
    },
    "ru": {
        "invalid_die": "Ошибка выполнения: Валидный кубик должен иметь минимум 2 грани.",
        "die_result": "🎲 Брошен **{sides}**-гранный кубик. Результат: **{result}**",
        "pong": "🏓 Понг! Сетевая задержка: **{latency}мс**",
        "avatar_title": "Аватар пользователя {name}",
        "lang_updated": "Языковые настройки успешно изменены на **Русский**.",
        "coin_heads": "Орел",
        "coin_tails": "Решка",
        "coin_result": "🪙 Результат алгоритмического определения: **{outcome}**",
        "pet_matrix": "Обработка матрицы привязанности для {name}",
        "rng_error": "Ошибка выполнения: Нижняя граница должна быть строго меньше верхней.",
        "rng_result": "🔢 Результат генерации случайного числа [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Превышен операционный лимит: Значение должно быть строго от 1 до 100.",
        "purge_success": "Операция успешна: Удалено сообщений: {count}."
    },
    "zh": {
        "invalid_die": "執行錯誤：有效的骰子必須至少具有 2 個面。",
        "die_result": "🎲 投擲了 **{sides}** 面骰子。結果：**{result}**",
        "pong": "🏓 乒乓！網路延遲：**{latency}ms**",
        "avatar_title": "{name} 的頭像",
        "lang_updated": "語言偏好已成功更新為 **中國人 (繁體中文)**。",
        "coin_heads": "正面",
        "coin_tails": "反面",
        "coin_result": "🪙 演算法判定結果：**{outcome}**",
        "pet_matrix": "正在處理 {name} 的撫摸矩陣",
        "rng_error": "執行錯誤：下限必須嚴格小於上限。",
        "rng_result": "🔢 隨機整數生成結果 [{min_val}-{max_val}]：**{result}**",
        "purge_limit": "超出操作限制：值必須嚴格介於 1 到 100 之間。",
        "purge_success": "操作成功：已終止 {count} 個訊息項目。"
    },
    "pt": {
        "invalid_die": "Erro de execução: Um dado válido deve possuir pelo menos 2 lados.",
        "die_result": "🎲 Rolou um dado de **{sides}** lados. Resultado: **{result}**",
        "pong": "🏓 Pong! Latência de Rede: **{latency}ms**",
        "avatar_title": "Avatar de {name}",
        "lang_updated": "Preferência de idioma atualizada com sucesso para **Português**.",
        "coin_heads": "Cara",
        "coin_tails": "Coroa",
        "coin_result": "🪙 Resultado da determinação algorítmica: **{outcome}**",
        "pet_matrix": "Processando matriz de afeto para {name}",
        "rng_error": "Erro de execução: O limite inferior deve ser estritamente menor que o limite superior.",
        "rng_result": "🔢 Resultado da geração de número inteiro aleatório [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Limite operacional excedido: O valor deve variar estritamente entre 1 e 100.",
        "purge_success": "Operação bem-sucedida: Foram eliminadas {count} mensagens."
    },
    "de": {
        "invalid_die": "Ausführungsfehler: Ein gültiger Würfel muss mindestens 2 Seiten haben.",
        "die_result": "🎲 Einen **{sides}**-seitigen Würfel gewürfelt. Ergebnis: **{result}**",
        "pong": "🏓 Pong! Netzwerklatenz: **{latency}ms**",
        "avatar_title": "Avatar von {name}",
        "lang_updated": "Spracheinstellung erfolgreich auf **Deutsch** aktualisiert.",
        "coin_heads": "Kopf",
        "coin_tails": "Zahl",
        "coin_result": "🪙 Algorithmisches Bestimmungsergebnis: **{outcome}**",
        "pet_matrix": "Zuneigungsmatrix für {name} wird verarbeitet",
        "rng_error": "Ausführungsfehler: Die untere Grenze muss strikt kleiner als die obere Grenze sein.",
        "rng_result": "🔢 Ergebnis der Zufallszahlengenerierung [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Betriebslimit überschritten: Der Wert muss strikt zwischen 1 und 100 liegen.",
        "purge_success": "Operation erfolgreich: {count} Nachrichteneinträge gelöscht."
    }
}

def get_string(user_id: int, key: str) -> str:
    lang = user_languages.get(user_id, "en")
    return LOCALIZATION[lang][key]

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

@bot.tree.command(name="setbotlanguage", description="Configures the localized language preference for your account interaction profile")
@app_commands.describe(language="Select the target operational language")
@app_commands.choices(language=[
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Español", value="es"),
    app_commands.Choice(name="Русский", value="ru"),
    app_commands.Choice(name="中國人", value="zh"),
    app_commands.Choice(name="Português", value="pt"),
    app_commands.Choice(name="Deutsch", value="de")
])
async def setbotlanguage(interaction: discord.Interaction, language: app_commands.Choice[str]):
    user_languages[interaction.user.id] = language.value
    response = get_string(interaction.user.id, "lang_updated")
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
    avatar_url = target_user.display_avatar.with_format("png").urlpetpet_url = f"vacefron.nl{avatar_url}"
    title_str = get_string(interaction.user.id, "pet_matrix").format(name=target_user.name)embed = discord.Embed(title=title_str, color=0x00a8fc)
    embed.set_image(url=petpet_url)
    await interaction.response.send_message(embed=embed)
    
@bot.tree.command(name="rng", description="Generates a random numerical integer within a specified bound")
@app_commands.describe(min_val="Minimum bound value", max_val="Maximum bound value")
async def rng(interaction: discord.Interaction, min_val: int = 1, max_val: int = 100):uid = interaction.user.id
    if min_val >= max_val:
        await interaction.response.send_message(get_string(uid, "rng_error"), ephemeral=True)return
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
keep_alive()
bot.run(TOKEN)
