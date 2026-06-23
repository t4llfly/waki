from typing import cast

from aiohttp import web
from discord.ext import commands

from utils.music_player import MusicPlayer


class WebserverCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.app = web.Application(middlewares=[self.cors_middleware])
        self.setup_routes()
        self.runner = None

    @web.middleware
    async def cors_middleware(self, request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    def setup_routes(self):
        self.app.router.add_get("/api/status", self.get_status)
        self.app.router.add_get("/api/player", self.get_player)
        self.app.router.add_post("/api/skip", self.post_skip)

    async def get_status(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "online",
                "bot_name": str(self.bot.user),
                "ping_ms": round(self.bot.latency * 1000),
                "guilds": len(self.bot.guilds),
            }
        )

    async def get_player(self, request: web.Request) -> web.Response:
        player = None
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                break

        if not player:
            return web.json_response({"is_playing": False})

        channel_name = (
            getattr(player.channel, "name", "Unknown") if player.channel else "Unknown"
        )

        data = {
            "is_playing": player.current is not None,
            "is_paused": player.paused,
            "volume": getattr(player, "volume", 20),
            "channel_name": channel_name,
        }

        if player.current:
            track = player.current
            req = getattr(player, "current_requester", None)

            data["current"] = {
                "title": track.title,
                "author": track.author,
                "uri": track.uri,
                "position_ms": player.position,
                "length_ms": track.length,
                "artwork": track.artwork_url
                or f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg",
                "requester": req.display_name if req else "Unknown",
            }

        queue_data = []
        for item in player.queue:
            t = item["track"]
            r = item["requester"]
            queue_data.append(
                {
                    "title": t.title,
                    "length_ms": t.length,
                    "requester": r.display_name if r else "Unknown",
                }
            )

        data["queue"] = queue_data

        return web.json_response(data)

    async def post_skip(self, request: web.Request) -> web.Response:
        if not self.bot.guilds:
            return web.json_response({"error": "No guild"}, status=400)

        guild = self.bot.guilds[0]
        player = cast(MusicPlayer, guild.voice_client)

        if player and player.current:
            await player.stop()
            return web.json_response({"success": True, "message": "Track skipped"})

        return web.json_response({"error": "Nothing is playing"}, status=400)

    async def cog_load(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()
        print("Запустила API на порту 8080!")

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()
            print("Остановила API.")


async def setup(bot: commands.Bot):
    await bot.add_cog(WebserverCog(bot))
