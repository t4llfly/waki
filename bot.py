import asyncio
import json
import os
from typing import Any, Dict, List

import discord
import mafic
from discord.ext import commands
from dotenv import load_dotenv

from utils.music_player import apply_mafic_patch

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Токен не найден в .env")

NODES_RAW = os.getenv("LAVALINK_NODES", "[]").strip("'").strip('"')
try:
    LAVALINK_NODES: List[Dict[str, Any]] = json.loads(NODES_RAW)
except json.JSONDecodeError as e:
    print(f"ОШИБКА JSON: {e}")
    LAVALINK_NODES = []


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.pool = mafic.NodePool(self)

    async def setup_hook(self) -> None:
        apply_mafic_patch(self)

        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")

        await self.tree.sync()
        print("Слэш-команды синхронизированы!")

        asyncio.create_task(self.connect_lavalink())

    async def connect_lavalink(self) -> None:
        await asyncio.sleep(2)
        if not LAVALINK_NODES:
            print("ПРЕДУПРЕЖДЕНИЕ: Список нод пуст.")
            return

        for node_data in LAVALINK_NODES:
            try:
                await self.pool.create_node(
                    host=node_data["host"],
                    port=node_data["port"],
                    password=node_data["password"],
                    label=node_data["label"],
                    secure=node_data.get("secure", False),
                )
                print(f"Узел {node_data['label']} успешно подключен!")
            except Exception as e:
                print(
                    f"Не удалось подключить узел {node_data.get('label', 'Unknown')}: {e}"
                )

    async def on_ready(self) -> None:
        print(f"Бот {self.user} запущен!")
        await self.change_presence(
            activity=discord.Streaming(name="(づ ◕‿◕ )づ", url="https://tallfly.me")
        )


if __name__ == "__main__":
    bot = MusicBot()
    bot.run(TOKEN)
