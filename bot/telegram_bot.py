#!/usr/bin/env python3
"""
Telegram Bot to forward media from groups/channels to a backup supergroup
Organizes media into topics by source group/channel
"""

import json
import logging
import os
import time
import re
import unicodedata
import tempfile
from typing import Dict, Optional, List
from datetime import datetime

import telebot
from telebot.types import Message
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot settings
BOT_TOKEN            = os.getenv('BOT_TOKEN')
BACKUP_GROUP_ID_STR  = os.getenv('BACKUP_GROUP_ID')
OWNER_ID_STR         = os.getenv('OWNER_ID', '')

# Validate and convert BACKUP_GROUP_ID
if not BACKUP_GROUP_ID_STR:
    raise ValueError("BACKUP_GROUP_ID not set!")
try:
    BACKUP_GROUP_ID = int(BACKUP_GROUP_ID_STR)
except ValueError:
    raise ValueError(f"Invalid BACKUP_GROUP_ID: {BACKUP_GROUP_ID_STR}")

OWNER_ID = int(OWNER_ID_STR) if OWNER_ID_STR.lstrip('-').isdigit() else None

# ── Persistent ignore list ────────────────────────────────────────────────────
IGNORED_FILE = 'bot/ignored.json'
BOT_START_TIME = datetime.now()

