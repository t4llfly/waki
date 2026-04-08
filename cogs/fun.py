from __future__ import annotations

import json
import os
import random

import discord
from discord import app_commands
from discord.ext import commands


class FunCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_path = "data/persona.json"

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

        data = self.load_responses()
        q_lower = question.lower()

        chosen_member: discord.Member | None = None
        response_text = ""

        # scripted responses
        scripted = data.get("scripted_who", [])
        for script in scripted:
            if any(key in q_lower for key in script.get("keys", [])):
                target_id = int(script.get("user_id", 0))
                member = guild.get_member(target_id)

                if member:
                    chosen_member = member
                    response_text = script.get("response", "Без сомнений, это")
                    break

        # unscripted random choice
        if not chosen_member:
            members: list[discord.Member] = []
            author = interaction.user

            if isinstance(author, discord.Member) and getattr(
                author.voice, "channel", None
            ):
                voice_channel = author.voice.channel  # type: ignore
                if voice_channel:
                    members = [m for m in voice_channel.members if not m.bot]

            if not members:
                members = [m for m in guild.members if not m.bot]

            if len(members) < 2:
                await interaction.response.send_message(
                    "Тут совсем никого нет... даже выбирать не из кого! 🥺"
                )
                return

            chosen_member = random.choice(members)
            responses = data.get("who_responses", ["Я думаю, это..."])
            response_text = random.choice(responses)

        embed = discord.Embed(
            description=f"❓ **Вопрос:** {question}\n✨ **{response_text}** {chosen_member.mention}!",
            color=discord.Color.random(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
