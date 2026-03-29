from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


class DeveloperCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    dev_group = app_commands.Group(
        name="dev", description="Команды управления разработчика"
    )

    @dev_group.command(name="load", description="Загрузить новый модуль")
    @app_commands.default_permissions(administrator=True)
    async def load(self, interaction: discord.Interaction, extension: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await self.bot.tree.sync()
            await interaction.followup.send(
                f"✅ Модуль `cogs/{extension}.py` успешно загружен!"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка при загрузке:\n```py\n{e}\n```")

    @dev_group.command(name="unload", description="Выключить модуль")
    @app_commands.default_permissions(administrator=True)
    async def unload(self, interaction: discord.Interaction, extension: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if extension == "developer":
            return await interaction.followup.send(
                "⚠️ Нельзя выгрузить модуль разработчика, иначе ты не сможешь его включить обратно!"
            )

        try:
            await self.bot.unload_extension(f"cogs.{extension}")
            await self.bot.tree.sync()
            await interaction.followup.send(
                f"🔌 Модуль `cogs/{extension}.py` успешно отключен."
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка при выгрузке:\n```py\n{e}\n```")

    @dev_group.command(name="reload", description="Перезагрузить модуль на лету")
    @app_commands.default_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction, extension: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await self.bot.tree.sync()
            await interaction.followup.send(
                f"♻️ Модуль `cogs/{extension}.py` успешно обновлен!"
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Ошибка при обновлении:\n```py\n{e}\n```"
            )

    @dev_group.command(
        name="say", description="[ADMIN] Отправлю сообщение от своего лица"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        text="Текст сообщения",
        channel="Канал, куда отправить (по умолчанию текущий)",
        reply_to_id="ID сообщения, на которое нужно ответить (необязательно)",
    )
    async def say(
        self,
        interaction: discord.Interaction,
        text: str,
        channel: discord.TextChannel | None = None,
        reply_to_id: str | None = None,
    ) -> None:
        target_channel = channel or interaction.channel

        if not isinstance(target_channel, discord.abc.Messageable):
            await interaction.response.send_message(
                "❌ В этот канал нельзя отправить сообщение!", ephemeral=True
            )
            return

        send_kwargs: dict[str, Any] = {"content": text}

        if reply_to_id:
            try:
                msg_id = int(reply_to_id)
                guild_id = interaction.guild_id
                channel_id = getattr(target_channel, "id", None)

                if guild_id and channel_id:
                    send_kwargs["reference"] = discord.MessageReference(
                        message_id=msg_id, channel_id=channel_id, guild_id=guild_id
                    )
            except ValueError:
                await interaction.response.send_message(
                    "❌ Неверный формат ID сообщения!", ephemeral=True
                )
                return

        try:
            await target_channel.send(**send_kwargs)

            channel_name = getattr(target_channel, "mention", "этот канал")

            await interaction.response.send_message(
                f"✅ Отправила сообщение в {channel_name}", ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У меня нет прав писать в этот канал!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperCog(bot))
