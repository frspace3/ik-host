import os
import time
import sqlite3
import datetime
import threading
import zipfile
import re
import psutil
import telebot

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'storage/ikhost.db')
restart_callback = None
bot = None
bot_lock = threading.Lock()
last_report_date = None
last_backup_date = None
last_warning_date = None
sched_lock = threading.Lock()
stop_event = threading.Event()
_config_cache = None
_config_cache_time = 0
_CONFIG_CACHE_TTL = 300  # seconds (5 minutes)

def register_restart_callback(cb):
    """Registers the server action callback from app.py to trigger restarts."""
    global restart_callback
    restart_callback = cb

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def read_config():
    global _config_cache, _config_cache_time
    now = time.time()
    if _config_cache is not None and (now - _config_cache_time) < _CONFIG_CACHE_TTL:
        return dict(_config_cache)  # Return a copy
    config = {
        'bot_token': '',
        'owner_id': '',
        'report_at': '06:30 AM',
        'zip_delay': 60,
        'hosting_name': '',
        'panel_url': '',
        'auto_backup': 'on',
        'backup_interval_days': 3,
        'last_auto_backup_date': '',
        'owner_username': 'imran',
        'owner_password': '',
        'admin_username': 'imran112233',
        'admin_password': ''
    }
    config_path = os.path.join(BASE_DIR, 'config.txt')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip().lower()
                        val = val.strip()
                        if key == 'bot token':
                            config['bot_token'] = val
                        elif key == 'owner id':
                            config['owner_id'] = val
                        elif key == 'report at':
                            config['report_at'] = val
                        elif key in ('hosting name', 'server name', 'hosting_name', 'server_name', 'host name', 'host_name'):
                            config['hosting_name'] = val
                        elif key in ('panel url', 'panel_url', 'hosting url', 'hosting_url'):
                            config['panel_url'] = val
                        elif key in ('auto backup', 'auto_backup', 'autobackup'):
                            config['auto_backup'] = 'on' if val.lower() in ('on', '1', 'true', 'yes', 'enable', 'enabled') else 'off'
                        elif key in ('backup interval', 'backup_interval_days', 'backup_days', 'interval_days'):
                            try:
                                config['backup_interval_days'] = max(1, int(val))
                            except:
                                pass
                        elif key in ('last auto backup', 'last_auto_backup_date', 'last_backup_date'):
                            config['last_auto_backup_date'] = val
                        elif key == 'zip_delay' or key == 'delay' or key == 'dely':
                            try:
                                config['zip_delay'] = int(val)
                            except:
                                pass
                        elif key == 'owner username' or key == 'owner user' or key == 'user':
                            config['owner_username'] = val
                        elif key == 'owner password' or key == 'owner pass' or key == 'password':
                            config['owner_password'] = val
                        elif key == 'admin panel username' or key == 'admin username':
                            config['admin_username'] = val
                        elif key == 'admin panel password' or key == 'admin password':
                            config['admin_password'] = val
        except Exception as e:
            print(f"[TelegramMonitor] Error reading config.txt: {e}")
    else:
        # Create a default blank config file
        write_config(config)
    _config_cache = dict(config)
    _config_cache_time = time.time()
    return config

def get_hosting_name():
    config = read_config()
    name = config.get('hosting_name', '').strip()
    if name:
        return name
    env_name = os.environ.get('HOSTING_NAME', '').strip()
    if env_name:
        return env_name
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "IK Host"

def write_config(config):
    config_path = os.path.join(BASE_DIR, 'config.txt')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(f"bot token = {config.get('bot_token', '')}\n")
            f.write(f"owner id = {config.get('owner_id', '')}\n")
            f.write(f"report at = {config.get('report_at', '06:30 AM')}\n")
            f.write(f"zip_delay = {config.get('zip_delay', 60)}\n")
            f.write(f"hosting name = {config.get('hosting_name', '')}\n")
            f.write(f"panel url = {config.get('panel_url', '')}\n")
            f.write(f"auto_backup = {config.get('auto_backup', 'on')}\n")
            f.write(f"backup_interval_days = {config.get('backup_interval_days', 3)}\n")
            f.write(f"last_auto_backup_date = {config.get('last_auto_backup_date', '')}\n")
            f.write(f"user = {config.get('owner_username', 'imran')}\n")
            f.write(f"password = {config.get('owner_password', '')}\n\n")
            f.write(f"#Admin Panel Credentials\n")
            f.write(f"#These credentials are used to access the administrator panel route (/admin/login / /admin/panel) and are stored in the admin_settings database table:\n")
            f.write(f"Admin Panel Username = {config.get('admin_username', 'imran112233')}\n")
            f.write(f"Admin Panel Password = {config.get('admin_password', '')}\n")
    except Exception as e:
        print(f"[TelegramMonitor] Error writing config.txt: {e}")
    global _config_cache, _config_cache_time
    _config_cache = None
    _config_cache_time = 0

