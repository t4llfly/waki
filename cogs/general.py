import json
import os
import random
from datetime import datetime

import discord
from discord.ext import commands, tasks


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_path = "data/responses.json"
        self.responses = self.load_responses()

        self.status_updater.start()

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

    async def cog_unload(self) -> None:
        self.status_updater.cancel()

    @tasks.loop(minutes=30)
    async def status_updater(self):
        await self.bot.wait_until_ready()

        hour = datetime.now().hour

        if 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 18:
            period = "day"
        elif 18 <= hour < 24:
            period = "evening"
        else:
            period = "night"

        status_data = self.responses.get("statuses", {}).get(period)
        if status_data:
            status_text = status_data["text"]

            await self.bot.change_presence(
                activity=discord.Streaming(name=status_text, url="https://tallfly.me")
            )

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
