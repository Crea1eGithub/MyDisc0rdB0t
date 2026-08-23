import os
import random
import asyncio
from datetime import datetime, timezone, timedelta
from threading import Thread
from collections import defaultdict, deque

from openai import OpenAI
from io import BytesIO

import aiohttp
from PIL import Image

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "Status: Operational"


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    thread = Thread(target=run_web_server, daemon=True)
    thread.start()


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
AI_KEY = os.getenv("AI-KEY")
NIGHT_OWL_KEY = os.getenv("NIGHT-OWL")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not configured. "
        "Create a .env file with DISCORD_TOKEN=your_bot_token"
    )

if not AI_KEY:
    raise RuntimeError(
        "AI-KEY is not configured. "
        "Create a .env file with AI-KEY=your_groq_api_key"
    )

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
AI_MODEL = "openai/gpt-oss-20b"
NIGHT_OWL_PREFIX = "[night-owl=on]"

ai_client = OpenAI(
    api_key=AI_KEY,
    base_url=GROQ_BASE_URL,
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    allowed_contexts=app_commands.AppCommandContext(
        guild=True,
        dm_channel=True,
        private_channel=True,
    ),
)

user_profiles: dict[int, bool] = {}

# Historial de los últimos 15 /ai por canal
ai_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=15))

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
        "query_label": "Query",
        "user_analysis": "User Analysis: {name}",
        "account_class": "Account Classification",
        "registry_date": "Registry Date",
        "session_init": "Guild Session Initiation",
    },
    True: {
        "invalid_die": "Error de ejecución: Un dado válido debe poseer al menos 2 lados.",
        "die_result": "🎲 Lanzaste un dado de **{sides}** lados. Resultado: **{result}**",
        "pong": "🏓 ¡Pong! Latencia de red: **{latency}ms**",
        "avatar_title": "Avatar de {name}",
        "lang_updated": "Preferencia de idioma cambiada a **Español**.",
        "coin_heads": "Cara",
        "coin_tails": "Cruz",
        "coin_result": "🪙 Resultado de la determinación algorítmica: **{outcome}**",
        "pet_matrix": "Procesando matriz de afecto para {name}",
        "rng_error": "Error de ejecución: El límite inferior debe ser estrictamente menor que el superior.",
        "rng_result": "🔢 Resultado de la generación de entero aleatorio [{min_val}-{max_val}]: **{result}**",
        "purge_limit": "Límite operacional excedido: el valor debe estar entre 1 y 100.",
        "purge_success": "Operación exitosa: se eliminaron {count} mensajes.",
        "guild_spec": "Especificaciones del servidor: {name}",
        "guild_id": "Clave de identificación",
        "guild_owner": "Propietario administrativo",
        "guild_members": "Miembros totales",
        "ball_title": "🔮 Respuesta de la matriz:",
        "query_label": "Pregunta",
        "user_analysis": "Análisis de usuario: {name}",
        "account_class": "Clasificación de la cuenta",
        "registry_date": "Fecha de registro",
        "session_init": "Inicio de sesión en el servidor",
    },
}

BALL_RESPONSES = {
    False: [
        "It is certain.",
        "Without a doubt.",
        "You may rely on it.",
        "Reply hazy, try again.",
        "Ask again later.",
        "Better not tell you now.",
        "Don't count on it.",
        "My sources say no.",
        "Outlook not so good.",
        "Yes.",
        "No.",
        "Most likely.",
        "Very doubtful.",
    ],
    True: [
        "Es cierto.",
        "Sin ninguna duda.",
        "Puedes confiar en ello.",
        "Respuesta confusa, intenta de nuevo.",
        "Pregunta más tarde.",
        "Mejor no te lo digo ahora.",
        "No cuentes con ello.",
        "Mis fuentes dicen que no.",
        "Las perspectivas no son buenas.",
        "Sí.",
        "No.",
        "Muy probable.",
        "Muy dudoso.",
    ],
}


def get_string(user_id: int, key: str) -> str:
    is_spanish = user_profiles.get(user_id, False)
    return LOCALIZATION[is_spanish][key]


def parse_night_owl_prompt(raw_prompt: str) -> tuple[bool, str]:
    stripped = raw_prompt.lstrip()
    prefix = NIGHT_OWL_PREFIX
    if stripped.lower().startswith(prefix.lower()):
        cleaned = stripped[len(prefix):].lstrip()
        return True, cleaned
    return False, raw_prompt.strip()