def normalize_time_str(t_str):
    t_str = t_str.strip().upper()
    if 'AM' not in t_str and 'PM' not in t_str:
        t_str += ' AM'
    parts = t_str.split()
    time_part = parts[0]
    meridiem = parts[1] if len(parts) > 1 else 'AM'
    
    if ':' in time_part:
        h, m = time_part.split(':')
        try:
            h = int(h)
            m = int(m)
            if h >= 24:
                h = 0
            if h >= 12:
                if h > 12: h = h - 12
                meridiem = 'PM'
            elif h == 0:
                h = 12
                meridiem = 'AM'
            return f"{h:02d}:{m:02d} {meridiem}"
        except:
            pass
    return "06:30 AM"

def check_owner(message):
    config = read_config()
    owner_id = str(config['owner_id']).strip()
    sender_id = str(message.from_user.id).strip()
    return owner_id and sender_id == owner_id

def get_days_left():
    conn = get_db_conn()
    try:
        user = conn.execute("SELECT created_at FROM users ORDER BY id ASC LIMIT 1").fetchone()
    finally:
        conn.close()
    
    if not user or not user['created_at']:
        return 28
        
    created_at_str = user['created_at']
    try:
        digits = list(map(int, re.findall(r'\d+', created_at_str)))
        if len(digits) >= 3:
            # Fill missing time elements with 0
            while len(digits) < 6:
                digits.append(0)
            created_at_dt = datetime.datetime(*digits[:6])
            delta = datetime.datetime.now() - created_at_dt
            return max(0, 28 - delta.days)
    except Exception as e:
        print(f"[TelegramMonitor] Error parsing created_at: {e}")
    return 28

def get_hosting_url():
    # 1. Check config.txt for explicit panel url
    config = read_config()
    cfg_url = config.get('panel_url') or config.get('hosting_url')
    if cfg_url and cfg_url.strip():
        url = cfg_url.strip()
        if not url.startswith('http://') and not url.startswith('https://'):
            return f"https://{url}"
        return url

    # 2. Check Environment Variables (e.g. PANEL_URL, HOSTING_URL)
    env_url = os.environ.get('PANEL_URL') or os.environ.get('HOSTING_URL')
    if env_url and env_url.strip():
        url = env_url.strip()
        if not url.startswith('http://') and not url.startswith('https://'):
            return f"https://{url}"
        return url

    # 3. Check Railway Environment Variables automatically (RAILWAY_PUBLIC_DOMAIN / RAILWAY_STATIC_URL)
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN') or os.environ.get('RAILWAY_STATIC_URL')
    if railway_domain and railway_domain.strip():
        domain = railway_domain.strip()
        if not domain.startswith('http://') and not domain.startswith('https://'):
            return f"https://{domain}"
        return domain

    # 4. Search DB for non-localhost public_url
    conn = get_db_conn()
    try:
        rows = conn.execute("SELECT public_url FROM servers WHERE public_url IS NOT NULL AND public_url != ''").fetchall()
    finally:
        conn.close()

    for row in rows:
        url = row['public_url']
        if url and '127.0.0.1' not in url and 'localhost' not in url:
            if '/instance/' in url:
                return url.split('/instance/')[0]
            return url

    # 5. Localhost fallback
    return "http://localhost:5000"

