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

@bot.event
async def on_ready():
    print(f'Logged in successfully as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"Successfully synchronized {len(synced)} application command(s)")
    except Exception as e:
        print(f"Synchronization failure: {e}")

@bot.tree.command(name="say", description="Echoes back the specified message text")
@app_commands.describe(message="The message string to be replicated by the bot")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(name="ping", description="Retrieves the current network latency of the application")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Network Latency: **{latency}ms**")

@bot.tree.command(name="roll", description="Simulates rolling a standard or custom multi-sided die")
@app_commands.describe(sides="The total number of sides for the die execution")
async def roll(interaction: discord.Interaction, sides: int = 6):
    if sides < 2:
        await interaction.response.send_message("Execution error: A valid die must possess at least 2 sides.", ephemeral=True)
        return
    result = random.randint(1, sides)
    await interaction.response.send_message(f"🎲 Rolled a **{sides}**-sided die. Result: **{result}**")

@bot.tree.command(name="avatar", description="Fetches and displays the profile asset of a designated user")
@app_commands.describe(user="The target user whose profile asset is to be retrieved")
async def avatar(interaction: discord.Interaction, user: discord.User = None):
    target_user = user or interaction.user
    embed = discord.Embed(title=f"{target_user.name}'s Avatar", color=0x00a8fc)
    embed.set_image(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

keep_alive()
bot.run(TOKEN)

