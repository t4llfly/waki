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


async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperCog(bot))
