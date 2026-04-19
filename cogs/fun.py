from __future__ import annotations

import json
import os
import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands


class FunCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.persona_path = "data/persona.json"
        self.quotes_path = "data/quotes.json"

    def load_json(self, path: str) -> dict:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # who game ========================================================================
    @app_commands.command(
        name="who", description="Выберу случайного участника для твоего вопроса"
    )
    @app_commands.describe(question="Твой вопрос (например: кто самый крутой?)")
    async def who(self, interaction: discord.Interaction, question: str) -> None:
        guild = interaction.guild
        if not guild:
            return

        data = self.load_json(self.persona_path)
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

    # quotes ==========================================================================
    quote_group = app_commands.Group(name="quote", description="Ваши цитаты")

    @quote_group.command(name="add", description="Сохраню гениальную фразу друга")
    @app_commands.describe(user="Кого цитируем?", text="Сама цитата")
    async def quote_add(
        self, interaction: discord.Interaction, user: discord.Member, text: str
    ) -> None:
        data = self.load_json(self.quotes_path)
        if "quotes" not in data:
            data["quotes"] = []

        date_str = datetime.now().strftime("%d.%m.%Y")

        new_quote = {
            "id": len(data["quotes"]) + 1,
            "user_id": user.id,
            "user_name": user.display_name,
            "text": text,
            "date": date_str,
            "added_by": interaction.user.display_name,
        }

        data["quotes"].append(new_quote)

        with open(self.quotes_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        embed = discord.Embed(
            description=f"✍️ *«{text}»*\n\n— **{user.mention}** ({date_str})",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Успешно сохранила цитату #{new_quote['id']}! ✨")

        await interaction.response.send_message(embed=embed)

    @quote_group.command(name="random", description="Вспомню случайную цитату")
    async def quote_random(self, interaction: discord.Interaction) -> None:
        data = self.load_json(self.quotes_path)
        quotes = data.get("quotes", [])

        if not quotes:
            await interaction.response.send_message(
                "📭 В цитатнике пусто. Сохрани что-нибудь через `/quote add`!",
                ephemeral=True,
            )
            return

        quote = random.choice(quotes)

        embed = discord.Embed(
            description=f"📜 *«{quote['text']}»*\n\n— <@{quote['user_id']}>",
            color=discord.Color.dark_gold(),
        )
        embed.set_footer(text=f"Цитата #{quote['id']} • Добавлена: {quote['date']}")

        await interaction.response.send_message(embed=embed)

    @quote_group.command(name="list", description="Покажу все цитаты человека")
    @app_commands.describe(user="Чьи цитаты ищем?")
    async def quote_list(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        data = self.load_json(self.quotes_path)
        quotes = data.get("quotes", [])

        user_quotes = [q for q in quotes if q.get("user_id") == user.id]

        if not user_quotes:
            await interaction.response.send_message(
                f"📭 Я не нашла ни одной цитаты {user.display_name}. Он(а) слишком молчаливый(ая)!",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📖 Золотые слова {user.display_name}", color=discord.Color.blue()
        )

        description = ""
        for i, q in enumerate(user_quotes[-10:], start=1):
            line = f"**#{q['id']}** *«{q['text']}»* ({q['date']})\n\n"
            if len(description) + len(line) > 3900:
                description += "*...и другие шедевры!*"
                break
            description += line

        embed.description = description
        embed.set_footer(text=f"Всего цитат: {len(user_quotes)}")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
