import asyncio
import os
from typing import Any

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists("cookies.txt"):
    print("cookies.txt найден")
    with open("cookies.txt", "r") as f:
        first_line = f.readline()
        print(f"Первая строка: {first_line[:50]}...")
else:
    print("cookies.txt НЕ найден по пути /app/cookies.txt")

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Токен не найден! Проверьте файл .env")

intents = discord.Intents.default()
intents.message_content = True


class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Слэш-команды успешно синхронизированы!")


bot = MusicBot()

ytdl_format_options: Any = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "cookiefile": "cookies.txt",
}

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: Any, volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title", "Неизвестное название")
        self.url = data.get("webpage_url", "")
        self.thumbnail = data.get("thumbnail", "")
        self.uploader = data.get("uploader", "Неизвестный автор")
        self.duration = self.parse_duration(int(data.get("duration", 0)))

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        stream: bool = False,
    ):
        loop = loop or asyncio.get_running_loop()
        raw_data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if not raw_data:
            raise ValueError("Не удалось получить информацию о видео.")

        data: Any = raw_data
        if "entries" in data:
            data = data["entries"][0]

        video_url = data.get("url")
        if not video_url:
            raise ValueError("URL отсутствует.")

        filename = str(video_url) if stream else str(ytdl.prepare_filename(data))
        audio_source = discord.FFmpegPCMAudio(
            filename, before_options=FFMPEG_BEFORE_OPTIONS, options=FFMPEG_OPTIONS
        )

        return cls(audio_source, data=data)


class MusicControlView(discord.ui.View):
    def __init__(self, voice_client: discord.VoiceClient, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.voice_client = voice_client

    @discord.ui.button(label="⏸️ Пауза", style=discord.ButtonStyle.secondary)
    async def pause_resume_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.voice_client.is_connected():
            return

        if self.voice_client.is_paused():
            self.voice_client.resume()
            button.label = "⏸️ Пауза"
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)
        elif self.voice_client.is_playing():
            self.voice_client.pause()
            button.label = "▶️ Продолжить"
            button.style = discord.ButtonStyle.success
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message(
                "Сейчас ничего не играет.", ephemeral=True
            )

    @discord.ui.button(label="⏹️ Стоп", style=discord.ButtonStyle.danger)
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.voice_client.is_connected():
            await self.voice_client.disconnect()

            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            await interaction.response.edit_message(
                content="⏹️ Воспроизведение остановлено.", view=self
            )
        else:
            await interaction.response.send_message(
                "Я уже не в канале.", ephemeral=True
            )


@bot.event
async def on_ready():
    print(f"Бот {bot.user} успешно запущен и готов к работе!")
    await bot.change_presence(
        activity=discord.Streaming(name="(づ ◕‿◕ )づ", url="https://tallfly.me")
    )


@bot.tree.command(name="play", description="Воспроизводит музыку с кнопками управления")
@app_commands.describe(url="Ссылка на видео или название")
async def play(interaction: discord.Interaction, url: str):
    author = interaction.user
    if (
        not isinstance(author, discord.Member)
        or not author.voice
        or not author.voice.channel
    ):
        await interaction.response.send_message(
            "❌ Вы должны быть в голосовом канале!", ephemeral=True
        )
        return

    await interaction.response.defer()

    guild = interaction.guild
    if not guild:
        return

    voice_client = guild.voice_client
    if not isinstance(voice_client, discord.VoiceClient):
        vc = await author.voice.channel.connect()
        if not isinstance(vc, discord.VoiceClient):
            await interaction.followup.send("Не удалось подключиться к каналу.")
            return
        voice_client = vc

    try:
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        voice_client.play(player, after=lambda e: print(f"Ошибка: {e}") if e else None)

        embed = discord.Embed(
            title="Музыкальный плеер",
            description=f"**[{player.title}]({player.url})**",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=player.thumbnail)
        embed.add_field(name="Канал", value=player.uploader, inline=True)
        embed.add_field(name="Время", value=player.duration, inline=True)
        embed.set_footer(
            text=f"Запросил: {author.display_name}", icon_url=author.display_avatar.url
        )

        view = MusicControlView(voice_client=voice_client)

        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}")


@bot.tree.command(name="stop", description="Остановить музыку")
async def stop(interaction: discord.Interaction):
    guild = interaction.guild
    if guild and isinstance(guild.voice_client, discord.VoiceClient):
        await guild.voice_client.disconnect()

        embed = discord.Embed(
            description="⏹️ **Воспроизведение остановлено. Бот покинул канал.**",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "Я не играю музыку в данный момент.", ephemeral=True
        )


bot.run(TOKEN)
