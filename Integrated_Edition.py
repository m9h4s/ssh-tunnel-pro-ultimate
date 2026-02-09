"""
SSH Tunnel Pro Ultimate - Integrated Edition
یک پروژه کامل با رابط کاربری پیشرفته و تمام قابلیت‌ها
"""

import sys
import io
import os

# تنظیم encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import socket
import threading
import select
import json
import time
import struct
import platform
import subprocess
import requests
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import queue
import logging
from pathlib import Path
import hashlib
import base64
import random
import webbrowser

# Import networking libraries
try:
    import paramiko
    import dns.resolver
    from cryptography.fernet import Fernet
    import psutil
except ImportError:
    print("=" * 60)
    print("ERROR: Required libraries are missing!")
    print("=" * 60)
    print("\nPlease run this command to install:")
    print("\npip install paramiko dnspython customtkinter requests cryptography psutil\n")
    input("Press Enter to exit...")
    sys.exit(1)

# ================= CONFIGURATION =================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

CONFIG_FILE = "config_ultimate.json"
LOG_FILE = "ssh_tunnel_ultimate.log"
ENCRYPTION_KEY_FILE = ".key_ultimate"

DEFAULT_CONFIG = {
    "servers": {},
    "dns_presets": {
        "Shecan": {"primary": "178.22.122.100", "secondary": "185.51.200.2"},
        "Google": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        "Cloudflare": {"primary": "1.1.1.1", "secondary": "1.0.0.1"},
        "OpenDNS": {"primary": "208.67.222.222", "secondary": "208.67.220.220"}
    },
    "settings": {
        "local_port": "1080",
        "auto_reconnect": True,
        "connection_timeout": 30,
        "log_traffic": False,
        "theme": "dark-blue",
        "wan_bonding_enabled": False,
        "load_balancing_mode": "round_robin",
        "max_threads": 100,
        "auto_reset_interval": 60,
        "auto_reset_enabled": True,
        "dns_test_rounds": 3,
        "health_check_interval": 30,
        "reconnect_max_attempts": 10,
        "reconnect_initial_delay": 5,
        "dns_fallback_enabled": True,
        "dns_fallback_list": ["8.8.8.8", "1.1.1.1", "9.9.9.9"],
        "dns_timeout": 5
    }
}

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ================= DNS TESTER =================
class DNSTester:
    """Test and select the best DNS server"""
    
    DNS_SERVERS = {
        'Google Primary': '8.8.8.8',
        'Google Secondary': '8.8.4.4',
        'Cloudflare Primary': '1.1.1.1',
        'Cloudflare Secondary': '1.0.0.1',
        'OpenDNS Primary': '208.67.222.222',
        'OpenDNS Secondary': '208.67.220.220',
        'Shecan Primary': '178.22.122.100',
        'Shecan Secondary': '185.51.200.2'
    }
    
    def __init__(self, target_host: str = "google.com", test_rounds: int = 3):
        self.target_host = target_host
        self.test_rounds = test_rounds
        self.best_dns = None
        self.best_response_time = float('inf')
        self.results = {}
    
    def test_dns_server(self, dns_ip: str, timeout: int = 3) -> Optional[float]:
        """Test DNS server speed"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            query = self._build_dns_query(self.target_host)
            
            start_time = time.time()
            sock.sendto(query, (dns_ip, 53))
            data, _ = sock.recvfrom(512)
            response_time = (time.time() - start_time) * 1000
            
            sock.close()
            
            if len(data) > 12 and data[3] & 0x0F == 0:
                return response_time
            return None
            
        except Exception as e:
            logger.debug(f"DNS test failed for {dns_ip}: {e}")
            return None
    
    def _build_dns_query(self, hostname: str) -> bytes:
        """Build DNS query"""
        transaction_id = b'\xaa\xbb'
        flags = b'\x01\x00'
        questions = b'\x00\x01'
        answer_rrs = b'\x00\x00'
        authority_rrs = b'\x00\x00'
        additional_rrs = b'\x00\x00'
        
        question = b''
        for part in hostname.split('.'):
            question += bytes([len(part)]) + part.encode()
        question += b'\x00'
        question += b'\x00\x01'
        question += b'\x00\x01'
        
        return transaction_id + flags + questions + answer_rrs + authority_rrs + additional_rrs + question

    def find_best_dns(self) -> Dict[str, Any]:
        """Find the best DNS server with reliability check."""
        logger.info("Starting DNS servers testing...")
        
        self.results = {}
        working_servers = {}
        
        for name, dns_ip in self.DNS_SERVERS.items():
            total_time = 0
            successful_tests = 0
            
            for _ in range(self.test_rounds):
                response_time = self.test_dns_server(dns_ip, timeout=2)
                if response_time is not None:
                    if response_time < 5000:
                        total_time += response_time
                        successful_tests += 1
            
            if successful_tests > 0:
                avg_time = total_time / successful_tests
                success_rate = (successful_tests / self.test_rounds) * 100
                
                # فقط سرورهایی با موفقیت بیش از 50٪
                if success_rate >= 50:
                    self.results[name] = {
                        "ip": dns_ip,
                        "avg_time": avg_time,
                        "success_rate": success_rate
                    }
                    working_servers[name] = avg_time
                    logger.info(f"  ✓ {name}: {avg_time:.2f}ms ({success_rate:.0f}%)")
                else:
                    logger.info(f"  ✗ {name}: Failed ({success_rate:.0f}% success)")
            else:
                logger.info(f"  ✗ {name}: No response")
        
        if not working_servers:
            logger.warning("⚠️ No reliable DNS servers found! Using default.")
            return {"name": "Default", "ip": "8.8.8.8", "avg_time": 0}
        
        # انتخاب بهترین بر اساس میانگین زمان
        best_name = min(working_servers.items(), key=lambda x: x[1])[0]
        best_result = self.results[best_name]
        
        logger.info(f"✅ Best DNS: {best_name} ({best_result['ip']}) - {best_result['avg_time']:.2f}ms")
        
        return {
            "name": best_name,
            "ip": best_result["ip"],
            "avg_time": best_result["avg_time"],
            "success_rate": best_result["success_rate"],
            "all_results": self.results
        }

# ================= ENCRYPTION UTILITIES =================
class EncryptionManager:
    """Handles encryption/decryption of sensitive data like passwords."""
    
    def __init__(self):
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)
    
    def _load_or_create_key(self) -> bytes:
        """Load existing key or create new one."""
        if os.path.exists(ENCRYPTION_KEY_FILE):
            with open(ENCRYPTION_KEY_FILE, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(ENCRYPTION_KEY_FILE, 'wb') as f:
                f.write(key)
            return key
    
    def encrypt(self, text: str) -> str:
        """Encrypt text and return base64 encoded string."""
        return self.cipher.encrypt(text.encode()).decode()
    
    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt base64 encoded string."""
        try:
            return self.cipher.decrypt(encrypted_text.encode()).decode()
        except Exception:
            return encrypted_text

# ================= DNS CACHE =================
class DNSCache:
    """Thread-safe DNS cache to avoid blocking DNS lookups."""
    
    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
        self._lock = threading.Lock()
    
    def get(self, domain):
        """Get cached DNS result."""
        with self._lock:
            if domain in self.cache:
                result, timestamp = self.cache[domain]
                if time.time() - timestamp < self.ttl:
                    return result
                else:
                    del self.cache[domain]
            return None
    
    def set(self, domain, result):
        """Cache DNS result."""
        with self._lock:
            self.cache[domain] = (result, time.time())
    
    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self.cache.clear()

