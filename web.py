#!/usr/bin/env python3
"""
Heroku Web Entry Point
======================
Runs both the Telegram bot AND a Flask web dashboard on Heroku.
Uses the PORT environment variable that Heroku provides.
"""

import os
import sys
import json
import time
import threading
from datetime import datetime

from flask import Flask, render_template_string, jsonify

# ── Flask App ──────────────────────────────────────────────────────────────────

app = Flask(__name__)

BOT_START_TIME = datetime.now()
BOT_PROCESS = None

# ── HTML Dashboard ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Telegram Backup Bot - Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f1a; color: #e0e0e0;
        }
        .nav {
            background: #1a1a2e; padding: 16px 24px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 2px solid #6c5ce7;
        }
        .nav h1 { font-size: 20px; color: #a29bfe; }
        .nav .badge {
            background: #6c5ce7; color: white; padding: 4px 12px;
            border-radius: 12px; font-size: 12px;
        }
        .container { max-width: 1000px; margin: 24px auto; padding: 0 16px; }

        .status-banner {
            padding: 16px 20px; border-radius: 10px; margin-bottom: 20px;
            display: flex; align-items: center; gap: 12px;
        }
        .status-banner.active { background: #1b4332; border: 1px solid #2d6a4f; }
        .status-banner.inactive { background: #3c1518; border: 1px solid #641220; }
        .status-dot {
            width: 12px; height: 12px; border-radius: 50%;
        }
        .status-dot.active { background: #40c057; box-shadow: 0 0 8px #40c057; }
        .status-dot.inactive { background: #e03131; }

        .stats-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 20px;
        }
        .stat-card {
            background: #1a1a2e; padding: 20px; border-radius: 12px;
            border: 1px solid #2a2a4a; text-align: center;
        }
        .stat-card .value { font-size: 32px; font-weight: 700; color: #6c5ce7; }
        .stat-card .label { font-size: 13px; color: #888; margin-top: 4px; }

        .card {
            background: #1a1a2e; border-radius: 12px;
            border: 1px solid #2a2a4a; margin-bottom: 16px; overflow: hidden;
        }
        .card-header {
            padding: 14px 20px; font-weight: 600; font-size: 15px;
            background: #22223a; border-bottom: 1px solid #2a2a4a;
            display: flex; justify-content: space-between; align-items: center;
        }
        .card-body { padding: 16px 20px; }

        .config-row {
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 0; border-bottom: 1px solid #2a2a4a;
        }
        .config-row:last-child { border-bottom: none; }
        .config-row .key { color: #888; font-size: 14px; }
        .config-row .val { font-size: 14px; font-family: monospace; }
        .config-row .val.ok { color: #40c057; }
        .config-row .val.err { color: #e03131; }
        .config-row .val.warn { color: #fab005; }

        .topic-list { max-height: 300px; overflow-y: auto; }
        .topic-item {
            padding: 10px 0; border-bottom: 1px solid #2a2a4a;
            display: flex; justify-content: space-between;
        }
        .topic-item:last-child { border-bottom: none; }
        .topic-name { font-size: 14px; }
        .topic-id { font-size: 12px; color: #6c5ce7; font-family: monospace; }

        .log-entry {
            padding: 6px 0; font-size: 12px; font-family: monospace;
            border-bottom: 1px solid #1a1a2e;
        }
        .log-entry .ts { color: #6c5ce7; }
        .log-entry .ok { color: #40c057; }
        .log-entry .fail { color: #e03131; }

        .btn {
            padding: 8px 16px; border: none; border-radius: 6px;
            font-size: 13px; cursor: pointer; font-weight: 500;
        }
        .btn-primary { background: #6c5ce7; color: white; }
        .btn-primary:hover { background: #5a4bd1; }
        .refresh-info { font-size: 12px; color: #666; }

        @media (max-width: 600px) {
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .stat-card .value { font-size: 24px; }
        }
    </style>
    <script>
        setTimeout(() => location.reload(), 30000);
    </script>
</head>
<body>
    <div class="nav">
        <h1>🤖 Telegram Backup Bot</h1>
        <span class="badge">Dashboard</span>
    </div>

    <div class="container">
        <!-- Status Banner -->
        <div class="status-banner {{ status_class }}">
            <div class="status-dot {{ status_class }}"></div>
            <div>
                <strong>{{ status_text }}</strong>
                <span style="margin-left:8px; font-size:12px; color:#888;">Uptime: {{ uptime }}</span>
            </div>
        </div>

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">{{ topics_count }}</div>
                <div class="label">Topics Created</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ total_messages }}</div>
                <div class="label">Messages Forwarded</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ today_messages }}</div>
                <div class="label">Today</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ memory_mb }}</div>
                <div class="label">Memory (MB)</div>
            </div>
        </div>

        <!-- Config -->
        <div class="card">
            <div class="card-header">
                <span>⚙️ Configuration</span>
                <span class="refresh-info">Auto-refreshes every 30s</span>
            </div>
            <div class="card-body">
                <div class="config-row">
                    <span class="key">BOT_TOKEN</span>
                    <span class="val {{ 'ok' if has_token else 'err' }}">{{ token_preview }}</span>
                </div>
                <div class="config-row">
                    <span class="key">BACKUP_GROUP_ID</span>
                    <span class="val {{ 'ok' if has_group else 'err' }}">{{ group_id }}</span>
                </div>
                <div class="config-row">
                    <span class="key">API_ID</span>
                    <span class="val {{ 'ok' if has_api_id else 'warn' }}">{{ 'Configured' if has_api_id else 'Not set' }}</span>
                </div>
                <div class="config-row">
                    <span class="key">API_HASH</span>
                    <span class="val {{ 'ok' if has_api_hash else 'warn' }}">{{ 'Configured' if has_api_hash else 'Not set' }}</span>
                </div>
                <div class="config-row">
                    <span class="key">OWNER_ID</span>
                    <span class="val {{ 'ok' if has_owner else 'warn' }}">{{ owner_id }}</span>
                </div>
            </div>
        </div>

        <!-- Topics -->
        <div class="card">
            <div class="card-header">
                <span>📁 Topics ({{ topics_count }})</span>
            </div>
            <div class="card-body topic-list">
                {% if topics %}
                    {% for name, tid in topics.items() %}
                    <div class="topic-item">
                        <span class="topic-name">{{ name }}</span>
                        <span class="topic-id">thread #{{ tid }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color:#666; text-align:center; padding:20px;">No topics yet. Add bot to source groups to start.</p>
                {% endif %}
            </div>
        </div>

        <!-- Recent Activity -->
        <div class="card">
            <div class="card-header">
                <span>📋 Recent Activity</span>
            </div>
            <div class="card-body">
                {% if logs %}
                    {% for log in logs %}
                    <div class="log-entry">
                        <span class="ts">{{ log.ts }}</span>
                        <span class="{{ 'ok' if log.ok else 'fail' }}">{{ log.icon }}</span>
                        {{ log.source }} — {{ log.type }} (msg #{{ log.msg_id }})
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color:#666; text-align:center; padding:20px;">No activity yet.</p>
                {% endif %}
            </div>
        </div>

        <div style="text-align:center; padding:16px; color:#444; font-size:12px;">
            Telegram Media Backup Bot &middot; {{ current_time }}
        </div>
    </div>
</body>
</html>
'''


# ── Data helpers ───────────────────────────────────────────────────────────────

def load_json(filepath, default=None):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default or {}


def get_bot_status():
    """Check if the bot subprocess is running."""
    global BOT_PROCESS
    if BOT_PROCESS and BOT_PROCESS.poll() is None:
        diff = datetime.now() - BOT_START_TIME
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m" if hours else f"{minutes}m {seconds}s"
        return "active", "🟢 Bot Running", uptime
    return "inactive", "🔴 Bot Stopped", "0s"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    status_class, status_text, uptime = get_bot_status()

    # Load topics
    topics = load_json('bot/topics.json', {})
    topics_count = len(topics)

    # Load stats
    stats = load_json('bot/stats.json', {})
    total_messages = stats.get('total_messages', 0)
    today_messages = stats.get('today_messages', 0)

    # Load logs
    raw_logs = load_json('bot/activity_logs.json', [])
    log_entries = []
    for log in reversed(raw_logs[-30:]):
        ts = log.get('timestamp', '')
        try:
            ts = datetime.fromisoformat(ts).strftime('%H:%M:%S')
        except Exception:
            pass
        log_entries.append({
            'ts': ts,
            'ok': log.get('status') == 'success',
            'icon': '✅' if log.get('status') == 'success' else '❌',
            'source': log.get('source', '?'),
            'type': log.get('media_type', '?'),
            'msg_id': log.get('message_id', '?'),
        })

    # Config
    config = load_json('config.json', {})
    has_token = bool(os.getenv('BOT_TOKEN') or config.get('bot_token'))
    token_preview = (os.getenv('BOT_TOKEN') or config.get('bot_token', ''))[:10] + '...' if has_token else 'Not set'
    has_group = bool(os.getenv('BACKUP_GROUP_ID') or config.get('backup_group_id'))
    group_id = os.getenv('BACKUP_GROUP_ID') or config.get('backup_group_id', 'Not set')
    has_api_id = bool(os.getenv('API_ID'))
    has_api_hash = bool(os.getenv('API_HASH'))
    has_owner = bool(os.getenv('OWNER_ID'))
    owner_id = os.getenv('OWNER_ID', 'Not set')

    # Memory
    try:
        import psutil
        memory_mb = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        memory_mb = '?'

    return render_template_string(
        DASHBOARD_HTML,
        status_class=status_class,
        status_text=status_text,
        uptime=uptime,
        topics_count=topics_count,
        topics=topics,
        total_messages=total_messages,
        today_messages=today_messages,
        memory_mb=memory_mb,
        has_token=has_token,
        token_preview=token_preview,
        has_group=has_group,
        group_id=group_id,
        has_api_id=has_api_id,
        has_api_hash=has_api_hash,
        has_owner=has_owner,
        owner_id=owner_id,
        logs=log_entries,
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


@app.route('/health')
def health():
    """Health check endpoint for Heroku."""
    status_class, _, _ = get_bot_status()
    return jsonify({
        'status': 'ok' if status_class == 'active' else 'degraded',
        'bot_running': status_class == 'active',
        'timestamp': datetime.now().isoformat(),
    })


# ── Start Telegram bot in background thread ────────────────────────────────────

def start_bot_thread():
    """Start the Telegram bot in a background thread."""
    global BOT_PROCESS
    try:
        import subprocess
        BOT_PROCESS = subprocess.Popen(
            [sys.executable, 'bot/telegram_bot.py'],
            env=os.environ.copy(),
        )
        print(f"✅ Bot process started (PID: {BOT_PROCESS.pid})")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))

    # Start bot in background
    bot_thread = threading.Thread(target=start_bot_thread, daemon=True)
    bot_thread.start()

    print(f"🌐 Starting Flask dashboard on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
