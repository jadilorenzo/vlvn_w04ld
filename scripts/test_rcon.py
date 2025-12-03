#!/usr/bin/env python3
"""Test RCON connection to diagnose issues"""

import threading
import json
import sys
from mcrcon import MCRcon

# Load config
config_path = "config/mole_hunt_config.json"
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    sys.exit(1)

rcon_config = config.get("rcon", {})
host = rcon_config.get("host", "localhost")
port = rcon_config.get("port", 25575)
password = rcon_config.get("password", "")

print(f"Testing RCON connection to {host}:{port}")

# Test 1: Simple connection
print("\n=== Test 1: Simple connection ===")
try:
    rcon = MCRcon(host, password, port=port)
    rcon.connect()
    print("✓ Connection successful")

    response = rcon.command("list")
    print(f"✓ 'list' command response: {repr(response)}")

    rcon.disconnect()
    print("✓ Disconnected successfully")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Multiple commands (simulating thread usage)
print("\n=== Test 2: Multiple commands (fresh connection each time) ===")
for i in range(3):
    try:
        print(f"\nAttempt {i+1}:")
        rcon = MCRcon(host, password, port=port)
        rcon.connect()
        print(f"  ✓ Connected")

        response = rcon.command("list")
        print(f"  ✓ 'list' response: {repr(response)}")

        rcon.disconnect()
        print(f"  ✓ Disconnected")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()

# Test 3: Test from a thread
print("\n=== Test 3: Testing from a thread ===")


def test_in_thread():
    try:
        print("  Thread: Creating connection...")
        rcon = MCRcon(host, password, port=port)
        rcon.connect()
        print("  Thread: ✓ Connected")

        response = rcon.command("list")
        print(f"  Thread: ✓ 'list' response: {repr(response)}")

        rcon.disconnect()
        print("  Thread: ✓ Disconnected")
    except Exception as e:
        print(f"  Thread: ✗ Error: {e}")
        import traceback
        traceback.print_exc()


thread = threading.Thread(target=test_in_thread)
thread.start()
thread.join()

print("\n=== Test Complete ===")