def is_ai_online() -> bool:
    colombia_time = datetime.now(timezone(timedelta(hours=-5)))
    return 6 <= colombia_time.hour < 21


def make_ai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


@bot.event
async def on_ready():
    print(f"Logged in successfully as {bot.user} (ID: {bot.user.id})")

    try:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="System Performance",
        )
        await bot.change_presence(
            status=discord.Status.online,
            activity=activity,
        )

        synced = await bot.tree.sync()
        print(f"Successfully synchronized {len(synced)} application command(s).")

    except Exception as error:
        print(f"Synchronization failure: {error}")


@bot.tree.command(
    name="ai",
    description="Ask the AI between 06:00 and 21:00 (Colombia). Use [night-owl=on] at night.",
)
@app_commands.describe(prompt="What you want to ask the AI.")
async def ai(interaction: discord.Interaction, prompt: str):
    night_owl, clean_prompt = parse_night_owl_prompt(prompt)
    online = is_ai_online()

    if not online and not night_owl:
        await interaction.response.send_message(
            "🤖 AI is currently offline. Available hours: **06:00–21:00**.\n"
            "To ask at night, start your prompt with `[night-owl=on]`.",
            ephemeral=True,
        )
        return

    if not clean_prompt:
        await interaction.response.send_message(
            "Please provide a prompt.",
            ephemeral=True,
        )
        return

    use_night_owl = night_owl and not online
    if use_night_owl:
        if not NIGHT_OWL_KEY:
            await interaction.response.send_message(
                "Night Owl is not configured. Set the `NIGHT-OWL` key in the environment.",
                ephemeral=True,
            )
            return
        client = make_ai_client(NIGHT_OWL_KEY)
    else:
        client = ai_client

    await interaction.response.defer()

    channel_id = interaction.channel.id if interaction.channel else 0
    username = interaction.user.display_name

    history_lines = []
    for entry in ai_history[channel_id]:
        history_lines.append(f"- {entry['user']}: {entry['prompt']}")
    history_text = "\n".join(history_lines) if history_lines else "No previous /ai messages in this channel."

    system_prompt = f"""You are a Discord bot AI assistant.
Your source code is publicly available at: https://github.com/Crea1eGithub/MyDisc0rdB0t

The user who just ran the /ai command is: {username}

Recent /ai history in this chat (last 15 prompts):
{history_text}

Answer clearly and helpfully. You can be casual and match the user's tone when appropriate.
Keep responses reasonably concise unless more detail is requested.
"""

    start_time = asyncio.get_event_loop().time()

    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": clean_prompt},
            ],
            max_tokens=1200,
        )

        answer = completion.choices[0].message.content or "No response generated."

        elapsed = asyncio.get_event_loop().time() - start_time
        thinking_seconds = max(1, round(elapsed))

        ai_history[channel_id].append({
            "user": username,
            "prompt": clean_prompt[:300],
        })

        response_text = (
            f"-# {clean_prompt}\n"
            f"\"Ö\" ahh bot thought for {thinking_seconds} seconds\n"
            f"{answer}"
        )

        if len(response_text) <= 2000:
            await interaction.followup.send(response_text)
        else:
            await interaction.followup.send(
                f"-# {clean_prompt}\n"
                f"\"Ö\" ahh bot thought for {thinking_seconds} seconds"
            )
            for start in range(0, len(answer), 1900):
                await interaction.followup.send(answer[start:start + 1900])

    except Exception as error:
        print(f"AI request failure: {error}")
        await interaction.followup.send(
            "⚠️ The AI service could not process the request right now."
        )


@bot.tree.command(
    name="switchengesp",
    description="Toggle your interaction language between English and Español.",
)
async def switchengesp(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_profiles[user_id] = not user_profiles.get(user_id, False)

    await interaction.response.send_message(
        get_string(user_id, "lang_updated"),
        ephemeral=True,
    )


@bot.tree.command(name="say", description="Echo the specified message.")
@app_commands.describe(message="The message to repeat.")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)


