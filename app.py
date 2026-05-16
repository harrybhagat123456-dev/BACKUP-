#!/usr/bin/env python3
"""
Telegram Bot Dashboard - Streamlit App
Monitoring and configuration dashboard for the Telegram Media Backup Bot
"""

import streamlit as st
import json
import os
import sys
import subprocess
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.analytics import AnalyticsManager
from utils.bot_monitor import BotMonitor
from utils.config_manager import ConfigManager

# Page configuration
st.set_page_config(
    page_title="Telegram Bot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        text-align: center;
    }
    .status-running {
        color: #28a745;
        font-weight: bold;
    }
    .status-stopped {
        color: #dc3545;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize managers
@st.cache_resource
def get_managers():
    return {
        'analytics': AnalyticsManager(),
        'monitor': BotMonitor(),
        'config': ConfigManager()
    }

managers = get_managers()

# Auto-start bot on dashboard load (once per session)
if 'bot_autostarted' not in st.session_state:
    st.session_state.bot_autostarted = True
    if not managers['monitor'].is_bot_running():
        managers['monitor'].start_bot()

# Sidebar navigation
st.sidebar.title("🤖 Telegram Bot")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Analytics", "Topics", "Activity Logs", "Configuration", "System Info", "Debug Log", "Copy History"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Quick Status**")

bot_status = managers['monitor'].get_bot_status()
if bot_status['is_running']:
    st.sidebar.success("Bot: Running")
else:
    st.sidebar.error("Bot: Stopped")

config_summary = managers['config'].get_config_summary()
if config_summary['is_complete']:
    st.sidebar.success("Config: Complete")
else:
    st.sidebar.warning("Config: Incomplete")

st.sidebar.markdown("---")
if st.sidebar.button("Refresh Data"):
    st.rerun()


# ========== DASHBOARD PAGE ==========
if page == "Dashboard":
    st.title("🤖 Telegram Bot Dashboard")
    st.markdown("Real-time monitoring of your Telegram Media Backup Bot")
    
    # Bot Status Banner
    if bot_status['is_running']:
        st.success(f"✅ Bot is running | Uptime: {bot_status.get('uptime', 'N/A')} | PID: {bot_status.get('process_id', 'N/A')}")
        b1, b2, b3 = st.columns([1, 1, 5])
        with b1:
            if st.button("⏹ Stop Bot"):
                managers['monitor'].stop_bot()
                st.rerun()
        with b2:
            if st.button("🔄 Restart"):
                managers['monitor'].restart_bot()
                time.sleep(2)
                st.rerun()
    else:
        st.error("❌ Bot is not running")
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("▶ Start Bot", type="primary"):
                if managers['config'].is_fully_configured():
                    with st.spinner("Starting bot..."):
                        success = managers['monitor'].start_bot()
                    if success:
                        st.success("Bot started successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to start bot. Check configuration.")
                else:
                    st.error("Bot is not configured. Go to Configuration page.")
    
    st.markdown("---")
    
    # Stats
    stats = managers['analytics'].get_summary_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Messages", stats.get('total_messages', 0))
    with col2:
        st.metric("Topics Created", stats.get('total_topics', 0))
    with col3:
        st.metric("Today's Messages", stats.get('today_messages', 0))
    with col4:
        st.metric("Active Sources", stats.get('active_sources', 0))
    
    st.markdown("---")
    
    # Configuration Status
    st.subheader("⚙️ Configuration Status")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Bot Token:**")
        if config_summary['has_token']:
            st.success(f"✅ Configured ({config_summary['token_preview']})")
        else:
            st.error("❌ Not configured")

        st.markdown("**API ID:**")
        if config_summary.get('has_api_id'):
            st.success(f"✅ Configured ({config_summary['api_id']})")
        else:
            st.warning("⚠️ Not set")

        st.markdown("**Owner ID:**")
        if config_summary.get('has_owner_id'):
            st.success(f"✅ Configured ({config_summary['owner_id']})")
        else:
            st.warning("⚠️ Not set")
    
    with col2:
        st.markdown("**Backup Group ID:**")
        if config_summary['has_group_id']:
            st.success(f"✅ Configured ({config_summary['group_id']})")
        else:
            st.error("❌ Not configured")

        st.markdown("**API Hash:**")
        if config_summary.get('has_api_hash'):
            st.success("✅ Configured (hidden)")
        else:
            st.warning("⚠️ Not set")
    
    if not config_summary['is_complete']:
        st.warning("⚠️ Bot requires configuration before it can run. Go to the **Configuration** page.")
    
    st.markdown("---")
    
    # Recent Activity
    st.subheader("📋 Recent Activity")
    recent_logs = managers['analytics'].get_recent_logs(10)
    
    if recent_logs:
        for log in reversed(recent_logs):
            ts = log.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts)
                ts_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                ts_str = ts
            
            status_icon = "✅" if log.get('status') == 'success' else "❌"
            st.text(f"{status_icon} [{ts_str}] {log.get('source', 'Unknown')} → {log.get('media_type', 'unknown')} (msg_id: {log.get('message_id', '?')})")
    else:
        st.info("No activity recorded yet. Once the bot is running and media is detected, activity will appear here.")


