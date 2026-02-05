#!/bin/bash
# =============================================================================
# reset_tidal_credentials.sh
# =============================================================================
# Purpose: Reset Tidal credentials to force re-authentication
#
# What this script does:
#   1. Stops the Mopidy service (if running)
#   2. Removes the Tidal OAuth token file
#   3. Optionally clears the Tidal cache (image/track cache)
#   4. Prompts you to restart Mopidy and re-authenticate
#
# Tidal credential locations:
#   - OAuth token:  ~/.local/share/mopidy/tidal/tidal-oauth.json
#   - Cache:        ~/.cache/mopidy/tidal/
#
# After running this script:
#   1. Start mopidy: sudo systemctl start mopidy  (or run 'mopidy' manually)
#   2. Check logs:   journalctl -u mopidy -f
#   3. Look for the Tidal authentication URL in the logs
#   4. Visit the URL in a browser to complete OAuth login
#   5. The new credentials will be saved automatically
#
# Usage:
#   ./reset_tidal_credentials.sh           # Remove OAuth only
#   ./reset_tidal_credentials.sh --cache   # Remove OAuth and all caches
#
# =============================================================================

set -e

OAUTH_FILE="$HOME/.local/share/mopidy/tidal/tidal-oauth.json"
CACHE_DIR="$HOME/.cache/mopidy/tidal"

echo "=== Tidal Credential Reset ==="
echo ""

# Check if mopidy service is running and stop it
if systemctl is-active --quiet mopidy 2>/dev/null; then
    echo "Stopping mopidy service..."
    sudo systemctl stop mopidy
    echo "  ✓ Mopidy stopped"
else
    echo "  ℹ Mopidy service not running (or not managed by systemd)"
fi

echo ""

# Remove OAuth token
if [ -f "$OAUTH_FILE" ]; then
    echo "Removing OAuth token: $OAUTH_FILE"
    rm -f "$OAUTH_FILE"
    echo "  ✓ OAuth token removed"
else
    echo "  ℹ OAuth token not found at $OAUTH_FILE"
fi

# Optionally remove cache
if [ "$1" == "--cache" ]; then
    echo ""
    if [ -d "$CACHE_DIR" ]; then
        echo "Removing Tidal cache: $CACHE_DIR"
        rm -rf "$CACHE_DIR"
        echo "  ✓ Cache cleared"
    else
        echo "  ℹ Cache directory not found"
    fi
fi

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Start Mopidy:"
echo "   sudo systemctl start mopidy"
echo ""
echo "2. Watch the logs for the authentication URL:"
echo "   journalctl -u mopidy -f"
echo ""
echo "3. Look for a line like:"
echo "   'Visit https://link.tidal.com/XXXXX to log in'"
echo ""
echo "4. Open that URL in a browser and complete the login"
echo ""
echo "5. Once authenticated, Mopidy will save the new credentials automatically"
echo ""
