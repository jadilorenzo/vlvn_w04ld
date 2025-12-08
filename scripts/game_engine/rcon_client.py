"""
RCON client for communicating with Minecraft server
"""

import json
import logging
import subprocess
import sys
import threading
from typing import List, Optional

try:
    from mcrcon import MCRcon, MCRconException
except ImportError:
    print("ERROR: mcrcon not installed. Run: pip install -r requirements.txt")
    exit(1)


class RCONClient:
    """Handles RCON communication with Minecraft server"""

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.logger = logging.getLogger(__name__)

        # Queue for RCON commands from threads
        self.command_queue = None
        self.worker_thread = None
        self.worker_running = False
        self._init_worker()

    def _init_worker(self):
        """Initialize worker thread that manages a persistent subprocess for RCON commands"""
        import queue
        import concurrent.futures

        # If worker already exists, do nothing
        if getattr(self, "worker_thread", None) and self.worker_thread.is_alive():
            return

        # Queues and state
        self.command_queue = queue.Queue()
        # We'll store (command: str, future: Future) tuples in the queue
        self.worker_running = True

        def worker():
            """Worker thread that manages a persistent subprocess for RCON commands"""
            # Create a persistent subprocess that runs MCRcon in the main thread
            # This subprocess reads commands from stdin and writes responses to stdout
            worker_script = f"""
import sys
import json
from mcrcon import MCRcon

host = {repr(self.host)}
password = {repr(self.password)}
port = {self.port}

# Connect once
rcon = MCRcon(host, password, port=port)
rcon.connect()

# Read commands from stdin, execute, write to stdout
try:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "__EXIT__":
            break
        try:
            response = rcon.command(line)
            # Send response as JSON to handle newlines properly
            print(json.dumps({{"status": "ok", "response": response}}), flush=True)
        except Exception as e:
            print(json.dumps({{"status": "error", "error": str(e)}}), flush=True)
finally:
    try:
        rcon.disconnect()
    except:
        pass
"""
            proc = None
            try:
                proc = subprocess.Popen(
                    [sys.executable, '-c', worker_script],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                self.logger.info(
                    f"RCON worker subprocess started for {self.host}:{self.port}")

                while self.worker_running:
                    try:
                        try:
                            command, future = self.command_queue.get(
                                timeout=0.1)
                        except queue.Empty:
                            # Check if subprocess is still alive
                            if proc and proc.poll() is not None:
                                # Subprocess died, try to restart
                                self.logger.warning(
                                    "RCON subprocess died, restarting...")
                                try:
                                    proc.terminate()
                                    proc.wait(timeout=1)
                                except:
                                    pass
                                proc = subprocess.Popen(
                                    [sys.executable, '-c', worker_script],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                                    bufsize=1
                                )
                                self.logger.info(
                                    "RCON worker subprocess restarted")
                            continue

                        # Sentinel to stop worker
                        if command is None:
                            if proc:
                                try:
                                    proc.stdin.write("__EXIT__\n")
                                    proc.stdin.flush()
                                    proc.wait(timeout=2)
                                except:
                                    try:
                                        proc.terminate()
                                        proc.wait(timeout=1)
                                    except:
                                        pass
                            if not future.done():
                                future.set_result(None)
                            break

                        if proc is None or proc.poll() is not None:
                            if not future.done():
                                future.set_exception(RuntimeError(
                                    "RCON subprocess unavailable"))
                            continue

                        # Send command to subprocess
                        try:
                            proc.stdin.write(command + "\n")
                            proc.stdin.flush()
                        except Exception as e:
                            self.logger.error(
                                f"Error sending command to subprocess: {e}")
                            if not future.done():
                                future.set_exception(RuntimeError(
                                    f"Failed to send command: {e}"))
                            continue

                        # Read response from subprocess
                        try:
                            response_line = proc.stdout.readline()
                            if not response_line:
                                raise RuntimeError("Subprocess closed stdout")
                            result = json.loads(response_line.strip())
                            if result.get("status") == "ok":
                                response = result.get("response", "")
                                self.logger.debug(
                                    f"RCON CMD: {command} -> {repr(response)}")
                                if not future.done():
                                    future.set_result(response)
                            else:
                                error = result.get("error", "Unknown error")
                                self.logger.error(
                                    f"RCON command error: {error}")
                                if not future.done():
                                    future.set_exception(
                                        RuntimeError(f"RCON error: {error}"))
                        except json.JSONDecodeError as e:
                            self.logger.error(
                                f"Failed to parse subprocess response: {e}")
                            if not future.done():
                                future.set_exception(RuntimeError(
                                    f"Invalid response format: {e}"))
                        except Exception as e:
                            self.logger.error(
                                f"Error reading from subprocess: {e}")
                            if not future.done():
                                future.set_exception(RuntimeError(
                                    f"Failed to read response: {e}"))

                    except Exception as e:
                        self.logger.error(
                            f"RCON worker loop error: {e}", exc_info=True)

            finally:
                if proc:
                    try:
                        proc.stdin.write("__EXIT__\n")
                        proc.stdin.flush()
                        proc.wait(timeout=2)
                    except:
                        try:
                            proc.terminate()
                            proc.wait(timeout=1)
                        except:
                            pass
                self.logger.info("RCON worker thread exiting")

        self.worker_thread = threading.Thread(target=worker, daemon=False)
        self.worker_thread.start()

    def connect(self) -> bool:
        """Test RCON connectivity by executing a simple command via the worker."""
        # Ensure worker is running
        self._init_worker()
        try:
            # 'list' is a safe test command
            response = self.execute("list")
            if response is not None:
                self.logger.info(
                    f"Connected to RCON at {self.host}:{self.port}")
                return True
            else:
                self.logger.error("RCON 'list' command returned no response")
                return False
        except Exception as e:
            self.logger.error(f"Failed to connect to RCON: {e}")
            return False

    def disconnect(self):
        """Disconnect from RCON server and stop worker thread"""
        try:
            self.worker_running = False
            if getattr(self, "command_queue", None) is not None:
                import concurrent.futures
                sentinel_future: "concurrent.futures.Future[Optional[str]]" = concurrent.futures.Future(
                )
                # Send sentinel (None, future) to make worker exit cleanly
                self.command_queue.put((None, sentinel_future))
        except Exception:
            pass

    def execute(self, command: str, retry: bool = True) -> Optional[str]:
        """Execute a command via a single RCON worker thread with automatic reconnection.

        All threads enqueue commands into a queue; the worker thread owns the MCRcon connection.
        """
        import concurrent.futures

        # Ensure worker exists
        if not getattr(self, "worker_thread", None) or not self.worker_thread.is_alive():
            self._init_worker()

        future: "concurrent.futures.Future[Optional[str]]" = concurrent.futures.Future(
        )
        # Put (command, future) into the queue; worker will fill the future
        self.command_queue.put((command, future))

        try:
            # Timeout to avoid hanging forever on a bad connection
            response = future.result(timeout=5.0)
            return response
        except concurrent.futures.TimeoutError:
            self.logger.error(f"RCON command timed out: {command}")
            return None
        except Exception as e:
            self.logger.error(f"RCON command failed: {command} ({e})")
            return None

    def get_online_players(self) -> List[str]:
        """Get list of online players"""
        response = self.execute("list")

        if not response:
            self.logger.warning("'list' command returned no response")
            return []

        # Parse "There are X of a max of Y players online: player1, player2,
        # ..."
        try:
            if ":" in response:
                players_str = response.split(":")[1].strip()
                if players_str:
                    # Split by comma and clean up each player name
                    # Remove newlines, extra whitespace, and any trailing text
                    players = []
                    for p in players_str.split(","):
                        # Strip whitespace and newlines
                        player_name = p.strip().replace("\n", " ").strip()
                        # Remove any trailing text that looks like part of the server message
                        # (e.g., "There are X of a max of Y players online")
                        if "There are" in player_name:
                            player_name = player_name.split("There are")[
                                0].strip()
                        if player_name:
                            players.append(player_name)

                    return players
            else:
                self.logger.warning(
                    f"Unexpected 'list' response format: {response}")
        except Exception as e:
            self.logger.error(
                f"Error parsing 'list' response: {e}, response: {repr(response)}")

        self.logger.warning(
            f"Failed to parse online players from response: {repr(response)}")
        return []

