#!/usr/bin/env python3
"""
Main entry point for Mole Hunt game
"""

import argparse
import sys
import time
from pathlib import Path

try:
    from mcrcon import MCRconException
except ImportError:
    print("ERROR: mcrcon not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

from game_engine.game_status import GameStatus
from .game_state import MoleHuntGameState
from .role import Role


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Mole Hunt Game Manager")
    parser.add_argument(
        "--config",
        default="config/mole_hunt_config.json",
        help="Path to config file")
    parser.add_argument("--start", action="store_true",
                        help="Start a new game")
    parser.add_argument("--stop", action="store_true",
                        help="Stop current game")
    parser.add_argument("--status", action="store_true",
                        help="Check game status")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: assign specific role to a player")
    parser.add_argument("--test-player", type=str,
                        help="Player username for test mode")
    parser.add_argument(
        "--test-role",
        type=str,
        choices=[
            "traitor",
            "innocent"],
        help="Role to assign in test mode (traitor or innocent)")
    parser.add_argument(
        "--spawn-simulated-player",
        action="store_true",
        help="Spawn a simulated player entity for testing (test mode only)")

    args = parser.parse_args()

    # Resolve config path relative to script directory
    script_dir = Path(__file__).parent.parent.parent.parent
    config_path = script_dir / args.config

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return

    game = MoleHuntGameState(str(config_path))

    if args.start:
        test_mode = args.test
        test_player = args.test_player
        test_role = None
        if args.test_role:
            test_role = Role.TRAITOR if args.test_role == "traitor" else Role.INNOCENT

        if test_mode and not test_player:
            print("ERROR: --test-player required when using --test mode")
            return

        if test_mode and not test_role:
            print("ERROR: --test-role required when using --test mode")
            print("Use: --test-role traitor or --test-role innocent")
            return

        spawn_simulated = args.spawn_simulated_player if test_mode else False
        if game.start_game(
                test_mode=test_mode,
                test_player=test_player,
                test_role=test_role,
                spawn_simulated_player=spawn_simulated):
            mode_str = f" (TEST MODE: {test_player} as {test_role.value})" if test_mode else ""
            if spawn_simulated:
                mode_str += " [Simulated Player Spawned]"
            print(f"Game started successfully!{mode_str}")
            # Keep script running to maintain monitoring
            try:
                while game.status == GameStatus.IN_PROGRESS:
                    try:
                        time.sleep(1)
                    except MCRconException:
                        # Ignore timeout errors during sleep - connection will be
                        # re-established when needed
                        pass
            except KeyboardInterrupt:
                print("\nStopping game...")
                game.stop_game()

            # Wait for threads to finish before exiting
            if getattr(game, "monitor_thread", None):
                game.monitor_thread.join()

            if getattr(game, "cleanup_thread", None):
                game.cleanup_thread.join()
        else:
            print("Failed to start game")
    elif args.stop:
        game.stop_game()
        print("Game stopped")
    elif args.status:
        print(f"Game status: {game.status.value}")
        if game.status == GameStatus.IN_PROGRESS:
            remaining = game.timer_manager.get_remaining_minutes()
            print(f"Time remaining: {remaining} minutes")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

