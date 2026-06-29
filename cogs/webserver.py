from __future__ import annotations

import asyncio
import json
import os
from typing import Any, cast

import discord
import mafic
from aiohttp import web
from discord.ext import commands, tasks

from utils.music_player import MusicPlayer

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]


class WebserverCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.app = web.Application(middlewares=[self.cors_middleware])
        self.websockets: set[web.WebSocketResponse] = set()
        self.setup_routes()
        self.runner: web.AppRunner | None = None

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
        self.app.router.add_get("/bot/ws", self.websocket_handler)
        self.app.router.add_post("/bot/restart", self.post_restart)

    # state & broadcast =============================================================

    def get_full_state(self) -> dict:
        player = None
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                break

        if not player:
            return {
                "is_playing": False,
                "is_paused": False,
                "volume": 20,
                "channel_name": None,
                "current": None,
                "queue": [],
            }

        channel_name = (
            getattr(player.channel, "name", "Unknown") if player.channel else "Unknown"
        )
        raw_volume = getattr(player, "volume", 20)
        display_volume = raw_volume if raw_volume <= 100 else round(raw_volume / 10)

        data: dict[str, Any] = {
            "is_playing": player.current is not None,
            "is_paused": player.paused,
            "volume": display_volume,
            "channel_name": channel_name,
            "current": None,
            "queue": [],
        }

        if player.current:
            track = player.current
            req = getattr(player, "current_requester", None)

            artwork = track.artwork_url
            if "youtube.com" in str(track.uri) or "youtu.be" in str(track.uri):
                artwork = f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg"

            data["current"] = {
                "title": track.title,
                "author": track.author,
                "uri": track.uri,
                "position_ms": player.position,
                "length_ms": track.length,
                "artwork": artwork,
                "requester": getattr(req, "display_name", "Unknown")
                if req
                else "Unknown",
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
                        "requester": getattr(r, "display_name", "Unknown")
                        if r
                        else "Unknown",
                    }
                )

        data["queue"] = queue_data
        return data

    async def broadcast(self, event: str, data: dict):
        if not self.websockets:
            return

        packet = json.dumps({"event": event, "data": data})
        closed_ws = set()

        for ws in self.websockets:
            try:
                await ws.send_str(packet)
            except Exception:
                closed_ws.add(ws)
        self.websockets -= closed_ws

    async def send_state_update(self):
        await self.broadcast("PLAYER_STATE", self.get_full_state())

    # ===============================================================================

    # commands handling =============================================================

    async def handle_ws_message(self, ws: web.WebSocketResponse, msg: dict):
        action = msg.get("action")
        payload = msg.get("payload", {})
        request_id = msg.get("request_id")

        # Роутер команд
        if action == "play":
            result = await self.cmd_play(payload)
        elif action == "skip":
            result = await self.cmd_skip(payload)
        elif action == "volume":
            result = await self.cmd_volume(payload)
        elif action == "pause":
            result = await self.cmd_pause()
        elif action == "resume":
            result = await self.cmd_resume()
        elif action == "stop":
            result = await self.cmd_stop()
        else:
            result = {"error": f"Unknown action: {action}"}

        if request_id:
            await ws.send_json(
                {"event": "COMMAND_RESULT", "request_id": request_id, "data": result}
            )

        if "error" not in result and action in ["volume", "pause", "resume", "stop"]:
            await self.send_state_update()

    # ===============================================================================

    # commands ======================================================================

    async def cmd_play(self, payload: dict) -> dict:
        url = payload.get("url")
        user_id = payload.get("user_id")
        if not url or not user_id:
            return {"error": "Missing URL or user_id"}

        guild, member, voice_channel = None, None, None
        for g in self.bot.guilds:
            m = g.get_member(int(user_id))
            if (
                m
                and m.voice
                and m.voice.channel
                and isinstance(
                    m.voice.channel, (discord.VoiceChannel, discord.StageChannel)
                )
            ):
                guild, member, voice_channel = g, m, m.voice.channel
                break

        if not guild or not member or not voice_channel:
            return {"error": "Сначала зайди в голосовой канал!"}

        player: MusicPlayer
        voice_client = guild.voice_client
        if not voice_client:
            vc = await voice_channel.connect(cls=cast(Any, MusicPlayer))
            player = cast(MusicPlayer, vc)
            await player.set_volume(20)
            if guild.text_channels:
                player.text_channel = guild.text_channels[0]
        else:
            player = cast(MusicPlayer, voice_client)

        try:
            tracks = await player.fetch_tracks(url)
            if not tracks:
                return {"error": "Трек не найден"}

            is_playlist = isinstance(tracks, mafic.Playlist)
            if is_playlist:
                for t in tracks.tracks:
                    player.queue.append({"track": t, "requester": member})
            else:
                track = tracks[0]
                if player.current:
                    player.queue.append({"track": track, "requester": member})
                else:
                    player.current_requester = member
                    await player.play(track)

            await self.send_state_update()
            title = tracks.name if is_playlist else tracks[0].title
            return {"success": True, "title": title, "is_playlist": is_playlist}
        except Exception as e:
            return {"error": str(e)}

    async def cmd_skip(self, payload: dict) -> dict:
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                if player.current:
                    await player.stop()
                    return {"success": True}
        return {"error": "Nothing is playing"}

    async def cmd_volume(self, payload: dict) -> dict:
        level = payload.get("level")
        if level is None:
            return {"error": "Missing level"}
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                await player.set_volume(int(level))
                return {"success": True, "level": level}
        return {"error": "Player not found"}

    async def cmd_pause(self) -> dict:
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                if player.current and not player.paused:
                    await player.pause()
                    return {"success": True}
        return {"error": "Nothing to pause"}

    async def cmd_resume(self) -> dict:
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                if player.current and player.paused:
                    await player.resume()
                    return {"success": True}
        return {"error": "Nothing to resume"}

    async def cmd_stop(self) -> dict:
        for vc in self.bot.voice_clients:
            if getattr(vc, "connected", False):
                player = cast(MusicPlayer, vc)
                player.queue.clear()
                await player.stop()
                return {"success": True}
        return {"error": "Player not found"}

    # ===============================================================================

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websockets.add(ws)

        await ws.send_json({"event": "INITIAL_STATE", "data": self.get_full_state()})

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = msg.json()
                        asyncio.create_task(self.handle_ws_message(ws, data))
                    except Exception as e:
                        print(f"Ошибка WS сообщения: {e}")
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            self.websockets.remove(ws)
        return ws

    # event listeners ===============================================================

    @commands.Cog.listener()
    async def on_track_start(self, event: mafic.TrackStartEvent[MusicPlayer]) -> None:
        await self.send_state_update()

    @commands.Cog.listener()
    async def on_track_end(self, event: mafic.TrackEndEvent[MusicPlayer]) -> None:
        await asyncio.sleep(0.5)
        await self.send_state_update()

    # ===============================================================================

    async def post_restart(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            user_id = int(data.get("user_id", 0))
            if user_id not in ADMIN_IDS:
                return web.json_response(
                    {"error": "У тебя нет прав для такого! 😠"}, status=403
                )
            print(f"Перезагрузка по просьбе пользователя {user_id}")

            async def shutdown():
                await asyncio.sleep(1)
                await self.bot.close()

            asyncio.create_task(shutdown())
            return web.json_response(
                {"success": True, "message": "Я перезагружаюсь..."}
            )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def cog_load(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()

    async def cog_unload(self):
        for ws in set(self.websockets):
            await ws.close()
        if self.runner:
            await self.runner.cleanup()


async def setup(bot: commands.Bot):
    await bot.add_cog(WebserverCog(bot))
