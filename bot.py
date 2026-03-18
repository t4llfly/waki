import asyncio
import json
import os
from typing import Any, Dict, List, cast

import discord
import mafic
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Токен не найден в .env")

NODES_RAW = os.getenv("LAVALINK_NODES", "[]").strip("'").strip('"')
try:
    LAVALINK_NODES: List[Dict[str, Any]] = json.loads(NODES_RAW)
except json.JSONDecodeError as e:
    print(f"ОШИБКА JSON: {e}")
    LAVALINK_NODES = []

intents = discord.Intents.default()
intents.message_content = True


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)
        self.pool = mafic.NodePool(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()
        print("Слэш-команды синхронизированы!")
        asyncio.create_task(self.connect_lavalink())

    async def connect_lavalink(self) -> None:
        await asyncio.sleep(2)
        if not LAVALINK_NODES:
            print("ПРЕДУПРЕЖДЕНИЕ: Список нод пуст.")
            return

        for node_data in LAVALINK_NODES:
            try:
                await self.pool.create_node(
                    host=node_data["host"],
                    port=node_data["port"],
                    password=node_data["password"],
                    label=node_data["label"],
                    secure=node_data.get("secure", False),
                )
                print(f"Узел {node_data['label']} успешно подключен!")
            except Exception as e:
                print(
                    f"Не удалось подключить узел {node_data.get('label', 'Unknown')}: {e}"
                )


bot = MusicBot()

# lavalink patch ==============================================================
original_request = getattr(mafic.Node, "_Node__request")


async def patched_request(
    self: Any, method: str, path: str, *args: Any, **kwargs: Any
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
# =============================================================================


class MusicPlayer(mafic.Player[commands.Bot]):
    def __init__(
        self, client: commands.Bot, channel: discord.VoiceChannel | discord.StageChannel
    ) -> None:
        super().__init__(client, channel)
        self.queue: List[mafic.Track] = []

    async def play_next(self) -> None:
        if not self.queue:
            return

        next_track = self.queue.pop(0)

        await self.play(next_track)

        channel = self.channel
        if isinstance(channel, discord.TextChannel) or hasattr(channel, "send"):
            embed = create_track_embed(next_track)
            view = MusicControlView(player=self)
            await channel.send(embed=embed, view=view)  # type: ignore


@bot.event
async def on_track_end(event: mafic.TrackEndEvent[MusicPlayer]) -> None:
    if "REPLACED" not in str(event.reason):
        await event.player.play_next()


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


# embed
def create_track_embed(track: mafic.Track) -> discord.Embed:
    embed = discord.Embed(
        title=track.title,
        description=f"**[Ссылочка на оригинал]({track.uri})**",
        color=discord.Color.blurple(),
    )

    artwork = track.artwork_url
    if "youtube.com" in str(track.uri) or "youtu.be" in str(track.uri):
        artwork = f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg"

    if artwork:
        embed.set_image(url=artwork)

    embed.add_field(name="Канал", value=track.author or "Неизвестно", inline=True)
    embed.add_field(name="Время", value=format_duration(track.length), inline=True)
    return embed


class MusicControlView(discord.ui.View):
    def __init__(self, player: MusicPlayer, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.player = player

    @discord.ui.button(label="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_resume_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not self.player.connected:
            await interaction.response.send_message(
                "❌ Я не в голосовом канале!", ephemeral=True
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

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.primary)
    async def skip_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not self.player.connected or not self.player.current:
            await interaction.response.send_message(
                "❌ Сейчас ничего не играет.", ephemeral=True
            )
            return

        await self.player.stop()
        await interaction.response.send_message("⏭️ Пропускаю песню!", ephemeral=False)

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger)
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if self.player.connected:
            self.player.queue.clear()
            await self.player.disconnect()
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await interaction.response.edit_message(
                content="⏹️ Остановила песни и очистила очередь!", view=self
            )
        else:
            await interaction.response.send_message(
                "❌ Я уже не в канале.", ephemeral=True
            )


@bot.event
async def on_ready() -> None:
    print(f"Бот {bot.user} запущен!")
    await bot.change_presence(
        activity=discord.Streaming(name="(づ ◕‿◕ )づ", url="https://tallfly.me")
    )


@bot.tree.command(name="join", description="Зайду к вам в канал")
async def join(interaction: discord.Interaction) -> None:
    author = interaction.user

    if not isinstance(author, discord.Member) or not getattr(
        author.voice, "channel", None
    ):
        await interaction.response.send_message(
            "❌ Вы должны быть в голосовом канале!", ephemeral=True
        )
        return

    channel = getattr(author.voice, "channel")
    guild = interaction.guild

    if not guild:
        return

    if guild.voice_client:
        if getattr(guild.voice_client.channel, "id", None) == channel.id:
            await interaction.response.send_message(
                "✅ Я уже сижу с вами!", ephemeral=True
            )
            return
        else:
            await interaction.response.send_message(
                "❌ Я уже сижу в другом голосовом канале.", ephemeral=True
            )
            return

    try:
        vc = await channel.connect(cls=MusicPlayer)
        player = cast(MusicPlayer, vc)

        await player.set_volume(20)

        embed = discord.Embed(
            description=f"👋 Успешно зашла в **{channel.name}**! Могу включить вам музыку!",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Не смогла подключиться: {e}", ephemeral=True
        )


@bot.tree.command(name="play", description="Включу музыку или добавлю ее в очередь")
@app_commands.describe(url="Ссылка на видео, плейлист или название")
async def play(interaction: discord.Interaction, url: str) -> None:
    author = interaction.user
    if not isinstance(author, discord.Member) or not getattr(
        author.voice, "channel", None
    ):
        await interaction.response.send_message(
            "❌ Вы должны быть в голосовом канале!", ephemeral=True
        )
        return

    await interaction.response.defer()

    guild = interaction.guild
    if not guild:
        return

    player: MusicPlayer
    voice_client = guild.voice_client
    channel = getattr(author.voice, "channel")

    if not voice_client:
        vc = await channel.connect(cls=MusicPlayer)
        player = cast(MusicPlayer, vc)

        await player.set_volume(20)
    else:
        player = cast(MusicPlayer, voice_client)

    try:
        tracks = await player.fetch_tracks(url)
        if not tracks:
            return await interaction.followup.send("❌ Не нашла ничего по запросу.")

        if isinstance(tracks, mafic.Playlist):
            player.queue.extend(tracks.tracks)
            embed = discord.Embed(
                description=f"📂 Добавила плейлист **{tracks.name}** ({len(tracks.tracks)} песен) в очередь!",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)
            if not player.current:
                await player.play_next()
            return

        track = tracks[0]

        if player.current:
            player.queue.append(track)
            embed = create_track_embed(track)
            return await interaction.followup.send(embed=embed)

        await player.play(track)
        embed = create_track_embed(track)
        view = MusicControlView(player=player)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}")


@bot.tree.command(name="skip", description="Пропущу текущую песню")
async def skip(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if not guild or not guild.voice_client:
        await interaction.response.send_message(
            "❌ Я не в голосовом канале!", ephemeral=True
        )
        return

    player = cast(MusicPlayer, guild.voice_client)
    if player.current:
        await player.stop()
        embed = discord.Embed(
            description="⏭️ Пропускаю песню!", color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Сейчас ничего не играет", ephemeral=True
        )


@bot.tree.command(name="queue", description="Покажу очередь песен")
async def queue(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if not guild or not guild.voice_client:
        embed = discord.Embed(
            description="**❌ Очередь пуста (я не в канале)**",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    player = cast(MusicPlayer, guild.voice_client)

    if not player.queue and not player.current:
        embed = discord.Embed(
            description="**❌ Очередь пуста**",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        return

    embed = discord.Embed(title="📃 Очередь песен", color=discord.Color.blurple())

    if player.current:
        embed.add_field(
            name="🔊 Сейчас играет:",
            value=f"**[{player.current.title}]({player.current.uri}) - {player.current.author}**",
            inline=False,
        )

    if player.queue:
        queue_text = ""
        for i, track in enumerate(player.queue[:10], start=1):
            queue_text += f"**{i}.**[{track.title}]({track.uri}) ({format_duration(track.length)})\n"

        if len(player.queue) > 10:
            queue_text += f"\n*...и еще {len(player.queue) - 10} песен*"

        embed.add_field(name="💕 Следующие песни:", value=queue_text, inline=False)
    else:
        embed.add_field(name="💕 Следующие песни:", value="*Пусто*", inline=False)

    await interaction.response.send_message(embed=embed)


# same command but different aliases ==========================================
@bot.tree.command(name="stop", description="Остановлю музыку и очищу очередь")
async def stop(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if not guild:
        return

    player = cast(MusicPlayer, guild.voice_client)
    if player and player.connected:
        player.queue.clear()
        await player.disconnect()
        embed = discord.Embed(
            description="**⏹️ Остановила песни и очистила очередь!**",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Я не играю сейчас музыку.", ephemeral=True
        )


@bot.tree.command(name="leave", description="Выйду из канала")
async def leave(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if not guild:
        return

    player = cast(MusicPlayer, guild.voice_client)
    if player and player.connected:
        player.queue.clear()
        await player.disconnect()
        embed = discord.Embed(
            description="**⏹️ Остановила песни и очистила очередь!**",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Я не играю сейчас музыку.", ephemeral=True
        )


# =============================================================================


@bot.tree.command(name="volume", description="Изменю громкость песен")
@app_commands.describe(level="Уровень громкости (от 0 до 100)")
async def volume(
    interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]
) -> None:
    guild = interaction.guild
    if not guild or not guild.voice_client:
        await interaction.response.send_message(
            "❌ Я не в голосовом канале!", ephemeral=True
        )
        return

    player = cast(MusicPlayer, guild.voice_client)

    if not player.connected:
        await interaction.response.send_message(
            "❌ Я сейчас ничего не играю.", ephemeral=True
        )
        return

    await player.set_volume(level)

    if level == 0:
        embed = discord.Embed(
            description="🔇 Выключила звук (Громкость: 0%)",
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)
    elif level <= 30:
        embed = discord.Embed(
            description=f"🔉 Понизила громкость до **{level}%**",
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            description=f"🔊 Установила громкость на **{level}%**",
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)


bot.run(TOKEN)
