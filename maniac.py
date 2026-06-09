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

    volume_levels = {"low": 0.25, "mid": 0.5, "max": 1.0}
    current_volume = 0.5

    ytdl = yt_dlp.YoutubeDL({
        "format": "bestaudio/best",
        "quiet": True,
        "ignoreerrors": True
    })

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

            if not data:
                await play_next(guild_id)
                return

            # Si viene playlist, toma primero y mete resto en cola
            if 'entries' in data:
                entries = data['entries']
                for entry in entries[1:]:
                    if entry and 'webpage_url' in entry:
                        queues[guild_id].append(entry['webpage_url'])
                data = entries[0]

            song = data['url']
            title = data.get('title', 'Unknown')

            print(f"🎶 Reproduciendo: {title}")

            player = discord.FFmpegPCMAudio(song, **get_ffmpeg_options(current_volume))

            def after_playing(error):
                if error:
                    print(f"Error: {error}")
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
        print(f'{client.user} ONLINE 🎶')

    @client.event
    async def on_message(message):
        nonlocal current_volume

        if message.author == client.user or not message.guild:
            return

        guild_id = message.guild.id
        queues.setdefault(guild_id, [])

        # ▶️ PLAY
        if message.content.startswith("?p "):
            try:
                if not message.author.voice:
                    await message.channel.send("❌ Debes estar en un canal de voz.")
                    return

                if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
                    voice_clients[guild_id] = await message.author.voice.channel.connect()

                query = message.content[3:].strip()

                if "youtube.com" in query or "youtu.be" in query:
                    queues[guild_id].append(query)
                else:
                    search = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False)
                    )
                    url = search['entries'][0]['webpage_url']
                    queues[guild_id].append(url)

                if not voice_clients[guild_id].is_playing():
                    await play_next(guild_id)

                await message.add_reaction("🎵")

            except Exception as e:
                print(f"Error en ?p: {e}")

        # 🔊 JOIN
        elif message.content.startswith("?join"):
            if message.author.voice:
                voice_clients[guild_id] = await message.author.voice.channel.connect()
                await message.add_reaction("🔊")
            else:
                await message.channel.send("❌ Entra a un canal de voz.")

        # 👋 LEAVE
        elif message.content.startswith("?leave"):
            if guild_id in voice_clients:
                await voice_clients[guild_id].disconnect()
                await message.add_reaction("👋")

        # ⏸️ PAUSE
        elif message.content.startswith("?pa"):
            if guild_id in voice_clients:
                voice_clients[guild_id].pause()
                await message.add_reaction("⏸️")

        # ▶️ RESUME
        elif message.content.startswith("?r"):
            if guild_id in voice_clients:
                voice_clients[guild_id].resume()
                await message.add_reaction("▶️")

        # ⏭️ SKIP
        elif message.content.startswith("?s"):
            if guild_id in voice_clients:
                voice_clients[guild_id].stop()
                await message.add_reaction("⏭️")

        # ⏹️ STOP
        elif message.content.startswith("?f"):
            if guild_id in voice_clients:
                queues[guild_id] = []
                voice_clients[guild_id].stop()
                await voice_clients[guild_id].disconnect()
                await message.add_reaction("⏹️")

        # 🔊 VOLUMEN
        elif message.content.startswith("?v"):
            parts = message.content.split()
            if len(parts) < 2:
                await message.channel.send("❌ Usa: ?v low | mid | max")
                return

            level = parts[1].lower()
            if level in volume_levels:
                current_volume = volume_levels[level]
                await message.channel.send(f"🔊 Volumen: {level}")
            else:
                await message.channel.send("❌ Usa: low, mid o max.")

        # 📜 LISTA DE COMANDOS
        elif message.content.startswith("?list"):
            embed = discord.Embed(
                title="🎵 Comandos del Bot",
                color=discord.Color.blue()
            )

            embed.add_field(name="▶️ Play", value="?p nombre/link", inline=False)
            embed.add_field(name="🔊 Join", value="?join", inline=True)
            embed.add_field(name="👋 Leave", value="?leave", inline=True)
            embed.add_field(name="⏸️ Pause", value="?pa", inline=True)
            embed.add_field(name="▶️ Resume", value="?r", inline=True)
            embed.add_field(name="⏭️ Skip", value="?s", inline=True)
            embed.add_field(name="⏹️ Stop", value="?f", inline=True)
            embed.add_field(name="🔊 Volumen", value="?v low / mid / max", inline=False)

            await message.channel.send(embed=embed)

    client.run(TOKEN)