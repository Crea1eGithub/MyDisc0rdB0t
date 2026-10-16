import ipaddress
import signal
import socket
import os
import re
import html as html_lib
import json
import random
import asyncio
import hashlib
import time
import traceback
from datetime import datetime, timezone, timedelta
from threading import Thread
from collections import defaultdict, deque
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from openai import OpenAI
from io import BytesIO

import aiohttp
from PIL import Image

Image.MAX_IMAGE_PIXELS = 20_000_000

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "Status: Operational"


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)


def keep_alive():
    thread = Thread(target=run_web_server, daemon=True)
    thread.start()


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
AI_KEY = os.getenv("AI-KEY")
NIGHT_OWL_KEY = os.getenv("NIGHT-OWL")
MEMORY_SUMMARY_KEY = os.getenv("MEMORY-SUMMARY")
APPLICATION_ID = os.getenv("APPLICATION_ID", "1348335637656371330")
PYTHON_ACTIVITY_ID = os.getenv("PYTHON_ACTIVITY_ID", APPLICATION_ID)
PYTHON_ACTIVITY_URL = os.getenv("PYTHON_ACTIVITY_URL")
OPEN_MOUTH_EMOJI = ":open_mouth:"
SEAHORSE_EMOJI = "<:seahorse:1554464159947817091>"

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
AI_MODEL = os.getenv("AI-MODEL", "openai/gpt-oss-20b")
SEARCH_MODEL = os.getenv("SEARCH-MODEL", "openai/gpt-oss-120b")
SUMMARY_MODEL = os.getenv("SUMMARY-MODEL", "openai/gpt-oss-20b")
NIGHT_OWL_PREFIX = "[night-owl=on]"
DEEP_SEARCH_PREFIX = "[deep_search=on]"
HISTORY_LIMIT = 100
RECENT_PROMPT_LIMIT = 8
OLDER_SNIPPET_LIMIT = 10
SNIPPET_CHARS = 72
PROMPT_STORE_CHARS = 160
REPLY_STORE_CHARS = 140
EMOJI_PROMPT_LIMIT = 12
MAX_ANSWER_TOKENS = 800
MAX_SEARCH_TOKENS = 600
STATUS_ROTATE_MINUTES = 8
MEMORY_FILE = os.getenv("MEMORY_FILE", "memory.json")
MEMORY_CHANNEL_ID = os.getenv("MEMORY_CHANNEL_ID")
OWNER_USERNAMES = {
    name.strip().lower()
    for name in os.getenv("OWNER_USERNAMES", "crea1e").split(",")
    if name.strip()
}
OWNER_USER_IDS = {
    int(value)
    for value in os.getenv("OWNER_USER_IDS", "").split(",")
    if value.strip().isdigit()
}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TALK_USER_DAILY_LIMIT = env_int("TALK_USER_DAILY_LIMIT", 12)
TALK_GLOBAL_DAILY_LIMIT = env_int("TALK_GLOBAL_DAILY_LIMIT", 200)
TALK_COOLDOWN_SECONDS = env_int("TALK_COOLDOWN_SECONDS", 15)
SYNC_COMMANDS = os.getenv("SYNC_COMMANDS", "auto").strip().lower()
DISCORD_MEMORY_INTERVAL = max(30, env_int("DISCORD_MEMORY_INTERVAL", 120))

ai_client = OpenAI(
    api_key=AI_KEY,
    base_url=GROQ_BASE_URL,
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    allowed_mentions=discord.AllowedMentions(
        everyone=False,
        roles=False,
        users=True,
        replied_user=False,
    ),
    allowed_contexts=app_commands.AppCommandContext(
        guild=True,
        dm_channel=True,
        private_channel=True,
    ),
)

# Repeating a user's text must not ping anyone.
NO_USER_PINGS = discord.AllowedMentions.none()

user_profiles: dict[int, bool] = {}
ai_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
ai_summaries: dict[int, dict] = {}
talk_usage: dict = {
    "day": "",
    "global": 0,
    "users": {},
    "last": {},
}
_memory_lock: asyncio.Lock | None = None
_quota_lock: asyncio.Lock | None = None
_memory_dirty = False
_discord_memory_loaded = False
command_sync_fingerprint_saved = ""
memory_saved_at = 0.0
BOT_STARTED_AT = time.monotonic()


def get_memory_lock() -> asyncio.Lock:
    global _memory_lock
    if _memory_lock is None:
        _memory_lock = asyncio.Lock()
    return _memory_lock


def get_quota_lock() -> asyncio.Lock:
    global _quota_lock
    if _quota_lock is None:
        _quota_lock = asyncio.Lock()
    return _quota_lock


def memory_payload() -> dict:
    usage = talk_usage if isinstance(talk_usage, dict) else {}
    return {
        "saved_at": memory_saved_at,
        "history": {
            str(channel_id): [dict(entry) for entry in entries]
            for channel_id, entries in ai_history.items()
        },
        "summaries": {
            str(channel_id): {
                "fingerprint": str(data.get("fingerprint", "")),
                "summary": str(data.get("summary", "")),
            }
            for channel_id, data in ai_summaries.items()
            if isinstance(data, dict)
        },
        "talk_usage": {
            "day": str(usage.get("day", "")),
            "global": int(usage.get("global", 0) or 0),
            "users": {
                str(key): int(value)
                for key, value in dict(usage.get("users") or {}).items()
                if str(value).lstrip("-").isdigit()
            },
            "last": {
                str(key): float(value)
                for key, value in dict(usage.get("last") or {}).items()
                if _is_float(value)
            },
        },
        "languages": {
            str(user_id): spanish
            for user_id, spanish in user_profiles.items()
        },
        "command_fingerprint": command_sync_fingerprint_saved,
    }