def generate_report(host_url):
    conn = get_db_conn()
    try:
        users = conn.execute("SELECT * FROM users").fetchall()
        servers = conn.execute("SELECT * FROM servers").fetchall()
    finally:
        conn.close()
    
    days_left = get_days_left()
    emoji = "🔴" if days_left < 10 else "🟢"
    
    total_instances = len(servers)
    running = 0
    crashed = 0
    stopped = 0
    for s in servers:
        status_val = (s['status'] or '').strip().lower()
        if status_val == 'running':
            running += 1
        elif status_val == 'crashed':
            crashed += 1
        else:
            stopped += 1
    
    # Calculate RAM recursively for running servers
    total_ram = 0.0
    srv_ram_map = {}
    
    for s in servers:
        pid = s['pid']
        ram_mb = 0.0
        status_val = (s['status'] or '').strip().lower()
        if status_val == 'running' and pid and psutil.pid_exists(pid):
            try:
                from helpers import get_process_resources
                _, _, ram_mb = get_process_resources(pid)
            except Exception:
                pass
        srv_ram_map[s['id']] = ram_mb
        total_ram += ram_mb
        
    h_name = get_hosting_name()
    report = []
    report.append("📊 *IK HOST MONITORING REPORT*")
    report.append(f"🌐 *Hosting Server:* `{h_name}`")
    report.append("----------------------------------")
    report.append(f"🔗 *Panel URL:* {host_url}")
    report.append(f"⏳ *Trial Days Remaining:* {emoji} {days_left} Days Left")
    report.append("")
    report.append(f"👥 *Total Users:* {len(users)}")
    report.append(f"📦 *Total Instances:* {total_instances}")
    report.append(f"  🟢 Running: {running}")
    report.append(f"  🔴 Crashed: {crashed}")
    report.append(f"  ⚪ Stopped/Offline: {stopped}")
    report.append(f"💾 *Total RAM Consumed:* {total_ram:.1f} MB")
    report.append("----------------------------------")
    report.append("👤 *USER DETAILS & INSTANCES:*")
    
    for u in users:
        u_srvs = [s for s in servers if s['user_id'] == u['id']]
        report.append(f"\n*User:* {u['username']} ({u['email']})")
        report.append(f"🔑 *Password:* `[HIDDEN]`" if u['password'] else "🔑 *Password:* N/A")
        report.append(f"📦 *Instances Count:* {len(u_srvs)}")
        for idx, s in enumerate(u_srvs, 1):
            ram_mb = srv_ram_map.get(s['id'], 0.0)
            p_type_lower = (s['project_type'] or 'script').lower()
            p_type_display = 'Flask' if p_type_lower in ('flask', 'fastapi', 'django', 'node') else 'Bot'
            
            status_lower = (s['status'] or 'Offline').lower()
            if status_lower == 'running':
                status_display = 'running'
                status_emoji = '🟢'
            elif status_lower == 'crashed':
                status_display = 'Crashed'
                status_emoji = '🔴'
            else:
                status_display = 'Stopped'
                status_emoji = '⚪'
                
            if ram_mb == 0.0:
                ram_display = "0.0 MB"
            elif ram_mb.is_integer():
                ram_display = f"{int(ram_mb)} MB"
            else:
                ram_display = f"{ram_mb:.1f} MB"
                
            report.append(f"{idx}. {status_emoji}{s['name']} ({p_type_display}) | {status_display} | RAM: {ram_display}")
            
    return "\n".join(report)

def send_telegram_msg(chat_id, text):
    config = read_config()
    token = config.get('bot_token')
    if not token or token == 'YOUR_TELEGRAM_BOT_TOKEN':
        return
    
    with bot_lock:
        local_bot = bot

    if not local_bot:
        try:
            local_bot = telebot.TeleBot(token)
        except Exception as e_init:
            print(f"[TelegramMonitor] Could not create TeleBot for sending: {e_init}")
            local_bot = None

    if local_bot:
        try:
            local_bot.send_message(chat_id, text, parse_mode='Markdown')
        except Exception as e:
            try:
                # Fallback to plain text if markdown formatting fails
                local_bot.send_message(chat_id, text)
            except Exception as e_plain:
                print(f"[TelegramMonitor] Error sending message: {e_plain}")

