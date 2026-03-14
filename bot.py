import os
import math
import logging
import datetime
import socket
import struct
import time
import pytz
import logging.config

# ── Pure-Python NTP clock sync ─────────────────────────────────────────────────
# Fixes: pyrogram.errors.BadMsgNotification [16] msg_id too low (clock drift)
# Uses no external binaries — works on any Docker/Render container.
def _sync_clock_via_ntp(host: str = "time.google.com", port: int = 123) -> None:
    """
    Query an NTP server and patch time.time so Pyrogram generates valid msg_ids.
    Falls back silently if the socket cannot reach the NTP host.
    """
    try:
        NTP_DELTA = 2208988800  # seconds between 1900-01-01 and 1970-01-01
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(5)
        data = b'\x1b' + 47 * b'\0'
        client.sendto(data, (host, port))
        data, _ = client.recvfrom(1024)
        client.close()

        if data:
            unpacked = struct.unpack('!12I', data)
            ntp_time = unpacked[10] + float(unpacked[11]) / 2**32
            ntp_epoch = ntp_time - NTP_DELTA
            drift = ntp_epoch - time.time()

            if abs(drift) > 1:  # only patch if drift > 1 second
                _real_time = time.time

                def _patched_time():
                    return _real_time() + drift

                time.time = _patched_time
                print(f"[NTP] Clock corrected by {drift:+.3f}s using {host}")
            else:
                print(f"[NTP] Clock is in sync (drift={drift:+.3f}s)")
    except Exception as e:
        print(f"[NTP] Clock sync skipped: {e}")

_sync_clock_via_ntp()
# ──────────────────────────────────────────────────────────────────────────────

from pyrogram.errors import BadRequest, Unauthorized
from pyrogram import Client
from pyrogram import types
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL, UPTIME, WEBHOOK, LOG_MSG
from utils import temp, __repo__, __license__, __copyright__, __version__
from typing import Union, Optional, AsyncGenerator
from plugins import web_server
from aiohttp import web

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.config.fileConfig("logging.conf")
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("cinemagoer").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="MoviiWrld-Bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=10,
        )

    async def start(self):
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats

        await super().start()
        await Media.ensure_indexes()

        me = await self.get_me()
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.id = me.id
        self.name = me.first_name
        self.mention = me.mention
        self.username = me.username
        self.log_channel = LOG_CHANNEL
        self.uptime = UPTIME

        curr = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
        date = curr.strftime('%d %B, %Y')
        tame = curr.strftime('%I:%M:%S %p')

        log_text = LOG_MSG.format(
            me.first_name, date, tame,
            __repo__, __version__, __license__, __copyright__
        )
        logger.info(log_text)

        try:
            await self.send_message(
                LOG_CHANNEL,
                text=log_text,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Bot isn't able to send message to LOG_CHANNEL\n{e}")

        if WEBHOOK is True:
            app = web.AppRunner(await web_server())
            await app.setup()
            await web.TCPSite(app, "0.0.0.0", 8080).start()
            logger.info("Web Response Is Running......🕸️")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot is restarting... ♻️")

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            messages = await self.get_messages(
                chat_id, list(range(current, current + new_diff + 1))
            )
            for message in messages:
                yield message
                current += 1


Bot().run()
