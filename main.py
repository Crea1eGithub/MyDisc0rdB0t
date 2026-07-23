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
@bot.tree.command(name="serverinfo", description="Retrieves comprehensive analytical data regarding the current guild")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Guild Specifications: {guild.name}", color=0x00a8fc)
    embed.add_field(name="Identification Key", value=guild.id, inline=True)
    embed.add_field(name="Administrative Owner", value=guild.owner, inline=True)
    embed.add_field(name="Total Membership", value=guild.member_count, inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="purge", description="Executes a bulk deletion of a specified quantity of recent messages")
@app_commands.describe(limit="The explicit quantity of messages to terminate from the channel history")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, limit: int):
    if limit < 1 or limit > 100:
        await interaction.response.send_message("Operational limit exceeded: Value must range strictly between 1 and 100.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=limit)
    await interaction.followup.send(f"Operation successful: Terminated {len(deleted)} message entries.")

@bot.tree.command(name="coinflip", description="Executes a binary randomized determination algorithm")
async def coinflip(interaction: discord.Interaction):
    outcome = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🪙 Algorithmic determination result: **{outcome}**")

bot.run(TOKEN)