def load_ignored() -> List[int]:
    try:
        if os.path.exists(IGNORED_FILE):
            with open(IGNORED_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_ignored(ids: List[int]):
    os.makedirs('bot', exist_ok=True)
    with open(IGNORED_FILE, 'w') as f:
        json.dump(ids, f, indent=2)

IGNORED_CHAT_IDS: List[int] = load_ignored()

# File to store topic mappings
TOPICS_FILE = 'bot/topics.json'

def normalize_topic_name(name: str) -> str:
    """Normalize topic name to better detect duplicates"""
    if not name:
        return ""
    
    # Remove accents and normalize unicode
    normalized = unicodedata.normalize('NFD', name)
    no_accents = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    
    # Remove emojis and special characters, keep only letters, numbers and spaces
    ascii_only = ''.join(char if ord(char) < 128 else ' ' for char in no_accents)
    
    # Remove punctuation and normalize spaces
    clean = re.sub(r'[^\w\s]', ' ', ascii_only)
    clean = re.sub(r'\s+', ' ', clean).strip().lower()
    
    return clean

# 📊 Função para registrar estatísticas — NOVA
def log_forwarded_media(source_topic: str, media_type: str, message_id: int, status: str = "success"):
    """Registra no log e atualiza estatísticas do dashboard"""
    try:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source_topic,
            "media_type": media_type,
            "message_id": message_id,
            "status": status
        }

        logs_file = 'bot/activity_logs.json'
        stats_file = 'bot/stats.json'

        # --- Atualiza activity_logs.json ---
        logs = []
        if os.path.exists(logs_file):
            with open(logs_file, 'r', encoding='utf-8') as f:
                try:
                    logs = json.load(f)
                    if not isinstance(logs, list):
                        logs = []
                except json.JSONDecodeError:
                    logs = []

        logs.append(log_entry)
        logs = logs[-1000:]  # Mantém apenas os últimos 1000 registros

        os.makedirs('bot', exist_ok=True)
        with open(logs_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

        # --- Atualiza stats.json ---
        stats = {
            "total_messages": 0,
            "today_messages": 0,
            "week_messages": 0,
            "topics": {}
        }

        if os.path.exists(stats_file):
            with open(stats_file, 'r', encoding='utf-8') as f:
                try:
                    stats = json.load(f)
                    if not isinstance(stats, dict):
                        stats = {}
                except json.JSONDecodeError:
                    pass

        # Garante que a estrutura básica existe
        stats.setdefault("total_messages", 0)
        stats.setdefault("today_messages", 0)
        stats.setdefault("week_messages", 0)
        stats.setdefault("topics", {})

        # Incrementa contadores
        stats["total_messages"] += 1
        stats["today_messages"] += 1
        stats["week_messages"] += 1

        # Incrementa contador por tópico
        if source_topic not in stats["topics"]:
            stats["topics"][source_topic] = 0
        stats["topics"][source_topic] += 1

        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        logger.info(f"📊 Estatísticas atualizadas para: {source_topic} ({media_type})")

    except Exception as e:
        logger.error(f"❌ Falha ao registrar estatísticas: {e}")


class TelegramBackupBot:
    def __init__(self):
        """Initialize Telegram bot"""
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN not set! Define it as an environment variable.")
        
        self.bot = telebot.TeleBot(BOT_TOKEN)
        self.topics: Dict[str, int] = self.load_topics()
        self.setup_handlers()
        
    def load_topics(self) -> Dict[str, int]:
        """Load topic mapping from JSON file"""
        try:
            with open(TOPICS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Migrate old format (chat_id -> group_name) if necessary
                if data and list(data.keys())[0].startswith('-'):
                    logger.info("Migrating old topics.json format...")
                    return {}  # Start empty to recreate with names
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_topics(self):
        """Save topic mapping to JSON file"""
        try:
            os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)
            with open(TOPICS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.topics, f, ensure_ascii=False, indent=2)
            logger.debug(f"Topics saved: {len(self.topics)} records")
        except Exception as e:
            logger.error(f"Error saving topics: {e}")
    
    def get_or_create_topic(self, chat_id: int, source_name: str) -> Optional[int]:
        """
        Get existing topic ID or create a new real topic
        Uses GROUP NAME as key to avoid duplicates
        
        Args:
            chat_id: Source chat ID
            source_name: Source group/channel name
            
        Returns:
            Real topic ID or None if error
        """
        normalized_name = normalize_topic_name(source_name)
        
        for existing_name, thread_id in self.topics.items():
            existing_normalized = normalize_topic_name(existing_name)
            if existing_normalized == normalized_name:
                logger.info(f"Similar topic found: '{existing_name}' for '{source_name}' (Thread ID: {thread_id})")
                return thread_id
        
        try:
            logger.info(f"Creating new topic for group: {source_name}")
            topic = self.bot.create_forum_topic(
                chat_id=BACKUP_GROUP_ID,
                name=source_name[:128]  # Max 128 chars
            )
            
            thread_id = None
            if hasattr(topic, 'message_thread_id'):
                thread_id = topic.message_thread_id
            elif hasattr(topic, 'thread_id'):
                thread_id = topic.thread_id  
            elif hasattr(topic, 'id'):
                thread_id = topic.id
            else:
                logger.warning(f"create_forum_topic returned object without identifiable thread ID: {topic}")
                return None
            
            self.topics[source_name] = thread_id
            self.save_topics()
            
            logger.info(f"✅ New topic created: '{source_name}' (Thread ID: {thread_id})")
            return thread_id
            
        except Exception as e:
            logger.error(f"❌ Error creating topic for '{source_name}': {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            return None
    
    def has_media(self, message: Message) -> bool:
        """Check if message contains media"""
        return bool(message.photo or message.video or message.document or 
                    message.audio or message.voice or message.video_note or 
                    message.sticker or message.animation)
    
    def forward_media(self, message: Message) -> bool:
        """
        Process media to backup supergroup.
        If forwarded, downloads and resends to remove "forwarded from".
        PRESERVES ORIGINAL CAPTION WHEN AVAILABLE.
        """
        source_name = "Unknown"
        original_caption = message.caption
        try:
            source_chat = message.chat
            source_name = source_chat.title or source_chat.first_name or f"Chat_{source_chat.id}"
            
            topic_id = self.get_or_create_topic(source_chat.id, source_name)
            if topic_id is None:
                logger.error(f"Could not get/create topic for {source_name}")
                return False

            is_forwarded = bool(message.forward_from or message.forward_from_chat)

            # ✅ SEMPRE usa fallback manual para mensagens encaminhadas
            if is_forwarded:
                logger.info(f"Forwarded message detected from {source_name}. Skipping copy_message, downloading and resending with original caption...")
                # Vai direto para o fallback manual
            else:
                # Só tenta copy_message se NÃO for encaminhada
                try:
                    logger.info(f"Copying original media from {source_name} with original caption...")
                    self.bot.copy_message(
                        chat_id=BACKUP_GROUP_ID,
                        from_chat_id=message.chat.id,
                        message_id=message.message_id,
                        message_thread_id=topic_id,
                        caption=original_caption
                    )
                    logger.info(f"✅ Media copied successfully from {source_name}")

                    # ✅ DELAY DE 5 SEGUNDOS APÓS QUALQUER ENVIO BEM-SUCEDIDO
                    logger.info("⏳ Waiting 5 seconds to avoid rate-limit...")
                    time.sleep(5)

                    log_forwarded_media(
                        source_topic=source_name,
                        media_type="photo" if message.photo else
                                   "video" if message.video else
                                   "document" if message.document else
                                   "audio" if message.audio else
                                   "voice" if message.voice else
                                   "video_note" if message.video_note else
                                   "sticker" if message.sticker else
                                   "animation" if message.animation else
                                   "unknown",
                        message_id=message.message_id
                    )
                    return True
                except Exception as copy_error:
                    logger.warning(f"copy_message failed: {copy_error}")
                    # Se for 429, espera o tempo indicado
                    if hasattr(copy_error, 'result') and hasattr(copy_error.result, 'error_code') and copy_error.result.error_code == 429:
                        retry_after = getattr(copy_error.result, 'parameters', {}).get('retry_after', 5)
                        logger.warning(f"Rate limited. Waiting {retry_after} seconds before fallback...")
                        time.sleep(retry_after)

            # 🚨 Fallback: manual resend — COM VERIFICAÇÃO DE TAMANHO
            try:
                # Determinar file_id
                if message.photo:
                    file_id = message.photo[-1].file_id
                elif message.video:
                    file_id = message.video.file_id
                elif message.document:
                    file_id = message.document.file_id
                elif message.audio:
                    file_id = message.audio.file_id
                elif message.voice:
                    file_id = message.voice.file_id
                elif message.video_note:
                    file_id = message.video_note.file_id
                elif message.animation:
                    file_id = message.animation.file_id
                else:
                    logger.warning("Unsupported media type")
                    return False

                # Baixar arquivo
                file_info = self.bot.get_file(file_id)
                downloaded_file = self.bot.download_file(file_info.file_path)
                actual_size = len(downloaded_file)
                logger.info(f"📥 Downloaded {actual_size} bytes")

                # 🔒 Verificação crítica: arquivo vazio ou muito pequeno?
                if actual_size == 0 or actual_size < 100:
                    logger.warning(
                        f"⚠️ File from '{source_name}' appears to be protected or invalid (downloaded size: {actual_size} bytes). "
                        "Skipping to avoid API errors."
                    )
                    return False

                # Salvar temporariamente
                suffix = ".bin"
                if message.photo:
                    suffix = ".jpg"
                elif message.video or message.video_note:
                    suffix = ".mp4"
                elif message.audio:
                    suffix = ".mp3"
                elif message.voice:
                    suffix = ".ogg"
                elif message.animation:
                    suffix = ".gif"
                elif message.document and message.document.file_name:
                    ext = os.path.splitext(message.document.file_name)[1]
                    if ext:
                        suffix = ext

                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    tmp_file.write(downloaded_file)
                    tmp_file.flush()

                    with open(tmp_file.name, 'rb') as f:
                        if message.photo:
                            self.bot.send_photo(
                                chat_id=BACKUP_GROUP_ID,
                                photo=f,
                                message_thread_id=topic_id,
                                caption=original_caption
                            )
                        elif message.video:
                            self.bot.send_video(
                                chat_id=BACKUP_GROUP_ID,
                                video=f,
                                message_thread_id=topic_id,
                                caption=original_caption
                            )
                        elif message.document:
                            self.bot.send_document(
                                chat_id=BACKUP_GROUP_ID,
                                document=f,
                                message_thread_id=topic_id,
                                caption=original_caption
                            )
                        elif message.audio:
                            self.bot.send_audio(
                                chat_id=BACKUP_GROUP_ID,
                                audio=f,
                                message_thread_id=topic_id,
                                caption=original_caption
                            )
                        elif message.voice:
                            self.bot.send_voice(
                                chat_id=BACKUP_GROUP_ID,
                                voice=f,
                                message_thread_id=topic_id
                            )
                        elif message.video_note:
                            self.bot.send_video_note(
                                chat_id=BACKUP_GROUP_ID,
                                video_note=f,
                                message_thread_id=topic_id
                            )
                        elif message.animation:
                            self.bot.send_animation(
                                chat_id=BACKUP_GROUP_ID,
                                animation=f,
                                message_thread_id=topic_id,
                                caption=original_caption
                            )

                    os.unlink(tmp_file.name)

                logger.info(f"✅ Media resent manually from {source_name}")

                # ✅ DELAY DE 5 SEGUNDOS APÓS QUALQUER ENVIO BEM-SUCEDIDO
                logger.info("⏳ Waiting 5 seconds to avoid rate-limit...")
                time.sleep(5)

                log_forwarded_media(
                    source_topic=source_name,
                    media_type="photo" if message.photo else
                               "video" if message.video else
                               "document" if message.document else
                               "audio" if message.audio else
                               "voice" if message.voice else
                               "video_note" if message.video_note else
                               "sticker" if message.sticker else
                               "animation" if message.animation else
                               "unknown",
                    message_id=message.message_id
                )
                return True

            except Exception as send_error:
                logger.error(f"❌ Error sending media manually: {send_error}")
                return False

        except Exception as e:
            logger.error(f"❌ Error processing media from {source_name}: {e}")

            try:
                log_forwarded_media(
                    source_topic=source_name,
                    media_type="unknown",
                    message_id=getattr(message, 'message_id', 0),
                    status="failed"
                )
            except Exception:
                pass

            return False
    
    def log_debug_event(self, event_type: str, chat_id, chat_title: str, detail: str):
        """Write a debug event to bot/debug_log.json"""
        try:
            debug_file = 'bot/debug_log.json'
            entry = {
                "timestamp": datetime.now().isoformat(),
                "event": event_type,
                "chat_id": chat_id,
                "chat_title": chat_title,
                "detail": detail
            }
            logs = []
            if os.path.exists(debug_file):
                with open(debug_file, 'r') as f:
                    try:
                        logs = json.load(f)
                    except Exception:
                        logs = []
            logs.append(entry)
            logs = logs[-200:]
            with open(debug_file, 'w') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Debug log write failed: {e}")

    def setup_handlers(self):
        """Configure bot handlers"""
        
        def process_media(message: Message):
            """Process media from group message or channel post"""
            try:
                chat_id  = message.chat.id
                chat_title = message.chat.title or message.chat.first_name or str(chat_id)
                chat_type  = message.chat.type

                logger.info(f"📩 Incoming update — chat: '{chat_title}' ({chat_id}), type: {chat_type}")
                self.log_debug_event("incoming", chat_id, chat_title,
                                     f"type={chat_type}, has_media={self.has_media(message)}")

                # Ignore messages from bots
                if message.from_user and message.from_user.is_bot:
                    logger.info(f"⏭ Skipping: sent by a bot")
                    self.log_debug_event("skipped_bot", chat_id, chat_title, "sender is a bot")
                    return

                # Ignore if forwarded from an ignored channel
                if message.forward_from_chat:
                    original_chat_id = message.forward_from_chat.id
                    if original_chat_id in IGNORED_CHAT_IDS:
                        logger.info(f"⏭ Skipping: forwarded from ignored channel {original_chat_id}")
                        self.log_debug_event("skipped_ignored_fwd", chat_id, chat_title,
                                             f"fwd from {original_chat_id}")
                        return

                if chat_type not in ['group', 'supergroup', 'channel']:
                    logger.info(f"⏭ Skipping: chat type '{chat_type}' not monitored")
                    self.log_debug_event("skipped_type", chat_id, chat_title, f"type={chat_type}")
                    return

                if chat_id in IGNORED_CHAT_IDS:
                    logger.info(f"⏭ Skipping: chat {chat_id} is in ignore list")
                    self.log_debug_event("skipped_ignored", chat_id, chat_title, "in IGNORED_CHAT_IDS")
                    return

                if chat_id == BACKUP_GROUP_ID:
                    logger.info(f"⏭ Skipping: this is the backup group itself")
                    self.log_debug_event("skipped_backup", chat_id, chat_title, "is backup group")
                    return

                if not self.has_media(message):
                    logger.info(f"⏭ Skipping: no media in message")
                    self.log_debug_event("skipped_no_media", chat_id, chat_title, "no media")
                    return

                logger.info(f"✅ Media detected in '{chat_title}' ({chat_id}) — forwarding...")
                self.log_debug_event("forwarding", chat_id, chat_title, "media found, forwarding")
                success = self.forward_media(message)

                if success:
                    logger.info(f"✅ Media forwarded successfully from '{chat_title}'")
                    self.log_debug_event("success", chat_id, chat_title, "forwarded OK")
                else:
                    logger.warning(f"❌ Failed to forward media from '{chat_title}'")
                    self.log_debug_event("failed", chat_id, chat_title, "forward failed")

            except Exception as e:
                logger.error(f"Error processing media: {e}")
                self.log_debug_event("error", 0, "unknown", str(e))

        @self.bot.message_handler(content_types=[
            'photo', 'video', 'document', 'audio',
            'voice', 'video_note', 'sticker', 'animation'
        ])
        def handle_media(message: Message):
            """Handler for group/supergroup media"""
            process_media(message)

        @self.bot.channel_post_handler(content_types=[
            'photo', 'video', 'document', 'audio',
            'voice', 'video_note', 'sticker', 'animation'
        ])
        def handle_channel_media(message: Message):
            """Handler for channel posts"""
            process_media(message)

        @self.bot.message_handler(func=lambda m: not (m.text and m.text.startswith('/')))
        def catch_all(message: Message):
            """Catch-all for non-command text messages — logs receipt for debugging"""
            chat_title = message.chat.title or message.chat.first_name or str(message.chat.id)
            logger.info(f"📨 Message received (catch-all) — '{chat_title}' ({message.chat.id}), "
                        f"type={message.chat.type}, content={message.content_type}")
            self.log_debug_event("catch_all", message.chat.id, chat_title,
                                 f"content_type={message.content_type}")
        
        @self.bot.message_handler(commands=['start'])
        def start_command(message: Message):
            """Handler for /start command"""
            if message.chat.type != 'private':
                return
            self.bot.reply_to(message,
                "🤖 *Telegram Backup Bot*\n\n"
                "I automatically forward media from groups and channels to your backup supergroup, "
                "organizing everything into topics by source.\n\n"
                "📋 *Available Commands:*\n"
                "/start — Show this welcome message\n"
                "/help — Detailed usage guide\n"
                "/status — Bot status and uptime\n"
                "/stats — Forwarding statistics\n"
                "/topics — List all mapped topics\n"
                "/sources — Show monitored sources\n"
                "/ping — Check if bot is alive\n\n"
                "✅ *Status:* Active and monitoring media",
                parse_mode='Markdown'
            )

        @self.bot.message_handler(commands=['help'])
        def help_command(message: Message):
            """Handler for /help command"""
            if message.chat.type != 'private':
                return
            self.bot.reply_to(message,
                "📖 *Help — Telegram Backup Bot*\n\n"
                "*How it works:*\n"
                "1\\. Add this bot to any group or channel as a member\n"
                "2\\. When media is posted, the bot forwards it to your backup supergroup\n"
                "3\\. Each source group gets its own topic thread automatically\n"
                "4\\. Captions are preserved; 'forwarded from' labels are removed\n\n"
                "*Supported media:*\n"
                "📷 Photos · 🎥 Videos · 📄 Documents\n"
                "🎵 Audio · 🎙 Voice · 📹 Video notes\n"
                "🖼 Animations · 🎭 Stickers\n\n"
                "*Commands:*\n"
                "/status — Runtime info and topic count\n"
                "/stats — Total media forwarded\n"
                "/topics — All topic→thread mappings\n"
                "/sources — Currently monitored sources\n"
                "/ping — Connectivity check\n\n"
                "*Need help?* Make sure the bot is:\n"
                "• An admin in the backup supergroup\n"
                "• Has 'Manage Topics' permission\n"
                "• A member of all source groups/channels",
                parse_mode='MarkdownV2'
            )

        @self.bot.message_handler(commands=['status'])
        def status_command(message: Message):
            """Handler for /status command"""
            if message.chat.type != 'private':
                return
            topics_count = len(self.topics)
            self.bot.reply_to(message,
                f"📊 *Bot Status*\n\n"
                f"🟢 *Running:* Yes\n"
                f"🎯 *Backup supergroup:* `{BACKUP_GROUP_ID}`\n"
                f"📁 *Mapped topics:* {topics_count}\n"
                f"⏰ *Last check:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"✅ All systems operational",
                parse_mode='Markdown'
            )

        @self.bot.message_handler(commands=['stats'])
        def stats_command(message: Message):
            """Handler for /stats command"""
            if message.chat.type != 'private':
                return
            try:
                stats = {"total_messages": 0, "today_messages": 0, "week_messages": 0}
                if os.path.exists('bot/stats.json'):
                    with open('bot/stats.json', 'r') as f:
                        stats = json.load(f)
                self.bot.reply_to(message,
                    f"📈 *Forwarding Statistics*\n\n"
                    f"📬 *Total forwarded:* {stats.get('total_messages', 0)}\n"
                    f"📅 *Today:* {stats.get('today_messages', 0)}\n"
                    f"📆 *This week:* {stats.get('week_messages', 0)}\n"
                    f"📁 *Topics created:* {len(self.topics)}\n\n"
                    f"🕐 *Updated:* {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                self.bot.reply_to(message, f"❌ Error reading stats: {e}")

        @self.bot.message_handler(commands=['topics'])
        def topics_command(message: Message):
            """Handler for /topics command"""
            if message.chat.type != 'private':
                return
            topics_count = len(self.topics)
            if not self.topics:
                self.bot.reply_to(message,
                    "📁 *Topics*\n\nNo topics created yet\\.\n"
                    "Topics are created automatically when media arrives from a new source\\.",
                    parse_mode='MarkdownV2'
                )
                return
            lines = [f"📁 *Topics \\({topics_count} total\\)*\n"]
            for name, thread_id in list(self.topics.items())[:20]:
                safe_name = name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                lines.append(f"• {safe_name} → thread `{thread_id}`")
            if topics_count > 20:
                lines.append(f"\n_...and {topics_count - 20} more_")
            self.bot.reply_to(message, "\n".join(lines), parse_mode='MarkdownV2')

        @self.bot.message_handler(commands=['sources'])
        def sources_command(message: Message):
            """Handler for /sources command"""
            if message.chat.type != 'private':
                return
            topics_count = len(self.topics)
            if not self.topics:
                self.bot.reply_to(message,
                    "📡 *Monitored Sources*\n\nNo sources detected yet\\.\n"
                    "Add this bot to groups or channels to start monitoring\\.",
                    parse_mode='MarkdownV2'
                )
                return
            lines = [f"📡 *Monitored Sources \\({topics_count}\\)*\n"]
            for name in list(self.topics.keys())[:20]:
                safe_name = name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                lines.append(f"✅ {safe_name}")
            if topics_count > 20:
                lines.append(f"\n_...and {topics_count - 20} more_")
            self.bot.reply_to(message, "\n".join(lines), parse_mode='MarkdownV2')

        @self.bot.message_handler(commands=['ping'])
        def ping_command(message: Message):
            if message.chat.type != 'private':
                return
            self.bot.reply_to(message, "🏓 Pong! Bot is alive and running.")

        # ── /id — works in any chat (groups, channels, private) ──────────────
        @self.bot.message_handler(commands=['id'])
        def id_command(message: Message):
            """Return the current chat's ID — useful for config"""
            chat = message.chat
            user = message.from_user
            lines = [f"🆔 *Chat ID:* `{chat.id}`"]
            if chat.title:
                lines.append(f"📛 *Name:* {chat.title}")
            lines.append(f"📂 *Type:* {chat.type}")
            if user:
                lines.append(f"\n👤 *Your user ID:* `{user.id}`")
            self.bot.reply_to(message, "\n".join(lines), parse_mode='Markdown')

        # ── /myid ─────────────────────────────────────────────────────────────
        @self.bot.message_handler(commands=['myid'])
        def myid_command(message: Message):
            user = message.from_user
            if user:
                self.bot.reply_to(message, f"👤 *Your Telegram ID:* `{user.id}`", parse_mode='Markdown')

        # ── /uptime ───────────────────────────────────────────────────────────
        @self.bot.message_handler(commands=['uptime'])
        def uptime_command(message: Message):
            if message.chat.type != 'private':
                return
            diff = datetime.now() - BOT_START_TIME
            days    = diff.days
            hours   = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            seconds = diff.seconds % 60
            parts = []
            if days:    parts.append(f"{days}d")
            if hours:   parts.append(f"{hours}h")
            if minutes: parts.append(f"{minutes}m")
            parts.append(f"{seconds}s")
            self.bot.reply_to(message,
                f"⏱ *Bot Uptime:* {' '.join(parts)}\n"
                f"🕐 *Started:* {BOT_START_TIME.strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode='Markdown')

        # ── /about ────────────────────────────────────────────────────────────
        @self.bot.message_handler(commands=['about'])
        def about_command(message: Message):
            if message.chat.type != 'private':
                return
            self.bot.reply_to(message,
                "ℹ️ *Telegram Media Backup Bot*\n\n"
                "Automatically forwards media from groups and channels to a backup supergroup, "
                "organized into topic threads per source.\n\n"
                "*Features:*\n"
                "• Copies photos, videos, documents, audio, voice, stickers, GIFs\n"
                "• Creates one topic per source group automatically\n"
                "• Removes 'forwarded from' label while preserving captions\n"
                "• Supports copying historical messages via MTProto\n"
                "• Web dashboard for monitoring and control\n\n"
                f"*Backup group:* `{BACKUP_GROUP_ID}`",
                parse_mode='Markdown')

        # ── /ignore — owner only ──────────────────────────────────────────────
        @self.bot.message_handler(commands=['ignore'])
        def ignore_command(message: Message):
            if message.chat.type != 'private':
                return
            if OWNER_ID and message.from_user and message.from_user.id != OWNER_ID:
                self.bot.reply_to(message, "⛔ Only the bot owner can use this command.")
                return
            parts = message.text.split()
            if len(parts) < 2:
                self.bot.reply_to(message,
                    "Usage: `/ignore <chat_id>`\n"
                    "Example: `/ignore -1001234567890`\n\n"
                    "The bot will stop forwarding media from that chat.",
                    parse_mode='Markdown')
                return
            try:
                chat_id = int(parts[1])
            except ValueError:
                self.bot.reply_to(message, "❌ Invalid chat ID. Must be a number like `-1001234567890`.")
                return
            if chat_id not in IGNORED_CHAT_IDS:
                IGNORED_CHAT_IDS.append(chat_id)
                save_ignored(IGNORED_CHAT_IDS)
                self.bot.reply_to(message, f"✅ Chat `{chat_id}` added to ignore list.", parse_mode='Markdown')
            else:
                self.bot.reply_to(message, f"ℹ️ Chat `{chat_id}` is already ignored.", parse_mode='Markdown')

        # ── /unignore — owner only ────────────────────────────────────────────
        @self.bot.message_handler(commands=['unignore'])
        def unignore_command(message: Message):
            if message.chat.type != 'private':
                return
            if OWNER_ID and message.from_user and message.from_user.id != OWNER_ID:
                self.bot.reply_to(message, "⛔ Only the bot owner can use this command.")
                return
            parts = message.text.split()
            if len(parts) < 2:
                self.bot.reply_to(message,
                    "Usage: `/unignore <chat_id>`\n"
                    "Example: `/unignore -1001234567890`",
                    parse_mode='Markdown')
                return
            try:
                chat_id = int(parts[1])
            except ValueError:
                self.bot.reply_to(message, "❌ Invalid chat ID.")
                return
            if chat_id in IGNORED_CHAT_IDS:
                IGNORED_CHAT_IDS.remove(chat_id)
                save_ignored(IGNORED_CHAT_IDS)
                self.bot.reply_to(message, f"✅ Chat `{chat_id}` removed from ignore list.", parse_mode='Markdown')
            else:
                self.bot.reply_to(message, f"ℹ️ Chat `{chat_id}` was not in the ignore list.", parse_mode='Markdown')

        # ── /ignored — owner only ─────────────────────────────────────────────
        @self.bot.message_handler(commands=['ignored'])
        def ignored_command(message: Message):
            if message.chat.type != 'private':
                return
            if OWNER_ID and message.from_user and message.from_user.id != OWNER_ID:
                self.bot.reply_to(message, "⛔ Only the bot owner can use this command.")
                return
            if not IGNORED_CHAT_IDS:
                self.bot.reply_to(message, "📋 Ignore list is empty — all chats are being monitored.")
                return
            lines = ["🚫 *Ignored Chats:*\n"]
            for cid in IGNORED_CHAT_IDS:
                lines.append(f"• `{cid}`")
            self.bot.reply_to(message, "\n".join(lines), parse_mode='Markdown')

        # ── /backup — trigger manual backup from a chat (owner only) ──────────
        @self.bot.message_handler(commands=['backup'])
        def backup_command(message: Message):
            if message.chat.type != 'private':
                return
            if OWNER_ID and message.from_user and message.from_user.id != OWNER_ID:
                self.bot.reply_to(message, "⛔ Only the bot owner can use this command.")
                return
            self.bot.reply_to(message,
                "📥 *Manual History Copy*\n\n"
                "To copy old messages, use the *Copy History* page in the web dashboard.\n"
                "It supports channels, groups, and forum supergroups with topics.",
                parse_mode='Markdown')

    def register_commands(self):
        """Register bot command menu with Telegram"""
        commands = [
            telebot.types.BotCommand("start",    "Welcome message & command list"),
            telebot.types.BotCommand("help",     "Detailed usage guide"),
            telebot.types.BotCommand("status",   "Bot status and uptime"),
            telebot.types.BotCommand("stats",    "Forwarding statistics"),
            telebot.types.BotCommand("topics",   "List all mapped topics"),
            telebot.types.BotCommand("sources",  "Show monitored sources"),
            telebot.types.BotCommand("ping",     "Check if bot is alive"),
            telebot.types.BotCommand("id",       "Get this chat's ID"),
            telebot.types.BotCommand("myid",     "Get your personal Telegram ID"),
            telebot.types.BotCommand("uptime",   "Show how long the bot has been running"),
            telebot.types.BotCommand("about",    "About this bot"),
            telebot.types.BotCommand("ignore",   "Stop forwarding from a chat (owner)"),
            telebot.types.BotCommand("unignore", "Re-enable a previously ignored chat (owner)"),
            telebot.types.BotCommand("ignored",  "List all ignored chats (owner)"),
            telebot.types.BotCommand("backup",   "How to copy old messages"),
        ]
        try:
            self.bot.set_my_commands(commands)
            logger.info("✅ Command menu registered with Telegram")
        except Exception as e:
            logger.warning(f"Could not register commands: {e}")

    def start_polling(self):
        """Start bot in polling mode"""
        try:
            logger.info("Starting Telegram backup bot...")
            me = self.bot.get_me()
            logger.info(f"Bot logged in as: @{me.username}")

            # Register command menu
            self.register_commands()

            # Discard pending updates
            self.bot.delete_webhook(drop_pending_updates=True)
            
            logger.info("Bot started successfully! Press Ctrl+C to stop.")
            self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logger.error(f"Error starting bot: {e}")

def main():
    """Main function to start the bot"""
    try:
        if not BOT_TOKEN:
            print("❌ ERROR: BOT_TOKEN not set!")
            print("Set the BOT_TOKEN environment variable with your bot token.")
            return
        bot = TelegramBackupBot()
        bot.start_polling()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")

if __name__ == "__main__":
    main()