# ================= HEALTH MONITOR =================
class HealthMonitor:
    """Monitors connection health and triggers reconnection if needed."""
    
    def __init__(self, threshold_rtt=2000, check_interval=10):
        self.threshold_rtt = threshold_rtt
        self.check_interval = check_interval
        self.rtt_history = deque(maxlen=10)
        self.last_check = time.time()
        self._lock = threading.Lock()
        self.unhealthy_count = 0
        self.is_running = False
        self.monitor_thread = None
    
    def add_rtt(self, rtt_ms: float):
        """Add RTT measurement."""
        with self._lock:
            self.rtt_history.append(rtt_ms)
    
    def is_healthy(self) -> bool:
        """Check if connection is healthy based on RTT."""
        with self._lock:
            if len(self.rtt_history) < 3:
                return True
            
            avg_rtt = sum(self.rtt_history) / len(self.rtt_history)
            
            if avg_rtt > self.threshold_rtt:
                self.unhealthy_count += 1
                if self.unhealthy_count >= 3:
                    logger.warning(f"Connection unhealthy: avg RTT {avg_rtt:.1f}ms")
                    return False
            else:
                self.unhealthy_count = 0
            
            return True
    
    def start(self):
        """Start health monitoring."""
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop health monitoring."""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _monitor_loop(self):
        """Monitor connection health loop."""
        while self.is_running:
            time.sleep(self.check_interval)
            if not self.is_healthy():
                logger.warning("Connection health check failed")
    
    def reset(self):
        """Reset health monitor."""
        with self._lock:
            self.rtt_history.clear()
            self.unhealthy_count = 0

# ================= NETWORK INTERFACE MANAGER =================
class NetworkInterfaceManager:
    """Manages multiple network interfaces for WAN bonding."""
    
    def __init__(self):
        self.interfaces = []
        self.selected_interfaces = []
        self.current_index = 0
        self.load_balancing_mode = "round_robin"
        self._lock = threading.Lock()
    
    def scan_interfaces(self) -> List[Dict[str, Any]]:
        """Scan and return available network interfaces."""
        interfaces = []
        
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            
            for iface_name, addr_list in addrs.items():
                if iface_name in stats and stats[iface_name].isup:
                    for addr in addr_list:
                        if addr.family == socket.AF_INET:
                            # Determine interface type
                            iface_type = "Unknown"
                            if "Wi-Fi" in iface_name or "wlan" in iface_name.lower():
                                iface_type = "Wi-Fi"
                            elif "Ethernet" in iface_name or "eth" in iface_name.lower():
                                iface_type = "Ethernet"
                            elif "LTE" in iface_name or "wwan" in iface_name.lower():
                                iface_type = "LTE/4G"
                            
                            interfaces.append({
                                "name": iface_name,
                                "ip": addr.address,
                                "netmask": addr.netmask,
                                "type": iface_type,
                                "mtu": stats[iface_name].mtu,
                                "speed": stats[iface_name].speed,
                                "enabled": False
                            })
            
            self.interfaces = interfaces
            logger.info(f"Found {len(interfaces)} network interface(s)")
            return interfaces
            
        except Exception as e:
            logger.error(f"Interface scan error: {e}")
            return []
    
    def set_selected_interfaces(self, selected: List[Dict[str, Any]]):
        """Set selected interfaces for WAN bonding."""
        with self._lock:
            self.selected_interfaces = [iface for iface in selected if iface.get('enabled', False)]
            logger.info(f"Selected {len(self.selected_interfaces)} interfaces for WAN bonding")
    
    def get_next_interface(self, mode: str = "round_robin") -> Optional[Dict[str, Any]]:
        """Get next interface based on load balancing mode."""
        with self._lock:
            if not self.selected_interfaces:
                return None
            
            if mode == "round_robin":
                iface = self.selected_interfaces[self.current_index % len(self.selected_interfaces)]
                self.current_index += 1
                return iface
            
            elif mode == "random":
                return random.choice(self.selected_interfaces)
            
            elif mode == "fastest":
                return max(self.selected_interfaces, key=lambda x: x.get("speed", 0))
            
            else:
                return self.selected_interfaces[0] if self.selected_interfaces else None

# ================= TRAFFIC STATISTICS =================
class TrafficStats:
    """Track network traffic statistics."""
    
    def __init__(self):
        self.bytes_sent = 0
        self.bytes_received = 0
        self.connections_total = 0
        self.connections_active = 0
        self.failed_connections = 0
        self.start_time = time.time()
        self.upload_speed = 0.0
        self.download_speed = 0.0
        self.last_upload_bytes = 0
        self.last_download_bytes = 0
        self.last_update_time = time.time()
        self._lock = threading.Lock()
        self.is_running = False
        self.monitor_thread = None
    
    def add_sent(self, bytes_count: int):
        with self._lock:
            self.bytes_sent += bytes_count
    
    def add_received(self, bytes_count: int):
        with self._lock:
            self.bytes_received += bytes_count
    
    def increment_connection(self):
        with self._lock:
            self.connections_total += 1
            self.connections_active += 1
    
    def decrement_connection(self):
        with self._lock:
            self.connections_active = max(0, self.connections_active - 1)
    
    def increment_failed(self):
        with self._lock:
            self.failed_connections += 1
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self.start_time
            return {
                "bytes_sent": self.bytes_sent,
                "bytes_received": self.bytes_received,
                "connections_total": self.connections_total,
                "connections_active": self.connections_active,
                "failed_connections": self.failed_connections,
                "uptime": uptime,
                "upload_speed": self.upload_speed,
                "download_speed": self.download_speed
            }
    
    def start(self):
        """Start speed monitoring."""
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._calculate_speeds, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop speed monitoring."""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _calculate_speeds(self):
        """Calculate upload/download speeds."""
        while self.is_running:
            time.sleep(1)
            
            current_time = time.time()
            with self._lock:
                time_diff = current_time - self.last_update_time
                
                if time_diff > 0:
                    upload_diff = self.bytes_sent - self.last_upload_bytes
                    download_diff = self.bytes_received - self.last_download_bytes
                    
                    self.upload_speed = upload_diff / time_diff
                    self.download_speed = download_diff / time_diff
                    
                    self.last_upload_bytes = self.bytes_sent
                    self.last_download_bytes = self.bytes_received
                    self.last_update_time = current_time
    
    def reset(self):
        with self._lock:
            self.bytes_sent = 0
            self.bytes_received = 0
            self.connections_total = 0
            self.connections_active = 0
            self.failed_connections = 0
            self.start_time = time.time()
            self.upload_speed = 0.0
            self.download_speed = 0.0
    
    @staticmethod
    def format_bytes(bytes_count: float) -> str:
        """Format bytes to human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.2f} PB"

# ================= CONNECTION LOGGER =================
class ConnectionLogger:
    """Log and display last N connections."""
    
    def __init__(self, max_connections: int = 50):
        self.max_connections = max_connections
        self.connections = deque(maxlen=max_connections)
        self.lock = threading.Lock()
    
    def add_connection(self, client_info: str, destination: str):
        """Add a new connection to the log."""
        with self.lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.connections.append({
                'time': timestamp,
                'client': client_info,
                'destination': destination
            })
    
    def get_connections(self) -> List[Dict]:
        """Get list of recent connections."""
        with self.lock:
            return list(self.connections)
    
    def clear(self):
        """Clear all connections."""
        with self.lock:
            self.connections.clear()

# ================= MULTI-HOP SSH =================
class MultiHopSSH:
    """Handles multi-hop SSH connections through multiple servers."""
    
    def __init__(self, log_callback: Callable):
        self.log_callback = log_callback
        self.clients = []
    
    def connect_multi_hop(self, servers: List[Dict[str, Any]]) -> Optional[paramiko.SSHClient]:
        """Connect through multiple SSH servers."""
        if not servers:
            return None
        
        try:
            self.log_callback(f"[*] Multi-hop mode: {len(servers)} servers")
            
            # Connect to first server
            first_server = servers[0]
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.log_callback(f"[*] Hop 1: Connecting to {first_server['host']}...")
            
            if first_server.get('key_file') and os.path.exists(first_server['key_file']):
                client.connect(
                    first_server['host'],
                    port=int(first_server['port']),
                    username=first_server['username'],
                    key_filename=first_server['key_file'],
                    timeout=10
                )
            else:
                client.connect(
                    first_server['host'],
                    port=int(first_server['port']),
                    username=first_server['username'],
                    password=first_server.get('password', ''),
                    timeout=10
                )
            
            self.clients.append(client)
            self.log_callback(f"[✓] Hop 1: Connected to {first_server['host']}")
            
            # Connect through intermediate servers
            previous_client = client
            
            for i, server in enumerate(servers[1:], start=2):
                self.log_callback(f"[*] Hop {i}: Connecting to {server['host']}...")
                
                # Open channel through previous connection
                transport = previous_client.get_transport()
                dest_addr = (server['host'], int(server['port']))
                local_addr = ('127.0.0.1', 0)
                channel = transport.open_channel("direct-tcpip", dest_addr, local_addr)
                
                # Create new SSH client using the channel
                new_client = paramiko.SSHClient()
                new_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                if server.get('key_file') and os.path.exists(server['key_file']):
                    new_client.connect(
                        server['host'],
                        port=int(server['port']),
                        username=server['username'],
                        key_filename=server['key_file'],
                        sock=channel,
                        timeout=10
                    )
                else:
                    new_client.connect(
                        server['host'],
                        port=int(server['port']),
                        username=server['username'],
                        password=server.get('password', ''),
                        sock=channel,
                        timeout=10
                    )
                
                self.clients.append(new_client)
                self.log_callback(f"[✓] Hop {i}: Connected to {server['host']}")
                
                previous_client = new_client
            
            self.log_callback(f"[✓] Multi-hop chain established ({len(servers)} hops)")
            return self.clients[-1]  # Return final connection
            
        except Exception as e:
            logger.error(f"Multi-hop connection failed: {e}")
            self.log_callback(f"[!] Multi-hop failed: {e}")
            self.cleanup()
            return None
    
    def cleanup(self):
        """Close all SSH connections in the chain."""
        for client in reversed(self.clients):
            try:
                client.close()
            except:
                pass
        self.clients = []

# ================= ADVANCED SOCKS5 PROXY =================
class AdvancedSOCKS5Proxy(threading.Thread):
    """Enhanced SOCKS5 proxy with all advanced features."""
    
    def __init__(self, config: Dict[str, Any], log_callback: Callable, 
                 status_callback: Callable, stats: TrafficStats,
                 iface_manager: NetworkInterfaceManager,
                 servers: List[Dict[str, Any]],
                 connection_logger: ConnectionLogger):
        super().__init__()
        self.config = config
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.stats = stats
        self.iface_manager = iface_manager
        self.servers = servers
        self.connection_logger = connection_logger
        self.running = True
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.multi_hop: Optional[MultiHopSSH] = None
        self.server_socket: Optional[socket.socket] = None
        self.resolver = dns.resolver.Resolver()
        self.connection_attempts = 0
        self.max_reconnect_attempts = int(config.get("reconnect_max_attempts", 5))
        self.reconnect_delay = int(config.get("reconnect_initial_delay", 5))
        self.timeout = int(config.get('connection_timeout', 30))  # افزایش timeout

        
        # Thread pool management
        self.max_workers = int(config.get("max_threads", 100))
        self.executor: Optional[ThreadPoolExecutor] = None
        self.thread_count = 0
        self.thread_count_lock = threading.Lock()
        
        # DNS Cache and Health Monitor
        self.dns_cache = DNSCache(ttl=300)
        self.health_monitor = HealthMonitor()
        
        # Active channels tracking
        self.active_channels = set()
        self.channels_lock = threading.Lock()
        
        # DNS optimization
        self.best_dns_name = None
        self.best_dns_ip = None
        self.dns_tester = DNSTester()

        # اضافه کردن تنظیمات مدیریت اتصال
        self.ssh_keepalive_interval = 30  # ارسال keepalive هر 30 ثانیه
        self.ssh_keepalive_count_max = 3  # حداکثر 3 بار تلاش
        self.last_keepalive_time = 0
        self.reconnect_in_progress = False
        self.reconnect_lock = threading.Lock()
        
        # Configure DNS
        dns_servers = []
        if self.config.get("dns_primary"): 
            dns_servers.append(self.config["dns_primary"])
        if self.config.get("dns_secondary"): 
            dns_servers.append(self.config["dns_secondary"])
        if dns_servers: 
            self.resolver.nameservers = dns_servers
        
        self.daemon = True
        
    def optimize_dns(self) -> bool:
        """Find and use the best DNS server."""
        try:
            test_rounds = int(self.config.get("dns_test_rounds", 3))
            self.dns_tester.test_rounds = test_rounds
            
            result = self.dns_tester.find_best_dns()
            if result["ip"]:
                self.best_dns_name = result["name"]
                self.best_dns_ip = result["ip"]
                
                # Update resolver
                self.resolver.nameservers = [self.best_dns_ip]
                self.log_callback(f"[✓] Using DNS: {self.best_dns_name} ({self.best_dns_ip})")
                
                # ذخیره در تنظیمات
                if self.config:
                    self.config["current_dns"] = {
                        "name": self.best_dns_name,
                        "ip": self.best_dns_ip,
                        "selected_by": "system"
                    }
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"DNS optimization error: {e}")
            self.log_callback(f"[!] DNS optimization failed: {e}")
            return False

    def get_thread_count(self) -> int:
        """Get current active thread count."""
        with self.thread_count_lock:
            return self.thread_count
    
    def increment_thread_count(self):
        """Increment thread counter."""
        with self.thread_count_lock:
            self.thread_count += 1
    
    def decrement_thread_count(self):
        """Decrement thread counter."""
        with self.thread_count_lock:
            if self.thread_count > 0:
                self.thread_count -= 1
    
    def reset_connections(self):
        """Reset all connections and thread pool."""
        logger.info("Resetting all connections...")
        self.log_callback("[*] Resetting connections...")
        
        # Cleanup channels
        with self.channels_lock:
            logger.info(f"Cleaning up {len(self.active_channels)} active channels")
            for channel in list(self.active_channels):
                try:
                    if channel and not channel.closed:
                        channel.close()
                except:
                    pass
            self.active_channels.clear()
        
        # Reset thread pool
        if self.executor:
            old_executor = self.executor
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SOCKS")
            old_executor.shutdown(wait=False, cancel_futures=True)
        
        with self.thread_count_lock:
            self.thread_count = 0
        
        self.dns_cache.clear()
        self.health_monitor.reset()
        
        # اضافه کردن: بازسازی اتصال SSH
        if self.ssh_client:
            try:
                # بررسی وضعیت اتصال SSH
                transport = self.ssh_client.get_transport()
                if not transport or not transport.is_active():
                    self.log_callback("[*] SSH transport inactive, reconnecting...")
                    self._establish_ssh_connection()
                else:
                    self.log_callback("[*] SSH transport is active, no need to reconnect")
            except Exception as e:
                logger.error(f"SSH transport check failed: {e}")
                self.log_callback(f"[!] SSH check failed, reconnecting: {e}")
                self._establish_ssh_connection()
        
        self.log_callback("[✓] Connections reset completed")
        logger.info("Connection reset completed")


    # ***** این تابع جدید را در اینجا اضافه کنید *****
    def recover_connection(self):
        """Attempt to recover SSH connection."""
        with self.reconnect_lock:
            if self.reconnect_in_progress:
                logger.debug("Recovery already in progress")
                return False
            
            self.reconnect_in_progress = True
            try:
                self.log_callback("[*] Attempting to recover SSH connection...")
                
                # بستن اتصال قبلی
                if self.ssh_client:
                    try:
                        self.ssh_client.close()
                    except Exception as e:
                        logger.debug(f"Error closing old SSH client: {e}")
                
                # برقراری مجدد اتصال
                self._establish_ssh_connection()
                self.log_callback("[✓] Connection recovered successfully")
                return True
                
            except Exception as e:
                logger.error(f"Connection recovery failed: {e}")
                self.log_callback(f"[!] Recovery failed: {e}")
                return False
            finally:
                self.reconnect_in_progress = False


    def run(self):
        """Main thread execution with auto-reconnect support."""
        while self.running and self.connection_attempts < self.max_reconnect_attempts:
            try:
                # Optimize DNS if enabled
                if self.config.get("dns_optimization", True):
                    self.optimize_dns()
                
                self._establish_ssh_connection()
                self._start_socks_server()
                break
            except Exception as e:
                self.connection_attempts += 1
                logger.error(f"Connection attempt {self.connection_attempts} failed: {e}")
                
                if self.config.get("auto_reconnect") and self.connection_attempts < self.max_reconnect_attempts:
                    self.log_callback(f"[!] Reconnecting in {self.reconnect_delay}s... (Attempt {self.connection_attempts}/{self.max_reconnect_attempts})")
                    time.sleep(self.reconnect_delay)
                else:
                    self.log_callback(f"[!] Connection failed: {e}")
                    self.status_callback(False, None)
                    break

            # در تابع _establish_ssh_connection بعد از خطا:
            except Exception as e:
                error_msg = f"SSH Connection failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # تشخیص نوع خطا
                if "timed out" in str(e).lower():
                    self.log_callback("[!] Connection timeout - Check network/firewall")
                elif "authentication" in str(e).lower():
                    self.log_callback("[!] Authentication failed - Check credentials")
                elif "refused" in str(e).lower():
                    self.log_callback("[!] Connection refused - Check port/server status")
                else:
                    self.log_callback(f"[!] Connection error: {str(e)[:100]}")
                
                raise

    def _establish_ssh_connection(self):
        """Establish SSH connection with multi-hop and multi-WAN support."""
        timeout = self.timeout

        if len(self.servers) > 1:
            # Multi-hop connection
            self.multi_hop = MultiHopSSH(self.log_callback)
            self.ssh_client = self.multi_hop.connect_multi_hop(self.servers)
            
            if not self.ssh_client:
                raise Exception("Multi-hop connection failed")
        else:
            # Single server connection
            server = self.servers[0]
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.log_callback(f"[*] Connecting to {server['host']}:{server['port']}...")
            
            connect_kwargs = {
                "hostname": server['host'],
                "port": int(server['port']),
                "username": server['username'],
                "timeout": timeout,
                "banner_timeout": timeout
            }
            
            # Key-based or password authentication
            if server.get('key_file') and os.path.exists(server['key_file']):
                connect_kwargs['key_filename'] = server['key_file']
            else:
                connect_kwargs['password'] = server.get('password', '')
            
            # Bind to specific interface if multi-WAN is enabled
            if self.config.get('wan_bonding_enabled'):
                iface = self.iface_manager.get_next_interface(
                    self.config.get('load_balancing_mode', 'round_robin')
                )
                if iface:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        sock.bind((iface['ip'], 0))
                        sock.settimeout(timeout)
                        sock.connect((server['host'], int(server['port'])))
                        connect_kwargs['sock'] = sock
                        self.log_callback(f"[*] Using interface: {iface['name']} ({iface['type']}) - {iface['ip']}")
                    except Exception as e:
                        logger.warning(f"Failed to bind to interface {iface['name']}: {e}")
                        sock.close()
                    
                    except Exception as e:
                        if 'sock' in locals() and sock:
                            try:
                                sock.close()
                            except:
                                pass
                        raise
            
            self.ssh_client.connect(**connect_kwargs)
            self.log_callback(f"[✓] Connected successfully")
        
        transport = self.ssh_client.get_transport()
        if not transport or not transport.is_active():
            raise Exception("SSH transport is not active")

        # 🔧 keepalive به روش صحیح
        if transport:
            transport.set_keepalive(15)  # ارسال keepalive هر 15 ثانیه
            
            # غیرفعال کردن فشرده‌سازی برای بهبود عملکرد
            transport.use_compression(False)
            
            # برای کنترل بهتر timeout از socket استفاده کنید
            sock = transport.sock
            if sock:
                sock.settimeout(30)  # تنظیم timeout سوکت
        
        self.log_callback(f"[✓] SSH tunnel established (Keepalive: 15s)")
        self.status_callback(True, self.ssh_client)

    def _start_socks_server(self):
        """Start SOCKS5 server with ThreadPool."""
        local_port = int(self.config.get('local_port', 1080))
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('127.0.0.1', local_port))
        self.server_socket.listen(128)
        self.server_socket.settimeout(1.0)
        
        # Initialize ThreadPool
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SOCKS")
        
        self.log_callback(f"[*] SOCKS5 Server listening on 127.0.0.1:{local_port}")
        logger.info(f"SOCKS5 server started on port {local_port}")
        
        while self.running:
            try:
                client, addr = self.server_socket.accept()
                if not self.running: 
                    break
                
                client.settimeout(30)
                self.stats.increment_connection()
                self.increment_thread_count()
                
                # Use thread pool instead of creating raw threads
                self.executor.submit(self._handle_client_wrapper, client, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")

    def _handle_client_wrapper(self, client, addr):
        """Wrapper for thread pool execution."""
        try:
            self.handle_client(client, addr)
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            self.stats.decrement_connection()
            self.decrement_thread_count()

    def handle_client(self, client_socket: socket.socket, addr: tuple):
        """Handle individual SOCKS5 client connection with DNS cache and channel tracking."""
        remote_socket = None
        client_info = f"{addr[0]}:{addr[1]}"
        destination = "unknown"
        
        try:
            # SOCKS5 greeting
            greeting = client_socket.recv(262)
            if not greeting or len(greeting) < 2:
                return
            
            client_socket.send(b"\x05\x00")
            
            # SOCKS5 request
            data = client_socket.recv(4)
            if not data or len(data) < 4 or data[1] != 1:
                return

            addr_type = data[3]
            dest_addr = ""
            
            # Parse destination address
            if addr_type == 1:  # IPv4
                dest_addr = socket.inet_ntoa(client_socket.recv(4))
            
            elif addr_type == 3:  # Domain name
                domain_len = ord(client_socket.recv(1))
                domain = client_socket.recv(domain_len).decode('utf-8', errors='ignore')
                dest_addr = domain
                
                # DNS resolution با fallback به DNS عمومی
                cached_ip = self.dns_cache.get(domain)
                if cached_ip:
                    dest_addr = cached_ip
                else:
                    # ابتدا از DNS تنظیم شده استفاده کنید
                    try:
                        answers = self.resolver.resolve(domain, 'A')
                        if answers:
                            dest_addr = str(answers[0])
                            self.dns_cache.set(domain, dest_addr)
                            logger.info(f"DNS resolved {domain} -> {dest_addr} via configured DNS")
                    except Exception as e:
                        logger.debug(f"Primary DNS resolution failed: {e}")
                        # اگر DNS اصلی جواب نداد، از DNS محلی سیستم استفاده کنید
                        try:
                            dest_addr = socket.gethostbyname(domain)
                            self.dns_cache.set(domain, dest_addr)
                            logger.info(f"DNS resolved {domain} -> {dest_addr} via system DNS")
                        except socket.gaierror:
                            logger.error(f"All DNS resolutions failed for {domain}")
                            client_socket.send(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
                            return
            
            elif addr_type == 4:  # IPv6 - باید فعال شود
                dest_addr = socket.inet_ntop(socket.AF_INET6, client_socket.recv(16))
            
            else:
                # Unsupported address type
                client_socket.send(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")  # Address type not supported
                return

            # دریافت پورت
            dest_port = struct.unpack('>H', client_socket.recv(2))[0]
            destination = f"{dest_addr}:{dest_port}"
            
            # Log connection
            self.connection_logger.add_connection(client_info, destination)
            
            # Log traffic if enabled
            if self.config.get("log_traffic"):
                self.log_callback(f"[Traffic] {client_info} -> {destination}")
            
            logger.debug(f"Connecting to {dest_addr}:{dest_port}")

            # Create SSH tunnel with RTT measurement
            transport = self.ssh_client.get_transport()
            if not transport or not transport.is_active():
                logger.error("SSH transport is not active - attempting to reconnect")
                self.log_callback("[!] SSH connection lost, reconnecting...")
                
                # تلاش برای بازسازی اتصال
                try:
                    self._establish_ssh_connection()
                    transport = self.ssh_client.get_transport()
                except Exception as e:
                    logger.error(f"Reconnection failed: {e}")
                    client_socket.send(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                    self.stats.increment_failed()
                    return
            
            try:
                start_time = time.time()
                remote_socket = transport.open_channel(
                    "direct-tcpip", 
                    (dest_addr, dest_port), 
                    addr,
                    timeout=10
                )
                rtt = (time.time() - start_time) * 1000
                self.health_monitor.add_rtt(rtt)
                
                # Track active channel
                with self.channels_lock:
                    self.active_channels.add(remote_socket)
                    
            except Exception as e:
                logger.debug(f"Channel open failed for {dest_addr}:{dest_port}: {e}")
                client_socket.send(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                self.stats.increment_failed()
                return
            
            if not remote_socket:
                logger.error(f"Failed to open channel to {dest_addr}:{dest_port}")
                client_socket.send(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                self.stats.increment_failed()
                return

            # Send success response
            client_socket.send(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            
            # Forward data
            self.forward_data(client_socket, remote_socket)
            
        except Exception as e:
            logger.error(f"Client handling error: {e}")
            self.stats.increment_failed()
        finally:
            try:
                client_socket.close()
            except:
                pass
            
            # Properly close and untrack channel
            if remote_socket:
                try:
                    remote_socket.close()
                except:
                    pass
                
                with self.channels_lock:
                    self.active_channels.discard(remote_socket)

    def forward_data(self, client: socket.socket, remote):
        """Bidirectional data forwarding with optimized timeout."""
        try:
            while self.running:
                # Reduced timeout from 10s to 0.5s for better responsiveness
                r, w, x = select.select([client, remote], [], [], 0.5)
                
                if not r:
                    continue
                
                if client in r:
                    data = client.recv(8192)
                    if not data:
                        break
                    remote.send(data)
                    self.stats.add_sent(len(data))
                
                if remote in r:
                    data = remote.recv(8192)
                    if not data:
                        break
                    client.send(data)
                    self.stats.add_received(len(data))
        except Exception as e:
            logger.debug(f"Forward data error: {e}")
        finally:
            try:
                remote.close()
            except:
                pass

    def stop(self):
        """Gracefully stop the proxy."""
        self.running = False
        self.status_callback(False, None)
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Shutdown thread pool
        if self.executor:
            logger.info("Shutting down thread pool...")
            self.executor.shutdown(wait=False, cancel_futures=True)
        
        # Cleanup all channels
        with self.channels_lock:
            logger.info(f"Cleaning up {len(self.active_channels)} active channels")
            for channel in list(self.active_channels):
                try:
                    if channel and not channel.closed:
                        channel.close()
                except:
                    pass
            self.active_channels.clear()
        
        if self.multi_hop:
            self.multi_hop.cleanup()
        elif self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
        
        self.log_callback("[*] Proxy server stopped")

# ================= ULTIMATE GUI APPLICATION =================
class TunnelProApp(ctk.CTk):
    """Ultimate SSH Tunnel application with all features."""

    def setup_windows_app_id(self):
        """Set Windows App ID for better taskbar integration."""
        if platform.system() == "Windows":
            try:
                import ctypes
                # Set AppUserModelID - این به ویندوز کمک می‌کند آیکون را بهتر تشخیص دهد
                app_id = 'SSH.Tunnel.Pro.Ultimate.4.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
                logger.info(f"Windows App ID set: {app_id}")
            except Exception as e:
                logger.warning(f"Failed to set Windows App ID: {e}")
    
    def __init__(self):
        super().__init__()

        # ابتدا پنجره را پنهان کنید
        self.withdraw()  # یا self.iconify()

        self.setup_icon()
        
        self.title("SSH Tunnel Pro Ultimate - Integrated Edition")
        self.geometry("1400x900")
        self.minsize(1200, 800)
        
        # Initialize components
        self.encryption_manager = EncryptionManager()
        self.iface_manager = NetworkInterfaceManager()
        self.traffic_stats = TrafficStats()
        self.connection_logger = ConnectionLogger(max_connections=50)
        self.dns_tester = DNSTester()
        self.app_config = self.load_config()
        
        self.proxy_thread: Optional[AdvancedSOCKS5Proxy] = None
        self.ssh_active_client: Optional[paramiko.SSHClient] = None
        self.servers_list = []
        self.ping_thread_running = False
        self.show_password = False
        self.stats_update_running = False
        self.auto_reset_thread_running = False
        self.interface_vars = []
        self.dns_test_results = {}
        
        # Apply theme
        theme = self.app_config.get("settings", {}).get("theme", "dark-blue")
        ctk.set_default_color_theme(theme)
        
        # Setup UI
        self.setup_layout()
        self.setup_sidebar()
        self.setup_tabs()
        self.setup_logs()
        
        # Initialize
        self.refresh_lists()
        
        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # بعد از کامل شدن setup، پنجره را نمایش دهید
        self.deiconify()  # پنجره را ظاهر کن
        
        # یا با تاخیر
        self.after(500, self.deiconify)
        
        self.log("=== SSH Tunnel Pro Ultimate Started ===")
        self.log(f"Platform: {platform.system()} {platform.release()}")
        logger.info("Application started")

    def setup_icon(self):
        """Set up application icon with improved timing."""
        try:
            self.update_idletasks()
            
            icon_paths = [
                "logo.ico",
                "logo.png",
                os.path.join(os.path.dirname(__file__), "logo.ico"),
                os.path.join(os.path.dirname(__file__), "logo.png")
            ]
            
            for icon_path in icon_paths:
                if os.path.exists(icon_path):
                    try:
                        if icon_path.endswith('.ico'):
                            self.iconbitmap(icon_path)
                            logger.info(f"Icon loaded: {icon_path}")
                            
                            # برای ویندوز، ترفند اضافه
                            if platform.system() == "Windows":
                                import ctypes
                                # Set app ID برای taskbar
                                app_id = 'ssh.tunnel.pro.ultimate.4.0'
                                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
                            
                            break
                        elif icon_path.endswith('.png'):
                            icon_image = tk.PhotoImage(file=icon_path)
                            self.iconphoto(True, icon_image)
                            logger.info(f"PNG Icon loaded: {icon_path}")
                            break
                    except Exception as e:
                        logger.warning(f"Failed to load icon {icon_path}: {e}")
                        continue
            
            else:
                logger.warning("No icon file found in expected paths")
                    
        except Exception as e:
            logger.error(f"Error setting up icon: {e}")
        
        self.update()

    # ================= LAYOUT SETUP =================
    
    def setup_layout(self):
        """Configure main layout grid."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def setup_sidebar(self):
        """Setup sidebar with saved servers and DNS presets."""
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        self.sidebar.grid_rowconfigure(1, weight=1)
        self.sidebar.grid_rowconfigure(3, weight=1)
        
        # Servers section
        ctk.CTkLabel(
            self.sidebar, 
            text="💾 Saved Servers", 
            font=("Roboto", 16, "bold")
        ).grid(row=0, column=0, pady=(20, 10), padx=15, sticky="w")
        
        self.scroll_servers = ctk.CTkScrollableFrame(self.sidebar, height=250)
        self.scroll_servers.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # DNS section
        ctk.CTkLabel(
            self.sidebar, 
            text="🌐 DNS Presets", 
            font=("Roboto", 16, "bold")
        ).grid(row=2, column=0, pady=(10, 10), padx=15, sticky="w")
        
        self.scroll_dns = ctk.CTkScrollableFrame(self.sidebar, height=180)
        self.scroll_dns.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # Action buttons
        btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=15, padx=10, sticky="ew")
        
        ctk.CTkButton(
            btn_frame, 
            text="🗑️ Delete Selected", 
            fg_color="#c0392b", 
            hover_color="#e74c3c",
            command=self.delete_item
        ).pack(fill="x", pady=2)
        
        ctk.CTkButton(
            btn_frame, 
            text="📁 Export Config", 
            command=self.export_config
        ).pack(fill="x", pady=2)
        
        ctk.CTkButton(
            btn_frame, 
            text="📥 Import Config", 
            command=self.import_config
        ).pack(fill="x", pady=2)

    def setup_tabs(self):
        """Setup tabbed interface."""
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        
        # Create tabs
        self.tab_connect = self.tab_view.add("🔌 Connection")
        self.tab_multihop = self.tab_view.add("🔗 Multi-Hop")
        self.tab_monitor = self.tab_view.add("📊 Network Monitor")
        self.tab_stats = self.tab_view.add("📈 Statistics")
        self.tab_connections = self.tab_view.add("🔗 Recent Connections")
        self.tab_dns = self.tab_view.add("🌐 DNS Optimizer")
        self.tab_threads = self.tab_view.add("⚙️ Thread Management")
        self.tab_settings = self.tab_view.add("🔧 Settings")
        
        self.setup_connection_tab()
        self.setup_multihop_tab()
        self.setup_monitor_tab()
        self.setup_statistics_tab()
        self.setup_connections_tab()
        self.setup_dns_tab()
        self.setup_thread_management_tab()
        self.setup_settings_tab()

    def setup_connection_tab(self):
        """Setup connection configuration tab."""
        # Server configuration
        self.frame_server = ctk.CTkFrame(self.tab_connect)
        self.frame_server.pack(fill="x", pady=(10, 15), padx=15)

        ctk.CTkLabel(
            self.frame_server, 
            text="Server Configuration", 
            font=("Roboto", 16, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 10))
        
        # Server details
        self.ent_server_name = ctk.CTkEntry(
            self.frame_server, 
            placeholder_text="Server Alias (e.g., MyVPS)"
        )
        self.ent_server_name.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.ent_host = ctk.CTkEntry(
            self.frame_server, 
            placeholder_text="Host IP or Domain"
        )
        self.ent_host.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        
        self.ent_port = ctk.CTkEntry(
            self.frame_server, 
            placeholder_text="SSH Port", 
            width=100
        )
        self.ent_port.insert(0, "22")
        self.ent_port.grid(row=1, column=2, padx=10, pady=5, sticky="ew")

        # Credentials
        self.ent_user = ctk.CTkEntry(
            self.frame_server, 
            placeholder_text="Username"
        )
        self.ent_user.insert(0, "root")
        self.ent_user.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        # Password with show/hide
        self.frame_pass = ctk.CTkFrame(self.frame_server, fg_color="transparent")
        self.frame_pass.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        
        self.ent_pass = ctk.CTkEntry(
            self.frame_pass, 
            placeholder_text="Password", 
            show="*"
        )
        self.ent_pass.pack(side="left", fill="x", expand=True)
        
        self.btn_toggle_pass = ctk.CTkButton(
            self.frame_pass, 
            text="👁️", 
            width=40,
            command=self.toggle_pass_visibility
        )
        self.btn_toggle_pass.pack(side="left", padx=(5, 0))
        
        # Key file option
        self.frame_key = ctk.CTkFrame(self.frame_server, fg_color="transparent")
        self.frame_key.grid(row=2, column=2, padx=10, pady=5, sticky="ew")
        
        self.ent_key_file = ctk.CTkEntry(
            self.frame_key, 
            placeholder_text="SSH Key (optional)", 
            width=150
        )
        self.ent_key_file.pack(side="left", fill="x", expand=True)
        
        ctk.CTkButton(
            self.frame_key, 
            text="📂", 
            width=40,
            command=self.browse_key_file
        ).pack(side="left", padx=(5, 0))
        
        # Save button
        ctk.CTkButton(
            self.frame_server, 
            text="💾 Save Server Configuration", 
            command=self.save_server,
            fg_color="#27ae60",
            hover_color="#2ecc71",
            height=35
        ).grid(row=3, column=0, columnspan=3, padx=10, pady=(10, 15), sticky="ew")
        
        self.frame_server.grid_columnconfigure(1, weight=1)

        # Proxy and DNS settings
        self.frame_mid = ctk.CTkFrame(self.tab_connect, fg_color="transparent")
        self.frame_mid.pack(fill="x", pady=(0, 15), padx=15)
        
        # Proxy settings
        self.frame_settings = ctk.CTkFrame(self.frame_mid)
        self.frame_settings.pack(side="left", fill="both", expand=True, padx=(0, 7))
        
        ctk.CTkLabel(
            self.frame_settings, 
            text="Proxy Settings", 
            font=("Roboto", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        self.ent_local_port = ctk.CTkEntry(
            self.frame_settings, 
            placeholder_text="Local SOCKS5 Port"
        )
        self.ent_local_port.insert(0, self.app_config.get("settings", {}).get("local_port", "1080"))
        self.ent_local_port.pack(fill="x", padx=15, pady=(5, 15))

        # DNS configuration - این بخش اول ایجاد می‌شود
        self.frame_dns = ctk.CTkFrame(self.frame_mid)
        self.frame_dns.pack(side="right", fill="both", expand=True, padx=(7, 0))
        self.frame_dns.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            self.frame_dns, 
            text="DNS Configuration", 
            font=("Roboto", 14, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 5))
        
        self.ent_dns_name = ctk.CTkEntry(
            self.frame_dns, 
            placeholder_text="DNS Alias"
        )
        self.ent_dns_name.grid(row=1, column=0, padx=5, pady=3, sticky="ew")
        
        self.ent_dns_1 = ctk.CTkEntry(
            self.frame_dns, 
            placeholder_text="Primary DNS"
        )
        self.ent_dns_1.grid(row=1, column=1, padx=5, pady=3, sticky="ew")
        
        self.ent_dns_2 = ctk.CTkEntry(
            self.frame_dns, 
            placeholder_text="Secondary DNS"
        )
        self.ent_dns_2.grid(row=2, column=1, padx=5, pady=3, sticky="ew")
        
        ctk.CTkButton(
            self.frame_dns, 
            text="💾 Save DNS", 
            width=100,
            command=self.save_dns
        ).grid(row=2, column=0, padx=5, pady=(3, 10), sticky="ew")
        
        # ========== CURRENT DNS STATUS FRAME - اینجا اضافه شود ==========
        self.current_dns_frame = ctk.CTkFrame(self.frame_dns)
        self.current_dns_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=(10, 5), sticky="ew")
        
        ctk.CTkLabel(
            self.current_dns_frame,
            text="🌐 Current DNS Status:",
            font=("Roboto", 11, "bold")
        ).pack(side="left", padx=(5, 10))
        
        self.lbl_current_dns = ctk.CTkLabel(
            self.current_dns_frame,
            text="Not selected yet",
            font=("Roboto", 11),
            text_color="#3498db"
        )
        self.lbl_current_dns.pack(side="left")
        
        # Auto-refresh current DNS status
        self.dns_status_update_running = True
        threading.Thread(target=self.update_dns_status_loop, daemon=True).start()
        # ==============================================================

        # Connection status and control
        self.frame_status = ctk.CTkFrame(self.tab_connect)
        self.frame_status.pack(fill="x", pady=(0, 10), padx=15)
        
        # Status indicator
        status_left = ctk.CTkFrame(self.frame_status, fg_color="transparent")
        status_left.pack(side="left", fill="y", pady=15, padx=15)
        
        self.status_light = ctk.CTkButton(
            status_left, 
            text="", 
            width=30, 
            height=30, 
            corner_radius=15,
            fg_color="#e74c3c", 
            state="disabled"
        )
        self.status_light.pack(side="left", padx=(0, 10))
        
        status_labels = ctk.CTkFrame(status_left, fg_color="transparent")
        status_labels.pack(side="left")
        
        self.lbl_status = ctk.CTkLabel(
            status_labels, 
            text="Disconnected", 
            font=("Roboto", 16, "bold")
        )
        self.lbl_status.pack(anchor="w")
        
        self.lbl_ping = ctk.CTkLabel(
            status_labels, 
            text="Latency: -- ms",
            font=("Roboto", 11),
            text_color="gray"
        )
        self.lbl_ping.pack(anchor="w")
        
        # Connect button
        self.btn_connect = ctk.CTkButton(
            self.frame_status, 
            text="🔌 CONNECT", 
            font=("Roboto", 16, "bold"),
            fg_color="#27ae60", 
            hover_color="#2ecc71", 
            height=50,
            width=200,
            command=self.toggle_connection
        )
        self.btn_connect.pack(side="right", padx=15, pady=10)

    def update_dns_status_loop(self):
        """Continuously update current DNS status."""
        while self.dns_status_update_running:
            try:
                if hasattr(self, 'proxy_thread') and self.proxy_thread:
                    dns_name = getattr(self.proxy_thread, 'best_dns_name', None)
                    dns_ip = getattr(self.proxy_thread, 'best_dns_ip', None)
                    
                    if dns_name and dns_ip:
                        status_text = f"{dns_name} ({dns_ip})"
                        self.lbl_current_dns.configure(text=status_text)
                    else:
                        # بررسی اگر DNS دستی تنظیم شده
                        dns1 = self.ent_dns_1.get().strip()
                        dns2 = self.ent_dns_2.get().strip()
                        
                        if dns1:
                            if dns1 in ["8.8.8.8", "8.8.4.4"]:
                                self.lbl_current_dns.configure(text=f"Google DNS ({dns1})")
                            elif dns1 in ["1.1.1.1", "1.0.0.1"]:
                                self.lbl_current_dns.configure(text=f"Cloudflare DNS ({dns1})")
                            elif dns1 in ["178.22.122.100", "185.51.200.2"]:
                                self.lbl_current_dns.configure(text=f"Shecan DNS ({dns1})")
                            else:
                                self.lbl_current_dns.configure(text=f"Custom DNS ({dns1})")
                        else:
                            self.lbl_current_dns.configure(text="Using system default DNS")
            except Exception as e:
                logger.debug(f"DNS status update error: {e}")
            
            time.sleep(2)

    def setup_multihop_tab(self):
        """Setup multi-hop tunneling configuration."""
        main_frame = ctk.CTkScrollableFrame(self.tab_multihop)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        ctk.CTkLabel(
            main_frame,
            text="🔗 Multi-Hop SSH Tunneling",
            font=("Roboto", 20, "bold")
        ).pack(pady=(0, 10))
        
        ctk.CTkLabel(
            main_frame,
            text="Chain multiple SSH servers for enhanced privacy and security",
            font=("Roboto", 12),
            text_color="gray"
        ).pack(pady=(0, 20))
        
        # Multi-hop toggle
        self.var_multihop = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            main_frame,
            text="Enable Multi-Hop Mode",
            variable=self.var_multihop,
            font=("Roboto", 14, "bold"),
            command=self.toggle_multihop
        ).pack(anchor="w", pady=10)
        
        # Server selection
        self.frame_hop_servers = ctk.CTkFrame(main_frame)
        self.frame_hop_servers.pack(fill="x", pady=20)
        
        ctk.CTkLabel(
            self.frame_hop_servers,
            text="Select Servers (in order):",
            font=("Roboto", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Server 1
        hop1_frame = ctk.CTkFrame(self.frame_hop_servers, fg_color="transparent")
        hop1_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            hop1_frame,
            text="1st Server:",
            width=100
        ).pack(side="left", padx=(0, 10))
        
        server_names = ["No servers"] + list(self.app_config.get("servers", {}).keys())
        self.var_server1 = tk.StringVar(value="No servers")
        self.menu_server1 = ctk.CTkOptionMenu(
            hop1_frame,
            values=server_names,
            variable=self.var_server1,
            width=300
        )
        self.menu_server1.pack(side="left", fill="x", expand=True)
        
        # Server 2
        hop2_frame = ctk.CTkFrame(self.frame_hop_servers, fg_color="transparent")
        hop2_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            hop2_frame,
            text="2nd Server:",
            width=100
        ).pack(side="left", padx=(0, 10))
        
        self.var_server2 = tk.StringVar(value="No servers")
        self.menu_server2 = ctk.CTkOptionMenu(
            hop2_frame,
            values=server_names,
            variable=self.var_server2,
            width=300
        )
        self.menu_server2.pack(side="left", fill="x", expand=True)
        
        # Apply button
        ctk.CTkButton(
            self.frame_hop_servers,
            text="✓ Apply Multi-Hop Configuration",
            command=self.apply_multihop,
            fg_color="#27ae60",
            hover_color="#2ecc71",
            height=35
        ).pack(padx=15, pady=(15, 15))
        
        # Info box
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=(20, 0))
        
        info_text = """
ℹ️ Multi-Hop Information:

• Your traffic will be routed through multiple servers in sequence
• Each additional hop adds latency but increases privacy
• Servers must allow TCP forwarding (AllowTcpForwarding yes)
• Connection chain: You → Server 1 → Server 2 → Internet

⚠️ Important Notes:
• All servers in the chain must be saved in "Saved Servers"
• Ensure you have valid credentials for all servers
• Test each server individually before using multi-hop
        """
        
        ctk.CTkLabel(
            info_frame,
            text=info_text,
            font=("Roboto", 11),
            justify="left"
        ).pack(padx=20, pady=20, anchor="w")

    def setup_monitor_tab(self):
        """Setup network monitoring tab."""
        # IP Information
        self.frame_info = ctk.CTkFrame(self.tab_monitor)
        self.frame_info.pack(fill="x", pady=20, padx=20)
        
        ctk.CTkLabel(
            self.frame_info, 
            text="🌍 Network Identity", 
            font=("Roboto", 18, "bold")
        ).pack(pady=(15, 10))
        
        info_grid = ctk.CTkFrame(self.frame_info, fg_color="transparent")
        info_grid.pack(pady=10, padx=20)
        
        self.lbl_ip = ctk.CTkLabel(
            info_grid, 
            text="Public IP: --", 
            font=("Consolas", 14)
        )
        self.lbl_ip.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        self.lbl_isp = ctk.CTkLabel(
            info_grid, 
            text="ISP: --", 
            font=("Consolas", 14)
        )
        self.lbl_isp.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        
        self.lbl_loc = ctk.CTkLabel(
            info_grid, 
            text="Location: --", 
            font=("Consolas", 14)
        )
        self.lbl_loc.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        ctk.CTkButton(
            self.frame_info, 
            text="🔄 Refresh IP Information", 
            command=self.update_ip_info,
            height=35
        ).pack(pady=(5, 15))

        # Network Interfaces (WAN Bonding)
        self.frame_interfaces = ctk.CTkFrame(self.tab_monitor)
        self.frame_interfaces.pack(fill="both", expand=True, pady=(0, 20), padx=20)
        
        ctk.CTkLabel(
            self.frame_interfaces,
            text="🌐 Network Interfaces (Multi-WAN)",
            font=("Roboto", 18, "bold")
        ).pack(pady=(15, 10))
        
        # Info text
        info_text = ctk.CTkLabel(
            self.frame_interfaces,
            text="Check interfaces below to use for WAN bonding. Traffic will be distributed across selected interfaces.",
            font=("Roboto", 11),
            text_color="gray",
            wraplength=600
        )
        info_text.pack(pady=(0, 10))
        
        self.scroll_interfaces = ctk.CTkScrollableFrame(self.frame_interfaces)
        self.scroll_interfaces.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        
        ctk.CTkButton(
            self.frame_interfaces,
            text="🔍 Scan Network Interfaces",
            command=self.scan_interfaces,
            height=35
        ).pack(pady=(0, 15))

    def setup_statistics_tab(self):
        """Setup statistics monitoring tab."""
        main_frame = ctk.CTkFrame(self.tab_stats, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            main_frame, 
            text="📊 Real-time Traffic Statistics", 
            font=("Roboto", 20, "bold")
        ).pack(pady=(0, 20))
        
        # Statistics grid
        stats_container = ctk.CTkFrame(main_frame)
        stats_container.pack(fill="both", expand=True)
        
        # Data Transfer
        transfer_frame = ctk.CTkFrame(stats_container)
        transfer_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            transfer_frame, 
            text="📤 Data Transfer", 
            font=("Roboto", 16, "bold")
        ).pack(pady=15)
        
        self.lbl_bytes_sent = ctk.CTkLabel(
            transfer_frame, 
            text="Uploaded: 0 B",
            font=("Consolas", 14)
        )
        self.lbl_bytes_sent.pack(pady=5)
        
        self.lbl_bytes_received = ctk.CTkLabel(
            transfer_frame, 
            text="Downloaded: 0 B",
            font=("Consolas", 14)
        )
        self.lbl_bytes_received.pack(pady=5)
        
        self.lbl_upload_speed = ctk.CTkLabel(
            transfer_frame,
            text="Upload Speed: 0 B/s",
            font=("Consolas", 12),
            text_color="#e74c3c"
        )
        self.lbl_upload_speed.pack(pady=2)
        
        self.lbl_download_speed = ctk.CTkLabel(
            transfer_frame,
            text="Download Speed: 0 B/s",
            font=("Consolas", 12),
            text_color="#3498db"
        )
        self.lbl_download_speed.pack(pady=2)
        
        self.lbl_total_transfer = ctk.CTkLabel(
            transfer_frame, 
            text="Total: 0 B",
            font=("Consolas", 14, "bold"),
            text_color="#2ecc71"
        )
        self.lbl_total_transfer.pack(pady=10)
        
        # Connections
        conn_frame = ctk.CTkFrame(stats_container)
        conn_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            conn_frame, 
            text="🔌 Connections", 
            font=("Roboto", 16, "bold")
        ).pack(pady=15)
        
        self.lbl_active_conn = ctk.CTkLabel(
            conn_frame, 
            text="Active: 0",
            font=("Consolas", 14)
        )
        self.lbl_active_conn.pack(pady=5)
        
        self.lbl_total_conn = ctk.CTkLabel(
            conn_frame, 
            text="Total: 0",
            font=("Consolas", 14)
        )
        self.lbl_total_conn.pack(pady=5)
        
        self.lbl_failed_conn = ctk.CTkLabel(
            conn_frame,
            text="Failed: 0",
            font=("Consolas", 12),
            text_color="#e74c3c"
        )
        self.lbl_failed_conn.pack(pady=2)
        
        self.lbl_conn_rate = ctk.CTkLabel(
            conn_frame, 
            text="Rate: 0/min",
            font=("Consolas", 14)
        )
        self.lbl_conn_rate.pack(pady=10)
        
        # Session Info
        session_frame = ctk.CTkFrame(stats_container)
        session_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(
            session_frame, 
            text="⏱️ Session Information", 
            font=("Roboto", 16, "bold")
        ).pack(pady=15)
        
        self.lbl_uptime = ctk.CTkLabel(
            session_frame, 
            text="Uptime: 00:00:00",
            font=("Consolas", 14)
        )
        self.lbl_uptime.pack(pady=5)
        
        self.lbl_avg_speed = ctk.CTkLabel(
            session_frame, 
            text="Avg Speed: 0 KB/s",
            font=("Consolas", 14)
        )
        self.lbl_avg_speed.pack(pady=5)
        
        # Reset button
        ctk.CTkButton(
            session_frame,
            text="🔄 Reset Statistics",
            command=self.reset_statistics,
            fg_color="#c0392b",
            hover_color="#e74c3c"
        ).pack(pady=15)
        
        stats_container.grid_columnconfigure(0, weight=1)
        stats_container.grid_columnconfigure(1, weight=1)
        stats_container.grid_rowconfigure(0, weight=1)
        stats_container.grid_rowconfigure(1, weight=1)

    def setup_connections_tab(self):
        """Setup recent connections display tab."""
        main_frame = ctk.CTkFrame(self.tab_connections)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            main_frame,
            text="🔗 Recent Connections (Last 50)",
            font=("Roboto", 20, "bold")
        ).pack(pady=(0, 20))
        
        # Treeview for connections
        self.connections_frame = ctk.CTkFrame(main_frame)
        self.connections_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Create a text widget for connections display
        self.connections_text = ctk.CTkTextbox(
            self.connections_frame,
            font=("Consolas", 11),
            state="disabled"
        )
        self.connections_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Control buttons
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(
            btn_frame,
            text="🔄 Refresh",
            command=self.update_connections_display,
            width=100
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="🗑️ Clear History",
            command=self.clear_connections_history,
            fg_color="#c0392b",
            hover_color="#e74c3c",
            width=120
        ).pack(side="left", padx=5)
        
        # Auto-refresh toggle
        self.var_auto_refresh = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            btn_frame,
            text="Auto-refresh (5s)",
            variable=self.var_auto_refresh,
            command=self.toggle_auto_refresh
        ).pack(side="left", padx=20)
        
        # Start auto-refresh
        self.auto_refresh_running = False
        self.start_auto_refresh()

    def setup_dns_tab(self):
        """Setup DNS optimizer tab."""
        main_frame = ctk.CTkScrollableFrame(self.tab_dns)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            main_frame,
            text="🌐 DNS Optimizer",
            font=("Roboto", 20, "bold")
        ).pack(pady=(0, 10))
        
        ctk.CTkLabel(
            main_frame,
            text="Test and select the fastest DNS server for your connection",
            font=("Roboto", 12),
            text_color="gray"
        ).pack(pady=(0, 20))
        
        # Test configuration
        config_frame = ctk.CTkFrame(main_frame)
        config_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            config_frame,
            text="Test Configuration",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Test target
        target_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        target_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            target_frame,
            text="Test Domain:",
            width=100
        ).pack(side="left", padx=(0, 10))
        
        self.ent_dns_test_domain = ctk.CTkEntry(target_frame)
        self.ent_dns_test_domain.insert(0, "google.com")
        self.ent_dns_test_domain.pack(side="left", fill="x", expand=True)
        
        # Test rounds
        rounds_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        rounds_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(
            rounds_frame,
            text="Test Rounds:",
            width=100
        ).pack(side="left", padx=(0, 10))
        
        self.ent_dns_test_rounds = ctk.CTkEntry(rounds_frame, width=100)
        self.ent_dns_test_rounds.insert(0, "3")
        self.ent_dns_test_rounds.pack(side="left")
        
        # Test button
        ctk.CTkButton(
            config_frame,
            text="🚀 Start DNS Test",
            command=self.start_dns_test,
            fg_color="#3498db",
            hover_color="#2980b9",
            height=40,
            font=("Roboto", 14, "bold")
        ).pack(pady=15, padx=15)
        
        # Results display
        self.results_frame = ctk.CTkFrame(main_frame)
        self.results_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        ctk.CTkLabel(
            self.results_frame,
            text="Test Results",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        self.dns_results_text = ctk.CTkTextbox(
            self.results_frame,
            font=("Consolas", 11),
            height=200,
            state="disabled"
        )
        self.dns_results_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Apply button
        self.btn_apply_dns = ctk.CTkButton(
            main_frame,
            text="✅ Apply Best DNS",
            command=self.apply_best_dns,
            fg_color="#27ae60",
            hover_color="#2ecc71",
            height=35,
            state="disabled"
        )
        self.btn_apply_dns.pack(pady=(0, 10))

    def setup_thread_management_tab(self):
        """Setup thread management and monitoring tab."""
        main_frame = ctk.CTkScrollableFrame(self.tab_threads)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Thread Statistics
        stats_frame = ctk.CTkFrame(main_frame)
        stats_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            stats_frame,
            text="⚙️ Thread Pool Status",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        self.lbl_thread_count = ctk.CTkLabel(
            stats_frame,
            text="Active Threads: 0",
            font=("Roboto", 24, "bold")
        )
        self.lbl_thread_count.pack(pady=15)
        
        self.lbl_max_threads = ctk.CTkLabel(
            stats_frame,
            text=f"Max Thread Pool Size: {self.app_config.get('settings', {}).get('max_threads', 100)}",
            font=("Roboto", 12)
        )
        self.lbl_max_threads.pack(pady=5)
        
        # Manual Reset
        reset_frame = ctk.CTkFrame(main_frame)
        reset_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            reset_frame,
            text="🔄 Manual Control",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        ctk.CTkButton(
            reset_frame,
            text="🔄 Reset All Threads & Connections",
            command=self.manual_thread_reset,
            height=50,
            font=("Roboto", 14, "bold"),
            fg_color="#e67e22",
            hover_color="#f39c12"
        ).pack(pady=15, padx=20, fill="x")
        
        # Auto Reset
        auto_frame = ctk.CTkFrame(main_frame)
        auto_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            auto_frame,
            text="⏱️ Automatic Thread Reset",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        self.var_auto_reset = ctk.BooleanVar(
            value=self.app_config.get("settings", {}).get("auto_reset_enabled", True)
        )
        ctk.CTkCheckBox(
            auto_frame,
            text="Enable Auto Reset (Prevents slowdown)",
            variable=self.var_auto_reset,
            command=self.toggle_auto_reset,
            font=("Roboto", 12)
        ).pack(anchor="w", padx=20, pady=10)
        
        # Interval setting
        interval_frame = ctk.CTkFrame(auto_frame, fg_color="transparent")
        interval_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            interval_frame,
            text="Reset Interval (seconds):",
            font=("Roboto", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.ent_reset_interval = ctk.CTkEntry(interval_frame, width=100)
        self.ent_reset_interval.insert(0, str(self.app_config.get("settings", {}).get("auto_reset_interval", 60)))
        self.ent_reset_interval.pack(side="left")
        
        ctk.CTkButton(
            interval_frame,
            text="Apply",
            width=80,
            command=self.apply_reset_interval
        ).pack(side="left", padx=10)
        
        # Next reset timer
        self.lbl_next_reset = ctk.CTkLabel(
            auto_frame,
            text="Next reset: --",
            font=("Roboto", 11),
            text_color="gray"
        )
        self.lbl_next_reset.pack(pady=10)
        
        # Info box
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            info_frame,
            text="ℹ️ Information",
            font=("Roboto", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        info_text = (
            "• Thread pool prevents thread explosion\n"
            "• Auto-reset clears hung connections\n"
            "• Recommended interval: 60-120 seconds\n"
            "• Manual reset available anytime"
        )
        
        ctk.CTkLabel(
            info_frame,
            text=info_text,
            font=("Roboto", 11),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 15))
        
        # Start thread counter update loop
        self.auto_reset_thread_running = False
        threading.Thread(target=self.update_thread_count_loop, daemon=True).start()

    def setup_settings_tab(self):
        """Setup application settings tab."""
        main_frame = ctk.CTkScrollableFrame(self.tab_settings)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # General Settings
        general_frame = ctk.CTkFrame(main_frame)
        general_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            general_frame, 
            text="⚙️ General Settings", 
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Auto-reconnect
        self.var_auto_reconnect = ctk.BooleanVar(
            value=self.app_config.get("settings", {}).get("auto_reconnect", True)
        )
        ctk.CTkCheckBox(
            general_frame,
            text="Enable Auto-reconnect",
            variable=self.var_auto_reconnect,
            command=self.save_settings
        ).pack(anchor="w", padx=20, pady=5)
        
        # Log traffic
        self.var_log_traffic = ctk.BooleanVar(
            value=self.app_config.get("settings", {}).get("log_traffic", False)
        )
        ctk.CTkCheckBox(
            general_frame,
            text="Log All Traffic (may impact performance)",
            variable=self.var_log_traffic,
            command=self.save_settings
        ).pack(anchor="w", padx=20, pady=5)
        
        # DNS optimization
        self.var_dns_optimization = ctk.BooleanVar(
            value=self.app_config.get("settings", {}).get("dns_optimization", True)
        )
        ctk.CTkCheckBox(
            general_frame,
            text="Enable DNS Optimization",
            variable=self.var_dns_optimization,
            command=self.save_settings
        ).pack(anchor="w", padx=20, pady=5)
        
        # Connection timeout
        timeout_frame = ctk.CTkFrame(general_frame, fg_color="transparent")
        timeout_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            timeout_frame,
            text="Connection Timeout (seconds):",
            font=("Roboto", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.ent_timeout = ctk.CTkEntry(timeout_frame, width=100)
        self.ent_timeout.insert(0, str(self.app_config.get("settings", {}).get("connection_timeout", 10)))
        self.ent_timeout.pack(side="left")
        
        ctk.CTkButton(
            timeout_frame,
            text="Apply",
            width=80,
            command=self.save_settings
        ).pack(side="left", padx=10)
        
        # Multi-WAN Settings
        wan_frame = ctk.CTkFrame(main_frame)
        wan_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            wan_frame,
            text="🌐 Multi-WAN Bonding",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # WAN Bonding toggle
        self.var_wan_bonding = ctk.BooleanVar(
            value=self.app_config.get("settings", {}).get("wan_bonding_enabled", False)
        )
        ctk.CTkCheckBox(
            wan_frame,
            text="Enable Multi-WAN Bonding",
            variable=self.var_wan_bonding,
            command=self.save_settings
        ).pack(anchor="w", padx=20, pady=5)
        
        # Load balancing mode
        lb_frame = ctk.CTkFrame(wan_frame, fg_color="transparent")
        lb_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            lb_frame,
            text="Load Balancing Mode:",
            font=("Roboto", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.var_lb_mode = tk.StringVar(
            value=self.app_config.get("settings", {}).get("load_balancing_mode", "round_robin")
        )
        lb_menu = ctk.CTkOptionMenu(
            lb_frame,
            values=["round_robin", "random", "fastest"],
            variable=self.var_lb_mode,
            command=lambda x: self.save_settings()
        )
        lb_menu.pack(side="left")
        
        ctk.CTkLabel(
            wan_frame,
            text="ℹ️ Multi-WAN Bonding Information:\n"
                 "• Select multiple interfaces in 'Network Monitor' tab\n"
                 "• Traffic will be distributed across selected interfaces\n"
                 "• Increases total bandwidth and provides redundancy\n"
                 "• Enable WAN bonding first, then scan and select interfaces",
            font=("Roboto", 10),
            text_color="gray",
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 15))
        
        # Reconnection Settings
        reconnect_frame = ctk.CTkFrame(main_frame)
        reconnect_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            reconnect_frame,
            text="🔄 Reconnection Settings",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Max attempts
        attempts_frame = ctk.CTkFrame(reconnect_frame, fg_color="transparent")
        attempts_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(
            attempts_frame,
            text="Max Reconnect Attempts:",
            font=("Roboto", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.ent_max_attempts = ctk.CTkEntry(attempts_frame, width=100)
        self.ent_max_attempts.insert(0, str(self.app_config.get("settings", {}).get("reconnect_max_attempts", 5)))
        self.ent_max_attempts.pack(side="left")
        
        # Initial delay
        delay_frame = ctk.CTkFrame(reconnect_frame, fg_color="transparent")
        delay_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(
            delay_frame,
            text="Initial Delay (seconds):",
            font=("Roboto", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.ent_initial_delay = ctk.CTkEntry(delay_frame, width=100)
        self.ent_initial_delay.insert(0, str(self.app_config.get("settings", {}).get("reconnect_initial_delay", 5)))
        self.ent_initial_delay.pack(side="left")
        
        ctk.CTkButton(
            reconnect_frame,
            text="Apply Reconnection Settings",
            command=self.save_settings,
            width=200
        ).pack(pady=10, padx=20)
        
        # Theme selection
        theme_frame = ctk.CTkFrame(main_frame)
        theme_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            theme_frame,
            text="🎨 Appearance",
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        theme_select = ctk.CTkFrame(theme_frame, fg_color="transparent")
        theme_select.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            theme_select,
            text="Color Theme:",
            font=("Roboto", 12)
        ).pack(side="left", padx=(0, 10))
        
        self.var_theme = tk.StringVar(
            value=self.app_config.get("settings", {}).get("theme", "dark-blue")
        )
        theme_menu = ctk.CTkOptionMenu(
            theme_select,
            values=["dark-blue", "blue", "green"],
            variable=self.var_theme,
            command=self.change_theme
        )
        theme_menu.pack(side="left")
        
        
        # ======== setup_settings_tab ========

        # About section
        about_frame = ctk.CTkFrame(main_frame)
        about_frame.pack(fill="x", pady=(15, 0))

        ctk.CTkLabel(
            about_frame, 
            text="ℹ️ About", 
            font=("Roboto", 16, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # ایجاد Text widget برای نمایش لینک‌های کلیک‌پذیر
        about_text_widget = ctk.CTkTextbox(
            about_frame,
            font=("Roboto", 11),
            height=290,
            state="normal",
            wrap="word"
        )
        about_text_widget.pack(anchor="w", padx=20, pady=(0, 15), fill="both", expand=True)

        about_text = """SSH Tunnel Pro Ultimate - Integrated Edition
        Version 1.0

        Features:
        • Multi-WAN Bonding for load balancing
        • Multi-Hop SSH tunneling for enhanced privacy
        • DNS Optimization with automatic selection
        • Encrypted credential storage
        • Real-time traffic statistics
        • Network monitoring and interface management
        • Connection logging and history
        • Auto-reconnect capability
        • Advanced thread management
        • Custom DNS configuration
        • Import/Export configuration

        Developed with ❤️ by Mohammad Hossein Soleymani (MHS)

        GitHub Repository: https://github.com/m9h4s/ssh-tunnel-pro-ultimate
        Personal Website: https://mhsoleymani.ir
        """

        about_text_widget.insert("1.0", about_text)

        # اضافه کردن تگ‌های لینک
        about_text_widget.tag_config("link", foreground="#3498db", underline=True)
        about_text_widget.tag_bind("link", "<Button-1>", self.open_link)
        about_text_widget.tag_bind("link", "<Enter>", lambda e: self.change_cursor("hand2"))
        about_text_widget.tag_bind("link", "<Leave>", lambda e: self.change_cursor(""))

        # پیدا کردن موقعیت لینک‌ها و اعمال تگ
        text_content = about_text_widget.get("1.0", "end")
        github_start = text_content.find("https://github.com/m9h4s/ssh-tunnel-pro-ultimate")
        github_end = github_start + len("https://github.com/m9h4s/ssh-tunnel-pro-ultimate")
        website_start = text_content.find("https://mhsoleymani.ir")
        website_end = website_start + len("https://mhsoleymani.ir")

        # اعمال تگ به لینک‌ها (محاسبه خطوط)
        if github_start != -1:
            about_text_widget.tag_add("link", f"1.0+{github_start}c", f"1.0+{github_end}c")
        if website_start != -1:
            about_text_widget.tag_add("link", f"1.0+{website_start}c", f"1.0+{website_end}c")

        # غیرفعال کردن ویرایش
        about_text_widget.configure(state="disabled")

    # ========== همچنین باید دو تابع جدید به کلاس اضافه کنید ==========
    def open_link(self, event):
        """باز کردن لینک در مرورگر"""
        try:
            # پیدا کردن متن زیر نشانگر ماوس
            index = event.widget.index(f"@{event.x},{event.y}")
            line_start = f"{index.split('.')[0]}.0"
            line_end = f"{int(index.split('.')[0]) + 1}.0"
            line_text = event.widget.get(line_start, line_end)
            
            # پیدا کردن لینک در خط
            import re
            urls = re.findall(r'https?://[^\s]+', line_text)
            
            if urls:
                import webbrowser
                webbrowser.open_new(urls[0])
        except Exception as e:
            logger.error(f"Error opening link: {e}")

    def change_cursor(self, cursor_type):
        """تغییر شکل نشانگر ماوس"""
        self.configure(cursor=cursor_type)
        self.update()


    def setup_logs(self):
        """Setup log display area."""
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        
        # Log header
        log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(
            log_header, 
            text="📋 Activity Log", 
            font=("Roboto", 14, "bold")
        ).pack(side="left")
        
        ctk.CTkButton(
            log_header,
            text="Clear",
            width=80,
            command=self.clear_logs,
            fg_color="#c0392b",
            hover_color="#e74c3c"
        ).pack(side="right")
        
        # Log text area
        self.log_box = ctk.CTkTextbox(
            self.log_frame, 
            font=("Consolas", 11), 
            height=120
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ================= CONFIG MANAGEMENT =================
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not os.path.exists(CONFIG_FILE):
            return DEFAULT_CONFIG.copy()
        
        try:
            with open(CONFIG_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                
            # Ensure all required keys exist
            if "settings" not in data:
                data["settings"] = DEFAULT_CONFIG["settings"].copy()
            if "dns_presets" not in data:
                data["dns_presets"] = DEFAULT_CONFIG["dns_presets"].copy()
            if "servers" not in data:
                data["servers"] = {}
            
            # Decrypt passwords
            for server_name, server_config in data.get("servers", {}).items():
                if "password" in server_config:
                    server_config["password"] = self.encryption_manager.decrypt(
                        server_config["password"]
                    )
            
            return data
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return DEFAULT_CONFIG.copy()

    def save_config(self):
        """Save configuration to file."""
        try:
            # Update settings
            settings = self.app_config["settings"]
            settings["local_port"] = self.ent_local_port.get()
            settings["auto_reconnect"] = self.var_auto_reconnect.get()
            settings["log_traffic"] = self.var_log_traffic.get()
            settings["connection_timeout"] = int(self.ent_timeout.get())
            settings["theme"] = self.var_theme.get()
            settings["wan_bonding_enabled"] = self.var_wan_bonding.get()
            settings["load_balancing_mode"] = self.var_lb_mode.get()
            settings["dns_optimization"] = self.var_dns_optimization.get()
            settings["reconnect_max_attempts"] = int(self.ent_max_attempts.get())
            settings["reconnect_initial_delay"] = int(self.ent_initial_delay.get())
            
            # Encrypt passwords before saving
            data_to_save = self.app_config.copy()
            data_to_save["servers"] = {}
            
            for server_name, server_config in self.app_config.get("servers", {}).items():
                server_copy = server_config.copy()
                if "password" in server_copy:
                    server_copy["password"] = self.encryption_manager.encrypt(
                        server_copy["password"]
                    )
                data_to_save["servers"][server_name] = server_copy
            
            with open(CONFIG_FILE, "w", encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)
            
            self.refresh_lists()
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    def export_config(self):
        """Export configuration to a file."""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if file_path:
                with open(file_path, "w", encoding='utf-8') as f:
                    json.dump(self.app_config, f, indent=4, ensure_ascii=False)
                
                self.log(f"Configuration exported to {file_path}")
                messagebox.showinfo("Success", "Configuration exported successfully!")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            messagebox.showerror("Error", f"Failed to export: {e}")

    def import_config(self):
        """Import configuration from a file."""
        try:
            file_path = filedialog.askopenfilename(
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if file_path:
                with open(file_path, "r", encoding='utf-8') as f:
                    imported_data = json.load(f)
                
                # Merge with existing config
                if "servers" in imported_data:
                    self.app_config["servers"].update(imported_data["servers"])
                if "dns_presets" in imported_data:
                    self.app_config["dns_presets"].update(imported_data["dns_presets"])
                if "settings" in imported_data:
                    self.app_config["settings"].update(imported_data["settings"])
                
                self.save_config()
                self.refresh_lists()
                self.update_settings_ui()
                
                self.log(f"Configuration imported from {file_path}")
                messagebox.showinfo("Success", "Configuration imported successfully!")
        except Exception as e:
            logger.error(f"Import failed: {e}")
            messagebox.showerror("Error", f"Failed to import: {e}")

    def update_settings_ui(self):
        """Update settings UI from config."""
        settings = self.app_config.get("settings", {})
        
        # Update UI elements
        self.ent_local_port.delete(0, "end")
        self.ent_local_port.insert(0, settings.get("local_port", "1080"))
        
        self.var_auto_reconnect.set(settings.get("auto_reconnect", True))
        self.var_log_traffic.set(settings.get("log_traffic", False))
        self.var_dns_optimization.set(settings.get("dns_optimization", True))
        
        self.ent_timeout.delete(0, "end")
        self.ent_timeout.insert(0, str(settings.get("connection_timeout", 10)))
        
        self.var_theme.set(settings.get("theme", "dark-blue"))
        self.var_wan_bonding.set(settings.get("wan_bonding_enabled", False))
        self.var_lb_mode.set(settings.get("load_balancing_mode", "round_robin"))
        
        self.ent_max_attempts.delete(0, "end")
        self.ent_max_attempts.insert(0, str(settings.get("reconnect_max_attempts", 5)))
        
        self.ent_initial_delay.delete(0, "end")
        self.ent_initial_delay.insert(0, str(settings.get("reconnect_initial_delay", 5)))
        
        self.var_auto_reset.set(settings.get("auto_reset_enabled", True))
        self.ent_reset_interval.delete(0, "end")
        self.ent_reset_interval.insert(0, str(settings.get("auto_reset_interval", 60)))

    def save_settings(self):
        """Save application settings."""
        self.save_config()
        self.log("Settings saved")

    def change_theme(self, theme: str):
        """Change application theme."""
        self.app_config["settings"]["theme"] = theme
        self.save_config()
        messagebox.showinfo(
            "Theme Changed", 
            "Theme will be applied on next restart."
        )

    # ================= UI INTERACTIONS =================
    def toggle_pass_visibility(self):
        """Toggle password visibility."""
        if self.show_password:
            self.ent_pass.configure(show="*")
            self.btn_toggle_pass.configure(text="👁️")
            self.show_password = False
        else:
            self.ent_pass.configure(show="")
            self.btn_toggle_pass.configure(text="🔒")
            self.show_password = True

    def browse_key_file(self):
        """Browse for SSH key file."""
        file_path = filedialog.askopenfilename(
            title="Select SSH Private Key",
            filetypes=[("All files", "*.*"), ("PEM files", "*.pem")]
        )
        
        if file_path:
            self.ent_key_file.delete(0, "end")
            self.ent_key_file.insert(0, file_path)

    def refresh_lists(self):
        """Refresh server and DNS lists in sidebar."""
        # Clear existing items
        for widget in self.scroll_servers.winfo_children():
            widget.destroy()
        for widget in self.scroll_dns.winfo_children():
            widget.destroy()
        
        # Add servers
        for name in sorted(self.app_config.get("servers", {}).keys()):
            btn = ctk.CTkButton(
                self.scroll_servers,
                text=f"🖥️ {name}",
                fg_color="transparent",
                border_width=2,
                border_color="#3498db",
                command=lambda n=name: self.load_server(n)
            )
            btn.pack(fill="x", pady=3, padx=5)
        
        # Add DNS presets
        for name in sorted(self.app_config.get("dns_presets", {}).keys()):
            btn = ctk.CTkButton(
                self.scroll_dns,
                text=f"🌐 {name}",
                fg_color="transparent",
                border_width=2,
                border_color="#2ecc71",
                command=lambda n=name: self.load_dns(n)
            )
            btn.pack(fill="x", pady=3, padx=5)
        
        # Update multi-hop server list
        if hasattr(self, 'menu_server1'):
            server_names = ["No servers"] + list(self.app_config.get("servers", {}).keys())
            self.menu_server1.configure(values=server_names)
            self.menu_server2.configure(values=server_names)

    def load_server(self, name: str):
        """Load server configuration into fields."""
        if name not in self.app_config["servers"]:
            return
        
        server = self.app_config["servers"][name]
        
        self.ent_server_name.delete(0, "end")
        self.ent_server_name.insert(0, name)
        
        self.ent_host.delete(0, "end")
        self.ent_host.insert(0, server.get("host", ""))
        
        self.ent_port.delete(0, "end")
        self.ent_port.insert(0, server.get("port", "22"))
        
        self.ent_user.delete(0, "end")
        self.ent_user.insert(0, server.get("username", "root"))
        
        self.ent_pass.delete(0, "end")
        self.ent_pass.insert(0, server.get("password", ""))
        
        self.ent_key_file.delete(0, "end")
        if "key_file" in server:
            self.ent_key_file.insert(0, server["key_file"])
        
        self.log(f"Loaded server configuration: {name}")

    def load_dns(self, name: str):
        """Load DNS preset into fields."""
        if name not in self.app_config["dns_presets"]:
            return
        
        dns = self.app_config["dns_presets"][name]
        
        self.ent_dns_name.delete(0, "end")
        self.ent_dns_name.insert(0, name)
        
        self.ent_dns_1.delete(0, "end")
        self.ent_dns_1.insert(0, dns.get("primary", ""))
        
        self.ent_dns_2.delete(0, "end")
        self.ent_dns_2.insert(0, dns.get("secondary", ""))
        
        self.log(f"Loaded DNS preset: {name}")

    def save_server(self):
        """Save current server configuration."""
        name = self.ent_server_name.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a server alias")
            return
        
        host = self.ent_host.get().strip()
        if not host:
            messagebox.showwarning("Warning", "Please enter a host")
            return
        
        server_config = {
            "host": host,
            "port": self.ent_port.get(),
            "username": self.ent_user.get(),
            "password": self.ent_pass.get()
        }
        
        key_file = self.ent_key_file.get().strip()
        if key_file:
            server_config["key_file"] = key_file
        
        self.app_config["servers"][name] = server_config
        self.save_config()
        self.log(f"Server '{name}' saved successfully")
        messagebox.showinfo("Success", f"Server '{name}' saved!")

    def save_dns(self):
        """Save current DNS preset."""
        name = self.ent_dns_name.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a DNS alias")
            return
        
        self.app_config["dns_presets"][name] = {
            "primary": self.ent_dns_1.get(),
            "secondary": self.ent_dns_2.get()
        }
        
        self.save_config()
        self.log(f"DNS preset '{name}' saved successfully")
        messagebox.showinfo("Success", f"DNS preset '{name}' saved!")

    def delete_item(self):
        """Delete selected server or DNS preset."""
        server_name = self.ent_server_name.get().strip()
        dns_name = self.ent_dns_name.get().strip()
        
        deleted = False
        
        if server_name and server_name in self.app_config["servers"]:
            if messagebox.askyesno("Confirm", f"Delete server '{server_name}'?"):
                del self.app_config["servers"][server_name]
                self.ent_server_name.delete(0, "end")
                deleted = True
                self.log(f"Deleted server: {server_name}")
        
        if dns_name and dns_name in self.app_config["dns_presets"]:
            if messagebox.askyesno("Confirm", f"Delete DNS preset '{dns_name}'?"):
                del self.app_config["dns_presets"][dns_name]
                self.ent_dns_name.delete(0, "end")
                deleted = True
                self.log(f"Deleted DNS preset: {dns_name}")
        
        if deleted:
            self.save_config()
        elif not server_name and not dns_name:
            messagebox.showinfo("Info", "No item selected")

    def clear_logs(self):
        """Clear log display."""
        self.log_box.delete("1.0", "end")
        self.log("Logs cleared")

    def log(self, msg: str):
        """Add message to log display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {msg}\n")
        self.log_box.see("end")
        logger.info(msg)

    # ================= MULTI-HOP MANAGEMENT =================

    def toggle_multihop(self):
        """Toggle multi-hop mode."""
        if self.var_multihop.get():
            self.log("Multi-hop mode enabled")
        else:
            self.log("Multi-hop mode disabled")
            self.servers_list = []

    def apply_multihop(self):
        """Apply multi-hop configuration."""
        server1_name = self.var_server1.get()
        server2_name = self.var_server2.get()
        
        if not self.var_multihop.get():
            messagebox.showwarning("Warning", "Enable multi-hop mode first")
            return
        
        if server1_name == "No servers" or server1_name not in self.app_config["servers"]:
            messagebox.showwarning("Warning", "Select valid first server")
            return
        
        self.servers_list = [self.app_config["servers"][server1_name].copy()]
        
        if server2_name != "No servers":
            if server2_name == "No servers" or server2_name not in self.app_config["servers"]:
                messagebox.showwarning("Warning", "Select valid second server")
                return
            self.servers_list.append(self.app_config["servers"][server2_name].copy())
        
        self.log(f"Multi-hop configured: {len(self.servers_list)} server(s)")
        messagebox.showinfo("Success", f"Multi-hop chain configured with {len(self.servers_list)} server(s)")

    # ================= NETWORK MANAGEMENT =================
    def scan_interfaces(self):
        """Scan and display network interfaces with selection checkboxes."""
        self.log("Scanning network interfaces...")
        
        # Clear existing interface widgets
        for widget in self.scroll_interfaces.winfo_children():
            widget.destroy()
        
        interfaces = self.iface_manager.scan_interfaces()
        
        if not interfaces:
            ctk.CTkLabel(
                self.scroll_interfaces,
                text="No network interfaces found",
                font=("Roboto", 12),
                text_color="gray"
            ).pack(pady=20)
            return
        
        self.log(f"Found {len(interfaces)} network interface(s)")
        
        # Store interface checkbox variables
        self.interface_vars = []
        
        for idx, iface in enumerate(interfaces):
            frame = ctk.CTkFrame(self.scroll_interfaces)
            frame.pack(fill="x", padx=10, pady=5)
            
            # Create checkbox variable
            var = tk.BooleanVar(value=iface.get('enabled', False))
            self.interface_vars.append((idx, var, iface))
            
            # Interface header with checkbox
            header = ctk.CTkFrame(frame, fg_color="transparent")
            header.pack(fill="x", padx=15, pady=(10, 5))
            
            # Checkbox for enabling this interface
            checkbox = ctk.CTkCheckBox(
                header,
                text="",
                variable=var,
                command=lambda i=idx, v=var: self.toggle_interface_selection(i, v),
                width=30
            )
            checkbox.pack(side="left", padx=(0, 10))
            
            # Interface name
            ctk.CTkLabel(
                header,
                text=f"🌐 {iface['name']}",
                font=("Roboto", 14, "bold")
            ).pack(side="left")
            
            # Interface type
            ctk.CTkLabel(
                header,
                text=f"[{iface['type']}]",
                font=("Roboto", 11),
                text_color="#3498db"
            ).pack(side="left", padx=10)
            
            # Details
            details = ctk.CTkFrame(frame, fg_color="transparent")
            details.pack(fill="x", padx=15, pady=(0, 10))
            
            info_text = f"IP: {iface['ip']} | Netmask: {iface['netmask']}"
            if iface['speed'] > 0:
                info_text += f" | Speed: {iface['speed']} Mbps"
            
            ctk.CTkLabel(
                details,
                text=info_text,
                font=("Consolas", 11),
                text_color="gray"
            ).pack(side="left")
        
        # Add "Select All" and "Deselect All" buttons
        button_frame = ctk.CTkFrame(self.scroll_interfaces, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=15)
        
        ctk.CTkButton(
            button_frame,
            text="✓ Select All",
            command=self.select_all_interfaces,
            width=120,
            height=30
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            button_frame,
            text="✗ Deselect All",
            command=self.deselect_all_interfaces,
            width=120,
            height=30,
            fg_color="gray",
            hover_color="darkgray"
        ).pack(side="left", padx=5)
        
        # Show selected count
        selected_count = sum(1 for _, var, _ in self.interface_vars if var.get())
        ctk.CTkLabel(
            button_frame,
            text=f"Selected: {selected_count}/{len(interfaces)} interfaces",
            font=("Roboto", 11, "bold"),
            text_color="#2ecc71" if selected_count > 0 else "gray"
        ).pack(side="left", padx=20)
    
    def toggle_interface_selection(self, idx, var):
        """Toggle interface selection for WAN bonding."""
        if idx < len(self.iface_manager.interfaces):
            self.iface_manager.interfaces[idx]['enabled'] = var.get()
            self.iface_manager.set_selected_interfaces(self.iface_manager.interfaces)
            
            selected_count = len(self.iface_manager.selected_interfaces)
            self.log(f"Selected {selected_count} interface(s) for WAN bonding")
            
            # Update the selected count display
            self.scan_interfaces()
    
    def select_all_interfaces(self):
        """Select all network interfaces."""
        for idx, var, iface in self.interface_vars:
            var.set(True)
            if idx < len(self.iface_manager.interfaces):
                self.iface_manager.interfaces[idx]['enabled'] = True
        
        self.iface_manager.set_selected_interfaces(self.iface_manager.interfaces)
        self.log(f"All {len(self.iface_manager.interfaces)} interfaces selected")
        self.scan_interfaces()
    
    def deselect_all_interfaces(self):
        """Deselect all network interfaces."""
        for idx, var, iface in self.interface_vars:
            var.set(False)
            if idx < len(self.iface_manager.interfaces):
                self.iface_manager.interfaces[idx]['enabled'] = False
        
        self.iface_manager.set_selected_interfaces(self.iface_manager.interfaces)
        self.log("All interfaces deselected")
        self.scan_interfaces()

    # ================= CONNECTION MANAGEMENT =================
    def toggle_connection(self):
        """Toggle SSH tunnel connection."""
        if self.proxy_thread and self.proxy_thread.is_alive():
            # Disconnect
            self.log("Disconnecting...")
            self.proxy_thread.stop()
            self.update_ui_state(False, None)
        else:
            # Connect
            self.save_config()
            
            # Determine if multi-hop or single connection
            if self.var_multihop.get() and self.servers_list:
                servers = self.servers_list
                self.log("Multi-hop mode enabled")
            else:
                # Single server connection
                config = {
                    "host": self.ent_host.get().strip(),
                    "port": self.ent_port.get().strip(),
                    "username": self.ent_user.get().strip(),
                    "password": self.ent_pass.get()
                }
                
                key_file = self.ent_key_file.get().strip()
                if key_file:
                    config["key_file"] = key_file
                
                servers = [config]
            
            # Validate
            if not servers or not servers[0].get("host"):
                messagebox.showerror("Error", "Host is required")
                return
            
            if not servers[0].get("password") and not servers[0].get("key_file"):
                messagebox.showerror("Error", "Password or SSH key is required")
                return
            
            try:
                # Scan interfaces if WAN bonding is enabled
                if self.app_config.get("settings", {}).get("wan_bonding_enabled"):
                    self.log("WAN bonding enabled, scanning interfaces...")
                    interfaces = self.iface_manager.scan_interfaces()
                    self.log(f"Using {len(interfaces)} network interface(s) for bonding")
                
                # Reset statistics
                self.traffic_stats.reset()
                self.traffic_stats.start()
                
                # Prepare configuration
                proxy_config = {
                    "local_port": self.ent_local_port.get().strip(),
                    "dns_primary": self.ent_dns_1.get().strip(),
                    "dns_secondary": self.ent_dns_2.get().strip(),
                    "auto_reconnect": self.app_config.get("settings", {}).get("auto_reconnect", True),
                    "connection_timeout": self.app_config.get("settings", {}).get("connection_timeout", 10),
                    "log_traffic": self.app_config.get("settings", {}).get("log_traffic", False),
                    "wan_bonding_enabled": self.app_config.get("settings", {}).get("wan_bonding_enabled", False),
                    "load_balancing_mode": self.app_config.get("settings", {}).get("load_balancing_mode", "round_robin"),
                    "max_threads": self.app_config.get("settings", {}).get("max_threads", 100),
                    "dns_test_rounds": self.app_config.get("settings", {}).get("dns_test_rounds", 3),
                    "dns_optimization": self.app_config.get("settings", {}).get("dns_optimization", True),
                    "reconnect_max_attempts": self.app_config.get("settings", {}).get("reconnect_max_attempts", 5),
                    "reconnect_initial_delay": self.app_config.get("settings", {}).get("reconnect_initial_delay", 5)
                }
                
                # Start proxy thread
                self.proxy_thread = AdvancedSOCKS5Proxy(
                    proxy_config,
                    self.log,
                    self.update_ui_state,
                    self.traffic_stats,
                    self.iface_manager,
                    servers,
                    self.connection_logger
                )
                self.proxy_thread.start()
                
                self.log("Initiating connection...")
                
            except Exception as e:
                logger.error(f"Failed to start connection: {e}")
                messagebox.showerror("Error", f"Failed to start connection: {e}")

    def update_ui_state(self, connected: bool, ssh_client: Optional[paramiko.SSHClient]):
        """Update UI based on connection state."""
        self.ssh_active_client = ssh_client
        
        if connected:
            # Connected state
            self.status_light.configure(fg_color="#2ecc71")
            self.lbl_status.configure(text="Connected ✓")
            self.btn_connect.configure(
                text="🔌 DISCONNECT",
                fg_color="#c0392b",
                hover_color="#e74c3c"
            )
            self.ent_local_port.configure(state="disabled")
            
            # Start ping monitoring
            self.ping_thread_running = True
            threading.Thread(target=self.ping_loop, daemon=True).start()
            
            # Start statistics updates
            self.stats_update_running = True
            threading.Thread(target=self.update_statistics_loop, daemon=True).start()
            
            # Start auto-reset if enabled
            if self.app_config.get("settings", {}).get("auto_reset_enabled", True):
                self.start_auto_reset()
            
            # Start health monitoring
            if self.proxy_thread:
                self.proxy_thread.health_monitor.start()
            
            # Update IP info
            self.update_ip_info()
            
            self.log("✓ Connection established successfully!")
        else:
            # Disconnected state
            self.status_light.configure(fg_color="#e74c3c")
            self.lbl_status.configure(text="Disconnected ✗")
            self.btn_connect.configure(
                text="🔌 CONNECT",
                fg_color="#27ae60",
                hover_color="#2ecc71"
            )
            self.lbl_ping.configure(text="Latency: -- ms")
            self.ent_local_port.configure(state="normal")
            
            # Stop monitoring threads
            self.ping_thread_running = False
            self.stats_update_running = False
            self.auto_reset_thread_running = False
            
            # Stop traffic stats
            self.traffic_stats.stop()
            
            # Stop health monitoring
            if self.proxy_thread:
                self.proxy_thread.health_monitor.stop()

    def ping_loop(self):
        """Monitor connection latency."""
        host = self.ent_host.get().strip()
        
        while self.ping_thread_running:
            try:
                # Platform-specific ping command
                param = '-n' if platform.system().lower() == 'windows' else '-c'
                
                # Execute ping
                result = subprocess.run(
                    ['ping', param, '1', host],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                
                if result.returncode == 0:
                    # Parse latency
                    output = result.stdout.decode()
                    if 'time=' in output:
                        try:
                            time_str = output.split('time=')[1].split()[0]
                            latency = float(time_str.replace('ms', ''))
                            self.lbl_ping.configure(text=f"Latency: {latency:.1f} ms")
                        except:
                            self.lbl_ping.configure(text="Latency: OK")
                    else:
                        self.lbl_ping.configure(text="Latency: OK")
                else:
                    self.lbl_ping.configure(text="Latency: Timeout")
                    
            except Exception as e:
                logger.debug(f"Ping error: {e}")
                self.lbl_ping.configure(text="Latency: Error")
            
            time.sleep(5)

    # ================= STATISTICS =================
    def update_statistics_loop(self):
        """Update statistics display periodically."""
        while self.stats_update_running:
            try:
                stats = self.traffic_stats.get_stats()
                
                # Format bytes
                bytes_sent = TrafficStats.format_bytes(stats["bytes_sent"])
                bytes_received = TrafficStats.format_bytes(stats["bytes_received"])
                total = TrafficStats.format_bytes(stats["bytes_sent"] + stats["bytes_received"])
                
                # Format speeds
                upload_speed = TrafficStats.format_bytes(stats["upload_speed"])
                download_speed = TrafficStats.format_bytes(stats["download_speed"])
                
                # Update labels
                self.lbl_bytes_sent.configure(text=f"Uploaded: {bytes_sent}")
                self.lbl_bytes_received.configure(text=f"Downloaded: {bytes_received}")
                self.lbl_upload_speed.configure(text=f"Upload Speed: {upload_speed}/s")
                self.lbl_download_speed.configure(text=f"Download Speed: {download_speed}/s")
                self.lbl_total_transfer.configure(text=f"Total: {total}")
                
                self.lbl_active_conn.configure(text=f"Active: {stats['connections_active']}")
                self.lbl_total_conn.configure(text=f"Total: {stats['connections_total']}")
                self.lbl_failed_conn.configure(text=f"Failed: {stats['failed_connections']}")
                
                # Connection rate
                if stats["uptime"] > 0:
                    rate = (stats["connections_total"] / stats["uptime"]) * 60
                    self.lbl_conn_rate.configure(text=f"Rate: {rate:.1f}/min")
                
                # Uptime
                uptime = self.format_uptime(stats["uptime"])
                self.lbl_uptime.configure(text=f"Uptime: {uptime}")
                
                # Average speed
                if stats["uptime"] > 0:
                    avg_speed = (stats["bytes_sent"] + stats["bytes_received"]) / stats["uptime"]
                    self.lbl_avg_speed.configure(text=f"Avg Speed: {TrafficStats.format_bytes(avg_speed)}/s")
                
            except Exception as e:
                logger.error(f"Statistics update error: {e}")
            
            time.sleep(1)

    def reset_statistics(self):
        """Reset traffic statistics."""
        if messagebox.askyesno("Confirm", "Reset all statistics?"):
            self.traffic_stats.reset()
            self.log("Statistics reset")

    # ================= CONNECTIONS DISPLAY =================
    def update_connections_display(self):
        """Update recent connections display."""
        connections = self.connection_logger.get_connections()
        
        self.connections_text.configure(state="normal")
        self.connections_text.delete("1.0", "end")
        
        if not connections:
            self.connections_text.insert("end", "No connections yet...\n")
        else:
            # Header
            header = f"{'Time':<20} {'Client':<25} {'Destination':<40}\n"
            separator = "-" * 85 + "\n"
            self.connections_text.insert("end", header)
            self.connections_text.insert("end", separator)
            
            # Connections (newest first)
            for conn in reversed(connections):
                line = f"{conn['time']:<20} {conn['client'][:24]:<25} {conn['destination'][:39]:<40}\n"
                self.connections_text.insert("end", line)
        
        self.connections_text.configure(state="disabled")
        self.connections_text.see("1.0")

    def clear_connections_history(self):
        """Clear connections history."""
        if messagebox.askyesno("Confirm", "Clear all connection history?"):
            self.connection_logger.clear()
            self.update_connections_display()
            self.log("Connection history cleared")

    def toggle_auto_refresh(self):
        """Toggle auto-refresh for connections display."""
        if self.var_auto_refresh.get():
            self.start_auto_refresh()
        else:
            self.auto_refresh_running = False

    def start_auto_refresh(self):
        """Start auto-refresh for connections display."""
        if not self.auto_refresh_running:
            self.auto_refresh_running = True
            threading.Thread(target=self.auto_refresh_loop, daemon=True).start()

    def auto_refresh_loop(self):
        """Auto-refresh loop for connections display."""
        while self.auto_refresh_running:
            try:
                if self.var_auto_refresh.get():
                    self.update_connections_display()
                time.sleep(5)
            except Exception as e:
                logger.error(f"Auto-refresh error: {e}")
                time.sleep(5)

    # ================= DNS OPTIMIZER =================
    def start_dns_test(self):
        """Start DNS testing in a separate thread."""
        def _test():
            try:
                domain = self.ent_dns_test_domain.get().strip()
                if not domain:
                    domain = "google.com"
                
                rounds = self.ent_dns_test_rounds.get().strip()
                try:
                    test_rounds = int(rounds)
                except:
                    test_rounds = 3
                
                self.dns_tester.target_host = domain
                self.dns_tester.test_rounds = test_rounds
                
                result = self.dns_tester.find_best_dns()
                self.dns_test_results = result
                
                # Update display
                self.dns_results_text.configure(state="normal")
                self.dns_results_text.delete("1.0", "end")
                
                if result["ip"]:
                    # Show best result
                    best_text = f"✓ BEST DNS: {result['name']}\n"
                    best_text += f"  IP Address: {result['ip']}\n"
                    best_text += f"  Average Response Time: {result['avg_time']:.2f} ms\n\n"
                    
                    self.dns_results_text.insert("end", best_text)
                    self.dns_results_text.insert("end", "All Test Results:\n")
                    self.dns_results_text.insert("end", "-" * 60 + "\n")
                    
                    # Show all results
                    for name, dns_result in result.get("all_results", {}).items():
                        line = f"{name:<25} {dns_result['ip']:<15} {dns_result['avg_time']:>6.2f} ms ({dns_result['success_rate']:.0f}%)\n"
                        self.dns_results_text.insert("end", line)
                    
                    # Enable apply button
                    self.btn_apply_dns.configure(state="normal")
                else:
                    self.dns_results_text.insert("end", "❌ No DNS servers responded to tests\n")
                    self.btn_apply_dns.configure(state="disabled")
                
                self.dns_results_text.configure(state="disabled")
                self.dns_results_text.see("1.0")
                
                self.log(f"DNS test completed. Best: {result.get('name', 'None')}")
                
            except Exception as e:
                logger.error(f"DNS test error: {e}")
                self.log(f"DNS test failed: {e}")
        
        # Run in thread to avoid blocking UI
        threading.Thread(target=_test, daemon=True).start()
        self.log("Starting DNS test...")

    def apply_best_dns(self):
        """Apply the best DNS to configuration."""
        if self.dns_test_results and self.dns_test_results.get("ip"):
            best_name = self.dns_test_results["name"]
            best_ip = self.dns_test_results["ip"]
            
            # Update DNS fields
            self.ent_dns_name.delete(0, "end")
            self.ent_dns_name.insert(0, f"Best_{best_name}")
            
            self.ent_dns_1.delete(0, "end")
            self.ent_dns_1.insert(0, best_ip)
            
            # Save as preset
            self.save_dns()
            
            self.log(f"Applied best DNS: {best_name} ({best_ip})")
            messagebox.showinfo("Success", f"Best DNS applied: {best_name} ({best_ip})")
        else:
            messagebox.showwarning("Warning", "No DNS test results available")

    # ================= THREAD MANAGEMENT =================
    def update_thread_count_loop(self):
        """Update thread count display periodically."""
        while True:
            try:
                if self.proxy_thread and self.proxy_thread.is_alive():
                    count = self.proxy_thread.get_thread_count()
                    self.lbl_thread_count.configure(text=f"Active Threads: {count}")
                else:
                    self.lbl_thread_count.configure(text="Active Threads: 0")
            except Exception as e:
                logger.debug(f"Thread count update error: {e}")
            
            time.sleep(0.5)
    
    def manual_thread_reset(self):
        """Manually reset all threads and connections."""
        if self.proxy_thread and self.proxy_thread.is_alive():
            if messagebox.askyesno("Confirm Reset", "This will reset all active connections and threads.\n\nContinue?"):
                self.log("Performing manual thread reset...")
                try:
                    self.proxy_thread.reset_connections()
                    self.log("✓ Thread reset completed successfully")
                    messagebox.showinfo("Success", "Threads and connections reset successfully!")
                except Exception as e:
                    logger.error(f"Thread reset failed: {e}")
                    self.log(f"✗ Thread reset failed: {e}")
                    messagebox.showerror("Error", f"Reset failed: {e}")
        else:
            messagebox.showwarning("Warning", "No active connection to reset")
    
    def toggle_auto_reset(self):
        """Toggle automatic thread reset."""
        enabled = self.var_auto_reset.get()
        self.app_config["settings"]["auto_reset_enabled"] = enabled
        self.save_config()
        
        if enabled and self.proxy_thread and self.proxy_thread.is_alive():
            self.start_auto_reset()
            self.log("Auto thread reset enabled")
        else:
            self.auto_reset_thread_running = False
            self.log("Auto thread reset disabled")
    
    def start_auto_reset(self):
        """Start automatic thread reset loop."""
        if not self.auto_reset_thread_running:
            self.auto_reset_thread_running = True
            threading.Thread(target=self.auto_reset_loop, daemon=True).start()
    
    def auto_reset_loop(self):
        """Automatic thread reset loop."""
        while self.auto_reset_thread_running:
            try:
                interval = int(self.ent_reset_interval.get() or 60)
                
                # Countdown
                for remaining in range(interval, 0, -1):
                    if not self.auto_reset_thread_running:
                        break
                    
                    self.lbl_next_reset.configure(text=f"Next reset: {remaining}s")
                    time.sleep(1)
                
                # Perform reset
                if self.auto_reset_thread_running and self.proxy_thread and self.proxy_thread.is_alive():
                    self.log("Auto thread reset triggered...")
                    self.proxy_thread.reset_connections()
                    self.log("✓ Auto thread reset completed")
                    self.lbl_next_reset.configure(text="Next reset: Completed")
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Auto reset error: {e}")
                time.sleep(5)
    
    def apply_reset_interval(self):
        """Apply new reset interval."""
        try:
            interval = int(self.ent_reset_interval.get())
            if interval < 10:
                messagebox.showwarning("Warning", "Interval should be at least 10 seconds")
                return
            
            self.app_config["settings"]["auto_reset_interval"] = interval
            self.save_config()
            messagebox.showinfo("Success", f"Reset interval set to {interval} seconds")
            self.log(f"Auto reset interval updated to {interval}s")
        except ValueError:
            messagebox.showerror("Error", "Invalid interval value")

    @staticmethod
    def format_uptime(seconds: float) -> str:
        """Format uptime in HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ================= NETWORK MONITORING =================
    def update_ip_info(self):
        """Fetch and display public IP information."""
        def _fetch():
            try:
                # First try without proxy
                try:
                    response = requests.get("http://ip-api.com/json", timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        self.lbl_ip.configure(text=f"Public IP: {data.get('query', 'N/A')}")
                        self.lbl_isp.configure(text=f"ISP: {data.get('isp', 'N/A')}")
                        location = f"{data.get('city', '')}, {data.get('regionName', '')}, {data.get('country', '')}"
                        self.lbl_loc.configure(text=f"Location: {location}")
                        self.log(f"✓ IP Info updated: {data.get('query')} ({data.get('country')})")
                        return
                except Exception as e:
                    logger.debug(f"Direct IP fetch failed: {e}")
                
                # If proxy is active, try with proxy
                if self.ssh_active_client:
                    try:
                        import socks
                        import socket
                        
                        # Set up SOCKS5 proxy
                        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", int(self.ent_local_port.get()))
                        socket.socket = socks.socksocket
                        
                        response = requests.get("http://ip-api.com/json", timeout=15)
                        if response.status_code == 200:
                            data = response.json()
                            self.lbl_ip.configure(text=f"Public IP (via proxy): {data.get('query', 'N/A')}")
                            self.lbl_isp.configure(text=f"ISP: {data.get('isp', 'N/A')}")
                            location = f"{data.get('city', '')}, {data.get('regionName', '')}, {data.get('country', '')}"
                            self.lbl_loc.configure(text=f"Location: {location}")
                            self.log(f"✓ IP Info via proxy: {data.get('query')}")
                    except Exception as e:
                        logger.error(f"Proxy IP fetch error: {e}")
                        self.lbl_ip.configure(text="Public IP: Could not fetch")
                        self.lbl_isp.configure(text="ISP: --")
                        self.lbl_loc.configure(text="Location: --")
                
            except Exception as e:
                logger.error(f"IP info fetch error: {e}")
                self.lbl_ip.configure(text="Public IP: Error")
                self.lbl_isp.configure(text="ISP: --")
                self.lbl_loc.configure(text="Location: --")
        
        threading.Thread(target=_fetch, daemon=True).start()

    # ================= CLEANUP =================
    def on_closing(self):
        """Handle application closing."""
        # توقف thread به‌روزرسانی وضعیت DNS
        self.dns_status_update_running = False
        
        if self.proxy_thread and self.proxy_thread.is_alive():
            if messagebox.askyesno("Confirm Exit", "Connection is active. Disconnect and exit?"):
                self.proxy_thread.stop()
                time.sleep(1)  # Give time to stop
                self.destroy()
        else:
            self.destroy()

# ================= MAIN ENTRY POINT =================
def main():
    """Main application entry point."""
    # بررسی وجود فایل‌های آیکون
    icon_files = ["logo.ico", "logo.png"]
    missing_icons = []
    
    for icon_file in icon_files:
        if not os.path.exists(icon_file):
            missing_icons.append(icon_file)
    
    if missing_icons:
        logger.warning(f"Missing icon files: {missing_icons}")
        print(f"⚠️ Note: Icon files missing: {missing_icons}")
        print("   Please ensure logo.ico and/or logo.png are in the same directory.")

    try:
        app = TunnelProApp()
        app.mainloop()
    except Exception as e:
        logger.critical(f"Application crash: {e}", exc_info=True)
        messagebox.showerror("Critical Error", f"Application crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
