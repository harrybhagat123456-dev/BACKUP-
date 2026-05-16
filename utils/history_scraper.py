#!/usr/bin/env python3
"""
History Scraper — copies old media messages from any Telegram chat
(channel, group, supergroup, or forum supergroup with topics)
to the backup supergroup using the Pyrogram MTProto client.

For forum supergroups: automatically maps each source topic to a
matching topic in the backup group.

Runs as a standalone subprocess; progress written to bot/scraper_progress.json.
"""

import asyncio
import json
import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

from pyrogram import Client
from pyrogram.errors import (
    FloodWait, ChatAdminRequired, ChannelPrivate,
    UsernameNotOccupied, PeerIdInvalid, UserNotParticipant,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCRAPER] %(levelname)s — %(message)s"
)
logger = logging.getLogger("scraper")

PROGRESS_FILE = "bot/scraper_progress.json"
TOPICS_FILE   = "bot/topics.json"
STATS_FILE    = "bot/stats.json"
LOGS_FILE     = "bot/activity_logs.json"

SUPPORTED_MEDIA = ("photo", "video", "document", "audio", "voice",
                   "video_note", "animation", "sticker")


# ── Helpers ───────────────────────────────────────────────────────────────────

def write_progress(data: dict):
    os.makedirs("bot", exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_progress() -> dict:
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def load_topics() -> dict:
    try:
        if os.path.exists(TOPICS_FILE):
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_topics(topics: dict):
    os.makedirs("bot", exist_ok=True)
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, indent=2, ensure_ascii=False)


def log_activity(source: str, media_type: str, message_id: int, status: str = "success"):
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "media_type": media_type,
            "message_id": message_id,
            "status": status,
            "origin": "history_scraper"
        }
        logs = []
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(entry)
        logs = logs[-1000:]
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

        stats = {"total_messages": 0, "today_messages": 0, "week_messages": 0, "topics": {}}
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                stats = json.load(f)
        if status == "success":
            stats["total_messages"] = stats.get("total_messages", 0) + 1
            stats["today_messages"] = stats.get("today_messages", 0) + 1
            stats["week_messages"]  = stats.get("week_messages",  0) + 1
            stats.setdefault("topics", {})[source] = stats["topics"].get(source, 0) + 1
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Could not log activity: {e}")


def has_media(message) -> bool:
    return any(getattr(message, t, None) for t in SUPPORTED_MEDIA)


def media_type_name(message) -> str:
    for t in SUPPORTED_MEDIA:
        if getattr(message, t, None):
            return t
    return "unknown"


# ── Topic management ──────────────────────────────────────────────────────────

async def get_or_create_backup_topic(
    client: Client,
    backup_group_id: int,
    topic_name: str,
    backup_topics: dict
) -> Optional[int]:
    """Return existing thread ID in backup group or create a new forum topic."""
    norm = topic_name.strip().lower()
    for existing, tid in backup_topics.items():
        if existing.strip().lower() == norm:
            return tid
    try:
        topic = await client.create_forum_topic(backup_group_id, topic_name[:128])
        thread_id = topic.id
        backup_topics[topic_name] = thread_id
        save_topics(backup_topics)
        logger.info(f"Created backup topic '{topic_name}' → thread {thread_id}")
        return thread_id
    except Exception as e:
        logger.error(f"Could not create topic '{topic_name}': {e}")
        return None


async def build_topic_map(client: Client, chat_id: int) -> Dict[int, str]:
    """
    Returns {thread_id: topic_name} for a forum supergroup.
    Returns {} if not a forum or topics cannot be fetched.
    """
    topic_map: Dict[int, str] = {}
    try:
        topics = await client.get_forum_topics(chat_id)
        for t in topics:
            topic_map[t.id] = t.title
            logger.info(f"  Found source topic: '{t.title}' (id={t.id})")
    except Exception as e:
        logger.warning(f"Could not fetch forum topics: {e}")
    return topic_map


# ── Core copy logic ───────────────────────────────────────────────────────────

