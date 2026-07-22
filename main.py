import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in successfully as {bot.user.name}!')
    try:
        # Syncs the slash commands globally with Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# Modern slash command structure
@bot.tree.command(name="say", description="Repeats back your message")
@app_commands.describe(message="The text you want the bot to say")
async def say(interaction: discord.Interaction, message: str):
    # Sends the repeated text directly to the channel
    await interaction.response.send_message(message)

bot.run(TOKEN)

