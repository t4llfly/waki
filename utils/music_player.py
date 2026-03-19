from typing import Any

import discord
import mafic
from discord.ext import commands


# lavalink patch ==============================================================
def apply_mafic_patch(bot: commands.Bot):
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


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


# embed =======================================================================
def create_track_embed(track: mafic.Track, position: int = 0) -> discord.Embed:
    embed = discord.Embed(
        title=track.title,
        description=f"**[Ссылочка на оригинал]({track.uri})**",
        color=discord.Color.pink(),
    )

    if track.length > 0:
        bar_length = 15
        progress = int((position / track.length) * bar_length)

        progress = min(max(progress, 0), bar_length - 1)

        bar = "".join(["▬" if i != progress else "🔘" for i in range(bar_length)])

        time_info = f"`{format_duration(position)} / {format_duration(track.length)}`"
        embed.add_field(name="Прогресс", value=f"{time_info}\n{bar}", inline=False)

    artwork = track.artwork_url
    if "youtube.com" in str(track.uri) or "youtu.be" in str(track.uri):
        artwork = f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg"

    if artwork:
        embed.set_image(url=artwork)

    embed.add_field(name="Канал", value=track.author or "Неизвестно", inline=True)
    return embed


# =============================================================================


class MusicPlayer(mafic.Player[commands.Bot]):
    def __init__(
        self, client: commands.Bot, channel: discord.VoiceChannel | discord.StageChannel
    ) -> None:
        super().__init__(client, channel)
        self.queue: list[mafic.Track] = []

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