# ========== ANALYTICS PAGE ==========
elif page == "Analytics":
    st.title("📊 Analytics")
    
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        import pandas as pd
        
        # Daily activity
        st.subheader("Daily Activity (Last 7 Days)")
        daily_data = managers['analytics'].get_daily_activity(7)
        
        if daily_data and any(d['count'] > 0 for d in daily_data):
            df = pd.DataFrame(daily_data)
            fig = px.bar(df, x='date', y='count', title='Messages per Day',
                        color_discrete_sequence=['#007bff'])
            fig.update_layout(xaxis_title="Date", yaxis_title="Messages")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No daily activity data available yet.")
        
        # Hourly activity
        st.subheader("Hourly Activity (Last 24 Hours)")
        hourly_data = managers['analytics'].get_hourly_activity(24)
        
        if hourly_data and any(d['count'] > 0 for d in hourly_data):
            df_h = pd.DataFrame(hourly_data)
            fig_h = px.line(df_h, x='hour', y='count', title='Messages per Hour',
                           color_discrete_sequence=['#28a745'])
            fig_h.update_layout(xaxis_title="Hour", yaxis_title="Messages")
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.info("No hourly activity data available yet.")
        
        # Media type distribution
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Media Type Distribution")
            media_types = managers['analytics'].get_media_types_distribution()
            
            if media_types:
                fig_pie = px.pie(
                    values=list(media_types.values()),
                    names=list(media_types.keys()),
                    title='Media Types'
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No media type data available yet.")
        
        with col2:
            st.subheader("Summary Statistics")
            stats = managers['analytics'].get_summary_stats()
            st.metric("Total Messages Processed", stats.get('total_messages', 0))
            st.metric("Topics Created", stats.get('total_topics', 0))
            st.metric("This Week", stats.get('week_messages', 0))
            st.metric("Today", stats.get('today_messages', 0))
    
    except ImportError:
        st.error("Analytics requires plotly and pandas. Please install them.")


# ========== TOPICS PAGE ==========
elif page == "Topics":
    st.title("📁 Topics")
    st.markdown("Topic mappings between source groups and backup supergroup threads")
    
    topics_file = 'bot/topics.json'
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Refresh"):
            st.rerun()
    
    if os.path.exists(topics_file):
        try:
            with open(topics_file, 'r', encoding='utf-8') as f:
                topics = json.load(f)
            
            if topics:
                st.success(f"✅ {len(topics)} topics configured")
                
                # Display topics in a table
                import pandas as pd
                topic_data = []
                for name, thread_id in topics.items():
                    media_count = managers['analytics'].get_topic_media_count(name)
                    topic_data.append({
                        'Source Group': name,
                        'Thread ID': thread_id,
                        'Media Count': media_count
                    })
                
                df = pd.DataFrame(topic_data)
                st.dataframe(df, use_container_width=True)
                
                # Topics timeline
                st.subheader("Topics Timeline")
                timeline = managers['analytics'].get_topics_timeline()
                if timeline:
                    for item in timeline:
                        st.text(f"📌 Thread #{item['thread_id']:>6} | {item['topic']:<50} | Updated: {item['last_updated_str']}")
            else:
                st.info("No topics created yet. Topics are automatically created when the bot receives media from a new source.")
        except Exception as e:
            st.error(f"Error loading topics: {e}")
    else:
        st.info("Topics file not found. Topics will be created automatically when the bot processes media.")


# ========== ACTIVITY LOGS PAGE ==========
elif page == "Activity Logs":
    st.title("📋 Activity Logs")
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        limit = st.selectbox("Show last", [25, 50, 100, 200], index=1)
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()
    
    logs = managers['analytics'].get_recent_logs(limit)
    
    if logs:
        st.success(f"Showing {len(logs)} most recent log entries")
        
        # Display as table
        import pandas as pd
        log_data = []
        for log in reversed(logs):
            ts = log.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts)
                ts_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                ts_str = ts
            
            log_data.append({
                'Timestamp': ts_str,
                'Source': log.get('source', 'Unknown'),
                'Media Type': log.get('media_type', 'unknown'),
                'Message ID': log.get('message_id', ''),
                'Status': log.get('status', 'unknown')
            })
        
        df = pd.DataFrame(log_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No activity logs available yet.")


# ========== CONFIGURATION PAGE ==========
elif page == "Configuration":
    st.title("⚙️ Configuration")
    st.markdown("Configure your bot token and backup supergroup")
    
    config = managers['config'].get_current_config()
    
    st.subheader("Credential Status")

    cred_col1, cred_col2 = st.columns(2)
    with cred_col1:
        if config.get('bot_token'):
            st.success(f"✅ BOT_TOKEN — {config['bot_token'][:10]}...")
        else:
            st.error("❌ BOT_TOKEN — not set")

        if config.get('api_id'):
            st.success(f"✅ API_ID — {config['api_id']}")
        else:
            st.warning("⚠️ API_ID — not set")

        if config.get('owner_id'):
            st.success(f"✅ OWNER_ID — {config['owner_id']}")
        else:
            st.warning("⚠️ OWNER_ID — not set")

    with cred_col2:
        if config.get('backup_group_id'):
            st.success(f"✅ BACKUP_GROUP_ID — {config['backup_group_id']}")
        else:
            st.error("❌ BACKUP_GROUP_ID — not set")

        if config.get('api_hash'):
            st.success("✅ API_HASH — configured (hidden)")
        else:
            st.warning("⚠️ API_HASH — not set")

    st.info("BOT_TOKEN, API_ID, API_HASH, and OWNER_ID are loaded from Replit Secrets. To change them, update the Secrets tab.")

    st.markdown("---")
    st.subheader("Bot Settings")
    
    with st.form("config_form"):
        new_group_id = st.text_input(
            "Backup Supergroup ID",
            value=config.get('backup_group_id', ''),
            placeholder="e.g., -1001234567890"
        )
        
        submitted = st.form_submit_button("💾 Save Configuration")
        
        if submitted:
            if not new_group_id:
                st.error("Backup supergroup ID is required")
            else:
                try:
                    int(new_group_id.strip())
                    success = managers['config'].update_config(
                        backup_group_id=new_group_id.strip()
                    )
                    if success:
                        st.success("✅ Configuration saved successfully!")
                        st.info("Restart the bot for changes to take effect.")
                        st.rerun()
                    else:
                        st.error("Failed to save configuration")
                except ValueError:
                    st.error("Group ID must be a number (e.g., -1001234567890)")
    
    st.markdown("---")
    
    # Diagnostics
    st.subheader("🔍 Configuration Diagnostics")
    diagnostics = managers['config'].run_diagnostics()
    
    for check, result in diagnostics.items():
        status = result.get('status', 'unknown')
        message = result.get('message', '')
        
        if status == 'ok':
            st.success(f"✅ {check}: {message}")
        elif status == 'warning':
            st.warning(f"⚠️ {check}: {message}")
        else:
            st.error(f"❌ {check}: {message}")
    
    st.markdown("---")
    
    # Bot Control
    st.subheader("🎮 Bot Control")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("▶ Start Bot", type="primary"):
            if managers['config'].is_fully_configured():
                with st.spinner("Starting..."):
                    success = managers['monitor'].start_bot()
                if success:
                    st.success("Bot started!")
                else:
                    st.error("Failed to start. Check token and group ID.")
            else:
                st.error("Configure the bot first.")
    
    with col2:
        if st.button("⏹ Stop Bot"):
            with st.spinner("Stopping..."):
                success = managers['monitor'].stop_bot()
            if success:
                st.success("Bot stopped.")
            else:
                st.error("Failed to stop bot.")
    
    with col3:
        if st.button("🔄 Restart Bot"):
            if managers['config'].is_fully_configured():
                with st.spinner("Restarting..."):
                    success = managers['monitor'].restart_bot()
                if success:
                    st.success("Bot restarted!")
                else:
                    st.error("Failed to restart bot.")
            else:
                st.error("Configure the bot first.")
    
    st.markdown("---")
    
    # Setup Help
    with st.expander("📖 Setup Instructions"):
        st.markdown("""
        ### How to set up the Telegram Bot
        
        **1. Create a Bot:**
        - Open Telegram and search for `@BotFather`
        - Send `/newbot` and follow the instructions
        - Copy the token provided (format: `123456:ABCdef...`)
        
        **2. Create a Supergroup:**
        - Create a new Telegram group
        - Go to group settings → convert to supergroup
        - Enable **Topics** in the group settings
        - Make the bot an administrator with **Manage Topics** permission
        
        **3. Get the Supergroup ID:**
        - Add `@userinfobot` to the supergroup
        - It will show the group ID (a negative number like `-1001234567890`)
        - Remove `@userinfobot` afterwards
        
        **4. Add bot to source groups:**
        - Add your bot as a member to all source groups/channels
        - The bot needs to be able to read messages
        
        **5. Configure and Start:**
        - Enter the token and supergroup ID above
        - Click "Save Configuration"
        - Click "Start Bot"
        """)


# ========== SYSTEM INFO PAGE ==========
elif page == "System Info":
    st.title("💻 System Information")
    
    system_info = managers['monitor'].get_system_info()
    
    if system_info:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("System Resources")
            
            cpu = system_info.get('cpu_percent', 0)
            st.metric("CPU Usage", f"{cpu}%")
            st.progress(cpu / 100)
            
            mem_pct = system_info.get('memory_percent', 0)
            mem_used = system_info.get('memory_used_gb', 0)
            mem_total = system_info.get('memory_total_gb', 0)
            st.metric("Memory Usage", f"{mem_pct}% ({mem_used:.1f} / {mem_total:.1f} GB)")
            st.progress(mem_pct / 100)
            
            disk_pct = system_info.get('disk_percent', 0)
            disk_used = system_info.get('disk_used_gb', 0)
            disk_total = system_info.get('disk_total_gb', 0)
            st.metric("Disk Usage", f"{disk_pct}% ({disk_used:.1f} / {disk_total:.1f} GB)")
            st.progress(disk_pct / 100)
        
        with col2:
            st.subheader("Bot Information")
            
            bot_status = managers['monitor'].get_bot_status()
            
            st.metric("Bot Status", "Running" if bot_status['is_running'] else "Stopped")
            if bot_status['is_running']:
                st.metric("Uptime", bot_status.get('uptime', 'N/A'))
                if bot_status.get('memory_usage'):
                    st.metric("Bot Memory", f"{bot_status['memory_usage']} MB")
                if bot_status.get('cpu_usage') is not None:
                    st.metric("Bot CPU", f"{bot_status['cpu_usage']}%")
            
            st.metric("Topics Created", managers['monitor'].get_topics_count())
            st.metric("Last Activity", system_info.get('last_activity', 'Unknown'))
    else:
        st.error("Could not retrieve system information.")
    
    st.markdown("---")
    
    # File status
    st.subheader("📁 Data Files")
    files_to_check = [
        ('config.json', 'Configuration'),
        ('bot/topics.json', 'Topics Mapping'),
        ('bot/stats.json', 'Statistics'),
        ('bot/activity_logs.json', 'Activity Logs'),
    ]
    
    for filepath, label in files_to_check:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            st.success(f"✅ {label}: {filepath} ({size} bytes, modified {mtime.strftime('%Y-%m-%d %H:%M')})")
        else:
            st.warning(f"⚠️ {label}: {filepath} (not found)")

# ========== DEBUG LOG PAGE ==========
elif page == "Debug Log":
    st.title("🔍 Debug Log")
    st.markdown("Every update the bot receives is logged here, including why messages are skipped.")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Refresh"):
            st.rerun()
    with col2:
        if st.button("🗑 Clear Log"):
            try:
                with open('bot/debug_log.json', 'w') as f:
                    json.dump([], f)
                st.success("Log cleared.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not clear: {e}")

    debug_file = 'bot/debug_log.json'
    if os.path.exists(debug_file):
        try:
            with open(debug_file, 'r') as f:
                debug_entries = json.load(f)

            if debug_entries:
                st.success(f"{len(debug_entries)} events recorded")

                EVENT_ICONS = {
                    "incoming":        "📩",
                    "forwarding":      "🚀",
                    "success":         "✅",
                    "failed":          "❌",
                    "error":           "💥",
                    "skipped_bot":     "🤖",
                    "skipped_type":    "🔕",
                    "skipped_ignored": "🚫",
                    "skipped_ignored_fwd": "🚫",
                    "skipped_backup":  "🔄",
                    "skipped_no_media":"📝",
                    "catch_all":       "📨",
                }

                import pandas as pd
                rows = []
                for e in reversed(debug_entries):
                    ts = e.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts).strftime("%H:%M:%S")
                    except Exception:
                        pass
                    icon = EVENT_ICONS.get(e.get("event", ""), "•")
                    rows.append({
                        "Time": ts,
                        "Event": f"{icon} {e.get('event', '')}",
                        "Chat": e.get("chat_title", ""),
                        "Chat ID": e.get("chat_id", ""),
                        "Detail": e.get("detail", ""),
                    })

                st.dataframe(pd.DataFrame(rows), use_container_width=True)

                st.markdown("---")
                st.subheader("📌 Troubleshooting Tips")
                events = [e.get("event") for e in debug_entries]
                if not any(e in events for e in ["incoming", "catch_all"]):
                    st.error("❌ **No messages received at all.** The bot is running but Telegram is not sending updates.")
                    st.markdown("""
**Most likely cause — Bot Privacy Mode is ON.**

Fix it in one of these two ways:

**Option A (recommended): Disable privacy mode via @BotFather**
1. Open Telegram → search `@BotFather`
2. Send `/mybots` → choose your bot
3. Go to **Bot Settings → Group Privacy → Turn off**
4. Restart the bot from the Dashboard

**Option B: Make the bot Admin in every source group**
1. Open each source group
2. Go to group settings → Administrators
3. Add your bot as admin (any permissions are fine)
4. The bot will then see all messages
                    """)
                elif all(e == "skipped_backup" for e in events):
                    st.warning("⚠️ Bot is only seeing its own backup group. Add it to source groups too.")
                elif "skipped_no_media" in events and "success" not in events:
                    st.warning("⚠️ Bot receives messages but no media. Try sending a photo/video to the source group.")
                elif "success" in events:
                    st.success("✅ Bot is working correctly — media is being forwarded!")
                else:
                    st.info("Bot is receiving messages. Check the event log above for details.")
            else:
                st.info("No events logged yet. Send a message or media to a group where the bot is a member, then refresh.")
        except Exception as e:
            st.error(f"Error reading debug log: {e}")
    else:
        st.info("Debug log not created yet — it appears once the bot receives its first update.")

    st.markdown("---")
    st.subheader("🔧 Privacy Mode Checker")
    st.markdown("""
| Situation | Can bot see messages? |
|---|---|
| Bot is a **regular member** + Privacy ON | ❌ Only `/commands` |
| Bot is a **regular member** + Privacy OFF | ✅ All messages |
| Bot is an **admin** in the group | ✅ All messages |
| Bot is in a **channel** | ✅ Always sees channel posts |

> **Privacy mode is ON by default.** To check: open `@BotFather` → `/mybots` → your bot → Bot Settings → Group Privacy.
    """)


