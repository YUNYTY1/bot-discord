import discord
import os
import asyncio
import yt_dlp
from discord.ext import commands
from dotenv import load_dotenv

def run_bot():
    load_dotenv()
    # Usamos el nombre exacto de la variable que tienes en Railway
    TOKEN = os.getenv('discord_token')

    # --- CONFIGURACIÓN DE INTENTS (CRUCIAL) ---
    intents = discord.Intents.default()
    intents.message_content = True  # Permite leer el contenido de los mensajes (?p, ?join, etc.)
    intents.voice_states = True     # Permite gestionar la conexión a canales de voz
    intents.guilds = True           # Permite interactuar con los servidores

    # Usamos discord.Client con los intents configurados
    client = discord.Client(intents=intents)

    queues = {}
    voice_clients = {}
    history = {}

    volume_levels = {"low": 0.25, "mid": 0.5, "max": 1.0}
    current_volume = 0.25

    # --- CONFIGURACIÓN DE YT-DLP PARA EVITAR BLOQUEOS ---
    yt_dl_options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "no_color": True,
        "extract_flat": False,
        "wait_for_video": (5, 30),
        # Este User-Agent simula un navegador real para evitar el error de "Sign in to confirm you're not a bot"
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    def get_ffmpeg_options(volume):
        return {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': f'-vn -filter:a "volume={volume}"'
        }

    async def play_next(guild_id):
        if guild_id not in queues or not queues[guild_id]:
            return

        url = queues[guild_id].pop(0)

        try:
            # Ejecutamos la extracción en un hilo separado para no bloquear el bot
            data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )

            if 'entries' in data:
                data = data['entries'][0]

            song = data['url']
            
            if guild_id not in history:
                history[guild_id] = []
            history[guild_id].append(url)

            player = discord.FFmpegPCMAudio(song, **get_ffmpeg_options(current_volume))

            def after_playing(error):
                if error:
                    print(f"Error en reproducción: {error}")
                fut = asyncio.run_coroutine_threadsafe(play_next(guild_id), client.loop)
                try:
                    fut.result()
                except:
                    pass

            voice_clients[guild_id].play(player, after=after_playing)

        except Exception as e:
            print(f"Error en play_next: {e}")
            await play_next(guild_id)

    @client.event
    async def on_ready():
        print(f'---')
        print(f'{client.user} is now jamming 🎶')
        print(f'Intents message_content: {intents.message_content}')
        print(f'---')

    @client.event
    async def on_message(message):
        nonlocal current_volume

        if message.author == client.user:
            return

        if not message.guild:
            return

        guild_id = message.guild.id
        content = message.content.lower().strip()

        # ▶️ PLAY
        if content.startswith("?p "):
            try:
                if guild_id not in queues:
                    queues[guild_id] = []

                if not message.author.voice:
                    await message.channel.send("❌ Debes estar en un canal de voz.")
                    return

                if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
                    voice_client = await message.author.voice.channel.connect()
                    voice_clients[guild_id] = voice_client

                query = message.content[3:].strip()

                if "youtube.com" in query or "youtu.be" in query:
                    url = query
                else:
                    # Búsqueda directa en YouTube
                    search_data = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False)
                    )
                    url = search_data['entries'][0]['webpage_url']

                queues[guild_id].append(url)

                if not voice_clients[guild_id].is_playing():
                    await play_next(guild_id)

                await message.add_reaction("🎵")

            except Exception as e:
                print(f"Error en ?p: {e}")
                await message.channel.send("❌ Hubo un error al buscar la canción. YouTube podría estar bloqueando la petición.")

        # 🔊 JOIN
        elif content.startswith("?join"):
            try:
                if not message.author.voice:
                    await message.channel.send("❌ Debes estar en un canal de voz.")
                    return

                if guild_id in voice_clients and voice_clients[guild_id].is_connected():
                    await message.channel.send("✅ Ya estoy aquí.")
                else:
                    voice_client = await message.author.voice.channel.connect()
                    voice_clients[guild_id] = voice_client
                    await message.add_reaction("🔊")
            except Exception as e:
                print(f"Error en ?join: {e}")

        # 👋 DISCONNECT / LEAVE
        elif content.startswith("?leave") or content.startswith("?disconnect"):
            try:
                if guild_id in voice_clients:
                    await voice_clients[guild_id].disconnect()
                    del voice_clients[guild_id]
                    await message.add_reaction("👋")
            except Exception as e:
                print(f"Error en leave: {e}")

        # ⏸️ PAUSE / RESUME / STOP / SKIP
        elif content.startswith("?pa"):
            if guild_id in voice_clients:
                voice_clients[guild_id].pause()
                await message.add_reaction("⏸️")

        elif content.startswith("?r"):
            if guild_id in voice_clients:
                voice_clients[guild_id].resume()
                await message.add_reaction("▶️")

        elif content.startswith("?f"):
            if guild_id in voice_clients:
                queues[guild_id] = []
                voice_clients[guild_id].stop()
                await voice_clients[guild_id].disconnect()
                await message.add_reaction("⏹️")

        elif content.startswith("?s"):
            if guild_id in voice_clients:
                voice_clients[guild_id].stop()
                await message.add_reaction("⏭️")

    client.run(TOKEN)