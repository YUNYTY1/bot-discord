import discord
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('discord_token')

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    queues = {}
    voice_clients = {}
    history = {}

    volume_levels = {"low": 0.25, "mid": 0.5, "max": 1.0}
    current_volume = 0.25

    yt_dl_options = {"format": "bestaudio/best"}
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
            data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )

            if 'entries' in data:
                data = data['entries'][0]

            song = data['url']
            title = data.get('title', 'Unknown Title')

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
        print(f'{client.user} is now jamming 🎶')

    @client.event
    async def on_message(message):
        nonlocal current_volume

        if message.author == client.user:
            return

        if not message.guild:
            return

        guild_id = message.guild.id

        # ▶️ PLAY
        if message.content.startswith("?p "):
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

        # 🔊 JOIN
        elif message.content.startswith("?join"):
            try:
                if not message.author.voice:
                    await message.channel.send("❌ Debes estar en un canal de voz.")
                    return

                if guild_id in voice_clients and voice_clients[guild_id].is_connected():
                    await message.channel.send("✅ Ya estoy en un canal de voz.")
                else:
                    voice_client = await message.author.voice.channel.connect()
                    voice_clients[guild_id] = voice_client
                    await message.add_reaction("🔊")

            except Exception as e:
                print(f"Error en ?join: {e}")

        # 👋 DISCONNECT / LEAVE
        elif message.content.startswith("?disconnect") or message.content.startswith("?leave"):
            try:
                if guild_id in voice_clients and voice_clients[guild_id].is_connected():
                    await voice_clients[guild_id].disconnect()
                    del voice_clients[guild_id]
                    await message.add_reaction("👋")
                else:
                    await message.channel.send("❌ No estoy en un canal de voz.")
            except Exception as e:
                print(f"Error en disconnect: {e}")

        # ⏸️ PAUSE
        elif message.content.startswith("?pa"):
            try:
                voice_clients[guild_id].pause()
                await message.add_reaction("⏸️")
            except Exception as e:
                print(e)

        # ▶️ RESUME
        elif message.content.startswith("?r"):
            try:
                voice_clients[guild_id].resume()
                await message.add_reaction("▶️")
            except Exception as e:
                print(e)

        # ⏹️ STOP + SALIR
        elif message.content.startswith("?f"):
            try:
                queues[guild_id] = []
                voice_clients[guild_id].stop()
                await voice_clients[guild_id].disconnect()
                await message.add_reaction("⏹️")
            except Exception as e:
                print(e)

        # ⏭️ SKIP
        elif message.content.startswith("?s"):
            try:
                voice_clients[guild_id].stop()
                await play_next(guild_id)
                await message.add_reaction("⏭️")
            except Exception as e:
                print(e)

        # 🔊 VOLUMEN
        elif message.content.startswith("?v"):
            try:
                level = message.content.split()[1].lower()
                if level in volume_levels:
                    current_volume = volume_levels[level]
                    await message.channel.send(f"🔊 Volumen: {level}")
                else:
                    await message.channel.send("❌ Usa: low, mid o max.")
            except Exception as e:
                print(e)

        # 📜 HISTORIAL
        elif message.content.startswith("?historial"):
            try:
                songs = history.get(guild_id, [])
                if songs:
                    display = "\n".join([f"{i+1}. {s}" for i, s in enumerate(songs)])
                    await message.channel.send(f"🎶 Historial:\n{display}")
                else:
                    await message.channel.send("❌ No hay historial.")
            except Exception as e:
                print(e)

        # 🔁 REPLAY HISTORIAL
        elif message.content.startswith("?replay historial"):
            try:
                songs = history.get(guild_id, [])
                if songs:
                    queues[guild_id].extend(songs)
                    if not voice_clients[guild_id].is_playing():
                        await play_next(guild_id)
                    await message.channel.send("🔁 Reproduciendo historial.")
                else:
                    await message.channel.send("❌ No hay historial.")
            except Exception as e:
                print(e)

    client.run(TOKEN)