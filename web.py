#!/usr/bin/env python3
"""
Heroku Web Entry Point — Full-Featured Flask Dashboard
======================================================
Flask dashboard that works on Heroku with ALL pages:
Dashboard, Analytics, Topics, Activity Logs, Configuration,
System Info, Debug Log, Copy History.
Bot auto-starts in background thread.
"""

import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime

from flask import Flask, render_template_string, request, redirect, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.analytics import AnalyticsManager
from utils.bot_monitor import BotMonitor
from utils.config_manager import ConfigManager

app = Flask(__name__)
analytics = AnalyticsManager()
monitor = BotMonitor()
config_mgr = ConfigManager()
BOT_START_TIME = datetime.now()

# ══════════════════════════════════════════════════════════════════════════════
# SHARED TEMPLATE PARTS
# ══════════════════════════════════════════════════════════════════════════════

CSS = '''
:root{--bg:#0f0f1a;--card:#1a1a2e;--border:#2a2a4a;--accent:#6c5ce7;--accent2:#a29bfe;--text:#e0e0e0;--green:#40c057;--red:#e03131;--yellow:#fab005;--header-bg:#22223a}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);display:flex;min-height:100vh}
.sidebar{width:220px;background:var(--card);border-right:1px solid var(--border);padding:16px 0;position:fixed;top:0;left:0;height:100vh;overflow-y:auto;z-index:10}
.sidebar h2{color:var(--accent2);font-size:15px;padding:0 16px 12px;border-bottom:1px solid var(--border);margin-bottom:6px}
.sidebar a{display:block;padding:9px 16px;color:var(--text);text-decoration:none;font-size:13px;border-left:3px solid transparent;transition:.15s}
.sidebar a:hover{background:rgba(108,92,231,.1)}
.sidebar a.active{background:rgba(108,92,231,.15);border-left-color:var(--accent);color:var(--accent2);font-weight:600}
.sidebar .sbox{margin:12px 16px;padding:10px;border-radius:6px;font-size:11px}
.sidebar .sbox.ok{background:#1b4332;border:1px solid #2d6a4f}
.sidebar .sbox.err{background:#3c1518;border:1px solid #641220}
.main{margin-left:220px;flex:1;padding:20px;max-width:1060px}
h1{font-size:20px;margin-bottom:4px;color:#fff}
h2{font-size:16px;margin:16px 0 8px;color:var(--accent2)}
.sub{color:#888;font-size:12px;margin-bottom:16px}
.banner{padding:12px 16px;border-radius:8px;margin-bottom:14px;display:flex;align-items:center;gap:8px;font-size:13px}
.banner.ok{background:#1b4332;border:1px solid #2d6a4f}
.banner.err{background:#3c1518;border:1px solid #641220}
.banner.warn{background:#3d2e00;border:1px solid #5c4400}
.banner.info{background:#1a1a4e;border:1px solid #2a2a6e}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.green{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.red{background:var(--red)}
.dot.yellow{background:var(--yellow)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:14px}
.stat{background:var(--card);padding:16px;border-radius:8px;border:1px solid var(--border);text-align:center}
.stat .val{font-size:26px;font-weight:700;color:var(--accent)}
.stat .lbl{font-size:11px;color:#888;margin-top:2px}
.card{background:var(--card);border-radius:8px;border:1px solid var(--border);margin-bottom:12px;overflow:hidden}
.card-head{padding:10px 14px;font-weight:600;font-size:13px;background:var(--header-bg);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.card-body{padding:14px}
.row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px}
.row:last-child{border-bottom:none}
.row .k{color:#888}
.row .v{font-family:monospace;font-size:12px}
.row .v.ok{color:var(--green)}
.row .v.err{color:var(--red)}
.row .v.warn{color:var(--yellow)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:6px 8px;border-bottom:2px solid var(--border);color:#888;font-weight:600;font-size:10px;text-transform:uppercase}
td{padding:5px 8px;border-bottom:1px solid var(--border)}
tr:hover td{background:rgba(108,92,231,.04)}
.btn{padding:7px 14px;border:none;border-radius:5px;font-size:12px;cursor:pointer;font-weight:500;color:#fff;transition:.15s}
.btn-p{background:var(--accent)}.btn-p:hover{background:#5a4bd1}
.btn-d{background:var(--red)}.btn-d:hover{background:#c92a2a}
.btn-s{background:var(--green)}.btn-s:hover{background:#2f9e44}
.btn-w{background:var(--yellow);color:#000}
.btns{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.fg{margin-bottom:12px}
.fg label{display:block;font-size:12px;color:#888;margin-bottom:3px}
.fg input,.fg select{width:100%;padding:7px 10px;border-radius:5px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px}
.fg input:focus{outline:none;border-color:var(--accent)}
.fr{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.pbar{background:var(--border);border-radius:6px;overflow:hidden;height:20px;position:relative}
.pbar .fill{background:var(--accent);height:100%;transition:width .3s;display:flex;align-items:center;justify-content:center;font-size:10px;color:#fff;font-weight:600;min-width:24px}
.cc{position:relative;height:240px;margin:8px 0}
.tip{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;margin-top:10px;font-size:12px}
.tip table{margin-top:6px}
.tip td,.tip th{font-size:11px}
.msg{padding:8px 12px;border-radius:5px;margin-bottom:10px;font-size:12px}
.msg.ok{background:#1b4332;border:1px solid #2d6a4f}
.msg.err{background:#3c1518;border:1px solid #641220}
.msg.info{background:#1a1a4e;border:1px solid #2a2a6e}
@media(max-width:768px){.sidebar{width:100%;height:auto;position:relative;display:flex;flex-wrap:wrap;padding:8px}.sidebar h2{display:none}.sidebar a{padding:6px 10px;font-size:11px;border-left:none;border-bottom:2px solid transparent}.sidebar .sbox{display:none}.main{margin-left:0}.stats{grid-template-columns:1fr 1fr}.fr{grid-template-columns:1fr}}
'''