# ========== COPY HISTORY PAGE ==========
elif page == "Copy History":
    import subprocess

    PROGRESS_FILE  = "bot/scraper_progress.json"
    BACKUP_GRP_ID  = os.getenv("BACKUP_GROUP_ID", "")

    st.title("📥 Copy History")
    st.markdown(
        "Copy **old media messages** from any Telegram chat — including "
        "**supergroups with topics** — into your backup supergroup."
    )

    st.info(
        "Uses **API_ID + API_HASH** (MTProto) to read full message history. "
        "The bot must be a **member or admin** of the source chat.\n\n"
        "🗂 **Forum supergroups**: each source topic is automatically mapped to its own "
        "topic in the backup group (`SourceGroup › TopicName`)."
    )

    def load_progress():
        if os.path.exists(PROGRESS_FILE):
            try:
                with open(PROGRESS_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    progress   = load_progress()
    is_running = bool(progress and progress.get("status") in ("running", "starting"))

    # ── Settings form ─────────────────────────────────────────────────────────
    st.subheader("⚙️ Settings")

    with st.form("scraper_form"):
        source_chat = st.text_input(
            "Source Chat",
            placeholder="@username   or   -1001234567890",
            help="@username for public chats. Numeric ID for private groups/channels."
        )

        c1, c2 = st.columns(2)
        with c1:
            limit = st.number_input("Max messages (0 = all)", min_value=0, value=0, step=100)
        with c2:
            topic_id_str = st.text_input(
                "Only copy one topic ID (optional)",
                placeholder="e.g. 12345",
                help="Leave blank to copy ALL topics. Get the topic ID from the Topics page."
            )

        use_date = st.checkbox("Filter by date range")
        from_date = to_date = None
        if use_date:
            d1, d2 = st.columns(2)
            with d1:
                from_date = st.date_input("From (newest date, inclusive)")
            with d2:
                to_date   = st.date_input("To (oldest date, inclusive)")

        delay = st.slider(
            "Delay between copies (seconds)", 1.0, 10.0, 3.0, 0.5,
            help="Higher = safer from rate limits. Use 3–5 s for large chats."
        )

        start_btn = st.form_submit_button("🚀 Start Copying", disabled=is_running)

    if start_btn:
        if not source_chat.strip():
            st.error("Enter a source chat username or ID.")
        elif not BACKUP_GRP_ID:
            st.error("BACKUP_GROUP_ID secret is not set.")
        else:
            cmd = [
                sys.executable, "utils/history_scraper.py",
                source_chat.strip(), BACKUP_GRP_ID,
                "--delay", str(delay),
            ]
            if limit > 0:
                cmd += ["--limit", str(int(limit))]
            if use_date and from_date:
                cmd += ["--from-date", str(from_date)]
            if use_date and to_date:
                cmd += ["--to-date", str(to_date)]
            if topic_id_str.strip():
                try:
                    cmd += ["--topic-id", str(int(topic_id_str.strip()))]
                except ValueError:
                    st.error("Topic ID must be a number.")
                    st.stop()

            subprocess.Popen(cmd, cwd=os.getcwd(), env=os.environ.copy())
            time.sleep(1.5)
            st.success("✅ Scraper launched! See progress below.")
            st.rerun()

    # ── Stop button ───────────────────────────────────────────────────────────
    if is_running:
        if st.button("⏹ Stop Scraper"):
            p = load_progress()
            if p:
                p["status"] = "stopped"
                with open(PROGRESS_FILE, "w") as f:
                    json.dump(p, f, indent=2)
            st.warning("Stop signal sent — will halt after the current message.")
            st.rerun()

    st.markdown("---")

    # ── Live progress ─────────────────────────────────────────────────────────
    st.subheader("📊 Progress")
    rc1, rc2 = st.columns([1, 6])
    with rc1:
        if st.button("🔄 Refresh"):
            st.rerun()

    progress = load_progress()

    if progress:
        status = progress.get("status", "unknown")
        STATUS_MAP = {
            "starting":  "⏳ Starting…",
            "running":   "🟢 Running",
            "finished":  "✅ Finished",
            "stopped":   "🟡 Stopped by user",
            "error":     "🔴 Error",
        }
        st.markdown(f"**Status:** {STATUS_MAP.get(status, status)} &nbsp;|&nbsp; "
                    f"**Mode:** {progress.get('mode', '—')}")

        # Topic progress for forum supergroups
        t_done  = progress.get("topics_done",  0)
        t_total = progress.get("topics_total", 0)
        if t_total > 0:
            st.progress(
                min(t_done / t_total, 1.0),
                text=f"Topics: {t_done} / {t_total} done"
                     + (f" — current: {progress.get('current_topic', '')}" if progress.get("current_topic") else "")
            )

        # Message counters
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Processed",  progress.get("processed",  0))
        m2.metric("Forwarded",  progress.get("forwarded",  0))
        m3.metric("Skipped",    progress.get("skipped",    0))
        m4.metric("Errors",     progress.get("errors",     0))

        # Message-level progress bar
        fwd  = progress.get("forwarded",  0)
        proc = progress.get("processed",  0)
        if proc > 0:
            st.progress(min(fwd / proc, 1.0), text=f"Media forwarded: {fwd} / {proc} scanned")

        info_cols = st.columns(3)
        info_cols[0].markdown(f"**Source:** `{progress.get('source', '—')}`")
        if progress.get("started_at"):
            info_cols[1].markdown(f"**Started:** {progress['started_at'][:19].replace('T',' ')}")
        if progress.get("finished_at"):
            info_cols[2].markdown(f"**Finished:** {progress['finished_at'][:19].replace('T',' ')}")

        # Live log
        if progress.get("log"):
            st.subheader("📋 Live Log")
            st.code("\n".join(progress["log"][-50:]), language=None)

        if status == "error":
            st.error("Scraper stopped with an error — check the log above.")
        elif status == "finished":
            st.success(f"🎉 Done! **{progress.get('forwarded', 0)}** media items copied to your backup supergroup.")
    else:
        st.info("No scraper job yet. Fill in the form and click **🚀 Start Copying**.")

    st.markdown("---")
    st.subheader("💡 Tips & Requirements")
    st.markdown("""
| Source type | How to enter |
|---|---|
| Public channel / group | `@username` |
| Private group / supergroup | `-1001234567890` (numeric ID) |
| Supergroup WITH topics | Same — topics are detected automatically |

**Requirements:**
- Bot must be a **member** of the source chat (or chat is public)
- Bot must be **Admin with Manage Topics** in the backup supergroup
- For private groups without the bot: you'd need user-account auth (coming soon)

**Forum supergroups** — how it works:
- The scraper reads all topics from the source supergroup
- For each topic it creates a matching topic in backup: `SourceGroup › TopicName`
- Messages are routed to the correct topic
- Use the "Only copy one topic ID" field to copy a single topic

**Performance:**
- Use delay **3–5 s** for large chats to stay within Telegram rate limits
- The live bot and the scraper can run at the same time safely
    """)


# Footer
st.markdown("---")
st.markdown(
    f"<small>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"Telegram Media Backup Bot Dashboard</small>",
    unsafe_allow_html=True
)
