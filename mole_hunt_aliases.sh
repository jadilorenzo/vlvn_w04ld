#!/bin/bash
# Mole Hunt Game Aliases
# Source this file to add convenient aliases: source mole_hunt_aliases.sh
# Works from any directory - finds the server root automatically

# Find the server root directory (where this file is located)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="config/mole_hunt_config.json"

# Unalias any existing versions to avoid conflicts
unalias molehunt-start 2>/dev/null
unalias molehunt-stop 2>/dev/null
unalias molehunt-status 2>/dev/null

# Regular game commands (using modular version)
# Note: The script resolves config relative to the root directory
alias molehunt-start="cd $SCRIPT_DIR/scripts && python3 -m games.mole_hunt.main --start --config $CONFIG_PATH"
alias molehunt-stop="cd $SCRIPT_DIR/scripts && python3 -m games.mole_hunt.main --stop --config $CONFIG_PATH"
alias molehunt-status="cd $SCRIPT_DIR/scripts && python3 -m games.mole_hunt.main --status --config $CONFIG_PATH"

# Test mode commands (requires player name and role)
# Usage: molehunt-test <playername> <traitor|innocent> [--spawn-simulated-player]
# Note: If testing as traitor with only 1 player, simulated player is automatically spawned
molehunt-test() {
    if [ $# -lt 2 ]; then
        echo "Usage: molehunt-test <playername> <traitor|innocent> [--spawn-simulated-player]"
        echo "Example: molehunt-test VLVND1L0 traitor"
        echo "Example: molehunt-test VLVND1L0 innocent --spawn-simulated-player"
        return 1
    fi
    
    local player="$1"
    local role="$2"
    local extra_args="${@:3}"
    
    if [ "$role" != "traitor" ] && [ "$role" != "innocent" ]; then
        echo "Error: Role must be 'traitor' or 'innocent'"
        return 1
    fi
    
    # Automatically add --spawn-simulated-player for traitor role (unless explicitly disabled)
    local spawn_flag=""
    if [ "$role" = "traitor" ]; then
        # Check if --no-simulated-player is in extra_args
        case " $extra_args " in
            *" --no-simulated-player "*)
                # Flag is present, don't add spawn flag
                ;;
            *)
                # Flag not present, add spawn flag
                spawn_flag="--spawn-simulated-player"
                ;;
        esac
    fi
    
    cd "$SCRIPT_DIR/scripts" && python3 -m games.mole_hunt.main --start --test --test-player "$player" --test-role "$role" $spawn_flag $extra_args --config "$CONFIG_PATH"
}

echo "Mole Hunt aliases loaded!"
echo "  molehunt-start              - Start a regular game"
echo "  molehunt-stop               - Stop current game"
echo "  molehunt-status             - Check game status"
echo "  molehunt-test <player> <role> [--spawn-simulated] - Start test mode"
echo ""
echo "Example: molehunt-test VLVND1L0 traitor"

