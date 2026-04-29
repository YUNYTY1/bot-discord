import discord
import os
import asyncio
import yt_dlp
from discord.ext import commands
from dotenv import load_dotenv

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('discord_token')

    # --- CONFIGURACIÓN DE INTENTS ---
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True

    client = discord.Client(intents=intents)

    queues = {}
    voice_clients = {}
    history = {}
    current_volume = 0.25

    # --- CONFIGURACIÓN DE YT-DLP ---
    yt_dl_options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "extract_flat": False,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    def get_ffmpeg_options(volume):
        return {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': f'-vn -filter:a "volume={volume}" -dn -sn -ignore_unknown'
        }

    async def play_next(guild_id):
        if guild_id not in queues or not queues[guild_id]:
            return

        url = queues[guild_id].pop(0)

        try:
            # Extracción con manejo de errores para evitar 'NoneType'
            data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )

            if data is None:
                print(f"Error: No se pudo obtener datos de la URL: {url}")
                return await play_next(guild_id)

            if 'entries' in data:
                data = data['entries'][0]

            song_url = data['url']
            
            if guild_id not in history:
                history[guild_id] = []
            history[guild_id].append(url)

            player = discord.FFmpegPCMAudio(
                song_url, 
                executable="ffmpeg", 
                **get_ffmpeg_options(current_volume)
            )

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
        print(f'---')

    @client.event
    async def on_message(message):
        nonlocal current_volume

        if message.author == client.user or not message.guild:
            return

        guild_id = message.guild.id
        content = message.content.lower().strip()

        # ▶️ COMANDO PLAY REFORZADO
        if content.startswith("?p "):
            try:
                if not message.author.voice:
                    await message.channel.send("❌ Debes estar en un canal de voz.")
                    return

                query = message.content[3:].strip()
                
                # Conectar si no está conectado
                if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
                    voice_clients[guild_id] = await message.author.voice.channel.connect()

                # Mostrar que el bot está "pensando"
                async with message.channel.typing():
                    # Decidir si es búsqueda o link
                    search_query = query if "http" in query else f"ytsearch:{query}"
                    
                    search_data = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ytdl.extract_info(search_query, download=False)
                    )

                    # Validación anti-NoneType
                    if search_data is None:
                        await message.channel.send("❌ YouTube no devolvió resultados. Prueba con un link directo.")
                        return

                    if 'entries' in search_data:
                        if len(search_data['entries']) == 0:
                            await message.channel.send("❌ No encontré resultados para tu búsqueda.")
                            return
                        video_url = search_data['entries'][0]['webpage_url']
                    else:
                        video_url = search_data.get('webpage_url') or search_data.get('url')

                if guild_id not in queues:
                    queues[guild_id] = []
                
                queues[guild_id].append(video_url)

                if not voice_clients[guild_id].is_playing():
                    await play_next(guild_id)
                    await message.channel.send(f"🎶 Reproduciendo ahora.")
                else:
                    await message.channel.send(f"✅ Añadido a la cola.")

            except Exception as e:
                print(f"Error en ?p: {e}")
                await message.channel.send(f"⚠️ Error al procesar: {str(e)[:100]}")

        # 🔊 JOIN / LEAVE / CONTROLES
        elif content == "?join":
            if message.author.voice:
                voice_clients[guild_id] = await message.author.voice.channel.connect()
                await message.add_reaction("🔊")

        elif content in ["?leave", "?disconnect"]:
            if guild_id in voice_clients:
                await voice_clients[guild_id].disconnect()
                del voice_clients[guild_id]
                await message.add_reaction("👋")

        elif content == "?pa":
            if guild_id in voice_clients and voice_clients[guild_id].is_playing():
                voice_clients[guild_id].pause()
                await message.add_reaction("⏸️")

        elif content == "?r":
            if guild_id in voice_clients and voice_clients[guild_id].is_paused():
                voice_clients[guild_id].resume()
                await message.add_reaction("▶️")

        elif content == "?s":
            if guild_id in voice_clients:
                voice_clients[guild_id].stop()
                await message.add_reaction("⏭️")

        elif content == "?f":
            if guild_id in voice_clients:
                queues[guild_id] = []
                voice_clients[guild_id].stop()
                await message.add_reaction("⏹️")

    client.run(TOKEN)