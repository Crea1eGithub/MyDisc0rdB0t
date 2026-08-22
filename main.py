import discord
from discord.ext import commands
import os
import asyncio
import logging
from datetime import datetime
from flask import Flask
import threading

# ==================== CONFIGURACIÓN ====================
TOKEN = os.environ.get('DISCORD_TOKEN')

if TOKEN is None:
    raise ValueError("❌ DISCORD_TOKEN no está configurado en Render")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Crear bot
bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=None  # Usaremos nuestro propio comando de ayuda
)

# ==================== SERVIDOR WEB PARA RENDER ====================
app = Flask('')

@app.route('/')
def home():
    return "Bot está activo y funcionando! 🤖"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# ==================== EVENTOS ====================
@bot.event
async def on_ready():
    print(f"""
    🟢 Bot conectado como: {bot.user.name}
    🆔 ID: {bot.user.id}
    📊 Servidores: {len(bot.guilds)}
    👥 Usuarios totales: {sum(guild.member_count for guild in bot.guilds)}
    🔗 Invite: https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot
    """)
    
    # Cambiar estado del bot
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"!help | {len(bot.guilds)} servidores"
        )
    )
    
    # Cargar cogs si existen
    if os.path.exists('./cogs'):
        await load_extensions()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Espera {round(error.retry_after)} segundos antes de usar este comando nuevamente.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permisos para usar este comando.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Falta el argumento: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ El argumento no es válido. Revisa el formato.")
    else:
        logger.error(f"Error no manejado: {error}")
        await ctx.send("❌ Ocurrió un error inesperado.")

# ==================== COGS ====================
async def load_extensions():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'✅ Cargado: {filename}')
            except Exception as e:
                print(f'❌ Error en {filename}: {e}')

# ==================== COMANDOS ====================
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def ping(ctx):
    """Muestra la latencia del bot"""
    await ctx.send(f'🏓 Pong! {round(bot.latency * 1000)}ms')

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def info(ctx):
    """Muestra información del servidor"""
    logger.info(f"Comando info usado por {ctx.author} en {ctx.guild}")
    embed = discord.Embed(
        title=f"📊 Información de {ctx.guild.name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="👥 Miembros", value=ctx.guild.member_count, inline=True)
    embed.add_field(name="📅 Creado", value=ctx.guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👑 Dueño", value=ctx.guild.owner.mention, inline=True)
    embed.add_field(name="📝 Canales", value=len(ctx.guild.channels), inline=True)
    embed.add_field(name="🔊 Roles", value=len(ctx.guild.roles), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def ayuda(ctx, comando=None):
    """Muestra los comandos disponibles"""
    if comando is None:
        embed = discord.Embed(
            title="📋 Comandos disponibles",
            description="Usa `!ayuda <comando>` para más detalles",
            color=discord.Color.blue()
        )
        
        for cmd in bot.commands:
            if not cmd.hidden:
                embed.add_field(
                    name=f"!{cmd.name}",
                    value=cmd.brief or cmd.help or "Sin descripción",
                    inline=False
                )
        
        await ctx.send(embed=embed)
    else:
        cmd = bot.get_command(comando)
        if cmd:
            embed = discord.Embed(
                title=f"!{cmd.name}",
                description=cmd.help or "Sin descripción",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Comando no encontrado")

# ==================== COMANDOS DE ADMINISTRACIÓN ====================
@bot.command()
@commands.has_permissions(administrator=True)
@commands.cooldown(1, 10, commands.BucketType.guild)
async def limpiar(ctx, cantidad: int):
    """Limpia mensajes (solo admins)"""
    if cantidad < 1:
        await ctx.send("❌ La cantidad debe ser mayor a 0")
        return
    if cantidad > 100:
        await ctx.send("❌ No puedo borrar más de 100 mensajes")
        return
    
    try:
        await ctx.channel.purge(limit=cantidad + 1)
        msg = await ctx.send(f'✅ Borrados {cantidad} mensajes')
        await asyncio.sleep(3)
        await msg.delete()
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para borrar mensajes")
    except Exception as e:
        logger.error(f"Error en limpiar: {e}")
        await ctx.send("❌ Error al borrar mensajes")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, razon="No especificada"):
    """Expulsa a un miembro del servidor"""
    try:
        await member.kick(reason=razon)
        await ctx.send(f"✅ {member.mention} ha sido expulsado. Razón: {razon}")
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para expulsar a ese usuario")
    except Exception as e:
        logger.error(f"Error en kick: {e}")
        await ctx.send("❌ Error al expulsar al usuario")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, razon="No especificada"):
    """Banea a un miembro del servidor"""
    try:
        await member.ban(reason=razon)
        await ctx.send(f"✅ {member.mention} ha sido baneado. Razón: {razon}")
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para banear a ese usuario")
    except Exception as e:
        logger.error(f"Error en ban: {e}")
        await ctx.send("❌ Error al banear al usuario")

# ==================== INICIO DEL BOT ====================
async def main():
    try:
        # Iniciar servidor web para Render
        threading.Thread(target=run_web).start()
        print("🌐 Servidor web iniciado en puerto 8080")
        
        # Iniciar bot con reconexión automática
        await bot.start(TOKEN)
    except (discord.HTTPException, discord.GatewayNotFound) as e:
        logger.error(f"Error de conexión: {e}")
        print("🔄 Intentando reconectar en 5 segundos...")
        await asyncio.sleep(5)
        await main()
    except KeyboardInterrupt:
        print("🛑 Bot detenido manualmente")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    if TOKEN is None:
        print("❌ Error: No se encontró el token. Revisa las variables de entorno en Render")
    else:
        asyncio.run(main())
