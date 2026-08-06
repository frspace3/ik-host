import os
import time
import sqlite3
import socket

import threading
import datetime
import psutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'storage/ikhost.db')
restart_callback = None
monitor_thread = None
stop_event = threading.Event()
active_restarts = set()
active_restarts_lock = threading.Lock()
process_cache = {}
process_cache_lock = threading.Lock()

# Cached metrics from last health check cycle (shared with API routes)
metrics_cache = {}  # {folder: {'cpu': '0%', 'ram': '0MB', 'ram_mb': 0.0, 'online': False, 'health': 'Unknown'}}
metrics_cache_lock = threading.Lock()

def register_restart_callback(cb):
    """Registers the server action callback from app.py to trigger restarts."""
    global restart_callback
    restart_callback = cb

def check_http_port(port):
    """Fast TCP port check — verifies if a process is listening on the port."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        return result == 0
    except:
        return False

def kill_process_tree(proc):
    """Kills a process and all of its descendants recursively."""
    try:
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except:
                pass
    except:
        pass
    try:
        proc.kill()
    except:
        pass

def run_health_checks():
    """Background loop that queries instances, updates metrics, and handles crashes."""
    while not stop_event.is_set():
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Fetch all servers joined with users to get role and limits
            servers = cursor.execute('SELECT s.*, u.role, u.ram_limit, u.cpu_limit FROM servers s LEFT JOIN users u ON s.user_id = u.id').fetchall()
            now_ts = time.time()
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Prune dead PIDs from process cache
            with process_cache_lock:
                dead_pids = [pid for pid, proc in process_cache.items() if not proc.is_running()]
                for dead_pid in dead_pids:
                    del process_cache[dead_pid]

            # Get current time and date in Bangladesh Time (UTC+6)
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            bdt_now = utc_now + datetime.timedelta(hours=6)
            current_time_str = bdt_now.strftime('%H:%M')
            current_date_str = bdt_now.strftime('%Y-%m-%d')

            for srv in servers:
                folder = srv['folder']
                pid = srv['pid']
                port = srv['assigned_port']
                status = srv['status']
                server_status = srv['server_status']
                restart_count = srv['restart_count'] or 0
                last_restart = srv['last_health_check']  # We store restart timestamps or use db fields
                
                # Suspended servers are skipped
                if server_status == 'suspended':
                    continue

                # Check scheduled auto-restart (Bangladesh Time)
                try:
                    ar_enabled = srv['auto_restart_enabled'] or 0
                    ar_time = srv['auto_restart_time']
                    last_ar = srv['last_auto_restart']
                    if ar_enabled and ar_time == current_time_str and last_ar != current_date_str:
                        # Log to console
                        logpath = os.path.join(BASE_DIR, 'storage/instances', folder, 'console.log')
                        if os.path.exists(logpath):
                            try:
                                with open(logpath, 'a', encoding='utf-8') as f:
                                    f.write(f"\n[{now_str}] ⏰ Scheduled Auto-Restart triggered (Bangladesh Time)\n")
                            except:
                                pass
                        
                        # Mark last_auto_restart as today
                        cursor.execute('UPDATE servers SET last_auto_restart = ? WHERE folder = ?', (current_date_str, folder))
                        conn.commit()
                        
                        # Trigger asynchronous restart
                        if restart_callback:
                            with active_restarts_lock:
                                active_restarts.add(folder)
                            def trigger_ar(fld=folder):
                                try:
                                    restart_callback(fld, act='restart')
                                except Exception as err:
                                    print(f"Error in scheduled auto-restart for {fld}: {err}")
                                finally:
                                    with active_restarts_lock:
                                        active_restarts.discard(fld)
                            threading.Thread(target=trigger_ar, daemon=True).start()
                        continue  # Skip health checks for this iteration as it's restarting
                except Exception as ar_err:
                    print(f"Error checking auto-restart for {folder}: {ar_err}")

                with active_restarts_lock:
                    in_active_restarts = (folder in active_restarts)
                if in_active_restarts:
                    continue

                online = False
                # 1. Verify if PID is running on host
                if pid and psutil.pid_exists(pid):
                    try:
                        with process_cache_lock:
                            if pid not in process_cache:
                                proc_obj = psutil.Process(pid)
                                proc_obj.cpu_percent(interval=None) # Initialize baseline
                                process_cache[pid] = proc_obj
                            p = process_cache[pid]
                        
                        if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                            online = True
                            
                            # Cache children list once per server cycle
                            try:
                                children = p.children(recursive=True)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                children = []
                            
                            # Detect actual listening port (skip if already known to save CPU)
                            if not port:
                                detected_port = None
                                try:
                                    processes = [p] + children
                                    for proc in processes:
                                        conns = []
                                        try:
                                            conns = proc.connections(kind='inet')
                                        except:
                                            try:
                                                conns = proc.connections()
                                            except:
                                                pass
                                        for c in conns:
                                            is_listen = False
                                            if hasattr(c, 'status'):
                                                status_str = str(c.status).lower()
                                                if 'listen' in status_str:
                                                    is_listen = True
                                            if is_listen and hasattr(c, 'laddr') and hasattr(c.laddr, 'port'):
                                                detected_port = c.laddr.port
                                                break
                                        if detected_port:
                                            break
                                except:
                                    pass
                                    
                                if detected_port and detected_port != port:
                                    cursor.execute('UPDATE servers SET assigned_port = ? WHERE folder = ?', (detected_port, folder))
                                    port = detected_port

                            # Enforce RAM and CPU resource limits (admin is unlimited)
                            try:
                                role = srv['role']
                                if role != 'admin':
                                    # 1. RAM limit check
                                    limit = float(srv['ram_limit'] or 100)
                                    total_rss = 0
                                    try:
                                        total_rss += p.memory_info().rss
                                        for child in children:
                                            try:
                                                total_rss += child.memory_info().rss
                                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                                pass
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        pass
                                    
                                    rss_mb = total_rss / (1024 * 1024)
                                    if rss_mb > limit:
                                        online = False
                                        kill_process_tree(p)
                                        logpath = os.path.join(BASE_DIR, 'storage/instances', folder, 'console.log')
                                        if os.path.exists(logpath):
                                            with open(logpath, 'a', encoding='utf-8') as flog:
                                                flog.write(f"\n[{now_str}] ✗ CRASH: Memory limit exceeded ({rss_mb:.1f}MB / Max: {limit:.0f}MB)\n")
                                        with process_cache_lock:
                                            process_cache.pop(pid, None)

                                    # 2. CPU limit check
                                    if online:
                                        cpu_limit = float(srv['cpu_limit'] or 100)
                                        total_cpu = 0
                                        try:
                                            total_cpu += p.cpu_percent(interval=None)
                                            for child in children:
                                                try:
                                                    total_cpu += child.cpu_percent(interval=None)
                                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                                    pass
                                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                                            pass
                                            
                                        if total_cpu > cpu_limit:
                                            online = False
                                            kill_process_tree(p)
                                            logpath = os.path.join(BASE_DIR, 'storage/instances', folder, 'console.log')
                                            if os.path.exists(logpath):
                                                with open(logpath, 'a', encoding='utf-8') as flog:
                                                    flog.write(f"\n[{now_str}] ✗ CRASH: CPU limit exceeded ({total_cpu:.1f}% / Max: {cpu_limit:.0f}%)\n")
                                            with process_cache_lock:
                                                process_cache.pop(pid, None)
                            except Exception as re_err:
                                pass
                    except:
                        with process_cache_lock:
                            process_cache.pop(pid, None)
                
                # 2. Check HTTP health if it's a web API
                health = 'Healthy'
                if online:
                    if port:
                        port_up = check_http_port(port)
                        health = 'Healthy' if port_up else 'Unhealthy'
                    if health == 'Healthy' and restart_count > 0:
                        cursor.execute('UPDATE servers SET restart_count = 0 WHERE folder = ?', (folder,))
                else:
                    health = 'Unhealthy' if status == 'Running' else 'Unknown'

                # 3. Update health status in database
                cursor.execute(
                    'UPDATE servers SET health_status = ?, last_health_check = ? WHERE folder = ?',
                    (health, now_str, folder)
                )

                # Update shared metrics cache for API use
                cached_cpu = '0%'
                cached_ram = '0MB'
                cached_ram_mb = 0.0
                if online and pid:
                    try:
                        from helpers import get_process_resources
                        cached_cpu, cached_ram, cached_ram_mb = get_process_resources(pid)
                    except Exception:
                        pass
                with metrics_cache_lock:
                    metrics_cache[folder] = {
                        'cpu': cached_cpu,
                        'ram': cached_ram,
                        'ram_mb': cached_ram_mb,
                        'online': online,
                        'health': health
                    }

                # 4. Handle crash auto-restart
                if status == 'Running' and not online:
                    # Server crashed or stopped unexpectedly
                    # Calculate exponential backoff delay (attempts * 5s)
                    delay = min(300, (2 ** restart_count) * 5)
                    
                    # Log failure to console.log
                    logpath = os.path.join(BASE_DIR, 'storage/instances', folder, 'console.log')
                    if os.path.exists(logpath):
                        try:
                            with open(logpath, 'a', encoding='utf-8') as f:
                                f.write(f"\n[{now_str}] ✗ CRASH DETECTED (PID {pid} is dead)\n")
                        except:
                            pass

                    if restart_count >= 1:
                        # Max retries reached (1 retry only), mark as Crashed
                        cursor.execute(
                            'UPDATE servers SET status = "Crashed", health_status = "Unhealthy" WHERE folder = ?',
                            (folder,)
                        )
                        if os.path.exists(logpath):
                            try:
                                with open(logpath, 'a', encoding='utf-8') as f:
                                    f.write(f"[{now_str}] 🛑 Max auto-restart attempts reached (1 attempt). Server marked as CRASHED.\n")
                            except:
                                pass
                    else:
                        # Attempt restart with backoff check
                        # Check last action log to prevent instant spamming
                        if restart_callback:
                            new_count = restart_count + 1
                            cursor.execute(
                                'UPDATE servers SET restart_count = ? WHERE folder = ?',
                                (new_count, folder)
                            )
                            if os.path.exists(logpath):
                                try:
                                    with open(logpath, 'a', encoding='utf-8') as f:
                                        f.write(f"[{now_str}] 🔄 Auto-restarting (Attempt {new_count}/1, Backoff Delay: {delay}s)...\n")
                                except:
                                    pass
                            
                            # Trigger asynchronous restart
                            with active_restarts_lock:
                                active_restarts.add(folder)
                            def trigger(fld=folder):
                                time.sleep(delay)
                                try:
                                    # Query DB to check if the user stopped it while waiting
                                    import sqlite3
                                    conn_check = sqlite3.connect(DB_PATH, timeout=10.0)
                                    conn_check.row_factory = sqlite3.Row
                                    srv_check = conn_check.execute('SELECT status, server_status FROM servers WHERE folder=?', (fld,)).fetchone()
                                    conn_check.close()
                                    
                                    # Only restart if it is still marked as Running and not suspended
                                    if srv_check and srv_check['status'] == 'Running' and srv_check['server_status'] != 'suspended':
                                        restart_callback(fld, act='auto_restart')
                                except Exception as err:
                                    print(f"Error checking status before auto-restart: {err}")
                                finally:
                                    with active_restarts_lock:
                                        active_restarts.discard(fld)
                            threading.Thread(target=trigger, daemon=True).start()

            conn.commit()
        except Exception as e:
            print(f"[HealthMonitor] Error: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
            
        stop_event.wait(60)

def start_health_monitor():
    """Starts the health check loop inside a background daemon thread."""
    global monitor_thread
    if monitor_thread and monitor_thread.is_alive():
        return
    stop_event.clear()
    monitor_thread = threading.Thread(target=run_health_checks, daemon=True)
    monitor_thread.start()

def stop_health_monitor():
    """Stops the background health check daemon thread."""
    stop_event.set()
