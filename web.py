#!/usr/bin/env python3
"""
Heroku Web Entry Point — Full-Featured Flask Dashboard
======================================================
Replaces the Streamlit dashboard with a Flask-based one that works on Heroku.
Includes ALL pages: Dashboard, Analytics, Topics, Activity Logs,
Configuration, System Info, Debug Log, Copy History.
"""

import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime

from flask import Flask, render_template_string, request, redirect, url_for, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.analytics import AnalyticsManager
from utils.bot_monitor import BotMonitor
from utils.config_manager import ConfigManager

# ── Flask App ──────────────────────────────────────────────────────────────────

app = Flask(__name__)
analytics = AnalyticsManager()
monitor = BotMonitor()
config_mgr = ConfigManager()
BOT_START_TIME = datetime.now()
BOT_PROCESS = None

# ── Base HTML Template ─────────────────────────────────────────────────────────

BASE_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }} - Telegram Backup Bot</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        :root {
            --bg: #0f0f1a; --card: #1a1a2e; --border: #2a2a4a;
            --accent: #6c5ce7; --accent2: #a29bfe; --text: #e0e0e0;
            --green: #40c057; --red: #e03131; --yellow: #fab005;
            --header-bg: #22223a;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); display: flex; min-height: 100vh; }
        .sidebar {
            width: 240px; background: var(--card); border-right: 1px solid var(--border);
            padding: 20px 0; position: fixed; top: 0; left: 0; height: 100vh; overflow-y: auto;
        }
        .sidebar h2 { color: var(--accent2); font-size: 16px; padding: 0 20px 16px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
        .sidebar a {
            display: block; padding: 10px 20px; color: var(--text); text-decoration: none;
            font-size: 14px; border-left: 3px solid transparent; transition: all .15s;
        }
        .sidebar a:hover { background: rgba(108,92,231,.1); }
        .sidebar a.active { background: rgba(108,92,231,.15); border-left-color: var(--accent); color: var(--accent2); font-weight: 600; }
        .sidebar .status-box { margin: 16px 20px; padding: 12px; border-radius: 8px; font-size: 12px; }
        .sidebar .status-box.ok { background: #1b4332; border: 1px solid #2d6a4f; }
        .sidebar .status-box.err { background: #3c1518; border: 1px solid #641220; }
        .main { margin-left: 240px; flex: 1; padding: 24px; max-width: 1100px; }

        h1 { font-size: 22px; margin-bottom: 6px; color: #fff; }
        h2 { font-size: 17px; margin: 20px 0 10px; color: var(--accent2); }
        .subtitle { color: #888; font-size: 13px; margin-bottom: 20px; }

        .banner { padding: 14px 18px; border-radius: 10px; margin-bottom: 18px; display: flex; align-items: center; gap: 10px; font-size: 14px; }
        .banner.ok { background: #1b4332; border: 1px solid #2d6a4f; }
        .banner.err { background: #3c1518; border: 1px solid #641220; }
        .banner.warn { background: #3d2e00; border: 1px solid #5c4400; }
        .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
        .dot.green { background: var(--green); box-shadow: 0 0 6px var(--green); }
        .dot.red { background: var(--red); }
        .dot.yellow { background: var(--yellow); }

        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 18px; }
        .stat { background: var(--card); padding: 18px; border-radius: 10px; border: 1px solid var(--border); text-align: center; }
        .stat .val { font-size: 28px; font-weight: 700; color: var(--accent); }
        .stat .lbl { font-size: 12px; color: #888; margin-top: 2px; }

        .card { background: var(--card); border-radius: 10px; border: 1px solid var(--border); margin-bottom: 16px; overflow: hidden; }
        .card-head { padding: 12px 18px; font-weight: 600; font-size: 14px; background: var(--header-bg); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .card-body { padding: 16px 18px; }

        .row { display: flex; justify-content: space-between; align-items: center; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
        .row:last-child { border-bottom: none; }
        .row .k { color: #888; }
        .row .v { font-family: monospace; }
        .row .v.ok { color: var(--green); }
        .row .v.err { color: var(--red); }
        .row .v.warn { color: var(--yellow); }

        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border); color: #888; font-weight: 600; font-size: 11px; text-transform: uppercase; }
        td { padding: 7px 10px; border-bottom: 1px solid var(--border); }
        tr:hover td { background: rgba(108,92,231,.04); }

        .btn { padding: 8px 18px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; color: #fff; transition: .15s; }
        .btn-primary { background: var(--accent); }
        .btn-primary:hover { background: #5a4bd1; }
        .btn-danger { background: var(--red); }
        .btn-danger:hover { background: #c92a2a; }
        .btn-success { background: var(--green); }
        .btn-success:hover { background: #2f9e44; }
        .btn-warn { background: var(--yellow); color: #000; }
        .btns { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }

        .form-group { margin-bottom: 14px; }
        .form-group label { display: block; font-size: 13px; color: #888; margin-bottom: 4px; }
        .form-group input, .form-group select { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 14px; }
        .form-group input:focus { outline: none; border-color: var(--accent); }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

        .progress-bar { background: var(--border); border-radius: 8px; overflow: hidden; height: 22px; position: relative; }
        .progress-bar .fill { background: var(--accent); height: 100%; transition: width .3s; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #fff; font-weight: 600; min-width: 30px; }

        .chart-container { position: relative; height: 260px; margin: 10px 0; }

        .log-entry { padding: 4px 0; font-size: 12px; font-family: monospace; border-bottom: 1px solid var(--bg); }
        .log-entry .ts { color: var(--accent); }
        .log-entry .ok { color: var(--green); }
        .log-entry .fail { color: var(--red); }

        .tip-box { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin-top: 12px; font-size: 13px; }
        .tip-box table { margin-top: 8px; }
        .tip-box td, .tip-box th { font-size: 12px; }

        .msg { padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 13px; }
        .msg.ok { background: #1b4332; border: 1px solid #2d6a4f; }
        .msg.err { background: #3c1518; border: 1px solid #641220; }
        .msg.info { background: #1a1a4e; border: 1px solid #2a2a6e; }

        @media (max-width: 768px) {
            .sidebar { width: 100%; height: auto; position: relative; display: flex; flex-wrap: wrap; padding: 10px; }
            .sidebar h2 { display: none; }
            .sidebar a { padding: 8px 12px; font-size: 12px; border-left: none; border-bottom: 2px solid transparent; }
            .sidebar .status-box { display: none; }
            .main { margin-left: 0; }
            .stats { grid-template-columns: 1fr 1fr; }
            .form-row { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <nav class="sidebar">
        <h2>🤖 TGBackup</h2>
        {% set pages = [('dashboard','📊 Dashboard'),('analytics','📈 Analytics'),('topics','📁 Topics'),('logs','📋 Activity Logs'),('config','⚙️ Configuration'),('system','💻 System Info'),('debug','🔍 Debug Log'),('copy','📥 Copy History')] %}
        {% for pid, plabel in pages %}
        <a href="/{{ pid }}" class="{{ 'active' if page==pid else '' }}">{{ plabel }}</a>
        {% endfor %}
        <div class="status-box {{ 'ok' if bot_running else 'err' }}">
            Bot: {{ '🟢 Running' if bot_running else '🔴 Stopped' }}<br>
            <span style="font-size:11px;color:#888;">Config: {{ '✅' if config_ok else '⚠️' }}</span>
        </div>
    </nav>

    <div class="main">
        {% if msg_text %}
        <div class="msg {{ msg_type }}">{{ msg_text }}</div>
        {% endif %}
        {% block content %}{% endblock %}
        <div style="text-align:center;padding:20px;color:#444;font-size:11px;">
            Telegram Media Backup Bot &middot; {{ now.strftime('%Y-%m-%d %H:%M:%S') }}
        </div>
    </div>
</body>
</html>
'''

# ── Page Templates ─────────────────────────────────────────────────────────────

DASHBOARD_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>🤖 Telegram Bot Dashboard</h1>
<p class="subtitle">Real-time monitoring of your Telegram Media Backup Bot</p>

{% if bot_running %}
<div class="banner ok"><div class="dot green"></div><strong>Bot Running</strong>&nbsp;&nbsp;Uptime: {{ uptime }} &nbsp;|&nbsp; PID: {{ bot_pid }}</div>
<div class="btns">
    <form method="post" action="/bot/stop"><button class="btn btn-danger" type="submit">⏹ Stop Bot</button></form>
    <form method="post" action="/bot/restart"><button class="btn btn-warn" type="submit">🔄 Restart</button></form>
</div>
{% else %}
<div class="banner err"><div class="dot red"></div><strong>Bot Not Running</strong></div>
<div class="btns">
    <form method="post" action="/bot/start"><button class="btn btn-success" type="submit">▶ Start Bot</button></form>
</div>
{% endif %}

<div class="stats">
    <div class="stat"><div class="val">{{ stats.total_messages }}</div><div class="lbl">Total Messages</div></div>
    <div class="stat"><div class="val">{{ stats.total_topics }}</div><div class="lbl">Topics Created</div></div>
    <div class="stat"><div class="val">{{ stats.today_messages }}</div><div class="lbl">Today</div></div>
    <div class="stat"><div class="val">{{ stats.active_sources }}</div><div class="lbl">Active Sources</div></div>
</div>

<div class="card">
    <div class="card-head"><span>⚙️ Configuration Status</span></div>
    <div class="card-body">
        <div class="row"><span class="k">BOT_TOKEN</span><span class="v {{ 'ok' if csum.has_token else 'err' }}">{{ csum.token_preview }}</span></div>
        <div class="row"><span class="k">BACKUP_GROUP_ID</span><span class="v {{ 'ok' if csum.has_group_id else 'err' }}">{{ csum.group_id }}</span></div>
        <div class="row"><span class="k">API_ID</span><span class="v {{ 'ok' if csum.has_api_id else 'warn' }}">{{ 'Configured' if csum.has_api_id else 'Not set' }}</span></div>
        <div class="row"><span class="k">API_HASH</span><span class="v {{ 'ok' if csum.has_api_hash else 'warn' }}">{{ 'Configured' if csum.has_api_hash else 'Not set' }}</span></div>
        <div class="row"><span class="k">OWNER_ID</span><span class="v {{ 'ok' if csum.has_owner_id else 'warn' }}">{{ csum.owner_id }}</span></div>
    </div>
</div>

<div class="card">
    <div class="card-head"><span>📋 Recent Activity</span></div>
    <div class="card-body">
        {% if recent_logs %}
        <table><tr><th>Time</th><th>Source</th><th>Type</th><th>Msg ID</th><th>Status</th></tr>
        {% for log in recent_logs %}
        <tr>
            <td>{{ log.ts }}</td><td>{{ log.source }}</td><td>{{ log.media_type }}</td>
            <td>{{ log.message_id }}</td><td>{{ '✅' if log.status=='success' else '❌' }}</td>
        </tr>
        {% endfor %}
        </table>
        {% else %}
        <p style="color:#666;text-align:center;padding:16px;">No activity yet.</p>
        {% endif %}
    </div>
</div>
{% endblock %}
''')

ANALYTICS_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>📈 Analytics</h1>
<p class="subtitle">Activity charts and media statistics</p>

<div class="card">
    <div class="card-head"><span>Daily Activity (Last 7 Days)</span></div>
    <div class="card-body"><div class="chart-container"><canvas id="dailyChart"></canvas></div></div>
</div>

<div class="card">
    <div class="card-head"><span>Hourly Activity (Last 24 Hours)</span></div>
    <div class="card-body"><div class="chart-container"><canvas id="hourlyChart"></canvas></div></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
    <div class="card">
        <div class="card-head"><span>Media Type Distribution</span></div>
        <div class="card-body"><div class="chart-container"><canvas id="mediaChart"></canvas></div></div>
    </div>
    <div class="card">
        <div class="card-head"><span>Summary</span></div>
        <div class="card-body">
            <div class="row"><span class="k">Total Messages</span><span class="v">{{ stats.total_messages }}</span></div>
            <div class="row"><span class="k">Topics Created</span><span class="v">{{ stats.total_topics }}</span></div>
            <div class="row"><span class="k">This Week</span><span class="v">{{ stats.week_messages }}</span></div>
            <div class="row"><span class="k">Today</span><span class="v">{{ stats.today_messages }}</span></div>
        </div>
    </div>
</div>

<script>
new Chart(document.getElementById('dailyChart'), {
    type: 'bar', data: { labels: {{ daily_labels | tojson }}, datasets: [{ label: 'Messages', data: {{ daily_counts | tojson }}, backgroundColor: '#6c5ce7' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { color: '#888' }, grid: { color: '#2a2a4a' } }, x: { ticks: { color: '#888' }, grid: { color: '#2a2a4a' } } } }
});
new Chart(document.getElementById('hourlyChart'), {
    type: 'line', data: { labels: {{ hourly_labels | tojson }}, datasets: [{ label: 'Messages', data: {{ hourly_counts | tojson }}, borderColor: '#40c057', backgroundColor: 'rgba(64,192,87,.1)', fill: true, tension: .3 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { color: '#888' }, grid: { color: '#2a2a4a' } }, x: { ticks: { color: '#888' }, grid: { color: '#2a2a4a' } } } }
});
new Chart(document.getElementById('mediaChart'), {
    type: 'doughnut', data: { labels: {{ media_labels | tojson }}, datasets: [{ data: {{ media_counts | tojson }}, backgroundColor: ['#6c5ce7','#40c057','#fab005','#e03131','#15aabf','#fd7e14','#be4bdb','#868e96'] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#e0e0e0' } } } }
});
</script>
{% endblock %}
''')

TOPICS_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>📁 Topics</h1>
<p class="subtitle">Topic mappings between source groups and backup supergroup threads</p>

{% if topics %}
<div class="banner ok"><div class="dot green"></div><strong>{{ topics|length }} topics configured</strong></div>
<div class="card">
    <div class="card-head"><span>Topic Map</span></div>
    <div class="card-body">
        <table><tr><th>Source Group</th><th>Thread ID</th><th>Media Count</th></tr>
        {% for name, tid in topics.items() %}
        <tr><td>{{ name }}</td><td style="color:var(--accent);font-family:monospace;">{{ tid }}</td><td>{{ topic_counts.get(name, 0) }}</td></tr>
        {% endfor %}
        </table>
    </div>
</div>

<div class="card">
    <div class="card-head"><span>Topics Timeline</span></div>
    <div class="card-body">
        {% for item in timeline %}
        <div class="row">
            <span>📌 Thread #{{ item.thread_id }}</span>
            <span>{{ item.topic }}</span>
            <span style="color:#888;">Updated: {{ item.last_updated_str }}</span>
        </div>
        {% endfor %}
    </div>
</div>
{% else %}
<div class="banner warn"><div class="dot yellow"></div>No topics yet. Add the bot to source groups to start.</div>
{% endif %}
{% endblock %}
''')

LOGS_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>📋 Activity Logs</h1>
<p class="subtitle">Detailed log of all bot activity</p>

<div class="btns">
    <form method="get" action="/logs">
        <label style="font-size:13px;color:#888;">Show last</label>
        <select name="limit" style="padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);">
            <option value="25" {{ 'selected' if limit==25 else '' }}>25</option>
            <option value="50" {{ 'selected' if limit==50 else '' }}>50</option>
            <option value="100" {{ 'selected' if limit==100 else '' }}>100</option>
            <option value="200" {{ 'selected' if limit==200 else '' }}>200</option>
        </select>
        <button class="btn btn-primary" type="submit">🔄 Refresh</button>
    </form>
</div>

{% if logs %}
<div class="banner ok"><div class="dot green"></div>Showing {{ logs|length }} most recent entries</div>
<div class="card">
    <div class="card-body">
        <table><tr><th>Timestamp</th><th>Source</th><th>Media Type</th><th>Msg ID</th><th>Status</th></tr>
        {% for log in logs %}
        <tr>
            <td>{{ log.ts }}</td><td>{{ log.source }}</td><td>{{ log.media_type }}</td>
            <td>{{ log.message_id }}</td><td>{{ '✅' if log.status=='success' else '❌' }}</td>
        </tr>
        {% endfor %}
        </table>
    </div>
</div>
{% else %}
<div class="banner warn"><div class="dot yellow"></div>No activity logs yet.</div>
{% endif %}
{% endblock %}
''')

CONFIG_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>⚙️ Configuration</h1>
<p class="subtitle">Configure bot token and backup supergroup</p>

<div class="card">
    <div class="card-head"><span>Credential Status</span></div>
    <div class="card-body">
        <div class="form-row">
            <div>
                <div class="row"><span class="k">BOT_TOKEN</span><span class="v {{ 'ok' if csum.has_token else 'err' }}">{{ csum.token_preview }}</span></div>
                <div class="row"><span class="k">API_ID</span><span class="v {{ 'ok' if csum.has_api_id else 'warn' }}">{{ csum.api_id }}</span></div>
                <div class="row"><span class="k">OWNER_ID</span><span class="v {{ 'ok' if csum.has_owner_id else 'warn' }}">{{ csum.owner_id }}</span></div>
            </div>
            <div>
                <div class="row"><span class="k">BACKUP_GROUP_ID</span><span class="v {{ 'ok' if csum.has_group_id else 'err' }}">{{ csum.group_id }}</span></div>
                <div class="row"><span class="k">API_HASH</span><span class="v {{ 'ok' if csum.has_api_hash else 'warn' }}">{{ 'Configured' if csum.has_api_hash else 'Not set' }}</span></div>
            </div>
        </div>
    </div>
</div>

<div class="card">
    <div class="card-head"><span>Bot Settings</span></div>
    <div class="card-body">
        <form method="post" action="/config/save">
            <div class="form-group">
                <label>Backup Supergroup ID</label>
                <input type="text" name="backup_group_id" value="{{ config.backup_group_id }}" placeholder="e.g., -1001234567890">
            </div>
            <button class="btn btn-primary" type="submit">💾 Save Configuration</button>
        </form>
    </div>
</div>

<div class="card">
    <div class="card-head"><span>🔍 Diagnostics</span></div>
    <div class="card-body">
        {% for check, result in diagnostics.items() %}
        <div class="row">
            <span class="k">{{ check }}</span>
            <span class="v {{ result.status }}">{{ '✅' if result.status=='ok' else '⚠️' if result.status=='warning' else '❌' }} {{ result.message }}</span>
        </div>
        {% endfor %}
    </div>
</div>

<div class="card">
    <div class="card-head"><span>🎮 Bot Control</span></div>
    <div class="card-body">
        <div class="btns">
            <form method="post" action="/bot/start"><button class="btn btn-success" type="submit">▶ Start</button></form>
            <form method="post" action="/bot/stop"><button class="btn btn-danger" type="submit">⏹ Stop</button></form>
            <form method="post" action="/bot/restart"><button class="btn btn-warn" type="submit">🔄 Restart</button></form>
        </div>
    </div>
</div>

<div class="card">
    <div class="card-head"><span>📖 Setup Instructions</span></div>
    <div class="card-body" style="font-size:13px;line-height:1.7;">
        <strong>1. Create a Bot:</strong> Open Telegram → @BotFather → /newbot → Copy token<br>
        <strong>2. Create a Supergroup:</strong> New group → Settings → Convert to supergroup → Enable Topics<br>
        <strong>3. Make Bot Admin:</strong> Group settings → Administrators → Add bot → Enable "Manage Topics"<br>
        <strong>4. Get Group ID:</strong> Add @userinfobot to group → Copy the negative ID → Remove @userinfobot<br>
        <strong>5. Add Bot to Source Groups:</strong> Add bot as member to all groups/channels you want to monitor<br>
        <strong>6. Configure & Start:</strong> Enter token & group ID → Save → Start Bot
    </div>
</div>
{% endblock %}
''')

SYSTEM_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>💻 System Information</h1>
<p class="subtitle">System resources and bot performance</p>

{% if sys_info %}
<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
    <div class="card">
        <div class="card-head"><span>System Resources</span></div>
        <div class="card-body">
            <div class="form-group"><label>CPU Usage</label>
                <div class="progress-bar"><div class="fill" style="width:{{ sys_info.cpu_percent }}%">{{ sys_info.cpu_percent }}%</div></div>
            </div>
            <div class="form-group"><label>Memory ({{ sys_info.memory_used_gb }} / {{ sys_info.memory_total_gb }} GB)</label>
                <div class="progress-bar"><div class="fill" style="width:{{ sys_info.memory_percent }}%">{{ sys_info.memory_percent }}%</div></div>
            </div>
            <div class="form-group"><label>Disk ({{ sys_info.disk_used_gb }} / {{ sys_info.disk_total_gb }} GB)</label>
                <div class="progress-bar"><div class="fill" style="width:{{ sys_info.disk_percent }}%">{{ sys_info.disk_percent }}%</div></div>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-head"><span>Bot Information</span></div>
        <div class="card-body">
            <div class="row"><span class="k">Status</span><span class="v {{ 'ok' if bot_running else 'err' }}">{{ 'Running' if bot_running else 'Stopped' }}</span></div>
            <div class="row"><span class="k">Uptime</span><span class="v">{{ uptime }}</span></div>
            <div class="row"><span class="k">Bot Memory</span><span class="v">{{ bot_mem }} MB</span></div>
            <div class="row"><span class="k">Bot CPU</span><span class="v">{{ bot_cpu }}%</span></div>
            <div class="row"><span class="k">Topics</span><span class="v">{{ topics_count }}</span></div>
            <div class="row"><span class="k">Last Activity</span><span class="v">{{ sys_info.last_activity }}</span></div>
        </div>
    </div>
</div>
{% else %}
<div class="banner err"><div class="dot red"></div>Could not retrieve system info.</div>
{% endif %}

<div class="card">
    <div class="card-head"><span>📁 Data Files</span></div>
    <div class="card-body">
        {% for fpath, flabel in data_files %}
        {% if fpath.exists %}
        <div class="row"><span class="k">{{ flabel }}</span><span class="v ok">{{ fpath.size }} bytes — {{ fpath.modified }}</span></div>
        {% else %}
        <div class="row"><span class="k">{{ flabel }}</span><span class="v warn">Not found</span></div>
        {% endif %}
        {% endfor %}
    </div>
</div>
{% endblock %}
''')

DEBUG_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>🔍 Debug Log</h1>
<p class="subtitle">Every update the bot receives is logged here, including skipped messages</p>

<div class="btns">
    <a href="/debug" class="btn btn-primary">🔄 Refresh</a>
    <form method="post" action="/debug/clear"><button class="btn btn-danger" type="submit">🗑 Clear Log</button></form>
</div>

{% if debug_entries %}
<div class="banner ok"><div class="dot green"></div>{{ debug_entries|length }} events recorded</div>
<div class="card">
    <div class="card-body">
        <table><tr><th>Time</th><th>Event</th><th>Chat</th><th>Chat ID</th><th>Detail</th></tr>
        {% for e in debug_entries %}
        <tr>
            <td>{{ e.ts }}</td>
            <td>{{ e.icon }} {{ e.event }}</td>
            <td>{{ e.chat_title }}</td>
            <td style="font-family:monospace;">{{ e.chat_id }}</td>
            <td>{{ e.detail }}</td>
        </tr>
        {% endfor %}
        </table>
    </div>
</div>
{% else %}
<div class="banner warn"><div class="dot yellow"></div>No events logged yet.</div>
{% endif %}

<div class="tip-box">
    <strong>📌 Privacy Mode Checker</strong>
    <table>
        <tr><th>Situation</th><th>Can bot see messages?</th></tr>
        <tr><td>Bot is regular member + Privacy ON</td><td>❌ Only /commands</td></tr>
        <tr><td>Bot is regular member + Privacy OFF</td><td>✅ All messages</td></tr>
        <tr><td>Bot is admin in the group</td><td>✅ All messages</td></tr>
        <tr><td>Bot is in a channel</td><td>✅ Always sees posts</td></tr>
    </table>
    <p style="margin-top:8px;color:#888;">Privacy mode is ON by default. Check: @BotFather → /mybots → Bot Settings → Group Privacy</p>
</div>
{% endblock %}
''')

COPY_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''
{% block content %}
<h1>📥 Copy History</h1>
<p class="subtitle">Copy old media messages from any Telegram chat into your backup supergroup</p>

<div class="banner info" style="background:#1a1a4e;border:1px solid #2a2a6e;">
    <div class="dot" style="background:var(--accent);"></div>
    Uses <strong>API_ID + API_HASH</strong> (MTProto) to read full message history. The bot must be a member or admin of the source chat.<br>
    🗂 <strong>Forum supergroups</strong>: each source topic is automatically mapped to its own topic in the backup group.
</div>

<div class="card">
    <div class="card-head"><span>⚙️ Settings</span></div>
    <div class="card-body">
        <form method="post" action="/copy/start">
            <div class="form-group"><label>Source Chat</label><input type="text" name="source_chat" placeholder="@username or -1001234567890"></div>
            <div class="form-row">
                <div class="form-group"><label>Max messages (0 = all)</label><input type="number" name="limit" value="0" min="0" step="100"></div>
                <div class="form-group"><label>Only copy one topic ID (optional)</label><input type="text" name="topic_id" placeholder="e.g. 12345"></div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>From date (optional)</label><input type="date" name="from_date"></div>
                <div class="form-group"><label>To date (optional)</label><input type="date" name="to_date"></div>
            </div>
            <div class="form-group"><label>Delay between copies (seconds)</label><input type="range" name="delay" min="1" max="10" step="0.5" value="3" oninput="this.nextElementSibling.textContent=this.value+'s'"><span style="color:var(--accent);">3s</span></div>
            <button class="btn btn-success" type="submit" {{ 'disabled' if scraper_running else '' }}>🚀 Start Copying</button>
        </form>
    </div>
</div>

{% if scraper_running %}
<div class="btns"><form method="post" action="/copy/stop"><button class="btn btn-danger" type="submit">⏹ Stop Scraper</button></form></div>
{% endif %}

<div class="card">
    <div class="card-head"><span>📊 Progress</span> <a href="/copy" class="btn btn-primary" style="padding:4px 10px;font-size:11px;">🔄</a></div>
    <div class="card-body">
        {% if progress %}
        <div class="row"><span class="k">Status</span><span class="v {{ 'ok' if progress.status=='finished' else 'warn' if progress.status=='running' else 'err' }}">{{ progress.status }}</span></div>
        <div class="row"><span class="k">Mode</span><span class="v">{{ progress.mode }}</span></div>

        {% if progress.topics_total and progress.topics_total > 0 %}
        <div class="form-group" style="margin-top:10px;">
            <label>Topics: {{ progress.topics_done }} / {{ progress.topics_total }}{% if progress.current_topic %} — current: {{ progress.current_topic }}{% endif %}</label>
            <div class="progress-bar"><div class="fill" style="width:{{ (progress.topics_done / progress.topics_total * 100)|int }}%">{{ progress.topics_done }}/{{ progress.topics_total }}</div></div>
        </div>
        {% endif %}

        <div class="stats" style="margin-top:12px;">
            <div class="stat"><div class="val">{{ progress.processed }}</div><div class="lbl">Processed</div></div>
            <div class="stat"><div class="val" style="color:var(--green);">{{ progress.forwarded }}</div><div class="lbl">Forwarded</div></div>
            <div class="stat"><div class="val" style="color:var(--yellow);">{{ progress.skipped }}</div><div class="lbl">Skipped</div></div>
            <div class="stat"><div class="val" style="color:var(--red);">{{ progress.errors }}</div><div class="lbl">Errors</div></div>
        </div>

        {% if progress.processed and progress.processed > 0 %}
        <div class="form-group">
            <label>Media forwarded: {{ progress.forwarded }} / {{ progress.processed }}</label>
            <div class="progress-bar"><div class="fill" style="width:{{ (progress.forwarded / progress.processed * 100)|int }}%">{{ (progress.forwarded / progress.processed * 100)|int }}%</div></div>
        </div>
        {% endif %}

        <div class="form-row" style="margin-top:8px;">
            <div class="row"><span class="k">Source</span><span class="v">{{ progress.source }}</span></div>
            <div class="row"><span class="k">Started</span><span class="v">{{ progress.started_at[:19] if progress.started_at else '-' }}</span></div>
            <div class="row"><span class="k">Finished</span><span class="v">{{ progress.finished_at[:19] if progress.finished_at else '-' }}</span></div>
        </div>

        {% if progress.log %}
        <h2 style="margin-top:14px;">📋 Live Log</h2>
        <div style="background:var(--bg);border-radius:8px;padding:10px;max-height:250px;overflow-y:auto;font-family:monospace;font-size:11px;">
        {% for line in progress.log[-50:] %}<div>{{ line }}</div>{% endfor %}
        </div>
        {% endif %}

        {% if progress.status == 'finished' %}
        <div class="banner ok" style="margin-top:12px;"><div class="dot green"></div>🎉 Done! {{ progress.forwarded }} media items copied.</div>
        {% elif progress.status == 'error' %}
        <div class="banner err" style="margin-top:12px;"><div class="dot red"></div>Scraper stopped with an error — check the log.</div>
        {% endif %}

        {% else %}
        <p style="color:#666;text-align:center;padding:20px;">No scraper job yet. Fill in the form above and start copying.</p>
        {% endif %}
    </div>
</div>

<div class="tip-box">
    <strong>💡 Tips & Requirements</strong>
    <table>
        <tr><th>Source type</th><th>How to enter</th></tr>
        <tr><td>Public channel / group</td><td>@username</td></tr>
        <tr><td>Private group / supergroup</td><td>-1001234567890</td></tr>
        <tr><td>Supergroup WITH topics</td><td>Same — topics detected automatically</td></tr>
    </table>
    <p style="margin-top:8px;color:#888;">Use delay 3–5s for large chats. Bot must be Admin with Manage Topics in backup group.</p>
</div>
{% endblock %}
''')


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(filepath, default=None):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default or {}


def get_bot_status():
    status = monitor.get_bot_status()
    return status


def format_logs(logs, limit=50):
    result = []
    for log in reversed(logs[-limit:]):
        ts = log.get('timestamp', '')
        try:
            ts = datetime.fromisoformat(ts).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        result.append({
            'ts': ts,
            'source': log.get('source', '?'),
            'media_type': log.get('media_type', '?'),
            'message_id': log.get('message_id', ''),
            'status': log.get('status', 'unknown'),
        })
    return result


def base_ctx(page):
    bs = get_bot_status()
    csum = config_mgr.get_config_summary()
    return {
        'page': page,
        'bot_running': bs['is_running'],
        'uptime': bs.get('uptime', 'Stopped'),
        'bot_pid': bs.get('process_id', 'N/A'),
        'bot_mem': bs.get('memory_usage', 'N/A'),
        'bot_cpu': bs.get('cpu_usage', 'N/A'),
        'config_ok': csum['is_complete'],
        'csum': csum,
        'now': datetime.now(),
        'msg_text': '',
        'msg_type': 'info',
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    ctx = base_ctx('dashboard')
    bs = get_bot_status()
    ctx.update({
        'stats': analytics.get_summary_stats(),
        'csum': config_mgr.get_config_summary(),
        'recent_logs': format_logs(load_json('bot/activity_logs.json', []), 10),
    })
    return render_template_string(DASHBOARD_TEMPLATE, **ctx)


@app.route('/analytics')
def analytics_page():
    ctx = base_ctx('analytics')
    daily = analytics.get_daily_activity(7)
    hourly = analytics.get_hourly_activity(24)
    media = analytics.get_media_types_distribution()
    ctx.update({
        'stats': analytics.get_summary_stats(),
        'daily_labels': [d['date'] for d in daily],
        'daily_counts': [d['count'] for d in daily],
        'hourly_labels': [h['hour'] for h in hourly],
        'hourly_counts': [h['count'] for h in hourly],
        'media_labels': list(media.keys()),
        'media_counts': list(media.values()),
    })
    return render_template_string(ANALYTICS_TEMPLATE, **ctx)


@app.route('/topics')
def topics_page():
    ctx = base_ctx('topics')
    topics = load_json('bot/topics.json', {})
    timeline = analytics.get_topics_timeline()
    topic_counts = {}
    stats = load_json('bot/stats.json', {})
    for name in topics:
        topic_counts[name] = stats.get('topics', {}).get(name, 0)
    ctx.update({'topics': topics, 'timeline': timeline, 'topic_counts': topic_counts})
    return render_template_string(TOPICS_TEMPLATE, **ctx)


@app.route('/logs')
def logs_page():
    ctx = base_ctx('logs')
    limit = int(request.args.get('limit', 50))
    logs = load_json('bot/activity_logs.json', [])
    ctx.update({'logs': format_logs(logs, limit), 'limit': limit})
    return render_template_string(LOGS_TEMPLATE, **ctx)


@app.route('/config', methods=['GET'])
def config_page():
    ctx = base_ctx('config')
    ctx.update({
        'config': config_mgr.get_current_config(),
        'csum': config_mgr.get_config_summary(),
        'diagnostics': config_mgr.run_diagnostics(),
    })
    return render_template_string(CONFIG_TEMPLATE, **ctx)


@app.route('/config/save', methods=['POST'])
def config_save():
    group_id = request.form.get('backup_group_id', '').strip()
    if group_id:
        try:
            int(group_id)
            config_mgr.update_config(backup_group_id=group_id)
            return redirect('/config?msg=saved')
        except ValueError:
            return redirect('/config?msg=invalid')
    return redirect('/config')


@app.route('/system')
def system_page():
    ctx = base_ctx('system')
    sys_info = monitor.get_system_info()
    data_files = []
    for fpath, flabel in [
        ('config.json', 'Configuration'),
        ('bot/topics.json', 'Topics Mapping'),
        ('bot/stats.json', 'Statistics'),
        ('bot/activity_logs.json', 'Activity Logs'),
    ]:
        if os.path.exists(fpath):
            data_files.append({
                'exists': True,
                'size': os.path.getsize(fpath),
                'modified': datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M'),
                'label': flabel,
            })
        else:
            data_files.append({'exists': False, 'label': flabel})
    ctx.update({
        'sys_info': sys_info,
        'data_files': data_files,
        'topics_count': monitor.get_topics_count(),
    })
    return render_template_string(SYSTEM_TEMPLATE, **ctx)


@app.route('/debug', methods=['GET'])
def debug_page():
    ctx = base_ctx('debug')
    raw = load_json('bot/debug_log.json', [])
    EVENT_ICONS = {
        "incoming": "📩", "forwarding": "🚀", "success": "✅", "failed": "❌",
        "error": "💥", "skipped_bot": "🤖", "skipped_type": "🔕",
        "skipped_ignored": "🚫", "skipped_ignored_fwd": "🚫",
        "skipped_backup": "🔄", "skipped_no_media": "📝", "catch_all": "📨",
    }
    entries = []
    for e in reversed(raw[-100:]):
        ts = e.get('timestamp', '')
        try:
            ts = datetime.fromisoformat(ts).strftime('%H:%M:%S')
        except Exception:
            pass
        entries.append({
            'ts': ts,
            'icon': EVENT_ICONS.get(e.get('event', ''), '•'),
            'event': e.get('event', ''),
            'chat_title': e.get('chat_title', ''),
            'chat_id': e.get('chat_id', ''),
            'detail': e.get('detail', ''),
        })
    ctx.update({'debug_entries': entries})
    return render_template_string(DEBUG_TEMPLATE, **ctx)


@app.route('/debug/clear', methods=['POST'])
def debug_clear():
    try:
        with open('bot/debug_log.json', 'w') as f:
            json.dump([], f)
    except Exception:
        pass
    return redirect('/debug')


@app.route('/copy', methods=['GET'])
def copy_page():
    ctx = base_ctx('copy')
    progress = load_json('bot/scraper_progress.json', {})
    is_running = bool(progress and progress.get('status') in ('running', 'starting'))
    ctx.update({'progress': progress, 'scraper_running': is_running})
    return render_template_string(COPY_TEMPLATE, **ctx)


@app.route('/copy/start', methods=['POST'])
def copy_start():
    source_chat = request.form.get('source_chat', '').strip()
    if not source_chat:
        return redirect('/copy')
    backup_group_id = os.getenv('BACKUP_GROUP_ID', '')
    if not backup_group_id:
        return redirect('/copy')

    cmd = [sys.executable, 'utils/history_scraper.py', source_chat, backup_group_id, '--delay', str(request.form.get('delay', '3'))]
    limit = request.form.get('limit', '0')
    if limit and int(limit) > 0:
        cmd += ['--limit', str(int(limit))]
    from_date = request.form.get('from_date', '')
    if from_date:
        cmd += ['--from-date', from_date]
    to_date = request.form.get('to_date', '')
    if to_date:
        cmd += ['--to-date', to_date]
    topic_id = request.form.get('topic_id', '').strip()
    if topic_id:
        try:
            cmd += ['--topic-id', str(int(topic_id))]
        except ValueError:
            pass

    subprocess.Popen(cmd, cwd=os.getcwd(), env=os.environ.copy())
    time.sleep(1.5)
    return redirect('/copy')


@app.route('/copy/stop', methods=['POST'])
def copy_stop():
    progress_file = 'bot/scraper_progress.json'
    p = load_json(progress_file, {})
    if p:
        p['status'] = 'stopped'
        with open(progress_file, 'w') as f:
            json.dump(p, f, indent=2)
    return redirect('/copy')


# ── Bot Control ────────────────────────────────────────────────────────────────

@app.route('/bot/start', methods=['POST'])
def bot_start():
    monitor.start_bot()
    time.sleep(2)
    return redirect(request.referrer or '/')


@app.route('/bot/stop', methods=['POST'])
def bot_stop():
    monitor.stop_bot()
    time.sleep(1)
    return redirect(request.referrer or '/')


@app.route('/bot/restart', methods=['POST'])
def bot_restart():
    monitor.restart_bot()
    time.sleep(2)
    return redirect(request.referrer or '/')


# ── Health Check ───────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    bs = get_bot_status()
    return jsonify({
        'status': 'ok' if bs['is_running'] else 'degraded',
        'bot_running': bs['is_running'],
        'timestamp': datetime.now().isoformat(),
    })


# ── Start Bot in Background ───────────────────────────────────────────────────

def start_bot_thread():
    time.sleep(3)
    if config_mgr.is_fully_configured():
        monitor.start_bot()


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))

    # Start bot in background thread
    bot_thread = threading.Thread(target=start_bot_thread, daemon=True)
    bot_thread.start()

    print(f"🌐 Flask dashboard starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
