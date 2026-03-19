import json
import os
import random

import discord
from discord.ext import commands


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_path = "data/responses.json"
        self.responses = self.load_responses()

    def load_responses(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            print(f"⚠️ Файл {self.data_path} не найден!")
            return {
                "thanks": [],
                "praise": [],
                "thanks_replies": ["❤️"],
                "praise_replies": ["❤️"],
            }

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.lower()

        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )

        if not (is_mentioned or is_reply_to_bot):
            return

        if any(word in content for word in self.responses["thanks"]):
            await message.reply(random.choice(self.responses["thanks_replies"]))

        elif any(word in content for word in self.responses["praise"]):
            await message.reply(random.choice(self.responses["praise_replies"]))


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
