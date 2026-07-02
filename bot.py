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
            print("ПРЕДУПРЕЖДЕНИЕ: Список узлов пуст.")
            return

        for node in list(self.pool.nodes):
            try:
                await self.pool.remove_node(node)
            except Exception:
                pass

        for node_data in LAVALINK_NODES:
            try:
                await self.pool.create_node(
                    host=node_data["host"],
                    port=node_data["port"],
                    password=node_data["password"],
                    label=node_data["label"],
                    secure=node_data.get("secure", False),
                    heartbeat=15,
                    timeout=10.0,
                )
                print(f"Узел {node_data['label']} успешно подключен!")
            except Exception as e:
                print(
                    f"Не удалось подключить узел {node_data.get('label', 'Unknown')}: {e}"
                )

        asyncio.create_task(self._node_health_monitor())

    async def _node_health_monitor(self) -> None:
        while not self.is_closed():
            await asyncio.sleep(30)

            for node_data in LAVALINK_NODES:
                label = node_data["label"]
                node = next((n for n in self.pool.nodes if n.label == label), None)

                if not node or not node.available:
                    print(f"Узел '{label}' недоступен, пытаюсь переподключить...")
                    try:
                        if node:
                            await self.pool.remove_node(node)
                        await self.pool.create_node(
                            host=node_data["host"],
                            port=node_data["port"],
                            password=node_data["password"],
                            label=label,
                            secure=node_data.get("secure", False),
                            heartbeat=15,
                            timeout=10.0,
                        )
                        print(f"Узел '{label}' восстановлен!")
                    except Exception as e:
                        print(f"❌ Не удалось восстановить узел '{label}': {e}")

    async def on_ready(self) -> None:
        print(f"Бот {self.user} запущен!")


if __name__ == "__main__":
    bot = MusicBot()
    bot.run(TOKEN)
