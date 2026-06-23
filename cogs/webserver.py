from __future__ import annotations

from typing import cast

import discord
import mafic
from aiohttp import web
from discord.ext import commands, tasks

from utils.music_player import MusicPlayer


class WebserverCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.app = web.Application(middlewares=[self.cors_middleware])
        self.websockets = set()
        self.setup_routes()
        self.runner = None
        self.broadcast_task.start()

    @web.middleware
    async def cors_middleware(self, request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    def setup_routes(self):
        self.app.router.add_get("/api/ws", self.websocket_handler)
        self.app.router.add_post("/api/skip", self.post_skip)
        self.app.router.add_post("/api/play", self.post_play)

    def get_player_data(self) -> dict:
        player = None
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                break

        if not player:
            return {"is_playing": False}

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
                "requester": getattr(req, "display_name", "Unknown"),
            }

        queue_data = []
        for item in getattr(player, "queue", []):
            t = item.get("track")
            r = item.get("requester")
            if t:
                queue_data.append(
                    {
                        "title": t.title,
                        "length_ms": t.length,
                        "requester": getattr(r, "display_name", "Unknown"),
                    }
                )

        data["queue"] = queue_data
        return data

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websockets.add(ws)
        await ws.send_json(self.get_player_data())

        try:
            async for msg in ws:
                pass
        finally:
            self.websockets.remove(ws)
        return ws

    @tasks.loop(seconds=1)
    async def broadcast_task(self):
        if not self.websockets:
            return

        data = self.get_player_data()
        for ws in list(self.websockets):
            try:
                await ws.send_json(data)
            except Exception:
                self.websockets.remove(ws)

    async def post_skip(self, request: web.Request) -> web.Response:
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                if player.current:
                    await player.stop()
                    return web.json_response({"success": True})
        return web.json_response({"error": "Nothing is playing"}, status=400)

    async def post_play(self, request: web.Request) -> web.Response:
        data = await request.json()
        url = data.get("url")
        user_id = data.get("user_id")

        if not url or not user_id:
            return web.json_response({"error": "Missing URL or user_id"}, status=400)

        guild: discord.Guild | None = None
        member: discord.Member | None = None
        voice_channel: discord.VoiceChannel | discord.StageChannel | None = None

        member = None
        guild = None
        for g in self.bot.guilds:
            m = g.get_member(int(user_id))
            if m and m.voice and m.voice.channel:
                if isinstance(
                    m.voice.channel, (discord.VoiceChannel, discord.StageChannel)
                ):
                    guild = g
                    member = m
                    voice_channel = m.voice.channel
                    break

        if not guild or not member or not voice_channel:
            return web.json_response(
                {"error": "Сначала зайди в голосовой канал в Дискорде!"}, status=400
            )

        player: MusicPlayer
        voice_client = guild.voice_client

        if not voice_client:
            from typing import Any

            vc = await voice_channel.connect(cls=cast(Any, MusicPlayer))
            player = cast(MusicPlayer, vc)
            await player.set_volume(20)
        else:
            player = cast(MusicPlayer, voice_client)

        try:
            tracks = await player.fetch_tracks(url)
            if not tracks:
                return web.json_response({"error": "Трек не найден"}, status=404)

            track = (
                tracks[0]
                if not isinstance(tracks, mafic.Playlist)
                else tracks.tracks[0]
            )

            if player.current:
                player.queue.append({"track": track, "requester": member})
            else:
                player.current_requester = member
                await player.play(track)

            return web.json_response({"success": True, "title": track.title})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def cog_load(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()

    async def cog_unload(self):
        self.broadcast_task.cancel()
        for ws in set(self.websockets):
            await ws.close()
        if self.runner:
            await self.runner.cleanup()


async def setup(bot: commands.Bot):
    await bot.add_cog(WebserverCog(bot))