@bot.tree.command(name="ping", description="Show the bot's current latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    response = get_string(interaction.user.id, "pong").format(latency=latency)
    await interaction.response.send_message(response)


@bot.tree.command(name="roll", description="Roll a die with a custom number of sides.")
@app_commands.describe(sides="Number of sides. Minimum: 2.")
async def roll(interaction: discord.Interaction, sides: int = 6):
    user_id = interaction.user.id

    if sides < 2:
        await interaction.response.send_message(
            get_string(user_id, "invalid_die"),
            ephemeral=True,
        )
        return

    result = random.randint(1, sides)
    response = get_string(user_id, "die_result").format(
        sides=sides,
        result=result,
    )
    await interaction.response.send_message(response)


@bot.tree.command(name="avatar", description="Display a user's avatar.")
@app_commands.describe(user="The user whose avatar you want to display.")
async def avatar(
    interaction: discord.Interaction,
    user: discord.User | None = None,
):
    target_user = user or interaction.user

    embed = discord.Embed(
        title=get_string(interaction.user.id, "avatar_title").format(
            name=target_user.name
        ),
        color=0x00A8FC,
    )
    embed.set_image(url=target_user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip", description="Flip a virtual coin.")
async def coinflip(interaction: discord.Interaction):
    user_id = interaction.user.id

    outcome = random.choice(
        [
            get_string(user_id, "coin_heads"),
            get_string(user_id, "coin_tails"),
        ]
    )

    response = get_string(user_id, "coin_result").format(outcome=outcome)
    await interaction.response.send_message(response)


@bot.tree.command(
    name="petpet",
    description="Create a Vencord-style PetPet GIF.",
)
@app_commands.describe(
    image="Image attachment to use.",
    url="Direct URL to an image.",
    user="User whose avatar to use.",
    delay="Delay between frames in ms. Minimum 20.",
    resolution="GIF resolution. Default: 128.",
    no_server_pfp="Use the normal avatar instead of the server avatar.",
)
async def petpet(
    interaction: discord.Interaction,
    image: discord.Attachment | None = None,
    url: str | None = None,
    user: discord.User | None = None,
    delay: int = 20,
    resolution: int = 128,
    no_server_pfp: bool = False,
):
    supplied = sum(source is not None for source in (image, url, user))

    if supplied > 1:
        await interaction.response.send_message(
            "Use only one image source: `image`, `url`, or `user`.",
            ephemeral=True,
        )
        return

    if delay < 20:
        await interaction.response.send_message(
            "Delay must be at least **20 ms**.",
            ephemeral=True,
        )
        return

    delay = round(delay / 10) * 10
    resolution = max(32, min(resolution, 512))

    if supplied == 0:
        user = interaction.user

    await interaction.response.defer()

    try:
        if image is not None:
            if not image.content_type or not image.content_type.startswith("image/"):
                raise ValueError("The attachment must be an image.")
            image_bytes = await image.read()

        elif url is not None:
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError("The image URL must start with http:// or https://.")

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise ValueError(f"Could not download the image (HTTP {response.status}).")
                    image_bytes = await response.read()

        else:
            target = user or interaction.user
            avatar_url = target.display_avatar.with_format("png").url

            if interaction.guild is not None and not no_server_pfp:
                member = interaction.guild.get_member(target.id)
                if member is not None:
                    avatar_url = member.display_avatar.with_format("png").url

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(avatar_url) as response:
                    if response.status != 200:
                        raise ValueError(f"Could not download the avatar (HTTP {response.status}).")
                    image_bytes = await response.read()

        avatar = Image.open(BytesIO(image_bytes)).convert("RGBA")

        frame_urls = [
            f"https://raw.githubusercontent.com/VenPlugs/petpet/main/frames/pet{i}.gif"
            for i in range(10)
        ]

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async def fetch_frame(frame_url: str) -> bytes:
                async with session.get(frame_url) as response:
                    if response.status != 200:
                        raise ValueError(f"Could not download PetPet frame (HTTP {response.status}).")
                    return await response.read()

            frame_bytes = await asyncio.gather(
                *(fetch_frame(frame_url) for frame_url in frame_urls)
            )

        pet_frames = []
        for data in frame_bytes:
            frame_image = Image.open(BytesIO(data))
            frame_image.seek(0)
            pet_frames.append(
                frame_image.convert("RGBA").resize(
                    (resolution, resolution),
                    Image.Resampling.LANCZOS,
                )
            )

        output_frames = []

        for i, hand_frame in enumerate(pet_frames):
            j = i if i < 5 else 10 - i

            width = 0.8 + j * 0.02
            height = 0.8 - j * 0.05
            offset_x = (1 - width) * 0.5 + 0.1
            offset_y = 1 - height - 0.08

            canvas = Image.new(
                "RGBA",
                (resolution, resolution),
                (0, 0, 0, 0),
            )

            resized_avatar = avatar.resize(
                (
                    max(1, round(width * resolution)),
                    max(1, round(height * resolution)),
                ),
                Image.Resampling.LANCZOS,
            )

            canvas.alpha_composite(
                resized_avatar,
                (
                    round(offset_x * resolution),
                    round(offset_y * resolution),
                ),
            )
            canvas.alpha_composite(hand_frame)

            output_frames.append(canvas)

        gif_buffer = BytesIO()
        output_frames[0].save(
            gif_buffer,
            format="GIF",
            save_all=True,
            append_images=output_frames[1:],
            duration=delay,
            loop=0,
            disposal=2,
            optimize=False,
        )
        gif_buffer.seek(0)

        await interaction.followup.send(
            file=discord.File(gif_buffer, filename="petpet.gif")
        )

    except Exception as error:
        print(f"PetPet failure: {error}")
        await interaction.followup.send(
            "⚠️ PetPet could not generate the GIF. "
            f"Reason: `{error}`"
        )


@bot.tree.command(name="rng", description="Generate a random integer in a range.")
@app_commands.describe(
    min_val="Minimum value.",
    max_val="Maximum value.",
)
async def rng(
    interaction: discord.Interaction,
    min_val: int = 1,
    max_val: int = 100,
):
    user_id = interaction.user.id

    if min_val >= max_val:
        await interaction.response.send_message(
            get_string(user_id, "rng_error"),
            ephemeral=True,
        )
        return

    result = random.randint(min_val, max_val)
    response = get_string(user_id, "rng_result").format(
        min_val=min_val,
        max_val=max_val,
        result=result,
    )
    await interaction.response.send_message(response)


@bot.tree.command(
    name="purge",
    description="Delete up to 100 recent messages.",
)
@app_commands.describe(limit="Number of messages to delete (1-100).")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, limit: int):
    user_id = interaction.user.id

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    if not 1 <= limit <= 100:
        await interaction.response.send_message(
            get_string(user_id, "purge_limit"),
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=limit)
        response = get_string(user_id, "purge_success").format(
            count=len(deleted)
        )
        await interaction.followup.send(response)
    except (discord.Forbidden, discord.HTTPException) as error:
        await interaction.followup.send(
            f"Could not delete messages: {error}"
        )


@purge.error
async def purge_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You need the **Manage Messages** permission to use this command."
    else:
        message = "An error occurred while executing `/purge`."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(
    name="serverinfo",
    description="Display information about the current server.",
)
async def serverinfo(interaction: discord.Interaction):
    user_id = interaction.user.id
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=get_string(user_id, "guild_spec").format(name=guild.name),
        color=0x00A8FC,
    )

    embed.add_field(
        name=get_string(user_id, "guild_id"),
        value=str(guild.id),
        inline=True,
    )
    embed.add_field(
        name=get_string(user_id, "guild_owner"),
        value=str(guild.owner) if guild.owner else "Unknown",
        inline=True,
    )
    embed.add_field(
        name=get_string(user_id, "guild_members"),
        value=str(guild.member_count),
        inline=True,
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="8ball",
    description="Ask the virtual 8-ball a question.",
)
@app_commands.describe(question="Your question.")
async def eightball(interaction: discord.Interaction, question: str):
    user_id = interaction.user.id
    is_spanish = user_profiles.get(user_id, False)
    responses = BALL_RESPONSES[is_spanish]
    outcome = random.choice(responses)

    query_label = get_string(user_id, "query_label")
    ball_title = get_string(user_id, "ball_title")

    await interaction.response.send_message(
        f"❓ **{query_label}:** {question}\n"
        f"{ball_title} {outcome}"
    )


@bot.tree.command(
    name="userinfo",
    description="Display information about a server member.",
)
@app_commands.describe(user="The member to inspect.")
async def userinfo(
    interaction: discord.Interaction,
    user: discord.User | None = None,
):
    user_id = interaction.user.id
    target_user = user or interaction.user

    embed = discord.Embed(
        title=get_string(user_id, "user_analysis").format(
            name=target_user.name
        ),
        color=0x00A8FC,
    )

    embed.add_field(
        name=get_string(user_id, "account_class"),
        value=f"ID: {target_user.id}",
        inline=False,
    )
    embed.add_field(
        name=get_string(user_id, "registry_date"),
        value=target_user.created_at.strftime("%Y-%m-%d"),
        inline=True,
    )
    embed.add_field(
        name=get_string(user_id, "session_init"),
        value=(
            target_user.joined_at.strftime("%Y-%m-%d")
            if isinstance(target_user, discord.Member) and target_user.joined_at
            else "N/A"
        ),
        inline=True,
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