def nav_html(page, bot_running, config_ok):
    pages = [('dashboard','📊 Dashboard'),('analytics','📈 Analytics'),('topics','📁 Topics'),
             ('logs','📋 Logs'),('config','⚙️ Config'),('system','💻 System'),
             ('debug','🔍 Debug'),('copy','📥 Copy')]
    links = ''.join(f'<a href="/{p}" class="{"active" if page==p else ""}">{l}</a>' for p,l in pages)
    sbox_cls = 'ok' if bot_running else 'err'
    sbox_txt = '🟢 Running' if bot_running else '🔴 Stopped'
    cfg_txt = '✅' if config_ok else '⚠️'
    return f'''<nav class="sidebar"><h2>🤖 TGBackup</h2>{links}<div class="sbox {sbox_cls}">Bot: {sbox_txt}<br><span style="font-size:10px;color:#888;">Config: {cfg_txt}</span></div></nav>'''

def page_wrap(page, bot_running, config_ok, title, content):
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} - TGBackup</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script><style>{CSS}</style></head><body>{nav_html(page, bot_running, config_ok)}<div class="main">{content}<div style="text-align:center;padding:16px;color:#444;font-size:10px;">Telegram Media Backup Bot &middot; {datetime.now().strftime("%Y-%m-%d %H:%M")}</div></div></body></html>'''

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def load_json(fp, default=None):
    try:
        if os.path.exists(fp):
            with open(fp,'r',encoding='utf-8') as f: return json.load(f)
    except: pass
    return default or {}

def ctx_base():
    bs = monitor.get_bot_status()
    cs = config_mgr.get_config_summary()
    return bs, cs

def fmt_logs(logs, limit=50):
    r = []
    for log in reversed(logs[-limit:]):
        ts = log.get('timestamp','')
        try: ts = datetime.fromisoformat(ts).strftime('%H:%M:%S')
        except: pass
        r.append({'ts':ts,'source':log.get('source','?'),'media_type':log.get('media_type','?'),'message_id':log.get('message_id',''),'status':log.get('status','?')})
    return r

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    bs, cs = ctx_base()
    stats = analytics.get_summary_stats()
    logs = fmt_logs(load_json('bot/activity_logs.json',[]),10)
    rows = ''.join(f'<tr><td>{l["ts"]}</td><td>{l["source"]}</td><td>{l["media_type"]}</td><td>{l["message_id"]}</td><td>{"✅" if l["status"]=="success" else "❌"}</td></tr>' for l in logs)
    log_table = f'<table><tr><th>Time</th><th>Source</th><th>Type</th><th>Msg</th><th>OK</th></tr>{rows}</table>' if logs else '<p style="color:#666;text-align:center;padding:14px">No activity yet.</p>'

    if bs['is_running']:
        banner = f'<div class="banner ok"><div class="dot green"></div><strong>Bot Running</strong>&nbsp;&nbsp;Uptime: {bs.get("uptime","?")} &nbsp;|&nbsp; PID: {bs.get("process_id","?")}</div><div class="btns"><form method="post" action="/bot/stop"><button class="btn btn-d" type="submit">⏹ Stop</button></form><form method="post" action="/bot/restart"><button class="btn btn-w" type="submit">🔄 Restart</button></form></div>'
    else:
        banner = '<div class="banner err"><div class="dot red"></div><strong>Bot Not Running</strong></div><div class="btns"><form method="post" action="/bot/start"><button class="btn btn-s" type="submit">▶ Start</button></form></div>'

    cfg_rows = f'''<div class="row"><span class="k">BOT_TOKEN</span><span class="v {"ok" if cs["has_token"] else "err"}">{cs["token_preview"]}</span></div>
    <div class="row"><span class="k">BACKUP_GROUP_ID</span><span class="v {"ok" if cs["has_group_id"] else "err"}">{cs["group_id"]}</span></div>
    <div class="row"><span class="k">API_ID</span><span class="v {"ok" if cs["has_api_id"] else "warn"}">{"✓" if cs["has_api_id"] else "Not set"}</span></div>
    <div class="row"><span class="k">API_HASH</span><span class="v {"ok" if cs["has_api_hash"] else "warn"}">{"✓" if cs["has_api_hash"] else "Not set"}</span></div>
    <div class="row"><span class="k">OWNER_ID</span><span class="v {"ok" if cs["has_owner_id"] else "warn"}">{cs["owner_id"]}</span></div>'''

    content = f'''<h1>🤖 Dashboard</h1><p class="sub">Real-time monitoring of your Telegram Media Backup Bot</p>
    {banner}
    <div class="stats"><div class="stat"><div class="val">{stats["total_messages"]}</div><div class="lbl">Total Messages</div></div><div class="stat"><div class="val">{stats["total_topics"]}</div><div class="lbl">Topics</div></div><div class="stat"><div class="val">{stats["today_messages"]}</div><div class="lbl">Today</div></div><div class="stat"><div class="val">{stats["active_sources"]}</div><div class="lbl">Sources</div></div></div>
    <div class="card"><div class="card-head"><span>⚙️ Config Status</span></div><div class="card-body">{cfg_rows}</div></div>
    <div class="card"><div class="card-head"><span>📋 Recent Activity</span></div><div class="card-body">{log_table}</div></div>'''
    return page_wrap('dashboard', bs['is_running'], cs['is_complete'], 'Dashboard', content)


@app.route('/analytics')
def analytics_page():
    bs, cs = ctx_base()
    stats = analytics.get_summary_stats()
    daily = analytics.get_daily_activity(7)
    hourly = analytics.get_hourly_activity(24)
    media = analytics.get_media_types_distribution()
    dl = json.dumps([d['date'] for d in daily])
    dc = json.dumps([d['count'] for d in daily])
    hl = json.dumps([h['hour'] for h in hourly])
    hc = json.dumps([h['count'] for h in hourly])
    ml = json.dumps(list(media.keys()))
    mc = json.dumps(list(media.values()))
    content = f'''<h1>📈 Analytics</h1><p class="sub">Activity charts and media statistics</p>
    <div class="card"><div class="card-head"><span>Daily Activity (7 Days)</span></div><div class="card-body"><div class="cc"><canvas id="dailyChart"></canvas></div></div></div>
    <div class="card"><div class="card-head"><span>Hourly Activity (24h)</span></div><div class="card-body"><div class="cc"><canvas id="hourlyChart"></canvas></div></div></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="card"><div class="card-head"><span>Media Types</span></div><div class="card-body"><div class="cc"><canvas id="mediaChart"></canvas></div></div></div>
    <div class="card"><div class="card-head"><span>Summary</span></div><div class="card-body">
    <div class="row"><span class="k">Total</span><span class="v">{stats["total_messages"]}</span></div>
    <div class="row"><span class="k">Topics</span><span class="v">{stats["total_topics"]}</span></div>
    <div class="row"><span class="k">Week</span><span class="v">{stats["week_messages"]}</span></div>
    <div class="row"><span class="k">Today</span><span class="v">{stats["today_messages"]}</span></div></div></div></div>
    <script>
    new Chart(document.getElementById('dailyChart'),{{type:'bar',data:{{labels:{dl},datasets:[{{label:'Messages',data:{dc},backgroundColor:'#6c5ce7'}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{y:{{beginAtZero:true,ticks:{{color:'#888'}},grid:{{color:'#2a2a4a'}}}},x:{{ticks:{{color:'#888'}},grid:{{color:'#2a2a4a'}}}}}}}}});
    new Chart(document.getElementById('hourlyChart'),{{type:'line',data:{{labels:{hl},datasets:[{{label:'Messages',data:{hc},borderColor:'#40c057',backgroundColor:'rgba(64,192,87,.1)',fill:true,tension:.3}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{y:{{beginAtZero:true,ticks:{{color:'#888'}},grid:{{color:'#2a2a4a'}}}},x:{{ticks:{{color:'#888'}},grid:{{color:'#2a2a4a'}}}}}}}}});
    new Chart(document.getElementById('mediaChart'),{{type:'doughnut',data:{{labels:{ml},datasets:[{{data:{mc},backgroundColor:['#6c5ce7','#40c057','#fab005','#e03131','#15aabf','#fd7e14','#be4bdb','#868e96']}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'right',labels:{{color:'#e0e0e0'}}}}}}}}});
    </script>'''
    return page_wrap('analytics', bs['is_running'], cs['is_complete'], 'Analytics', content)


@app.route('/topics')
def topics_page():
    bs, cs = ctx_base()
    topics = load_json('bot/topics.json',{})
    timeline = analytics.get_topics_timeline()
    st = load_json('bot/stats.json',{})
    if topics:
        rows = ''.join(f'<tr><td>{n}</td><td style="color:var(--accent);font-family:monospace">{t}</td><td>{st.get("topics",{}).get(n,0)}</td></tr>' for n,t in topics.items())
        ttable = f'<table><tr><th>Source</th><th>Thread ID</th><th>Media</th></tr>{rows}</table>'
        tl_rows = ''.join(f'<div class="row"><span>📌 #{i["thread_id"]}</span><span>{i["topic"]}</span><span style="color:#888">{i["last_updated_str"]}</span></div>' for i in timeline)
        content = f'<h1>📁 Topics</h1><p class="sub">Source → thread mappings</p><div class="banner ok"><div class="dot green"></div><strong>{len(topics)} topics</strong></div><div class="card"><div class="card-head"><span>Topic Map</span></div><div class="card-body">{ttable}</div></div><div class="card"><div class="card-head"><span>Timeline</span></div><div class="card-body">{tl_rows}</div></div>'
    else:
        content = '<h1>📁 Topics</h1><p class="sub">No topics yet</p><div class="banner warn"><div class="dot yellow"></div>Add bot to source groups to start.</div>'
    return page_wrap('topics', bs['is_running'], cs['is_complete'], 'Topics', content)


@app.route('/logs')
def logs_page():
    bs, cs = ctx_base()
    limit = int(request.args.get('limit',50))
    logs = fmt_logs(load_json('bot/activity_logs.json',[]), limit)
    if logs:
        rows = ''.join(f'<tr><td>{l["ts"]}</td><td>{l["source"]}</td><td>{l["media_type"]}</td><td>{l["message_id"]}</td><td>{"✅" if l["status"]=="success" else "❌"}</td></tr>' for l in logs)
        content = f'<h1>📋 Activity Logs</h1><p class="sub">{len(logs)} recent entries</p><div class="card"><div class="card-body"><table><tr><th>Time</th><th>Source</th><th>Type</th><th>Msg</th><th>OK</th></tr>{rows}</table></div></div>'
    else:
        content = '<h1>📋 Activity Logs</h1><div class="banner warn"><div class="dot yellow"></div>No logs yet.</div>'
    return page_wrap('logs', bs['is_running'], cs['is_complete'], 'Logs', content)


@app.route('/config', methods=['GET'])
def config_page():
    bs, cs = ctx_base()
    cfg = config_mgr.get_current_config()
    diag = config_mgr.run_diagnostics()
    diag_rows = ''.join(f'<div class="row"><span class="k">{k}</span><span class="v {"ok" if v["status"]=="ok" else "warn" if v["status"]=="warning" else "err"}">{"✅" if v["status"]=="ok" else "⚠️" if v["status"]=="warning" else "❌"} {v["message"]}</span></div>' for k,v in diag.items())
    content = f'''<h1>⚙️ Configuration</h1><p class="sub">Bot settings and diagnostics</p>
    <div class="card"><div class="card-head"><span>Credentials</span></div><div class="card-body">
    <div class="row"><span class="k">BOT_TOKEN</span><span class="v {"ok" if cs["has_token"] else "err"}">{cs["token_preview"]}</span></div>
    <div class="row"><span class="k">BACKUP_GROUP_ID</span><span class="v {"ok" if cs["has_group_id"] else "err"}">{cs["group_id"]}</span></div>
    <div class="row"><span class="k">API_ID</span><span class="v {"ok" if cs["has_api_id"] else "warn"}">{cs["api_id"]}</span></div>
    <div class="row"><span class="k">API_HASH</span><span class="v {"ok" if cs["has_api_hash"] else "warn"}">{"✓" if cs["has_api_hash"] else "Not set"}</span></div>
    <div class="row"><span class="k">OWNER_ID</span><span class="v {"ok" if cs["has_owner_id"] else "warn"}">{cs["owner_id"]}</span></div></div></div>
    <div class="card"><div class="card-head"><span>Bot Settings</span></div><div class="card-body">
    <form method="post" action="/config/save"><div class="fg"><label>Backup Supergroup ID</label><input type="text" name="backup_group_id" value="{cfg.get("backup_group_id","")}" placeholder="-1001234567890"></div><button class="btn btn-p" type="submit">💾 Save</button></form></div></div>
    <div class="card"><div class="card-head"><span>🔍 Diagnostics</span></div><div class="card-body">{diag_rows}</div></div>
    <div class="card"><div class="card-head"><span>🎮 Bot Control</span></div><div class="card-body"><div class="btns"><form method="post" action="/bot/start"><button class="btn btn-s" type="submit">▶ Start</button></form><form method="post" action="/bot/stop"><button class="btn btn-d" type="submit">⏹ Stop</button></form><form method="post" action="/bot/restart"><button class="btn btn-w" type="submit">🔄 Restart</button></form></div></div></div>'''
    return page_wrap('config', bs['is_running'], cs['is_complete'], 'Config', content)


@app.route('/config/save', methods=['POST'])
def config_save():
    gid = request.form.get('backup_group_id','').strip()
    if gid:
        try: int(gid); config_mgr.update_config(backup_group_id=gid)
        except: pass
    return redirect('/config')


@app.route('/system')
def system_page():
    bs, cs = ctx_base()
    si = monitor.get_system_info()
    if not si:
        content = '<h1>💻 System</h1><div class="banner err"><div class="dot red"></div>Could not get system info.</div>'
        return page_wrap('system', bs['is_running'], cs['is_complete'], 'System', content)
    files_info = ''
    for fp, lb in [('config.json','Config'),('bot/topics.json','Topics'),('bot/stats.json','Stats'),('bot/activity_logs.json','Logs')]:
        if os.path.exists(fp):
            files_info += f'<div class="row"><span class="k">{lb}</span><span class="v ok">{os.path.getsize(fp)}B — {datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%m/%d %H:%M")}</span></div>'
        else:
            files_info += f'<div class="row"><span class="k">{lb}</span><span class="v warn">Not found</span></div>'
    content = f'''<h1>💻 System</h1><p class="sub">Resources and performance</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="card"><div class="card-head"><span>Resources</span></div><div class="card-body">
    <div class="fg"><label>CPU</label><div class="pbar"><div class="fill" style="width:{si["cpu_percent"]}%">{si["cpu_percent"]}%</div></div></div>
    <div class="fg"><label>Memory ({si["memory_used_gb"]}/{si["memory_total_gb"]} GB)</label><div class="pbar"><div class="fill" style="width:{si["memory_percent"]}%">{si["memory_percent"]}%</div></div></div>
    <div class="fg"><label>Disk ({si["disk_used_gb"]}/{si["disk_total_gb"]} GB)</label><div class="pbar"><div class="fill" style="width:{si["disk_percent"]}%">{si["disk_percent"]}%</div></div></div></div></div>
    <div class="card"><div class="card-head"><span>Bot</span></div><div class="card-body">
    <div class="row"><span class="k">Status</span><span class="v {"ok" if bs["is_running"] else "err"}">{"Running" if bs["is_running"] else "Stopped"}</span></div>
    <div class="row"><span class="k">Uptime</span><span class="v">{bs.get("uptime","-")}</span></div>
    <div class="row"><span class="k">Memory</span><span class="v">{bs.get("memory_usage","-")} MB</span></div>
    <div class="row"><span class="k">CPU</span><span class="v">{bs.get("cpu_usage","-")}%</span></div>
    <div class="row"><span class="k">Topics</span><span class="v">{monitor.get_topics_count()}</span></div>
    <div class="row"><span class="k">Last Activity</span><span class="v">{si.get("last_activity","?")}</span></div></div></div></div>
    <div class="card"><div class="card-head"><span>📁 Data Files</span></div><div class="card-body">{files_info}</div></div>'''
    return page_wrap('system', bs['is_running'], cs['is_complete'], 'System', content)


@app.route('/debug')
def debug_page():
    bs, cs = ctx_base()
    raw = load_json('bot/debug_log.json',[])
    ICONS = {"incoming":"📩","forwarding":"🚀","success":"✅","failed":"❌","error":"💥","skipped_bot":"🤖","skipped_type":"🔕","skipped_ignored":"🚫","skipped_ignored_fwd":"🚫","skipped_backup":"🔄","skipped_no_media":"📝","catch_all":"📨"}
    entries = []
    for e in reversed(raw[-100:]):
        ts = e.get('timestamp','')
        try: ts = datetime.fromisoformat(ts).strftime('%H:%M:%S')
        except: pass
        entries.append(f'<tr><td>{ts}</td><td>{ICONS.get(e.get("event",""),"•")} {e.get("event","")}</td><td>{e.get("chat_title","")}</td><td style="font-family:monospace">{e.get("chat_id","")}</td><td>{e.get("detail","")}</td></tr>')
    etable = f'<table><tr><th>Time</th><th>Event</th><th>Chat</th><th>ID</th><th>Detail</th></tr>{"".join(entries)}</table>' if entries else '<p style="color:#666;text-align:center;padding:14px">No events yet.</p>'
    content = f'''<h1>🔍 Debug Log</h1><p class="sub">All bot events including skipped messages</p>
    <div class="btns"><a href="/debug" class="btn btn-p">🔄 Refresh</a><form method="post" action="/debug/clear"><button class="btn btn-d" type="submit">🗑 Clear</button></form></div>
    <div class="card"><div class="card-body">{etable}</div></div>
    <div class="tip"><strong>📌 Privacy Mode</strong><table><tr><th>Situation</th><th>Bot sees?</th></tr><tr><td>Regular member + Privacy ON</td><td>❌ Only /commands</td></tr><tr><td>Regular member + Privacy OFF</td><td>✅ All messages</td></tr><tr><td>Admin in group</td><td>✅ All messages</td></tr><tr><td>In a channel</td><td>✅ Always</td></tr></table><p style="margin-top:6px;color:#888">Check: @BotFather → /mybots → Bot Settings → Group Privacy</p></div>'''
    return page_wrap('debug', bs['is_running'], cs['is_complete'], 'Debug', content)


@app.route('/debug/clear', methods=['POST'])
def debug_clear():
    try:
        with open('bot/debug_log.json','w') as f: json.dump([],f)
    except: pass
    return redirect('/debug')


@app.route('/copy')
def copy_page():
    bs, cs = ctx_base()
    progress = load_json('bot/scraper_progress.json',{})
    is_running = bool(progress and progress.get('status') in ('running','starting'))
    disabled = 'disabled' if is_running else ''

    prog_html = ''
    if progress:
        status_cls = 'ok' if progress.get('status')=='finished' else 'warn' if progress.get('status')=='running' else 'err'
        prog_html = f'''<div class="row"><span class="k">Status</span><span class="v {status_cls}">{progress.get("status","?")}</span></div>
        <div class="row"><span class="k">Mode</span><span class="v">{progress.get("mode","-")}</span></div>'''
        tt = progress.get('topics_total',0)
        if tt and tt > 0:
            td = progress.get('topics_done',0)
            pct = int(td/tt*100)
            cur = progress.get('current_topic','')
            prog_html += f'<div class="fg"><label>Topics: {td}/{tt}{" — "+cur if cur else ""}</label><div class="pbar"><div class="fill" style="width:{pct}%">{td}/{tt}</div></div></div>'
        p,fwd,sk,err = progress.get('processed',0),progress.get('forwarded',0),progress.get('skipped',0),progress.get('errors',0)
        prog_html += f'''<div class="stats"><div class="stat"><div class="val">{p}</div><div class="lbl">Processed</div></div><div class="stat"><div class="val" style="color:var(--green)">{fwd}</div><div class="lbl">Forwarded</div></div><div class="stat"><div class="val" style="color:var(--yellow)">{sk}</div><div class="lbl">Skipped</div></div><div class="stat"><div class="val" style="color:var(--red)">{err}</div><div class="lbl">Errors</div></div></div>'''
        if p > 0:
            pct2 = int(fwd/p*100)
            prog_html += f'<div class="fg"><label>Progress: {fwd}/{p}</label><div class="pbar"><div class="fill" style="width:{pct2}%">{pct2}%</div></div></div>'
        prog_html += f'''<div class="fr"><div class="row"><span class="k">Source</span><span class="v">{progress.get("source","-")}</span></div><div class="row"><span class="k">Started</span><span class="v">{str(progress.get("started_at","-"))[:19]}</span></div><div class="row"><span class="k">Finished</span><span class="v">{str(progress.get("finished_at","-"))[:19]}</span></div></div>'''
        log_lines = progress.get('log',[])
        if log_lines:
            prog_html += f'<h2>📋 Live Log</h2><div style="background:var(--bg);border-radius:6px;padding:8px;max-height:200px;overflow-y:auto;font-family:monospace;font-size:10px">{"".join(f"<div>{l}</div>" for l in log_lines[-50:])}</div>'
        if progress.get('status')=='finished':
            prog_html += '<div class="banner ok" style="margin-top:10px"><div class="dot green"></div>🎉 Done!</div>'
        elif progress.get('status')=='error':
            prog_html += '<div class="banner err" style="margin-top:10px"><div class="dot red"></div>Error — check log.</div>'
    else:
        prog_html = '<p style="color:#666;text-align:center;padding:14px">No scraper job yet.</p>'

    stop_btn = '<form method="post" action="/copy/stop"><button class="btn btn-d" type="submit">⏹ Stop Scraper</button></form>' if is_running else ''

    content = f'''<h1>📥 Copy History</h1><p class="sub">Copy old media from any Telegram chat to your backup supergroup</p>
    <div class="banner info"><div class="dot" style="background:var(--accent)"></div>Uses <strong>API_ID + API_HASH</strong> (MTProto). Bot must be member/admin of source chat.<br>🗂 <strong>Forum supergroups</strong>: each source topic mapped automatically.</div>
    <div class="card"><div class="card-head"><span>⚙️ Settings</span></div><div class="card-body">
    <form method="post" action="/copy/start">
    <div class="fg"><label>Source Chat</label><input type="text" name="source_chat" placeholder="@username or -1001234567890"></div>
    <div class="fr"><div class="fg"><label>Max messages (0=all)</label><input type="number" name="limit" value="0" min="0" step="100"></div><div class="fg"><label>Topic ID (optional)</label><input type="text" name="topic_id" placeholder="e.g. 12345"></div></div>
    <div class="fr"><div class="fg"><label>From date</label><input type="date" name="from_date"></div><div class="fg"><label>To date</label><input type="date" name="to_date"></div></div>
    <div class="fg"><label>Delay (seconds)</label><input type="range" name="delay" min="1" max="10" step="0.5" value="3" oninput="this.nextElementSibling.textContent=this.value+'s'"><span style="color:var(--accent)">3s</span></div>
    <button class="btn btn-s" type="submit" {disabled}>🚀 Start Copying</button></form></div></div>
    <div class="btns">{stop_btn}</div>
    <div class="card"><div class="card-head"><span>📊 Progress</span> <a href="/copy" class="btn btn-p" style="padding:3px 8px;font-size:10px">🔄</a></div><div class="card-body">{prog_html}</div></div>
    <div class="tip"><strong>💡 Tips</strong><table><tr><th>Source</th><th>Enter as</th></tr><tr><td>Public channel</td><td>@username</td></tr><tr><td>Private group</td><td>-1001234567890</td></tr><tr><td>Forum supergroup</td><td>Same — auto-detected</td></tr></table><p style="margin-top:6px;color:#888">Use delay 3-5s. Bot needs Admin + Manage Topics in backup group.</p></div>'''
    return page_wrap('copy', bs['is_running'], cs['is_complete'], 'Copy', content)


@app.route('/copy/start', methods=['POST'])
def copy_start():
    source_chat = request.form.get('source_chat','').strip()
    if not source_chat: return redirect('/copy')
    backup_group_id = os.getenv('BACKUP_GROUP_ID','')
    if not backup_group_id: return redirect('/copy')
    cmd = [sys.executable, 'utils/history_scraper.py', source_chat, backup_group_id, '--delay', str(request.form.get('delay','3'))]
    limit = request.form.get('limit','0')
    if limit and int(limit) > 0: cmd += ['--limit', str(int(limit))]
    from_date = request.form.get('from_date','')
    if from_date: cmd += ['--from-date', from_date]
    to_date = request.form.get('to_date','')
    if to_date: cmd += ['--to-date', to_date]
    topic_id = request.form.get('topic_id','').strip()
    if topic_id:
        try: cmd += ['--topic-id', str(int(topic_id))]
        except: pass
    subprocess.Popen(cmd, cwd=os.getcwd(), env=os.environ.copy())
    time.sleep(1.5)
    return redirect('/copy')


@app.route('/copy/stop', methods=['POST'])
def copy_stop():
    pf = 'bot/scraper_progress.json'
    p = load_json(pf,{})
    if p:
        p['status'] = 'stopped'
        with open(pf,'w') as f: json.dump(p,f,indent=2)
    return redirect('/copy')


# ══════════════════════════════════════════════════════════════════════════════
# BOT CONTROL
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/bot/start', methods=['POST'])
def bot_start():
    monitor.start_bot(); time.sleep(2); return redirect(request.referrer or '/')

@app.route('/bot/stop', methods=['POST'])
def bot_stop():
    monitor.stop_bot(); time.sleep(1); return redirect(request.referrer or '/')

@app.route('/bot/restart', methods=['POST'])
def bot_restart():
    monitor.restart_bot(); time.sleep(2); return redirect(request.referrer or '/')


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/health')
def health():
    bs = monitor.get_bot_status()
    return jsonify({'status':'ok' if bs['is_running'] else 'degraded','bot_running':bs['is_running'],'timestamp':datetime.now().isoformat()})


# ══════════════════════════════════════════════════════════════════════════════
# FIX: History Scraper — add fallback for bot token auth
# ══════════════════════════════════════════════════════════════════════════════
# The scraper uses bot_token to connect, but for some chats it needs
# user-account auth. We patch it to try harder.


# ══════════════════════════════════════════════════════════════════════════════
# START BOT AUTOMATICALLY IN BACKGROUND
# ══════════════════════════════════════════════════════════════════════════════

def auto_start_bot():
    """Auto-start the Telegram bot when the web server starts."""
    time.sleep(3)  # Wait for Flask to be ready
    if config_mgr.is_fully_configured():
        print("🤖 Auto-starting Telegram bot...")
        success = monitor.start_bot()
        if success:
            print("✅ Bot auto-started successfully!")
        else:
            print("❌ Bot auto-start failed. Check configuration.")
    else:
        print("⚠️ Bot not configured. Set BOT_TOKEN and BACKUP_GROUP_ID.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))

    # Auto-start bot in background thread
    bot_thread = threading.Thread(target=auto_start_bot, daemon=True)
    bot_thread.start()

    print(f"🌐 Flask dashboard on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