def _is_float(value) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def apply_memory_payload(payload: dict, source: str) -> None:
    global command_sync_fingerprint_saved, memory_saved_at
    if not isinstance(payload, dict):
        return

    for key, entries in (payload.get("history") or {}).items():
        try:
            channel_id = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(entries, list):
            continue
        cleaned = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            user = str(item.get("user", "unknown"))
            prompt = str(item.get("prompt", ""))[:PROMPT_STORE_CHARS]
            reply = " ".join(str(item.get("reply", "")).split())[:REPLY_STORE_CHARS]
            if prompt:
                entry = {"user": user, "prompt": prompt}
                if reply:
                    entry["reply"] = reply
                cleaned.append(entry)
        ai_history[channel_id] = deque(cleaned, maxlen=HISTORY_LIMIT)

    for key, summary in (payload.get("summaries") or {}).items():
        try:
            channel_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(summary, dict) and summary.get("summary"):
            ai_summaries[channel_id] = {
                "fingerprint": str(summary.get("fingerprint", "")),
                "summary": str(summary.get("summary", "")),
            }

    saved_usage = payload.get("talk_usage")
    if isinstance(saved_usage, dict):
        talk_usage["day"] = str(saved_usage.get("day", ""))
        try:
            talk_usage["global"] = int(saved_usage.get("global", 0))
        except (TypeError, ValueError):
            talk_usage["global"] = 0
        users = saved_usage.get("users") or {}
        last = saved_usage.get("last") or {}
        talk_usage["users"] = {
            str(key): int(value)
            for key, value in users.items()
            if str(value).lstrip("-").isdigit()
        }
        cleaned_last = {}
        for key, value in last.items():
            try:
                cleaned_last[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        talk_usage["last"] = cleaned_last

    for key, spanish in (payload.get("languages") or {}).items():
        if str(key).isdigit() and isinstance(spanish, bool):
            user_profiles[int(key)] = spanish

    saved_fingerprint = payload.get("command_fingerprint")
    if isinstance(saved_fingerprint, str):
        command_sync_fingerprint_saved = saved_fingerprint
    elif str(source).startswith("discord:"):
        command_sync_fingerprint_saved = ""

    try:
        memory_saved_at = float(payload.get("saved_at") or 0)
    except (TypeError, ValueError):
        memory_saved_at = 0.0

    print(
        f"Loaded AI memory: {sum(len(v) for v in ai_history.values())} prompts "
        f"across {len(ai_history)} chats from {source}"
    )


def load_memory() -> None:
    if not os.path.isfile(MEMORY_FILE):
        return
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as error:
        print(f"Memory load failure: {error}")
        return
    apply_memory_payload(payload, MEMORY_FILE)


def dump_memory(payload: dict) -> None:
    directory = os.path.dirname(os.path.abspath(MEMORY_FILE))
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = MEMORY_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(temp_path, MEMORY_FILE)


def memory_channel_id() -> int | None:
    if not MEMORY_CHANNEL_ID:
        return None
    try:
        return int(MEMORY_CHANNEL_ID)
    except ValueError:
        print("MEMORY_CHANNEL_ID must be a numeric channel id.")
        return None


async def load_memory_from_discord() -> None:
    channel_id = memory_channel_id()
    if channel_id is None:
        return
    if _memory_dirty:
        print("Skipping Discord memory load; newer changes are still in memory.")
        return
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    async for message in channel.history(limit=30):
        if message.author.id != bot.user.id:
            continue
        attachment = next(
            (item for item in message.attachments if item.filename == "memory.json"),
            None,
        )
        if attachment is None:
            continue
        raw = await attachment.read()
        payload = json.loads(raw.decode("utf-8"))
        remote_saved = 0.0
        if isinstance(payload, dict):
            try:
                remote_saved = float(payload.get("saved_at") or 0)
            except (TypeError, ValueError):
                remote_saved = 0.0
        if memory_saved_at and remote_saved + 1 < memory_saved_at:
            print("Discord memory snapshot is older than the local file. Keeping local memory.")
            return
        apply_memory_payload(payload, f"discord:{channel_id}")
        return
    print("No Discord memory.json found yet. It will be created on the next /talk.")


async def save_memory_to_discord() -> None:
    channel_id = memory_channel_id()
    if channel_id is None:
        return
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    payload = json.dumps(memory_payload(), ensure_ascii=False).encode("utf-8")
    upload = discord.File(BytesIO(payload), filename="memory.json")
    sent = await channel.send(
        content="AI memory snapshot (do not delete this channel).",
        file=upload,
    )
    async for message in channel.history(limit=30):
        if message.id == sent.id or message.author.id != bot.user.id:
            continue
        if not any(item.filename == "memory.json" for item in message.attachments):
            continue
        try:
            await message.delete()
        except Exception:
            break


async def save_memory(*, force_discord: bool = False) -> None:
    global _memory_dirty, memory_saved_at
    async with get_memory_lock():
        memory_saved_at = time.time()
        payload = memory_payload()
        try:
            await asyncio.to_thread(dump_memory, payload)
        except Exception as error:
            print(f"Memory save failure: {error}")
        _memory_dirty = True
        if force_discord:
            await _upload_discord_memory_locked()


async def _upload_discord_memory_locked() -> None:
    global _memory_dirty
    try:
        await save_memory_to_discord()
        _memory_dirty = False
    except Exception as error:
        print(f"Discord memory save failure: {error}")


@tasks.loop(seconds=DISCORD_MEMORY_INTERVAL)
async def flush_discord_memory() -> None:
    if not _memory_dirty or memory_channel_id() is None:
        return
    async with get_memory_lock():
        if _memory_dirty:
            await _upload_discord_memory_locked()


@flush_discord_memory.before_loop
async def before_flush_discord_memory() -> None:
    await bot.wait_until_ready()


load_memory()

FUN_FACTS = [
    "Honey never spoils",
    "Octopuses have three hearts",
    "A day on Venus is longer than its year",
    "Sharks are older than trees",
    "Bananas are berries, strawberries are not",
    "Wombats poop in cubes",
    "Otters hold hands when they sleep",
    "The Eiffel Tower grows in summer",
    "Cats cannot taste sweetness",
    "There are more trees on Earth than stars in the Milky Way",
]
_last_fact: str | None = None

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
        "choose_empty": "Give me at least two options, separated by commas.",
        "choose_result": "🎯 I choose: **{choice}**",
        "say_denied": "Only the bot owner or members with **Manage Messages** can use this command.",
        "say_length": "The message must be between 1 and 2000 characters.",
        "talk_cooldown": "⏳ Wait **{wait}s** before using the AI again.",
        "talk_user_limit": "🚫 You reached today's limit of **{limit}** AI messages. It resets at **00:00 UTC-5**.",
        "talk_global_limit": "🚫 The bot reached today's global AI limit. It resets at **00:00 UTC-5**.",
        "purge_channel": "This command only works in a text channel or thread.",
        "quota_ai_on": "AI is **online** (06:00–21:00 UTC-5).",
        "quota_ai_off": "AI is **offline** until 06:00 UTC-5 (hours: 06:00–21:00).",
        "quota_night_on": "Night Owl is **configured** for after-hours requests.",
        "quota_night_off": "Night Owl is **not configured**.",
        "quota_owner": "Your AI limit: **none** (owner). Bot-wide today: **{global_used}/{global_limit}**.",
        "quota_uses": "Your AI messages today: **{used}/{limit}**. Bot-wide: **{global_used}/{global_limit}**.",
        "quota_wait": "Cooldown: wait **{wait}s**.",
        "quota_ready": "Cooldown: **ready**.",
        "quota_reset": "Counters reset at **00:00 UTC-5**.",
        "quota_uptime": "Uptime: **{uptime}** · latency: **{latency}ms**.",
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
        "choose_empty": "Dame al menos dos opciones, separadas por comas.",
        "choose_result": "🎯 Elijo: **{choice}**",
        "say_denied": "Solo el dueño del bot o quien tenga **Gestionar mensajes** puede usar este comando.",
        "say_length": "El mensaje debe tener entre 1 y 2000 caracteres.",
        "talk_cooldown": "⏳ Espera **{wait}s** antes de volver a usar la IA.",
        "talk_user_limit": "🚫 Llegaste a tu límite de **{limit}** mensajes de IA hoy. Se reinicia a las **00:00 UTC-5**.",
        "talk_global_limit": "🚫 El bot llegó al límite global de IA de hoy. Se reinicia a las **00:00 UTC-5**.",
        "purge_channel": "Este comando solo funciona en un canal de texto o un hilo.",
        "quota_ai_on": "La IA está **en línea** (06:00–21:00 UTC-5).",
        "quota_ai_off": "La IA está **fuera de horario** hasta las 06:00 UTC-5 (horario: 06:00–21:00).",
        "quota_night_on": "Night Owl está **configurado** para usarla fuera de horario.",
        "quota_night_off": "Night Owl **no está configurado**.",
        "quota_owner": "Tu límite de IA: **ninguno** (owner). Total del bot hoy: **{global_used}/{global_limit}**.",
        "quota_uses": "Tus mensajes de IA hoy: **{used}/{limit}**. Total del bot: **{global_used}/{global_limit}**.",
        "quota_wait": "Cooldown: espera **{wait}s**.",
        "quota_ready": "Cooldown: **listo**.",
        "quota_reset": "Los contadores se reinician a las **00:00 UTC-5**.",
        "quota_uptime": "Tiempo activo: **{uptime}** · latencia: **{latency}ms**.",
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
    night_owl, deep_search, clean = strip_prompt_flags(raw_prompt)
    return night_owl, clean


def strip_prompt_flags(raw_prompt: str) -> tuple[bool, bool, str]:
    text = raw_prompt.lstrip()
    night_owl = False
    deep_search = False
    while True:
        match = re.match(r"\[night[-_]?owl\s*=\s*on\]\s*", text, flags=re.IGNORECASE)
        if match:
            night_owl = True
            text = text[match.end():]
            continue
        match = re.match(r"\[deep[-_]?search\s*=\s*on\]\s*", text, flags=re.IGNORECASE)
        if match:
            deep_search = True
            text = text[match.end():]
            continue
        match = re.match(r"\[groq/compound\s*=\s*on\]\s*", text, flags=re.IGNORECASE)
        if match:
            deep_search = True
            text = text[match.end():]
            continue
        match = re.match(r"\[search\]\s*", text, flags=re.IGNORECASE)
        if match:
            text = text[match.end():]
            continue
        break
    return night_owl, deep_search, text.strip()


FRESH_INFO_RE = re.compile(
    r"\b("
    r"202[4-9]|203\d|"
    r"hoy|ahora|actual(?:es|idad|izado)?|reciente(?:mente|s)?|"
    r"este a[nñ]o|noticias?|[uú]ltim[oa]s?|qui[eé]n gan[oó]|"
    r"latest|current|today|tonight|this year|right now|who won|breaking"
    r")\b",
    flags=re.IGNORECASE,
)


def needs_fresh_info(prompt: str) -> bool:
    return bool(FRESH_INFO_RE.search(prompt or ""))


_search_cache: dict[str, tuple[float, str]] = {}


def cache_search(query: str, snippets: str) -> None:
    _search_cache[query.lower()[:200]] = (time.monotonic(), snippets)
    if len(_search_cache) > 40:
        oldest = min(_search_cache, key=lambda key: _search_cache[key][0])
        _search_cache.pop(oldest, None)


def cached_search(query: str) -> str | None:
    key = query.lower()[:200]
    item = _search_cache.get(key)
    if not item:
        return None
    stored_at, snippets = item
    if time.monotonic() - stored_at > 900:
        _search_cache.pop(key, None)
        return None
    return snippets


def unwrap_ddg_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    return url


def strip_html_text(raw: str) -> str:
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html_lib.unescape(re.sub(r"\s+", " ", raw)).strip()
    return raw


def host_is_blocked(host: str) -> bool:
    host = (host or "").strip(".").lower()
    if not host:
        return True
    if host in {"localhost", "metadata.google.internal", "metadata.internal"}:
        return True
    return host.endswith((".local", ".internal", ".localhost", ".localdomain"))


def ip_is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(address).split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(ip.is_global)


def url_is_safe(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return False
    host = parsed.hostname or ""
    if host_is_blocked(host):
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return False
    return bool(addresses) and all(ip_is_public(address) for address in addresses)


class SafeResolver(aiohttp.DefaultResolver):
    """Use the DNS answer aiohttp will actually connect to, not an earlier lookup."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        if host_is_blocked(host):
            raise OSError(f"Blocked host: {host}")
        results = await super().resolve(host, port, family)
        safe = [
            item
            for item in results
            if ip_is_public(str(item.get("host", "")))
        ]
        if not safe:
            raise OSError(f"Blocked address for {host}")
        return safe


def open_http_session(
    timeout: aiohttp.ClientTimeout,
    headers: dict | None = None,
) -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(resolver=SafeResolver())
    return aiohttp.ClientSession(
        timeout=timeout,
        headers=headers,
        connector=connector,
    )


async def fetch_limited(
    session: aiohttp.ClientSession,
    url: str,
    limit: int,
    hops: int = 3,
) -> tuple[int, str, bytes]:
    if hops < 0 or not await asyncio.to_thread(url_is_safe, url):
        raise ValueError("That URL is not allowed.")
    async with session.get(url, allow_redirects=False) as response:
        if response.status in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location or hops == 0:
                raise ValueError(f"Could not download the file (HTTP {response.status}).")
            return await fetch_limited(session, urljoin(url, location), limit, hops - 1)
        content_type = (response.headers.get("Content-Type") or "").lower()
        data = await response.content.read(limit) if response.status == 200 else b""
        return response.status, content_type, data


async def fetch_page_extract(session: aiohttp.ClientSession, url: str) -> str:
    url = unwrap_ddg_url(url)
    try:
        status, content_type, raw = await fetch_limited(session, url, 200_000)
    except Exception as error:
        print(f"Page extract failure: {error}")
        return ""
    if status != 200 or not raw:
        return ""
    if "html" not in content_type and "text" not in content_type:
        return ""
    text = strip_html_text(raw.decode("utf-8", errors="ignore"))
    return text[:1200]


async def fetch_web_context(query: str, deep: bool = False) -> str:
    cache_key = ("deep:" if deep else "lite:") + query
    cached = cached_search(cache_key)
    if cached:
        return cached

    snippets: list[str] = []
    page_urls: list[str] = []
    timeout = aiohttp.ClientTimeout(total=12 if deep else 8)
    headers = {"User-Agent": "MyDisc0rdB0t/1.0 (educational Discord bot)"}
    wiki_limit = "5" if deep else "3"
    ddg_limit = 12 if deep else 8

    async with open_http_session(timeout, headers) as session:
        for wiki in (
            "https://es.wikipedia.org/w/api.php",
            "https://en.wikipedia.org/w/api.php",
        ):
            try:
                async with session.get(
                    wiki,
                    params={
                        "action": "opensearch",
                        "search": query[:200],
                        "limit": wiki_limit,
                        "namespace": "0",
                        "format": "json",
                    },
                ) as response:
                    if response.status != 200:
                        continue
                    data = await response.json()
                    titles = data[1] if len(data) > 1 else []
                    descs = data[2] if len(data) > 2 else []
                    urls = data[3] if len(data) > 3 else []
                    for index, title in enumerate(titles):
                        desc = descs[index] if index < len(descs) else ""
                        url = urls[index] if index < len(urls) else ""
                        snippets.append(f"- {title}: {desc} {url}".strip())
                        if url:
                            page_urls.append(url)
            except Exception as error:
                print(f"Wikipedia search failure: {error}")

        try:
            async with session.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query[:200]},
            ) as response:
                page = await response.text() if response.status == 200 else ""
            for match in re.finditer(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                page,
                flags=re.IGNORECASE | re.DOTALL,
            ):
                url = html_lib.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
                title = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(2)))
                title = re.sub(r"\s+", " ", title).strip()
                resolved = unwrap_ddg_url(url)
                if title:
                    snippets.append(f"- {title} ({resolved})")
                if resolved.startswith("http"):
                    page_urls.append(resolved)
                if len(snippets) >= ddg_limit + 6:
                    break
        except Exception as error:
            print(f"DuckDuckGo search failure: {error}")

        if deep:
            unique_pages = []
            seen_pages = set()
            for url in page_urls:
                host = urlparse(url).netloc.lower()
                if not host or host in seen_pages:
                    continue
                seen_pages.add(host)
                unique_pages.append(url)
                if len(unique_pages) >= 3:
                    break
            extracts = await asyncio.gather(
                *[fetch_page_extract(session, url) for url in unique_pages],
                return_exceptions=True,
            )
            for url, extract in zip(unique_pages, extracts):
                if isinstance(extract, str) and extract:
                    snippets.append(f"- Extract from {url}: {extract}")

    unique: list[str] = []
    seen = set()
    for line in snippets:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)

    if not unique:
        # Don't cache a miss. A short DuckDuckGo/Wikipedia outage was sticking
        # for 15 minutes and the model treated it as "nothing exists".
        return "No web results found."

    result = "\n".join(unique[: (14 if deep else 8)])
    cache_search(cache_key, result)
    return result


def colombia_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=-5)))


def is_ai_online() -> bool:
    return 6 <= colombia_now().hour < 21


def is_owner(user: discord.abc.User) -> bool:
    return user.id in OWNER_USER_IDS or (user.name or "").lower() in OWNER_USERNAMES


def reset_talk_usage_if_needed() -> None:
    today = colombia_now().strftime("%Y-%m-%d")
    if talk_usage.get("day") != today:
        talk_usage["day"] = today
        talk_usage["global"] = 0
        talk_usage["users"] = {}
        talk_usage["last"] = {}


def check_talk_quota(user: discord.abc.User) -> str | None:
    reset_talk_usage_if_needed()
    if is_owner(user):
        return None
    user_key = str(user.id)
    last = talk_usage["last"].get(user_key)
    now = colombia_now().timestamp()
    if last is not None:
        try:
            elapsed = now - float(last)
        except (TypeError, ValueError):
            elapsed = TALK_COOLDOWN_SECONDS
        if elapsed < TALK_COOLDOWN_SECONDS:
            wait = max(1, int(TALK_COOLDOWN_SECONDS - elapsed))
            return get_string(user.id, "talk_cooldown").format(wait=wait)
    used = int(talk_usage["users"].get(user_key, 0))
    if used >= TALK_USER_DAILY_LIMIT:
        return get_string(user.id, "talk_user_limit").format(limit=TALK_USER_DAILY_LIMIT)
    if int(talk_usage["global"]) >= TALK_GLOBAL_DAILY_LIMIT:
        return get_string(user.id, "talk_global_limit")
    return None


def consume_talk_quota(user: discord.abc.User) -> None:
    reset_talk_usage_if_needed()
    if is_owner(user):
        return
    user_key = str(user.id)
    talk_usage["users"][user_key] = int(talk_usage["users"].get(user_key, 0)) + 1
    talk_usage["global"] = int(talk_usage["global"]) + 1
    talk_usage["last"][user_key] = colombia_now().timestamp()


def refund_talk_quota(user: discord.abc.User) -> None:
    reset_talk_usage_if_needed()
    if is_owner(user):
        return
    user_key = str(user.id)
    used = int(talk_usage["users"].get(user_key, 0))
    if used > 0:
        talk_usage["users"][user_key] = used - 1
    if int(talk_usage.get("global", 0)) > 0:
        talk_usage["global"] = int(talk_usage["global"]) - 1
    talk_usage["last"].pop(user_key, None)


async def take_talk_turn(user: discord.abc.User) -> str | None:
    async with get_quota_lock():
        error = check_talk_quota(user)
        if error:
            return error
        consume_talk_quota(user)
        return None


async def release_talk_turn(user: discord.abc.User) -> None:
    async with get_quota_lock():
        refund_talk_quota(user)


async def read_talk_quota(user: discord.abc.User) -> dict:
    async with get_quota_lock():
        reset_talk_usage_if_needed()
        user_key = str(user.id)
        wait = 0
        if not is_owner(user):
            last = talk_usage["last"].get(user_key)
            if last is not None:
                try:
                    elapsed = colombia_now().timestamp() - float(last)
                except (TypeError, ValueError):
                    elapsed = TALK_COOLDOWN_SECONDS
                if elapsed < TALK_COOLDOWN_SECONDS:
                    wait = max(1, int(TALK_COOLDOWN_SECONDS - elapsed))
        return {
            "owner": is_owner(user),
            "used": int(talk_usage["users"].get(user_key, 0)),
            "global_used": int(talk_usage.get("global", 0)),
            "wait": wait,
            "online": is_ai_online(),
            "night_owl": bool(NIGHT_OWL_KEY),
        }


def format_uptime(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def discord_units(text: str) -> int:
    """Discord counts UTF-16 code units, not Python characters."""
    return len(text.encode("utf-16-le")) // 2


def clip_discord(text: str, limit: int = 2000) -> str:
    if discord_units(text) <= limit:
        return text
    ellipsis = "…"
    budget = limit - discord_units(ellipsis)
    if budget < 1:
        return ""
    kept: list[str] = []
    used = 0
    for char in text:
        size = discord_units(char)
        if used + size > budget:
            break
        kept.append(char)
        used += size
    return "".join(kept) + ellipsis


def take_discord_prefix(text: str, limit: int) -> tuple[str, str]:
    used = 0
    for index, char in enumerate(text):
        size = discord_units(char)
        if used + size > limit:
            return text[:index], text[index:]
        used += size
    return text, ""


def can_speak_as_bot(user: discord.abc.User) -> bool:
    if is_owner(user):
        return True
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and (perms.manage_messages or perms.administrator))


def make_ai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


def format_history_lines(entries: list[dict], limit_chars: int | None = None) -> str:
    if not entries:
        return "No previous /talk messages in this channel."
    lines = []
    for item in entries:
        prompt = item["prompt"].replace("\n", " ")
        if limit_chars is not None:
            prompt = prompt[:limit_chars]
        line = f"- {item['user']}: {prompt}"
        reply = str(item.get("reply") or "").replace("\n", " ").strip()
        if reply:
            if limit_chars is not None:
                reply = reply[:limit_chars]
            line += f" -> bot: {reply}"
        lines.append(line)
    return "\n".join(lines)


def format_guild_emojis(guild: discord.Guild | None) -> str:
    if guild is None or not guild.emojis:
        return "This chat has no custom server emojis."

    emojis = list(guild.emojis)
    lines = []
    for emoji in emojis[:EMOJI_PROMPT_LIMIT]:
        usage = f"<a:{emoji.name}:{emoji.id}>" if emoji.animated else f"<:{emoji.name}:{emoji.id}>"
        kind = "animated" if emoji.animated else "static"
        lines.append(
            f"- name={emoji.name} | usage={usage} | type={kind} | image={emoji.url}"
        )

    extra = len(emojis) - EMOJI_PROMPT_LIMIT
    if extra > 0:
        lines.append(f"- ...and {extra} more custom emojis not listed.")

    return "\n".join(lines)


async def build_memory_block(channel_id: int) -> str:
    entries = list(ai_history[channel_id])
    if not entries:
        return "No previous /talk messages in this channel."

    recent = entries[-RECENT_PROMPT_LIMIT:]
    older = entries[:-RECENT_PROMPT_LIMIT]
    if not older:
        return format_history_lines(recent, PROMPT_STORE_CHARS)

    older_tail = older[-OLDER_SNIPPET_LIMIT:]
    return (
        f"Older prompts ({len(older)} stored, showing last {len(older_tail)}, shortened):\n"
        f"{format_history_lines(older_tail, SNIPPET_CHARS)}\n\n"
        f"Most recent {len(recent)}:\n"
        f"{format_history_lines(recent, PROMPT_STORE_CHARS)}"
    )


def pick_fun_fact() -> str:
    global _last_fact
    choices = [fact for fact in FUN_FACTS if fact != _last_fact] or FUN_FACTS
    fact = random.choice(choices)
    _last_fact = fact
    return fact


async def set_fun_fact_status() -> None:
    global _last_fact
    fact = pick_fun_fact()
    _last_fact = fact
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.CustomActivity(name=fact),
    )


RETIRED_GROQ_MODELS = {"groq/compound", "groq/compound-mini"}


def active_search_model() -> str:
    """Groq shut down compound (and its browser_search tool) on 2026-09-21."""
    model = (SEARCH_MODEL or "").strip()
    if model.lower() in RETIRED_GROQ_MODELS:
        print(
            f"Search model {model} was retired by Groq on 2026-09-21. "
            f"Using {AI_MODEL} instead."
        )
        return AI_MODEL
    return model or AI_MODEL


def resolve_ai_client(night_owl: bool) -> tuple[OpenAI | None, str | None]:
    online = is_ai_online()
    if not online and not night_owl:
        return None, "🤖 AI is currently offline. Available hours: **06:00–21:00 UTC-5**."
    if night_owl and not online:
        if not NIGHT_OWL_KEY:
            return None, "Night Owl is not configured. Set the `NIGHT-OWL` key in the environment."
        return make_ai_client(NIGHT_OWL_KEY), None
    return ai_client, None


async def generate_ai_response(
    *,
    channel_id: int,
    username: str,
    guild: discord.Guild | None,
    clean_prompt: str,
    client: OpenAI,
    use_search: bool = False,
    deep_search: bool = False,
    is_dm: bool = False,
    prefers_spanish: bool = False,
) -> tuple[str, str]:
    history_text = await build_memory_block(channel_id)
    emoji_text = format_guild_emojis(guild)
    web_context = ""
    # Deep search used to send tools=[{type: browser_search}] to Groq compound.
    # That system was removed, so gpt-oss rejected the tool and the bot fell
    # back to a light lookup. Page fetches stay on the SSRF-checked client.
    if deep_search:
        model = active_search_model()
        web_context = await fetch_web_context(clean_prompt, deep=True)
        search_line = (
            "Web snippets and short page extracts were fetched with Wikipedia and DuckDuckGo. "
            "Use them if relevant. Do not invent sources or links. Keep the answer short."
        )
    elif use_search:
        model = AI_MODEL
        web_context = await fetch_web_context(clean_prompt, deep=False)
        search_line = (
            "Web snippets were fetched with Wikipedia and DuckDuckGo. "
            "Use them if relevant. Do not invent sources. Keep the answer short."
        )
    else:
        model = AI_MODEL
        search_line = (
            "You cannot browse the web in this request. Answer from what you know. "
            "If the user needs facts from 2024 onward, say you may be outdated."
        )

    if prefers_spanish:
        language_line = "The user turned on Spanish mode. Reply in Spanish unless they explicitly ask for another language."
    else:
        language_line = "Reply in the same language the user wrote in."

    system_prompt = f"""You are a Discord bot AI assistant.
Your source code is publicly available at: https://github.com/Crea1eGithub/MyDisc0rdB0t

The user who just talked to you is: {username}
{language_line}

{search_line}

Recent chat history in this channel (saved on disk; short user prompts and bot replies):
{history_text}

Custom emojis available in this server (use the exact usage string in your reply if you want one to render):
{emoji_text}

Application emojis (always available, write them EXACTLY as shown):
- seahorse: {SEAHORSE_EMOJI}
- open_mouth: {OPEN_MOUTH_EMOJI}
If anyone asks for a seahorse emoji, use {SEAHORSE_EMOJI}. Do not say you cannot find one.

When you want a custom emoji, write it exactly like <:name:id> or <a:name:id> for animated ones.
Answer clearly and helpfully. You can be casual and match the user's tone when appropriate.
Keep responses reasonably concise unless more detail is requested.
"""

    user_message = clean_prompt
    if web_context:
        user_message = (
            f"{clean_prompt}\n\nWeb snippets (may be incomplete):\n{web_context}"
        )

    request_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    max_tokens = MAX_SEARCH_TOKENS if deep_search else MAX_ANSWER_TOKENS

    start_time = time.monotonic()
    try:
        completion = await complete_chat(
            client,
            model=model,
            messages=request_messages,
            max_tokens=max_tokens,
        )
    except Exception as error:
        print(f"Primary AI request failure ({model}): {error}")
        if not deep_search or model == AI_MODEL:
            raise
        print(f"Retrying deep search with {AI_MODEL}.")
        model = AI_MODEL
        completion = await complete_chat(
            client,
            model=model,
            messages=request_messages,
            max_tokens=MAX_ANSWER_TOKENS,
        )
    answer = visible_answer(completion)
    if not answer:
        raise RuntimeError(f"Empty AI answer from {model}")
    elapsed = time.monotonic() - start_time
    thinking_seconds = max(1, round(elapsed))
    return format_thought_line(thinking_seconds), answer


def store_exchange(channel_id: int, username: str, clean_prompt: str, answer: str) -> None:
    ai_history[channel_id].append({
        "user": username,
        "prompt": clean_prompt[:PROMPT_STORE_CHARS],
        "reply": " ".join((answer or "").split())[:REPLY_STORE_CHARS],
    })


THINK_RE = re.compile(r"<think>[\s\S]*?</think>", flags=re.IGNORECASE)
OPEN_THINK_RE = re.compile(r"<think>[\s\S]*$", flags=re.IGNORECASE)


def model_uses_reasoning(model: str) -> bool:
    return "gpt-oss" in (model or "").lower()


def visible_answer(completion) -> str:
    message = completion.choices[0].message
    content = message.content or ""
    if not isinstance(content, str):
        content = str(content)
    content = THINK_RE.sub("", content)
    content = OPEN_THINK_RE.sub("", content)
    return content.strip()


async def complete_chat(client: OpenAI, *, model: str, messages: list, max_tokens: int):
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    # gpt-oss reasons by default. Those tokens count against max_tokens, so a
    # 500-token Discord reply often came back empty and still spent a credit.
    if model_uses_reasoning(model):
        kwargs["extra_body"] = {
            "reasoning_effort": "low",
            "include_reasoning": False,
        }
    return await asyncio.to_thread(client.chat.completions.create, **kwargs)


def format_thought_line(thinking_seconds: int) -> str:
    return f'**"Ö" ahh bot thought for {thinking_seconds} seconds**'


def thinking_status_text() -> str:
    return f"{OPEN_MOUTH_EMOJI} lemme think for a sec"


async def load_application_emojis() -> None:
    global OPEN_MOUTH_EMOJI, SEAHORSE_EMOJI
    try:
        emojis = await bot.fetch_application_emojis()
        for emoji in emojis:
            name = emoji.name.lower()
            if name == "open_mouth":
                OPEN_MOUTH_EMOJI = str(emoji)
                print(f"Using application emoji {OPEN_MOUTH_EMOJI}")
            elif name == "seahorse":
                SEAHORSE_EMOJI = str(emoji)
                print(f"Using application emoji {SEAHORSE_EMOJI}")
    except Exception as error:
        print(f"App emoji load failure: {error}")


async def handle_chat_prompt(message: discord.Message, prompt: str, is_dm: bool) -> None:
    night_owl, deep_search, clean_prompt = strip_prompt_flags(prompt)
    if not clean_prompt:
        await message.channel.send("Please provide a prompt.")
        return

    use_search = deep_search or needs_fresh_info(clean_prompt)

    client, error = resolve_ai_client(night_owl)
    if error or client is None:
        await message.channel.send(error or "The AI is unavailable.")
        return

    quota_error = await take_talk_turn(message.author)
    if quota_error:
        await message.channel.send(quota_error)
        return

    thinking_msg = None
    answered = False
    try:
        if not is_dm:
            thinking_msg = await message.reply(
                thinking_status_text(),
                mention_author=False,
                allowed_mentions=NO_USER_PINGS,
            )

        async def send(content):
            if is_dm:
                await message.channel.send(content, allowed_mentions=NO_USER_PINGS)
            else:
                await message.reply(
                    content,
                    mention_author=False,
                    allowed_mentions=NO_USER_PINGS,
                )

        async def edit(content):
            if thinking_msg is not None:
                await thinking_msg.edit(content=content, allowed_mentions=NO_USER_PINGS)
            else:
                await send(content)

        async with message.channel.typing():
            await save_memory()
            thought_line, answer = await generate_ai_response(
                channel_id=message.channel.id,
                username=message.author.display_name,
                guild=message.guild,
                clean_prompt=clean_prompt,
                client=client,
                use_search=use_search,
                deep_search=deep_search,
                is_dm=is_dm,
                prefers_spanish=user_profiles.get(message.author.id, False),
            )
            await send_ai_chunks(
                send,
                clean_prompt,
                thought_line,
                answer,
                edit=edit if thinking_msg is not None else None,
            )
            answered = True
            try:
                store_exchange(
                    message.channel.id,
                    message.author.display_name,
                    clean_prompt,
                    answer,
                )
                await save_memory()
            except Exception as error:
                print(f"Could not store the delivered reply: {error}")
    except Exception as error:
        print(f"AI message request failure: {error}")
        if not answered:
            await release_talk_turn(message.author)
            await save_memory()
        fail = "⚠️ The AI service could not process the request right now."
        try:
            if thinking_msg is not None:
                await thinking_msg.edit(content=fail, allowed_mentions=NO_USER_PINGS)
            else:
                await message.channel.send(fail, allowed_mentions=NO_USER_PINGS)
        except Exception:
            print("Could not report the AI failure to Discord.")


def mention_prompt(message: discord.Message) -> str | None:
    if bot.user is None or bot.user not in message.mentions:
        return None
    text = re.sub(rf"<@!?{bot.user.id}>", " ", message.content or "")
    return text.strip()


def prompt_preview(clean_prompt: str, limit: int = 180) -> str:
    preview = " ".join((clean_prompt or "").split())
    if len(preview) > limit:
        preview = preview[: limit - 1] + "…"
    return preview


async def send_ai_chunks(
    send,
    clean_prompt: str,
    thought_line: str,
    answer: str,
    edit=None,
) -> None:
    header = clip_discord(f"-# {prompt_preview(clean_prompt)}\n{thought_line}")
    response_text = f"{header}\n{answer}"
    first = edit or send
    if discord_units(response_text) <= 2000:
        await first(response_text)
        return
    await first(header)
    rest = answer
    while rest:
        chunk, rest = take_discord_prefix(rest, 1900)
        if not chunk:
            break
        await send(chunk)


@tasks.loop(minutes=STATUS_ROTATE_MINUTES)
async def rotate_status():
    await set_fun_fact_status()


@rotate_status.before_loop
async def before_rotate_status():
    await bot.wait_until_ready()


async def sync_app_commands() -> None:
    global command_sync_fingerprint_saved
    try:
        fingerprint = command_tree_fingerprint()
    except Exception as error:
        print(f"Command fingerprint failure: {error}")
        fingerprint = ""

    mode = SYNC_COMMANDS if SYNC_COMMANDS in {"auto", "always", "never"} else "auto"
    if mode == "never":
        print("Skipping slash command sync (SYNC_COMMANDS=never).")
        return
    if mode == "auto" and fingerprint and fingerprint == command_sync_fingerprint_saved:
        print("Slash commands unchanged. Skipping Discord sync.")
        return

    try:
        synced = await asyncio.wait_for(bot.tree.sync(), timeout=20)
        print(f"Successfully synchronized {len(synced)} application command(s).")
        if fingerprint:
            command_sync_fingerprint_saved = fingerprint
            await save_memory(force_discord=True)
    except asyncio.TimeoutError:
        print("Command sync timed out. Using the last successful Discord command list.")
    except Exception as error:
        print(f"Synchronization failure: {error}")


def command_tree_fingerprint() -> str:
    chunks: list[str] = []
    for command in bot.tree.walk_commands():
        params = []
        for param in getattr(command, "parameters", []) or []:
            kind = getattr(param, "type", "")
            kind_name = getattr(kind, "name", str(kind))
            required = int(bool(getattr(param, "required", False)))
            params.append(f"{param.name}:{required}:{kind_name}")
        params.sort()
        chunks.append(f"{command.qualified_name}|{command.description}|{','.join(params)}")
    chunks.sort()
    return hashlib.sha256("\n".join(chunks).encode()).hexdigest()[:20]


@bot.event
async def on_ready():
    global _discord_memory_loaded
    print(f"Logged in successfully as {bot.user} (ID: {bot.user.id})")
    print(f"Using AI model: {AI_MODEL}")

    try:
        await set_fun_fact_status()
    except Exception as error:
        print(f"Presence failure: {error}")

    if not rotate_status.is_running():
        rotate_status.start()

    try:
        await load_application_emojis()
    except Exception as error:
        print(f"Open mouth emoji failure: {error}")

    if not _discord_memory_loaded:
        try:
            await load_memory_from_discord()
            _discord_memory_loaded = True
        except Exception as error:
            print(f"Discord memory load failure: {error}")
    else:
        print("Skipping Discord memory reload after reconnect.")

    if not flush_discord_memory.is_running():
        flush_discord_memory.start()

    if not getattr(bot, "_command_sync_started", False):
        bot._command_sync_started = True
        asyncio.create_task(sync_app_commands())


@bot.event
async def on_error(event: str, *args, **kwargs):
    print(f"Error in event {event}:")
    traceback.print_exc()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    print(f"Slash command error: {error}")
    traceback.print_exc()
    message = "That command failed. Try again in a moment."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if isinstance(message.channel, discord.DMChannel):
        prompt = (message.content or "").strip()
        if prompt:
            await handle_chat_prompt(message, prompt, is_dm=True)
        return

    mentioned = mention_prompt(message)
    if mentioned is None:
        return
    if not mentioned:
        await message.reply("Please provide a prompt.", mention_author=False)
        return
    await handle_chat_prompt(message, mentioned, is_dm=False)


@bot.tree.command(
    name="talk",
    description="Talk to the AI. Available 06:00–21:00 UTC-5.",
)
@app_commands.describe(
    prompt="What you want to ask the AI.",
    deep_search="Look up a few web pages before answering. Default: off.",
)
async def talk(
    interaction: discord.Interaction,
    prompt: str,
    deep_search: bool = False,
):
    night_owl, tagged_deep, clean_prompt = strip_prompt_flags(prompt)
    deep_search = deep_search or tagged_deep

    if not clean_prompt:
        await interaction.response.send_message(
            "Please provide a prompt.",
            ephemeral=True,
        )
        return

    use_search = deep_search or needs_fresh_info(clean_prompt)

    client, error = resolve_ai_client(night_owl)
    if error or client is None:
        await interaction.response.send_message(error or "The AI is unavailable.", ephemeral=True)
        return

    quota_error = await take_talk_turn(interaction.user)
    if quota_error:
        await interaction.response.send_message(quota_error, ephemeral=True)
        return

    is_dm = interaction.guild is None
    answered = False
    try:
        if is_dm:
            await interaction.response.defer()
        else:
            await interaction.response.send_message(thinking_status_text())

        async def send(content):
            await interaction.followup.send(content, allowed_mentions=NO_USER_PINGS)

        async def edit(content):
            await interaction.edit_original_response(
                content=content,
                allowed_mentions=NO_USER_PINGS,
            )

        await save_memory()
        thought_line, answer = await generate_ai_response(
            channel_id=interaction.channel.id if interaction.channel else 0,
            username=interaction.user.display_name,
            guild=interaction.guild,
            clean_prompt=clean_prompt,
            client=client,
            use_search=use_search,
            deep_search=deep_search,
            is_dm=is_dm,
            prefers_spanish=user_profiles.get(interaction.user.id, False),
        )
        await send_ai_chunks(
            send,
            clean_prompt,
            thought_line,
            answer,
            edit=None if is_dm else edit,
        )
        answered = True
        try:
            store_exchange(
                interaction.channel.id if interaction.channel else 0,
                interaction.user.display_name,
                clean_prompt,
                answer,
            )
            await save_memory()
        except Exception as error:
            print(f"Could not store the delivered reply: {error}")
    except Exception as error:
        print(f"AI request failure: {error}")
        if not answered:
            await release_talk_turn(interaction.user)
            await save_memory()
        fail = "⚠️ The AI service could not process the request right now."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(fail, ephemeral=True)
            elif is_dm:
                await interaction.followup.send(fail)
            else:
                await interaction.edit_original_response(content=fail)
        except Exception:
            print("Could not report the AI failure to Discord.")


@bot.tree.command(
    name="quota",
    description="Show AI hours, your remaining daily messages, and uptime.",
)
async def quota(interaction: discord.Interaction):
    user_id = interaction.user.id
    snap = await read_talk_quota(interaction.user)
    lines = [
        get_string(user_id, "quota_ai_on" if snap["online"] else "quota_ai_off"),
        get_string(user_id, "quota_night_on" if snap["night_owl"] else "quota_night_off"),
    ]
    if snap["owner"]:
        lines.append(
            get_string(user_id, "quota_owner").format(
                global_used=snap["global_used"],
                global_limit=TALK_GLOBAL_DAILY_LIMIT,
            )
        )
    else:
        lines.append(
            get_string(user_id, "quota_uses").format(
                used=snap["used"],
                limit=TALK_USER_DAILY_LIMIT,
                global_used=snap["global_used"],
                global_limit=TALK_GLOBAL_DAILY_LIMIT,
            )
        )
        if snap["wait"]:
            lines.append(get_string(user_id, "quota_wait").format(wait=snap["wait"]))
        else:
            lines.append(get_string(user_id, "quota_ready"))
    lines.append(get_string(user_id, "quota_reset"))
    lines.append(
        get_string(user_id, "quota_uptime").format(
            uptime=format_uptime(int(time.monotonic() - BOT_STARTED_AT)),
            latency=round(bot.latency * 1000),
        )
    )
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(
    name="python",
    description="Open the Python playground as a Discord Activity.",
)
async def python_playground(interaction: discord.Interaction):
    launched = await launch_discord_activity(interaction)
    if launched:
        return

    activity_url = PYTHON_ACTIVITY_URL
    if activity_url:
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Open Python playground",
                style=discord.ButtonStyle.link,
                url=activity_url,
            )
        )
        await interaction.response.send_message(
            "No pude abrir la Activity dentro de Discord, así que aquí va el playground en el navegador.\n"
            "Para que se abra como Activity: Developer Portal → Activities → Enable, "
            "y URL Mapping `/` → tu host **sin** `https://`.",
            view=view,
        )
        return

    await interaction.response.send_message(
        "La Activity no está lista.\n"
        "1. Sube `python-activity/` a GitHub Pages (HTTPS).\n"
        "2. Developer Portal → Activities → URL Mappings: Prefix `/` Target `tudominio.com/ruta` (sin https://).\n"
        "3. Activa **Enable Activities**.\n"
        "4. Opcional: `PYTHON_ACTIVITY_URL` en Render para el enlace de respaldo.",
        ephemeral=True,
    )


async def launch_discord_activity(interaction: discord.Interaction) -> bool:
    try:
        launch = getattr(interaction.response, "launch_activity", None)
        if callable(launch):
            await launch()
            return True
    except Exception as error:
        print(f"launch_activity helper failed: {error}")

    try:
        url = (
            f"https://discord.com/api/v10/interactions/"
            f"{interaction.id}/{interaction.token}/callback"
        )
        timeout = aiohttp.ClientTimeout(total=10)
        async with open_http_session(timeout) as session:
            async with session.post(url, json={"type": 12}) as response:
                if response.status in (200, 204):
                    return True
                body = await response.text()
                print(f"LAUNCH_ACTIVITY failed: {response.status} {body}")
    except Exception as error:
        print(f"LAUNCH_ACTIVITY request failed: {error}")

    return False


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
    await save_memory()


@bot.tree.command(name="say", description="Echo the specified message. Use \\n for a new line.")
@app_commands.describe(message="The message to repeat. Write \\n to insert a line break.")
async def say(interaction: discord.Interaction, message: str):
    user_id = interaction.user.id
    if not can_speak_as_bot(interaction.user):
        await interaction.response.send_message(
            get_string(user_id, "say_denied"),
            ephemeral=True,
        )
        return

    text = message.replace("\\n", "\n")
    if not text.strip() or discord_units(text) > 2000:
        await interaction.response.send_message(
            get_string(user_id, "say_length"),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(text, allowed_mentions=NO_USER_PINGS)


@bot.tree.command(
    name="choose",
    description="Pick one option at random. Separate options with commas.",
)
@app_commands.describe(options="Options separated by commas. Example: pizza, tacos, pasta")
async def choose(interaction: discord.Interaction, options: str):
    user_id = interaction.user.id
    choices = [item.strip() for item in options.split(",") if item.strip()]

    if len(choices) < 2:
        await interaction.response.send_message(
            get_string(user_id, "choose_empty"),
            ephemeral=True,
        )
        return

    choice = random.choice(choices)
    await interaction.response.send_message(
        clip_discord(get_string(user_id, "choose_result").format(choice=choice)),
        allowed_mentions=NO_USER_PINGS,
    )


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
            timeout = aiohttp.ClientTimeout(total=15)
            async with open_http_session(timeout) as session:
                status, content_type, image_bytes = await fetch_limited(
                    session, url, 8_000_000
                )
            if status != 200 or not image_bytes:
                raise ValueError(f"Could not download the image (HTTP {status}).")
            if content_type and not content_type.startswith(("image/", "application/octet-stream")):
                raise ValueError("The URL must point to an image.")

        else:
            target = user or interaction.user
            avatar_url = target.display_avatar.with_format("png").url

            if interaction.guild is not None and not no_server_pfp:
                member = interaction.guild.get_member(target.id)
                if member is not None:
                    avatar_url = member.display_avatar.with_format("png").url

            timeout = aiohttp.ClientTimeout(total=15)
            async with open_http_session(timeout) as session:
                status, _, image_bytes = await fetch_limited(session, avatar_url, 8_000_000)
            if status != 200 or not image_bytes:
                raise ValueError(f"Could not download the avatar (HTTP {status}).")

        avatar = Image.open(BytesIO(image_bytes)).convert("RGBA")

        frame_urls = [
            f"https://raw.githubusercontent.com/VenPlugs/petpet/main/frames/pet{i}.gif"
            for i in range(10)
        ]

        timeout = aiohttp.ClientTimeout(total=30)
        async with open_http_session(timeout) as session:
            async def fetch_frame(frame_url: str) -> bytes:
                status, _, data = await fetch_limited(session, frame_url, 2_000_000)
                if status != 200 or not data:
                    raise ValueError(f"Could not download PetPet frame (HTTP {status}).")
                return data

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

    channel = interaction.channel
    if channel is None or not hasattr(channel, "purge"):
        await interaction.response.send_message(
            get_string(user_id, "purge_channel"),
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
        deleted = await channel.purge(limit=limit)
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
        clip_discord(
            f"❓ **{query_label}:** {question}\n"
            f"{ball_title} {outcome}"
        ),
        allowed_mentions=NO_USER_PINGS,
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
    member = target_user if isinstance(target_user, discord.Member) else None
    if member is None and interaction.guild is not None:
        member = interaction.guild.get_member(target_user.id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(target_user.id)
            except (discord.NotFound, discord.HTTPException):
                member = None

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
    joined = (
        member.joined_at.strftime("%Y-%m-%d")
        if member is not None and member.joined_at
        else "N/A"
    )
    embed.add_field(
        name=get_string(user_id, "session_init"),
        value=joined,
        inline=True,
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


_original_close = bot.close


async def close() -> None:
    print("Shutting down. Flushing AI memory...")
    try:
        await asyncio.wait_for(save_memory(force_discord=True), timeout=20)
    except Exception as error:
        print(f"Shutdown memory flush failure: {error}")
    await _original_close()


bot.close = close


if __name__ == "__main__":
    keep_alive()
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    bot.run(TOKEN)