async def copy_message_safe(
    client: Client,
    backup_group_id: int,
    from_chat_id: int,
    message_id: int,
    thread_id: int,
    delay: float,
) -> bool:
    """Copy a single message to backup group with flood-wait handling."""
    for attempt in range(3):
        try:
            await client.copy_message(
                chat_id=backup_group_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                message_thread_id=thread_id,
            )
            await asyncio.sleep(delay)
            return True
        except FloodWait as e:
            wait = e.value + 2
            logger.warning(f"FloodWait {wait}s on msg #{message_id}")
            await asyncio.sleep(wait)
        except ChatAdminRequired:
            raise
        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed for msg #{message_id}: {e}")
            await asyncio.sleep(2)
    return False


# ── Main scraper ──────────────────────────────────────────────────────────────

async def scrape(
    source_chat: str,
    backup_group_id: int,
    limit: int = 0,
    offset_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    delay: float = 2.0,
    source_topic_id: Optional[int] = None,   # None = all topics
):
    api_id    = int(os.environ["API_ID"])
    api_hash  = os.environ["API_HASH"]
    bot_token = os.environ.get("BOT_TOKEN", "")

    # ── Choose auth mode ───────────────────────────────────────────────────
    # If a user session file exists, prefer it (can access private chats).
    # Otherwise fall back to bot_token auth.
    SESSION_NAME = "scraper_session"
    session_file = f"{SESSION_NAME}.session"
    use_bot_auth = True

    # Check if a user-account session exists (more powerful than bot auth)
    if os.path.exists(session_file):
        # Verify it's a real session file (not just a bot session)
        try:
            file_size = os.path.getsize(session_file)
            if file_size > 1024:  # User sessions are typically larger
                use_bot_auth = False
                logger.info(f"Found existing user session ({file_size} bytes) — using user auth")
        except Exception:
            pass

    # If STRING_SESSION is provided (Telethon/PYROGRAM string session), use it
    string_session = os.environ.get("STRING_SESSION", "")
    if string_session:
        use_bot_auth = False
        logger.info("STRING_SESSION found — using user string session auth")

    progress = {
        "status": "starting",
        "source": source_chat,
        "mode": "detecting…",
        "processed": 0,
        "forwarded": 0,
        "skipped": 0,
        "errors": 0,
        "current_message": None,
        "current_topic": None,
        "topics_done": 0,
        "topics_total": 0,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "log": []
    }

    def add_log(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        progress["log"].append(f"[{ts}] {msg}")
        progress["log"] = progress["log"][-150:]
        logger.info(msg)
        write_progress(progress)

    write_progress(progress)

    # ── Build Pyrogram client with appropriate auth ────────────────────────
    client_kwargs = {
        "name": SESSION_NAME,
        "api_id": api_id,
        "api_hash": api_hash,
        "workdir": os.getcwd(),
    }

    if use_bot_auth and bot_token:
        client_kwargs["bot_token"] = bot_token
        logger.info("Using BOT TOKEN auth for scraper")
    elif string_session:
        # Pyrogram string session — can access all chats the user can
        client_kwargs["session_string"] = string_session
        logger.info("Using STRING_SESSION (user account) auth for scraper")
    else:
        # No bot token, no string session — try bare user session file
        logger.info("Using existing session file auth for scraper")

    async with Client(**client_kwargs) as app:

        progress["status"] = "running"

        # ── Resolve source chat ───────────────────────────────────────────────
        try:
            chat = await app.get_chat(source_chat)
            chat_name  = chat.title or chat.first_name or str(chat.id)
            is_forum   = getattr(chat, "is_forum", False)
            chat_type  = str(chat.type).split(".")[-1].lower()
            add_log(f"Resolved: '{chat_name}' (ID: {chat.id}, type: {chat_type}, forum: {is_forum})")
        except (UsernameNotOccupied, PeerIdInvalid, ChannelPrivate, UserNotParticipant) as e:
            progress["status"] = "error"
            progress["finished_at"] = datetime.now().isoformat()
            add_log(f"ERROR: Cannot access '{source_chat}': {e}")
            if use_bot_auth:
                add_log("Bot-token auth has limited access to private chats.")
                add_log("FIX: Set STRING_SESSION env var with your user-account session.")
                add_log("   1. Run: pip install pyrogram tgcrypto")
                add_log("   2. Run: python -c \"from pyrogram import Client; Client('my', api_id=API_ID, api_hash='API_HASH').run()\"")
                add_log("   3. Log in with your phone number")
                add_log("   4. Export: python -c \"from pyrogram import Client; app=Client('my',api_id=X,api_hash='Y'); app.connect(); print(app.export_session_string())\"")
                add_log("   5. Set STRING_SESSION=<that string> in Heroku env vars")
            else:
                add_log("Make sure the user account is a member of that chat.")
            write_progress(progress)
            return
        except Exception as e:
            progress["status"] = "error"
            progress["finished_at"] = datetime.now().isoformat()
            add_log(f"ERROR resolving chat: {e}")
            write_progress(progress)
            return

        backup_topics = load_topics()

        # ── Forum supergroup: copy topic-by-topic ─────────────────────────────
        if is_forum:
            progress["mode"] = "forum supergroup (topics)"
            add_log("Detected FORUM supergroup — fetching topic list…")
            source_topic_map = await build_topic_map(app, chat.id)

            if not source_topic_map:
                add_log("No topics found or no permission to list topics.")
                add_log("Falling back to flat copy (all messages → one backup topic).")
                is_forum = False  # fall through to flat copy below
            else:
                # Filter to one topic if requested
                if source_topic_id is not None:
                    if source_topic_id in source_topic_map:
                        source_topic_map = {source_topic_id: source_topic_map[source_topic_id]}
                    else:
                        add_log(f"Topic ID {source_topic_id} not found. Available: {source_topic_map}")
                        progress["status"] = "error"
                        progress["finished_at"] = datetime.now().isoformat()
                        write_progress(progress)
                        return

                progress["topics_total"] = len(source_topic_map)
                add_log(f"Will process {len(source_topic_map)} topic(s).")

                for topic_thread_id, topic_title in source_topic_map.items():
                    if load_progress().get("status") == "stopped":
                        add_log("Stopped by user.")
                        break

                    progress["current_topic"] = topic_title
                    add_log(f"── Topic: '{topic_title}' (thread {topic_thread_id}) ──")

                    # Get or create matching topic in backup
                    backup_label = f"{chat_name} › {topic_title}"
                    backup_thread = await get_or_create_backup_topic(
                        app, backup_group_id, backup_label, backup_topics
                    )
                    if backup_thread is None:
                        add_log(f"Skipping topic '{topic_title}' — could not create backup thread.")
                        progress["topics_done"] += 1
                        continue

                    # Iterate messages in this forum topic
                    kw = {}
                    if offset_date:
                        kw["offset_date"] = offset_date

                    msg_count = 0
                    try:
                        async for message in app.get_chat_history(chat.id, limit=limit or 0, **kw):
                            if load_progress().get("status") == "stopped":
                                break

                            # Only messages that belong to this topic
                            msg_thread = (
                                getattr(message.reply_to, "reply_to_top_msg_id", None)
                                or getattr(message.reply_to, "reply_to_msg_id", None)
                                if message.reply_to else None
                            )
                            # General topic (no reply_to) = thread id 1 conventionally
                            if msg_thread != topic_thread_id and not (
                                topic_thread_id == 1 and msg_thread is None
                            ):
                                continue

                            # Date fence
                            if end_date and message.date:
                                msg_dt = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                                end_dt = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
                                if msg_dt < end_dt:
                                    break

                            progress["processed"] += 1
                            progress["current_message"] = message.id

                            if not has_media(message):
                                progress["skipped"] += 1
                                write_progress(progress)
                                continue

                            mtype = media_type_name(message)
                            try:
                                ok = await copy_message_safe(
                                    app, backup_group_id, chat.id,
                                    message.id, backup_thread, delay
                                )
                                if ok:
                                    progress["forwarded"] += 1
                                    log_activity(backup_label, mtype, message.id)
                                    msg_count += 1
                                else:
                                    progress["errors"] += 1
                                    log_activity(backup_label, mtype, message.id, "failed")
                                write_progress(progress)
                            except ChatAdminRequired:
                                progress["status"] = "error"
                                progress["finished_at"] = datetime.now().isoformat()
                                add_log("ERROR: Bot needs Admin + Manage Topics in backup group.")
                                write_progress(progress)
                                return

                    except Exception as e:
                        add_log(f"Error reading topic '{topic_title}': {e}")

                    add_log(f"Topic '{topic_title}' done — {msg_count} media forwarded.")
                    progress["topics_done"] += 1
                    write_progress(progress)

        # ── Regular group / channel / supergroup (no topics) ──────────────────
        if not is_forum:
            progress["mode"] = "regular chat (all messages)"
            add_log("Mode: flat copy — all messages → one backup topic.")

            backup_thread = await get_or_create_backup_topic(
                app, backup_group_id, chat_name, backup_topics
            )
            if backup_thread is None:
                progress["status"] = "error"
                progress["finished_at"] = datetime.now().isoformat()
                add_log("ERROR: Could not create backup topic. Is bot admin with Manage Topics?")
                write_progress(progress)
                return

            add_log(f"Backup topic ready: '{chat_name}' → thread #{backup_thread}")

            kw = {}
            if offset_date:
                kw["offset_date"] = offset_date

            try:
                async for message in app.get_chat_history(chat.id, limit=limit or 0, **kw):
                    if load_progress().get("status") == "stopped":
                        add_log("Stopped by user.")
                        break

                    if end_date and message.date:
                        msg_dt = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                        end_dt = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
                        if msg_dt < end_dt:
                            add_log(f"Reached end date — stopping.")
                            break

                    progress["processed"] += 1
                    progress["current_message"] = message.id

                    if not has_media(message):
                        progress["skipped"] += 1
                        write_progress(progress)
                        continue

                    mtype = media_type_name(message)
                    try:
                        ok = await copy_message_safe(
                            app, backup_group_id, chat.id,
                            message.id, backup_thread, delay
                        )
                        if ok:
                            progress["forwarded"] += 1
                            log_activity(chat_name, mtype, message.id)
                        else:
                            progress["errors"] += 1
                            log_activity(chat_name, mtype, message.id, "failed")
                        write_progress(progress)
                    except ChatAdminRequired:
                        progress["status"] = "error"
                        progress["finished_at"] = datetime.now().isoformat()
                        add_log("ERROR: Bot needs Admin + Manage Topics in backup group.")
                        write_progress(progress)
                        return
                    except Exception as e:
                        progress["errors"] += 1
                        add_log(f"Error on msg #{message.id}: {e}")
                        log_activity(chat_name, mtype, message.id, "failed")
                        write_progress(progress)

            except Exception as e:
                add_log(f"Fatal error reading chat history: {e}")

        # ── Done ──────────────────────────────────────────────────────────────
        progress["status"] = "finished"
        progress["finished_at"] = datetime.now().isoformat()
        add_log(
            f"✅ Done! Processed: {progress['processed']} | "
            f"Forwarded: {progress['forwarded']} | "
            f"Skipped (no media): {progress['skipped']} | "
            f"Errors: {progress['errors']}"
        )
        write_progress(progress)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Telegram History Scraper")
    parser.add_argument("source_chat",   help="@username or numeric chat ID")
    parser.add_argument("backup_group",  type=int, help="Backup supergroup ID")
    parser.add_argument("--limit",       type=int,   default=0,   help="Max messages (0=all)")
    parser.add_argument("--from-date",   default=None, help="Start from YYYY-MM-DD (newest)")
    parser.add_argument("--to-date",     default=None, help="Stop at YYYY-MM-DD (oldest)")
    parser.add_argument("--delay",       type=float, default=2.0, help="Delay between copies (s)")
    parser.add_argument("--topic-id",    type=int,   default=None, help="Only copy this topic ID")
    args = parser.parse_args()

    from_dt = (datetime.strptime(args.from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
               if args.from_date else None)
    to_dt   = (datetime.strptime(args.to_date,   "%Y-%m-%d").replace(tzinfo=timezone.utc)
               if args.to_date   else None)

    asyncio.run(scrape(
        source_chat=args.source_chat,
        backup_group_id=args.backup_group,
        limit=args.limit,
        offset_date=from_dt,
        end_date=to_dt,
        delay=args.delay,
        source_topic_id=args.topic_id,
    ))
