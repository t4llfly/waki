import json
import os
import random

import discord
from discord import app_commands
from discord.ext import commands


class FunCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_path = "data/responses.json"

    def load_responses(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @app_commands.command(
        name="who", description="Выберу случайного участника для твоего вопроса"
    )
    @app_commands.describe(question="Твой вопрос (например: кто самый крутой?)")
    async def who(self, interaction: discord.Interaction, question: str) -> None:
        guild = interaction.guild
        if not guild:
            return

        members: list[discord.Member] = []

        author = interaction.user
        if isinstance(author, discord.Member) and author.voice:
            voice_channel = author.voice.channel
            if voice_channel:
                members = [m for m in voice_channel.members if not m.bot]

        if not members:
            members = [m for m in guild.members if not m.bot]

        if not members:
            await interaction.response.send_message(
                "Тут совсем никого нет... даже выбирать не из кого! 🥺"
            )
            return

        chosen = random.choice(members)

        responses_data = self.load_responses()
        responses = responses_data.get("who_responses", ["Я думаю, это..."])

        embed = discord.Embed(
            description=f"❓ **Вопрос:** {question}\n✨ **{random.choice(responses)}** {chosen.mention}!",
            color=discord.Color.random(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