def notify_hacking_attempt(username, password_hash, instance_name, folder):
    config = read_config()
    owner_id = config['owner_id']
    if not owner_id: return
    
    h_name = get_hosting_name()
    msg = (
        f"⚠️ *HACKING ATTEMPT DETECTED!*\n"
        f"🌐 *Hosting Server:* `{h_name}`\n"
        f"User: {username}\n"
        f"Instance: {instance_name} ({folder})\n"
        f"Action: Attempted to access restricted resources."
    )
    
    global bot
    with bot_lock:
        if not bot and config['bot_token'] and config['bot_token'] != 'YOUR_TELEGRAM_BOT_TOKEN':
            try:
                bot = telebot.TeleBot(config['bot_token'])
                register_handlers()
            except:
                pass
        local_bot = bot
            
    if local_bot:
        try:
            local_bot.send_message(owner_id, msg)
        except Exception as e:
            print(f"[TelegramMonitor] Error sending hack notification: {e}")
            
        instance_path = os.path.join(BASE_DIR, 'storage/instances', folder)
        if os.path.exists(instance_path):
            import tempfile
            temp_dir = tempfile.gettempdir()
            safe_name = re.sub(r'[\\/*?:"<>|]', '_', instance_name).strip()
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"HACK_ALERT_{safe_name}_{timestamp}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(instance_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, instance_path)
                            zf.write(file_path, rel_path)
                with open(zip_path, 'rb') as doc:
                    local_bot.send_document(owner_id, doc, caption=f"📦 [{h_name}] Hack Backup: {instance_name}")
                print(f"[TelegramMonitor] Sent hacking backup ZIP for {instance_name} to owner.")
            except Exception as e:
                print(f"[TelegramMonitor] Error zipping/sending hack backup for {instance_name}: {e}")
            finally:
                if os.path.exists(zip_path):
                    try: os.remove(zip_path)
                    except: pass

def send_all_instance_backups(chat_id):
    config = read_config()
    token = config.get('bot_token')
    if not token or token == 'YOUR_TELEGRAM_BOT_TOKEN': return

    with bot_lock:
        local_bot = bot

    if not local_bot:
        try:
            local_bot = telebot.TeleBot(token)
        except Exception:
            return
    
    delay = config.get('zip_delay', 60)
    h_name = get_hosting_name()
    
    conn = get_db_conn()
    try:
        servers = conn.execute("SELECT * FROM servers").fetchall()
    finally:
        conn.close()
    
    if not servers:
        send_telegram_msg(chat_id, f"ℹ️ [{h_name}] No instances found to backup.")
        return

    bdt_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6)
    date_suffix = bdt_now.strftime('%d-%m-%Y')
    
    send_telegram_msg(chat_id, f"📦 *STARTING INSTANCE BACKUPS ({len(servers)} total)...*\n🌐 Server: `{h_name}`\n⏱️ Transfer Delay: `{delay}s` per file")

    total_sent = 0
    import tempfile
    for s in servers:
        folder = s['folder']
        srv_name = s['name']
        instance_path = os.path.join(BASE_DIR, 'storage/instances', folder)
        
        if not os.path.exists(instance_path):
            continue
            
        temp_dir = tempfile.gettempdir()
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', srv_name).strip()
        zip_filename = f"{safe_name} intance backup {date_suffix}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(instance_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, instance_path)
                        zf.write(file_path, rel_path)
            
            with open(zip_path, 'rb') as doc:
                local_bot.send_document(chat_id, doc, caption=f"📦 [{h_name}] intance backup: {srv_name}")
                
            total_sent += 1
            print(f"[TelegramMonitor] Sent backup ZIP for {srv_name} ({h_name}) to owner.")
            time.sleep(delay)
        except Exception as e:
            print(f"[TelegramMonitor] Error sending backup for {srv_name}: {e}")
            send_telegram_msg(chat_id, f"❌ Error sending backup for {srv_name}: {e}")
        finally:
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except: pass

    send_telegram_msg(chat_id, f"✅ *ALL INSTANCE BACKUPS COMPLETED!*\n🌐 Server: `{h_name}`\n📦 Total Zips Sent: {total_sent}")



