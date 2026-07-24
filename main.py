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
        activity = discord.Activity(type=discord.ActivityType.watching, name="System Performance")
        await bot.change_presence(status=discord.Status.online, activity=activity)
        
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

@bot.tree.command(name="petpet", description="Generates a customized petpet animation overlay for a user asset")
@app_commands.describe(user="The targeted user to receive the petpet animation asset")
async def petpet(interaction: discord.Interaction, user: discord.User = None):
    target_user = user or interaction.user
    avatar_url = target_user.display_avatar.with_format("png").url
    petpet_url = f"https://vacefron.nl{avatar_url}"
    embed = discord.Embed(title=f"Processing affection matrix for {target_user.name}", color=0x00a8fc)
    embed.set_image(url=petpet_url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="8ball", description="Queries the algorithmic matrix for a definitive response to a binary query")
@app_commands.describe(question="The explicit query string directed to the application core")
async def eightball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "You may rely on it.", 
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", 
        "Don't count on it.", "My sources say no.", "Outlook not so good."
    ]
    outcome = random.choice(responses)
    await interaction.response.send_message(f"❓ **Query:** {question}\n🔮 **Matrix Response:** {outcome}")

@bot.tree.command(name="userinfo", description="Extracts structured identity profile analytics of a guild member")
@app_commands.describe(user="The specific member asset to analyze")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    embed = discord.Embed(title=f"User Analysis: {target_user.name}", color=0x00a8fc)
    embed.add_field(name="Account Classification", value=f"ID: {target_user.id}", inline=False)
    embed.add_field(name="Registry Date", value=target_user.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Guild Session Initiation", value=target_user.joined_at.strftime("%Y-%m-%d") if target_user.joined_at else "N/A", inline=True)
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rng", description="Generates a random numerical integer within a specified bound")
@app_commands.describe(min_val="Minimum bound value", max_val="Maximum bound value")
async def rng(interaction: discord.Interaction, min_val: int = 1, max_val: int = 100):
    if min_val >= max_val:
        await interaction.response.send_message("Execution error: Lower bound must be strictly less than upper bound.", ephemeral=True)
        return
    result = random.randint(min_val, max_val)
    await interaction.response.send_message(f"🔢 Random Integer Generation result [{min_val}-{max_val}]: **{result}**")

keep_alive()
bot.run(TOKEN)
