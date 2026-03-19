from typing import cast

import discord
import mafic
from discord import app_commands
from discord.ext import commands

from utils.music_player import (
    MusicControlView,
    MusicPlayer,
    create_track_embed,
    format_duration,
)


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_track_end(self, event: mafic.TrackEndEvent[MusicPlayer]) -> None:
        if "REPLACED" not in str(event.reason):
            await event.player.play_next()

    @app_commands.command(name="join", description="Зайду к вам в канал")
    async def join(self, interaction: discord.Interaction) -> None:
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
                embed = discord.Embed(
                    description="✅ Я уже сижу с вами!", color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            else:
                embed = discord.Embed(
                    description="❌ Я уже сижу в другом голосовом канале",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
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

    @app_commands.command(
        name="play", description="Включу музыку или добавлю ее в очередь"
    )
    @app_commands.describe(url="Ссылка на видео, плейлист или название")
    async def play(self, interaction: discord.Interaction, url: str) -> None:
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

    @app_commands.command(name="skip", description="Пропущу текущую песню")
    async def skip(self, interaction: discord.Interaction) -> None:
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

    @app_commands.command(name="queue", description="Покажу очередь песен")
    async def queue(self, interaction: discord.Interaction) -> None:
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
            for i, track in enumerate(player.queue, start=1):
                next_line = f"**{i}.** [{track.title}]({track.uri}) ({format_duration(track.length)})\n"

                if len(queue_text) + len(next_line) > 950:
                    queue_text += f"\n*...и еще {len(player.queue) - i + 1} треков*"
                    break

                queue_text += next_line

            embed.add_field(name="💕 Следующие песни:", value=queue_text, inline=False)
        else:
            embed.add_field(name="💕 Следующие песни:", value="*Пусто*", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="Очищу очередь песен")
    async def clear(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild or not guild.voice_client:
            await interaction.response.send_message(
                "❌ Я не в голосовом канале!", ephemeral=True
            )
            return

        player = cast(MusicPlayer, guild.voice_client)
        count = len(player.queue)

        if count == 0:
            embed = discord.Embed(
                description="Очередь и так пуста! ✨", color=discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        player.queue.clear()

        embed = discord.Embed(
            description=f"🗑️ Очередь очищена! Удалено треков: **{count}**",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    # same command but different aliases ==========================================
    async def _stop_logic(self, interaction: discord.Interaction) -> None:
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

    @app_commands.command(name="stop", description="Остановлю музыку и очищу очередь")
    async def stop(self, interaction: discord.Interaction) -> None:
        await self._stop_logic(interaction)

    @app_commands.command(name="leave", description="Выйду из канала")
    async def leave(self, interaction: discord.Interaction) -> None:
        await self._stop_logic(interaction)

    # =============================================================================

    @app_commands.command(name="volume", description="Изменю громкость песен")
    @app_commands.describe(level="Уровень громкости (от 0 до 100)")
    async def volume(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]
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


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
