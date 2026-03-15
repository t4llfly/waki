import asyncio
import json
import os
from typing import Any, cast

import discord
import mafic
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Токен не найден! Проверьте файл .env")

NODES_RAW = os.getenv("LAVALINK_NODES", "[]")
try:
    LAVALINK_NODES: list[dict[str, Any]] = json.loads(NODES_RAW)
except json.JSONDecodeError:
    print("ОШИБКА: Неверный формат LAVALINK_NODES в .env. Ожидался JSON.")
    LAVALINK_NODES = []

intents = discord.Intents.default()
intents.message_content = True


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)
        self.pool = mafic.NodePool(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()
        print("Слэш-команды синхронизированы")
        asyncio.create_task(self.connect_lavalink())

    async def connect_lavalink(self) -> None:
        await asyncio.sleep(2)

        if not LAVALINK_NODES:
            print("ПРЕДУПРЕЖДЕНИЕ: Список нод пуст. Бот не сможет играть музыку.")
            return

        for node_data in LAVALINK_NODES:
            try:
                await self.pool.create_node(
                    host=node_data["host"],
                    port=node_data["port"],
                    password=node_data["password"],
                    label=node_data["label"],
                    secure=node_data["secure"],
                )
                print(f"Узел {node_data['label']} успешно подключен!")
            except Exception as e:
                print(f"Не удалось подключить узел {node_data['label']}: {e}")


bot = MusicBot()


original_request = getattr(mafic.Node, "_Node__request")


async def patched_request(
    self: mafic.Node, method: str, path: str, *args: Any, **kwargs: Any
) -> Any:
    payload = kwargs.get("json")
    if payload is None and len(args) > 0:
        payload = args[0]

    if method == "PATCH" and "/players/" in path and isinstance(payload, dict):
        if "voice" in payload:
            try:
                guild_id_str = path.split("/")[-1].split("?")[0]
                guild = bot.get_guild(int(guild_id_str))
                if guild:
                    voice_state = getattr(guild.me, "voice", None)
                    channel = getattr(voice_state, "channel", None)
                    if channel:
                        payload["voice"]["channelId"] = str(channel.id)
            except Exception as e:
                print(f"Ошибка в патче: {e}")

    return await original_request(self, method, path, *args, **kwargs)


setattr(mafic.Node, "_Node__request", patched_request)


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class MusicControlView(discord.ui.View):
    def __init__(
        self, player: mafic.Player[commands.Bot], timeout: float | None = None
    ):
        super().__init__(timeout=timeout)
        self.player = player

    @discord.ui.button(label="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_resume_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not self.player.connected:
            await interaction.response.send_message(
                "Бот не подключен к каналу.", ephemeral=True
            )
            return

        if self.player.paused:
            await self.player.resume()
            button.label = "⏸️"
            button.style = discord.ButtonStyle.secondary
        else:
            await self.player.pause()
            button.label = "▶️"
            button.style = discord.ButtonStyle.success

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger)
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.player.connected:
            await self.player.disconnect()
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
async def on_ready() -> None:
    print(f"Бот {bot.user} успешно запущен!")
    await bot.change_presence(
        activity=discord.Streaming(name="(づ ◕‿◕ )づ", url="https://tallfly.me")
    )


@bot.tree.command(name="play", description="Воспроизводит музыку с YouTube")
@app_commands.describe(url="Ссылка на видео или название")
async def play(interaction: discord.Interaction, url: str) -> None:
    author = interaction.user
    if not isinstance(author, discord.Member) or not getattr(
        author.voice, "channel", None
    ):
        await interaction.response.send_message(
            "Вы должны быть в голосовом канале!", ephemeral=True
        )
        return

    await interaction.response.defer()

    guild = interaction.guild
    if not guild:
        return

    player: mafic.Player[commands.Bot]
    voice_client = guild.voice_client
    channel = getattr(author.voice, "channel")

    if not voice_client:
        vc = await channel.connect(cls=mafic.Player)
        player = cast(mafic.Player[commands.Bot], vc)
    else:
        player = cast(mafic.Player[commands.Bot], voice_client)

    try:
        tracks = await player.fetch_tracks(url)
        if not tracks:
            await interaction.followup.send("По вашему запросу ничего не найдено.")
            return

        track = tracks.tracks[0] if isinstance(tracks, mafic.Playlist) else tracks[0]

        await player.play(track)

        embed = discord.Embed(
            title=track.title,
            description=f"**[Слушать на Youtube]({track.uri})**",
            color=discord.Color.blurple(),
        )

        artwork = track.artwork_url
        if "youtube.com" in str(track.uri) or "youtu.be" in str(track.uri):
            artwork = f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg"

        if artwork:
            embed.set_image(url=artwork)

        embed.add_field(name="Канал", value=track.author or "Неизвестно", inline=True)
        embed.add_field(name="Время", value=format_duration(track.length), inline=True)
        embed.set_footer(
            text=f"Запросил: {author.display_name}", icon_url=author.display_avatar.url
        )

        view = MusicControlView(player=player)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await interaction.followup.send(f"Произошла ошибка: {e}")


@bot.tree.command(name="stop", description="Остановить музыку")
async def stop(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if not guild:
        return

    player = cast(mafic.Player[commands.Bot], guild.voice_client)
    if player and player.connected:
        await player.disconnect()
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