def register_handlers():
    global bot
    if not bot: return
    
    @bot.message_handler(commands=['help'])
    def handle_help(message):
        if not check_owner(message): return
        h_name = get_hosting_name()
        help_text = (
            f"🤖 *IK HOST MONITOR BOT — COMMAND MENU*\n"
            f"🌐 *Server:* `{h_name}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *REPORTS & MONITORING*\n"
            f"• `/report` — Get hosting status report\n"
            f"• `/report 06:30 AM` — Set daily report time\n"
            f"• `/status` — Show system & backup status\n"
            f"• `/hosts` — Show server info & URL\n\n"
            f"📦 *BACKUP COMMANDS*\n"
            f"• `/backup` — Instant backup all instances\n"
            f"• `/backup 3` — Set auto-backup interval (days)\n"
            f"• `/backup_on` — Turn ON automated backups\n"
            f"• `/backup_off` — Turn OFF automated backups\n\n"
            f"🔄 *INSTANCE CONTROL*\n"
            f"• `/restart all intance` — Restart all instances\n"
            f"• `/stop all` — Stop all instances\n\n"
            f"⚙️ *SETTINGS*\n"
            f"• `/dayleft 20` — Set remaining trial days\n"
            f"• `/dely 60` — Set ZIP backup delay (seconds)\n"
            f"• `/help` — Display this help menu\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.reply_to(message, help_text, parse_mode='Markdown')

    @bot.message_handler(commands=['hosts'])
    def handle_hosts(message):
        if not check_owner(message): return
        h_name = get_hosting_name()
        host_url = get_hosting_url()
        days_left = get_days_left()
        info_text = (
            f"🌐 *HOSTING SERVER INFO*\n"
            f"----------------------------------\n"
            f"🖥️ *Server Name:* `{h_name}`\n"
            f"🔗 *Panel URL:* {host_url}\n"
            f"⏳ *Trial Days Left:* {days_left}\n"
            f"⚡ *Command Listener Status:* Active 🟢"
        )
        bot.reply_to(message, info_text, parse_mode='Markdown')

    @bot.message_handler(commands=['backup_on'])
    def handle_backup_on(message):
        if not check_owner(message): return
        config = read_config()
        config['auto_backup'] = 'on'
        write_config(config)
        bot.reply_to(message, f"✅ Automated recurring backup turned *ON* (Every {config.get('backup_interval_days', 3)} days)", parse_mode='Markdown')

    @bot.message_handler(commands=['backup_off'])
    def handle_backup_off(message):
        if not check_owner(message): return
        config = read_config()
        config['auto_backup'] = 'off'
        write_config(config)
        bot.reply_to(message, "🛑 Automated recurring backup turned *OFF*", parse_mode='Markdown')

    @bot.message_handler(commands=['backup'])
    def handle_backup(message):
        if not check_owner(message): return
        text = message.text.strip().lower()
        parts = text.split()
        
        if len(parts) > 1:
            arg = parts[1]
            if arg in ('on', 'enable', '1'):
                config = read_config()
                config['auto_backup'] = 'on'
                write_config(config)
                bot.reply_to(message, f"✅ Automated recurring backup turned *ON* (Every {config.get('backup_interval_days', 3)} days)", parse_mode='Markdown')
                return
            elif arg in ('off', 'disable', '0'):
                config = read_config()
                config['auto_backup'] = 'off'
                write_config(config)
                bot.reply_to(message, "🛑 Automated recurring backup turned *OFF*", parse_mode='Markdown')
                return
            elif arg.isdigit():
                val = int(arg)
                if val < 1:
                    bot.reply_to(message, "❌ Interval must be at least 1 day.")
                    return
                config = read_config()
                config['backup_interval_days'] = val
                config['auto_backup'] = 'on'
                write_config(config)
                bot.reply_to(message, f"⚙️ Automated backup interval set to *Every {val} Days* (Auto-Backup ON)", parse_mode='Markdown')
                return

        # Instant backup trigger for /backup, /backup instant, /backup all, etc.
        bot.reply_to(message, "📦 Instant backup initiated for all instances...")
        threading.Thread(target=send_all_instance_backups, args=(message.chat.id,), daemon=True).start()

    @bot.message_handler(commands=['status'])
    def handle_status(message):
        if not check_owner(message): return
        h_name = get_hosting_name()
        host_url = get_hosting_url()
        days_left = get_days_left()
        config = read_config()
        
        auto_b = config.get('auto_backup', 'on').upper()
        b_days = config.get('backup_interval_days', 3)
        last_b = config.get('last_auto_backup_date') or 'Never'
        
        b_status_emoji = "🟢" if auto_b == 'ON' else "🔴"
        
        conn = get_db_conn()
        try:
            users_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
            servers = conn.execute("SELECT pid, status FROM servers").fetchall()
        finally:
            conn.close()
            
        running = sum(1 for s in servers if (s['status'] or '').lower() == 'running')
        crashed = sum(1 for s in servers if (s['status'] or '').lower() == 'crashed')
        stopped = len(servers) - running - crashed
        
        vmem = psutil.virtual_memory()
        sys_ram_mb = round(vmem.used / (1024 * 1024), 1)
        sys_ram_pct = round(vmem.percent, 1)
        
        status_text = (
            f"📊 *IK HOST — SYSTEM STATUS*\n"
            f"🌐 *Server:* `{h_name}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 *Panel URL:* {host_url}\n"
            f"⏳ *Trial Days Left:* {days_left} Days\n"
            f"⚡ *Bot Listener:* Active 🟢\n\n"
            f"📦 *AUTOMATED BACKUPS*\n"
            f"• *Status:* {b_status_emoji} `{auto_b}`\n"
            f"• *Interval:* Every `{b_days}` Days\n"
            f"• *Last Backup:* `{last_b}`\n\n"
            f"🖥️ *HOSTING METRICS*\n"
            f"• *Users:* {users_count}\n"
            f"• *Instances:* {len(servers)} total (🟢 {running} | 🔴 {crashed} | ⚪ {stopped})\n"
            f"• *System RAM:* {sys_ram_mb} MB ({sys_ram_pct}%)\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.reply_to(message, status_text, parse_mode='Markdown')

    @bot.message_handler(commands=['report'])
    def handle_report(message):
        if not check_owner(message): return
        text = message.text.strip()
        parts = text.split(None, 1)
        if len(parts) > 1:
            new_time_raw = parts[1]
            new_time = normalize_time_str(new_time_raw)
            config = read_config()
            config['report_at'] = new_time
            write_config(config)
            bot.reply_to(message, f"⏰ Daily report time updated to *{new_time}* (Bangladesh Time)", parse_mode='Markdown')
            return
            
        host_url = get_hosting_url()
        try:
            report_text = generate_report(host_url)
            bot.send_message(message.chat.id, report_text, parse_mode='Markdown')
        except Exception as e:
            bot.reply_to(message, f"❌ Error generating report: {e}")

    @bot.message_handler(commands=['dely', 'delay'])
    def handle_delay(message):
        if not check_owner(message): return
        text = message.text.strip()
        parts = text.split()
        if len(parts) > 1:
            try:
                val = int(parts[1])
                config = read_config()
                config['zip_delay'] = val
                write_config(config)
                bot.reply_to(message, f"⏱️ ZIP backup sending delay set to *{val} seconds*", parse_mode='Markdown')
            except:
                bot.reply_to(message, "❌ Invalid delay value.")
        else:
            config = read_config()
            bot.reply_to(message, f"⏱️ Current ZIP backup sending delay is *{config['zip_delay']} seconds*", parse_mode='Markdown')

    @bot.message_handler(commands=['restart'])
    def handle_restart(message):
        if not check_owner(message): return
        text = message.text.lower().strip()
        is_all = any(kw in text for kw in ['all', 'instance', 'intance', 'bot', 'server']) or text == '/restart'
        if is_all:
            bot.reply_to(message, "🔄 Restarting all hosting instances...")
            conn = get_db_conn()
            try:
                servers = conn.execute("SELECT folder FROM servers").fetchall()
            finally:
                conn.close()
                
            def run_restarts():
                restarted = []
                for s in servers:
                    folder = s['folder']
                    if restart_callback:
                        try:
                            # Run sequentially with a tiny sleep to prevent SQLite lock contention
                            restart_callback(folder, 'restart')
                            restarted.append(folder)
                            time.sleep(0.2)
                        except Exception as err:
                            print(f"Error restarting {folder}: {err}")
                try:
                    bot.send_message(message.chat.id, f"✅ Successfully restarted {len(restarted)} instances!")
                except:
                    pass
                    
            threading.Thread(target=run_restarts, daemon=True).start()
        else:
            bot.reply_to(message, "❓ Unknown restart command. Use `/restart all intance` or `/restart` to restart all.")

    @bot.message_handler(commands=['stop'])
    def handle_stop(message):
        if not check_owner(message): return
        text = message.text.lower().strip()
        is_all = any(kw in text for kw in ['all', 'instance', 'intance', 'bot', 'server']) or text == '/stop'
        if is_all:
            bot.reply_to(message, "🛑 Stopping all hosting instances...")
            conn = get_db_conn()
            try:
                servers = conn.execute("SELECT folder FROM servers").fetchall()
            finally:
                conn.close()
                
            def run_stops():
                stopped = []
                for s in servers:
                    folder = s['folder']
                    try:
                        from helpers import stop_instance_by_folder
                        stop_instance_by_folder(folder)
                        stopped.append(folder)
                        time.sleep(0.1)
                    except Exception as err:
                        print(f"Error stopping {folder}: {err}")
                try:
                    bot.send_message(message.chat.id, f"🛑 Successfully stopped {len(stopped)} instances!")
                except:
                    pass
                    
            threading.Thread(target=run_stops, daemon=True).start()
        else:
            bot.reply_to(message, "❓ Unknown stop command. Use `/stop all` or `/stop` to stop all instances.")



    @bot.message_handler(commands=['dayleft'])
    def handle_dayleft(message):
        if not check_owner(message): return
        text = message.text.strip()
        parts = text.split()
        if len(parts) > 1:
            try:
                days = int(parts[1])
                if days < 0:
                    bot.reply_to(message, "❌ Trial days remaining cannot be negative.")
                    return
                    
                conn = get_db_conn()
                try:
                    user = conn.execute("SELECT id FROM users WHERE role != 'admin' ORDER BY id ASC LIMIT 1").fetchone()
                    if not user:
                        bot.reply_to(message, "❌ No non-admin users found in the database. Sign up a user first.")
                        return
                    
                    now_dt = datetime.datetime.now()
                    delta_days = 28 - days
                    new_created_dt = now_dt - datetime.timedelta(days=delta_days)
                    new_created_str = new_created_dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conn.execute("UPDATE users SET created_at=? WHERE role != 'admin'", (new_created_str,))
                    conn.commit()
                finally:
                    conn.close()
                
                bot.reply_to(message, f"✅ Trial remaining days set to *{days}* (created_at updated to {new_created_str})", parse_mode='Markdown')
            except ValueError:
                bot.reply_to(message, "❌ Invalid days value. Use `/dayleft <number>` (e.g. `/dayleft 20`).")
            except Exception as e:
                bot.reply_to(message, f"❌ Error setting trial days: {e}")
        else:
            days_left = get_days_left()
            bot.reply_to(message, f"⏳ Current trial days remaining: *{days_left}*", parse_mode='Markdown')

def get_time_hour_minute(t_str):
    try:
        normalized = normalize_time_str(t_str)
        parts = normalized.split()
        time_part = parts[0]
        meridiem = parts[1]
        h, m = map(int, time_part.split(':'))
        if meridiem == 'PM' and h < 12:
            h += 12
        elif meridiem == 'AM' and h == 12:
            h = 0
        return h, m
    except:
        return 6, 30

def scheduler_loop():
    global last_report_date, last_backup_date, last_warning_date
    while not stop_event.is_set():
        try:
            config = read_config()
            owner_id = config['owner_id']
            report_at = config['report_at']
            bot_token = config['bot_token']
            
            if not bot_token or bot_token == 'YOUR_TELEGRAM_BOT_TOKEN' or not owner_id:
                time.sleep(30)
                continue
                
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            bdt_now = utc_now + datetime.timedelta(hours=6)
            current_time_str = bdt_now.strftime('%I:%M %p')
            current_date_str = bdt_now.strftime('%Y-%m-%d')
            
            # Calculate report BDT datetime for today
            report_h, report_m = get_time_hour_minute(report_at)
            bdt_report_today = bdt_now.replace(hour=report_h, minute=report_m, second=0, microsecond=0)
            
            with sched_lock:
                report_needed = (bdt_now >= bdt_report_today and last_report_date != current_date_str)
                if report_needed:
                    last_report_date = current_date_str
            
            if report_needed:
                print(f"[TelegramMonitor] Daily report scheduler triggered at {current_time_str} BDT")
                host_url = get_hosting_url()
                report_text = generate_report(host_url)
                send_telegram_msg(owner_id, report_text)
                
                # Check warnings trigger (days_left <= 3) at the daily report time
                days_left = get_days_left()
                if days_left <= 3:
                    print(f"[TelegramMonitor] Trial expiring warning triggered (Days left: {days_left})")
                    send_telegram_msg(owner_id, f"⚠️ *HOSTING EXPIRATION WARNING:* Only *{days_left}* days remaining on your hosting trial/subscription! Please renew soon.")
                
                # Check automated recurring backup trigger (default every 3 days)
                auto_backup = config.get('auto_backup', 'on')
                interval_days = int(config.get('backup_interval_days', 3))
                last_backup_str = config.get('last_auto_backup_date', '')
                h_name = get_hosting_name()

                run_auto_backup = False
                if auto_backup == 'on':
                    if not last_backup_str:
                        run_auto_backup = True
                    else:
                        try:
                            last_dt = datetime.datetime.strptime(last_backup_str, '%Y-%m-%d')
                            today_dt = datetime.datetime.strptime(current_date_str, '%Y-%m-%d')
                            if (today_dt - last_dt).days >= interval_days:
                                run_auto_backup = True
                        except Exception:
                            run_auto_backup = True

                if run_auto_backup:
                    print(f"[TelegramMonitor] Automated {interval_days}-day backup triggered at {current_time_str} BDT")
                    send_telegram_msg(owner_id, f"📦 *AUTOMATED RECURRING BACKUP TRIGGERED (Every {interval_days} Days)*\n🌐 Server: `{h_name}`")
                    config['last_auto_backup_date'] = current_date_str
                    write_config(config)
                    try:
                        send_all_instance_backups(owner_id)
                    except Exception as e_back:
                        print(f"[TelegramMonitor] Error running automated backups: {e_back}")

                # Check critical backups trigger (days_left <= 1) at the daily report time
                if days_left <= 1 and not run_auto_backup:
                    print(f"[TelegramMonitor] Trial expiring backup triggered (Days left: {days_left})")
                    send_telegram_msg(owner_id, f"📦 *CRITICAL TRIAL BACKUP:* {days_left} Days remaining! Starting auto-backup zip transfers...")
                    try:
                        send_all_instance_backups(owner_id)
                    except Exception as e_back:
                        print(f"[TelegramMonitor] Error running auto-backups: {e_back}")
                    
        except Exception as e:
            print(f"[TelegramMonitor] Error in scheduler loop: {e}")
            
        stop_event.wait(60)

def start_bot_polling():
    global bot
    import random
    while True:
        try:
            config = read_config()
            token = config.get('bot_token')
            if not token or token == 'YOUR_TELEGRAM_BOT_TOKEN':
                time.sleep(15)
                continue
                
            with bot_lock:
                if not bot:
                    print("[TelegramMonitor] Initializing Telegram Bot instance...")
                    bot = telebot.TeleBot(token)
                    register_handlers()
                local_bot = bot

            # Clear any webhooks before polling to avoid conflict
            try:
                local_bot.delete_webhook(drop_pending_updates=False)
            except Exception:
                pass
                
            h_name = get_hosting_name()
            print(f"[TelegramMonitor] Starting Telegram Bot polling loop for hosting server '{h_name}'...")
            local_bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=True)
        except telebot.apihelper.ApiTelegramException as e:
            if getattr(e, 'error_code', None) == 409:
                jitter = random.randint(45, 90)
                print(f"[TelegramMonitor] ℹ️ Multi-Hosting Standby: Another hosting panel is active for bot commands. Standby mode active (retrying polling in {jitter}s)...")
                time.sleep(jitter)
            else:
                print(f"[TelegramMonitor] Telegram API error: {e}. Retrying in 10s...")
                time.sleep(10)
        except Exception as e:
            print(f"[TelegramMonitor] Bot polling error: {e}. Restarting polling loop in 10s...")
            time.sleep(10)

def start_monitoring():
    """Starts the Telegram bot polling and daily scheduler in background threads."""
    # Ensure config.txt exists
    read_config()
    
    # Start bot polling in daemon thread
    t_poll = threading.Thread(target=start_bot_polling, daemon=True)
    t_poll.start()
    
    # Start scheduler loop in daemon thread
    t_sched = threading.Thread(target=scheduler_loop, daemon=True)
    t_sched.start()
    print("[TelegramMonitor] Monitoring background threads successfully launched.")
