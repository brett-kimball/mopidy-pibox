#!/bin/bash
# Script to disable mopidy-tidal search expansion

echo "Finding mopidy-tidal installation..."

# Find where mopidy_tidal is installed
MOPIDY_TIDAL_PATH=$(python3 -c "import sys; sys.path.insert(0, '/usr/lib/python3.13/site-packages'); import mopidy_tidal; import os; print(os.path.dirname(mopidy_tidal.__file__))" 2>/dev/null)

if [ -z "$MOPIDY_TIDAL_PATH" ]; then
    MOPIDY_TIDAL_PATH=$(python3 -c "import mopidy_tidal; import os; print(os.path.dirname(mopidy_tidal.__file__))" 2>/dev/null)
fi

if [ -z "$MOPIDY_TIDAL_PATH" ]; then
    echo "ERROR: Could not find mopidy_tidal installation"
    exit 1
fi

echo "Found mopidy-tidal at: $MOPIDY_TIDAL_PATH"

SEARCH_FILE="$MOPIDY_TIDAL_PATH/search.py"

if [ ! -f "$SEARCH_FILE" ]; then
    echo "ERROR: search.py not found at $SEARCH_FILE"
    exit 1
fi

echo "Backing up search.py..."
cp "$SEARCH_FILE" "$HOME/mopidy_tidal_search.py.backup"
echo "Backup saved to: $HOME/mopidy_tidal_search.py.backup"

echo "Applying fix..."
python3 << 'EOF'
import sys
search_file = sys.argv[1]

with open(search_file, 'r') as f:
    content = f.read()

if '# _expand_results_tracks(results)  # DISABLED' in content:
    print("Fix already applied!")
    sys.exit(0)

content = content.replace(
    '    _expand_results_tracks(results)',
    '    # _expand_results_tracks(results)  # DISABLED: expansion causes 2000+ results'
)

with open(search_file, 'w') as f:
    f.write(content)

print("✓ Search expansion disabled successfully")
EOF "$SEARCH_FILE"

echo ""
echo "Done! Restart mopidy to apply changes:"
echo "  sudo systemctl restart mopidy"
