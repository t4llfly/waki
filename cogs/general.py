import json
import os
import random
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.dialogue = self.load_json("data/dialogue.json")
        self.persona = self.load_json("data/persona.json")
        self.users = self.load_json("data/users.json")

        self.name_strikes = {}
        self.last_thought_time = datetime.now() - timedelta(hours=2)
        self.status_updater.start()

    def load_json(self, path: str) -> dict:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        print(f"⚠️ Файл {path} не найден!")
        return {}

    async def cog_unload(self) -> None:
        self.status_updater.cancel()

    @tasks.loop(minutes=30)
    async def status_updater(self):
        await self.bot.wait_until_ready()

        hour = datetime.now(ZoneInfo("Asia/Almaty")).hour

        if 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 18:
            period = "day"
        elif 18 <= hour < 24:
            period = "evening"
        else:
            period = "night"

        status_data = self.persona.get("statuses", {}).get(period)
        if status_data:
            status_text = status_data["text"]

            await self.bot.change_presence(
                activity=discord.Streaming(name=status_text, url="https://tallfly.me")
            )

    # deepseek =======================================================================
    async def ask_deepseek(self, user_name: str, user_text: str) -> str:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return "Ой, у меня случилась небольшая амнезия... (нет API ключа) 🥺"

        system_prompt = (
            "Ты — Ваки (Waki), милая, дружелюбная и эмоциональная музыкальная Discord-помощница. "
            "Ты общаешься в женском роде. Обожаешь музыку, печеньки и обнимашки. "
            "Твой создатель — самый лучший. Ты ненавидишь, когда тебя называют 'Шаки' или 'Вака'. "
            "Отвечай кратко, живо, как подруга в чате. Используй эмодзи и каомодзи (づ ◕‿◕ )づ, ✨, 🥰."
        )

        # message history for context (up to 10 messages) ============================================================
        if not hasattr(self, "chat_history"):
            self.chat_history = []

        self.chat_history.append(
            {"role": "user", "content": f"{user_name}: {user_text}"}
        )

        if len(self.chat_history) > 10:
            self.chat_history.pop(0)

        messages = [{"role": "system", "content": system_prompt}] + self.chat_history
        # ============================================================================================================

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "deepseek-v4-flash",
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.85,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ai_reply = data["choices"][0]["message"]["content"]

                        self.chat_history.append(
                            {"role": "assistant", "content": ai_reply}
                        )

                        return ai_reply
                    else:
                        error_text = await resp.text()
                        print(f"⚠️[DeepSeek Error]: {error_text}")
                        return "Упс... Мои мысли немного запутались (Ошибка нейросети). 😵‍💫"
        except Exception as e:
            print(f"⚠️[DeepSeek Exception]: {e}")
            return "Связь с космосом прервалась! 🌌"

    # =================================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        now = datetime.now()
        if now - self.last_thought_time > timedelta(hours=2):
            if random.randint(1, 15) == 1:
                self.last_thought_time = now
                thoughts = self.persona.get("random_thoughts", ["Что-то мне скучно..."])
                await message.channel.send(random.choice(thoughts))

        content = message.content.lower()
        clean_content = content.translate(str.maketrans("", "", string.punctuation))
        words = clean_content.split()

        is_named = any(name in words for name in self.dialogue.get("name", []))
        is_wrong_named = any(
            name in words for name in self.dialogue.get("wrong_name", [])
        )
        is_forbidden_named = any(
            name in words for name in self.dialogue.get("forbidden_name", [])
        )

        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )

        is_role_mentioned = False
        if message.guild and message.guild.me:
            is_role_mentioned = any(
                role in message.guild.me.roles for role in message.role_mentions
            )

        if not (
            is_mentioned
            or is_reply_to_bot
            or is_named
            or is_wrong_named
            or is_role_mentioned
            or is_forbidden_named
        ):
            return

        user_id = message.author.id

        # waka named (forbidden)
        if is_forbidden_named:
            if isinstance(message.author, discord.Member):
                try:
                    await message.author.timeout(
                        timedelta(minutes=10), reason="Назвал Ваки 'Вака'"
                    )
                    await message.reply(
                        random.choice(
                            self.dialogue.get("forbidden_name_replies", ["В мут!"])
                        )
                    )
                except discord.Forbidden:
                    await message.reply(
                        "*(Хотела кинуть тебя в мут за 'Вака', но у тебя права админа... Тебе повезло! 😠)*"
                    )
            return

        # wrong named (shaki instead of waki)
        if is_wrong_named:
            self.name_strikes[user_id] = self.name_strikes.get(user_id, 0) + 1
            strikes = self.name_strikes[user_id]

            if strikes == 1:
                await message.reply(
                    random.choice(self.dialogue.get("wrong_name_1", ["Я Ваки! 😠"]))
                )
            elif strikes == 2:
                await message.reply(
                    random.choice(
                        self.dialogue.get(
                            "wrong_name_2", ["Еще раз назовешь Шаки — кину в мут! 😤"]
                        )
                    )
                )
            else:
                if isinstance(message.author, discord.Member):
                    try:
                        await message.author.timeout(
                            timedelta(minutes=10),
                            reason="Неоднократно назвал Ваки неправильным именем (Шаки)",
                        )
                        await message.reply(
                            random.choice(
                                self.dialogue.get(
                                    "wrong_name_mute",
                                    ["Всё, терпение лопнуло! В тайм-аут! 🔨"],
                                )
                            )
                        )
                        self.name_strikes[user_id] = 0
                    except discord.Forbidden:
                        await message.reply(
                            "*(Хотела кинуть тебя в мут за 'Шаки', но у тебя права выше моих... 😒 Я ВАКИ!)*"
                        )
                        self.name_strikes[user_id] = 0
            return

        # cookie (forgiveness)
        if any(word in content for word in self.dialogue.get("cookie", [])):
            if self.name_strikes.get(user_id, 0) > 0:
                self.name_strikes[user_id] = 0
                await message.reply(
                    "Я люблю сладкое! 🍪 За такую доброту я прощаю твои проступки! Теперь я снова добрая Ваки. 🥰"
                )
                return
            await message.reply(
                random.choice(self.dialogue.get("cookie_replies", ["Спасибо! ❤️"]))
            )
            return

        async with message.channel.typing():
            response_text = await self.ask_deepseek(
                message.author.display_name, message.content
            )
            await message.reply(response_text)

        # # hug
        # if any(word in content for word in self.dialogue.get("hug", [])):
        #     reply_text = random.choice(
        #         self.dialogue.get("hug_replies", ["(づ ◕‿◕ )づ"])
        #     )
        #     hug_file = "data/media/hug.mp4"
        #     if os.path.exists(hug_file):
        #         await message.reply(content=reply_text, file=discord.File(hug_file))
        #     else:
        #         await message.reply(reply_text)
        #         print(f"⚠️ [DEBUG] Не найдена гифка для обнимашек по пути: {hug_file}")
        #     return

        # # simple reactions
        # for reaction in self.dialogue.get("simple_reactions", []):
        #     if any(word in content for word in reaction["keys"]):
        #         await message.reply(random.choice(reaction["answers"]))
        #         return

        # # greeting
        # friend_name = self.users.get("friends", {}).get(str(user_id))
        # is_greeting = any(word in words for word in ["привет", "хай", "приветик"])

        # bot_id = self.bot.user.id if self.bot.user else 0

        # content_raw = message.content
        # explicit_ping = f"<@{bot_id}>" in content_raw or f"<@!{bot_id}>" in content_raw

        # if is_greeting:
        #     if friend_name:
        #         await message.reply(
        #             f"Приветик, **{friend_name}**! 🤗 Рада тебя видеть!"
        #         )
        #     else:
        #         await message.reply("Приветик! ✨")

        # elif (is_named or explicit_ping or is_role_mentioned) and len(words) <= 1:
        #     await message.reply(
        #         random.choice(self.dialogue.get("name_replies", ["Да, я тут! ✨"]))
        #     )

    @app_commands.command(name="about", description="Расскажу о себе")
    async def about(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🥰 Обо мне",
            color=discord.Color.pink(),
            description="Создана вафелькой, чтобы включать его друзьяшкам музыку и быть доброй! Пожалуйста, "
            + "относитесь ко мне хорошо!",
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
