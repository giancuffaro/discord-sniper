"""
listener.py — sit on a Discord channel and fire.

Run it with:  python listener.py

It does four things and nothing else: connect, read every message in the
channels you named, run the message through the parser and the guards, and
send the order. There is no web page, no database, no charts. That is on
purpose — every extra thing is another thing that can be broken at 9:31.

Why discord.py instead of raw websockets: the gateway needs heartbeats,
RESUME after a drop, and session invalidation handling. Getting those subtly
wrong means the bot looks connected and silently stops receiving messages,
which is the worst possible failure for a trading bot. That library has had
those edge cases beaten out of it for years.
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import signals as sigmod
from guards import Guards
from execute import Executor

LOG_PATH = os.path.join(HERE, "trades.log")


def say(msg):
    line = "%s  %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_cfg():
    path = os.path.join(HERE, "settings.json")
    if not os.path.exists(path):
        say("There's no settings.json yet. Copy settings.example.json to "
            "settings.json and put your bot token and channel ID in it.")
        sys.exit(1)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        say("settings.json has a typo in it — %s on line %d. It's a JSON file, "
            "so every setting needs quotes around the name and a comma after it "
            "(except the last one)." % (e.msg, e.lineno))
        sys.exit(1)


def main():
    cfg = load_cfg()
    token = (cfg.get("bot_token") or "").strip()
    if not token or token.startswith("PASTE"):
        say("No bot token in settings.json. Open the Discord Developer Portal, "
            "make an application, add a Bot, and copy its token in.")
        sys.exit(1)

    try:
        import discord
    except ImportError:
        say("The discord library isn't installed. Run SETUP.bat (or: "
            "pip install -U discord.py) and try again.")
        sys.exit(1)

    guards = Guards(cfg, HERE)
    execu = Executor(cfg, log=say)

    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True      # privileged — must be ticked in the portal

    client = discord.Client(intents=intents, max_messages=None,
                            chunk_guilds_at_startup=False)

    @client.event
    async def on_ready():
        say("Connected as %s." % client.user)
        say(execu.describe())
        say("Listening to channel IDs: %s"
            % (", ".join(guards.channels) or "ALL (you should narrow this)"))
        say("Limits: %d contract(s) max, %d trades a day, %.0fs cooldown."
            % (guards.max_qty, guards.max_trades_per_day, guards.cooldown_s))
        if guards.killed():
            say("Heads up: the STOP file exists, so nothing will fire until you "
                "delete it.")
        execu.warm()

    @client.event
    async def on_message(m):
        # Fast path first: bail out before doing any real work.
        if m.author.id == client.user.id:
            return
        if guards.channels and str(m.channel.id) not in guards.channels:
            return

        text = m.content or ""
        if not text and m.embeds:
            # some rooms post signals as embeds, not plain text
            e = m.embeds[0]
            text = " ".join(x for x in (e.title, e.description) if x)

        sig = sigmod.parse(text, author=str(m.author), channel=str(m.channel),
                           cfg=cfg)
        if not sig.fire:
            return                       # silent — rooms are 95% chatter

        ok, why = guards.check(sig, m.channel.id, m.author.id, str(m.author),
                               msg_epoch=m.created_at.timestamp())
        if not ok:
            say("SKIPPED %s — %s   [%s]" % (sig.human(), why, text[:90]))
            return

        qty = guards.clamp_qty(sig.qty or 1)
        guards.record(sig)               # record BEFORE sending, so a crash
                                         # mid-order can't double-fire
        t0 = time.time()
        try:
            sent, msg = execu.fire(sig, qty)
        except Exception as ex:
            sent, msg = False, "unexpected problem: %s" % ex
            traceback.print_exc()
        say("%s %s x%d (%.0f ms) — %s"
            % ("FIRED" if sent else "FAILED", sig.human(), qty,
               (time.time() - t0) * 1000, msg))

    try:
        client.run(token, log_handler=None)
    except Exception as e:
        low = str(e).lower()
        if "privileged" in low or "intent" in low:
            say("Discord refused the connection because the Message Content "
                "intent is switched off. Go to the Developer Portal, open your "
                "app, click Bot, and turn on MESSAGE CONTENT INTENT.")
        elif "improper token" in low or "unauthorized" in low or "401" in low:
            say("Discord says that bot token is wrong. Copy it again from the "
                "Bot page — and note that resetting the token invalidates the "
                "old one.")
        else:
            say("Couldn't stay connected: %s" % str(e)[:200])
        sys.exit(1)


if __name__ == "__main__":
    main()
