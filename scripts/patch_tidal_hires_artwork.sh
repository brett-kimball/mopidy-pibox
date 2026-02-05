#!/bin/bash
# =============================================================================
# patch_tidal_hires_artwork.sh
# =============================================================================
# Purpose: Patch mopidy-tidal to request higher resolution album artwork
#
# Problem:
#   By default, mopidy-tidal requests artwork in this order: 750, 640, 480 pixels
#   Tidal actually provides artwork up to 1280x1280 pixels.
#   On 4K displays, 750px artwork displayed at 80vh (~1728px) looks soft/upscaled.
#
# Solution:
#   This script patches the mopidy-tidal library to request 1280px artwork first:
#     dimensions = (1280, 750, 640, 480)
#
# Location of the file to patch:
#   ~/.local/lib/python3.13/site-packages/mopidy_tidal/library.py
#   (or wherever pip installed mopidy-tidal)
#
# What the patch changes:
#   Line 64 (approximately):
#   FROM: dimensions = (750, 640, 480)
#   TO:   dimensions = (1280, 750, 640, 480)
#
# After patching:
#   1. Clear the image cache: rm -rf ~/.cache/mopidy/tidal/image
#   2. Restart Mopidy: sudo systemctl restart mopidy
#   3. New artwork will be fetched at 1280x1280 resolution
#
# Reverting the patch:
#   Run: pip install --force-reinstall mopidy-tidal
#   Or manually change 1280 back to the original values
#
# Usage:
#   ./patch_tidal_hires_artwork.sh          # Apply the patch
#   ./patch_tidal_hires_artwork.sh --check  # Check current state without patching
#   ./patch_tidal_hires_artwork.sh --revert # Revert to original dimensions
#
# =============================================================================

set -e

# Find the mopidy-tidal installation
LIBRARY_FILE=$(python3 -c "import mopidy_tidal; print(mopidy_tidal.__file__.replace('__init__.py', 'library.py'))" 2>/dev/null)

if [ -z "$LIBRARY_FILE" ] || [ ! -f "$LIBRARY_FILE" ]; then
    echo "ERROR: Could not find mopidy-tidal library.py"
    echo "Make sure mopidy-tidal is installed: pip show mopidy-tidal"
    exit 1
fi

echo "=== Tidal Hi-Res Artwork Patch ==="
echo ""
echo "Library file: $LIBRARY_FILE"
echo ""

# Check current state
CURRENT=$(grep -n "dimensions = " "$LIBRARY_FILE" | head -1)
echo "Current setting:"
echo "  $CURRENT"
echo ""

if [ "$1" == "--check" ]; then
    if echo "$CURRENT" | grep -q "1280"; then
        echo "Status: ✓ Already patched for hi-res artwork (1280px)"
    else
        echo "Status: ✗ Using default dimensions (750px max)"
        echo ""
        echo "Run without --check to apply the patch"
    fi
    exit 0
fi

if [ "$1" == "--revert" ]; then
    echo "Reverting to original dimensions..."
    sed -i 's/dimensions = (1280, 750, 640, 480)/dimensions = (750, 640, 480)/' "$LIBRARY_FILE"
    echo "  ✓ Reverted to: dimensions = (750, 640, 480)"
    echo ""
    echo "Restart Mopidy to apply: sudo systemctl restart mopidy"
    exit 0
fi

# Check if already patched
if echo "$CURRENT" | grep -q "1280"; then
    echo "Already patched! No changes needed."
    echo ""
    echo "Use --revert to undo the patch, or --check to verify status."
    exit 0
fi

# Apply the patch
echo "Applying patch..."
sed -i 's/dimensions = (750, 640, 480)/dimensions = (1280, 750, 640, 480)/' "$LIBRARY_FILE"

# Verify
NEW=$(grep -n "dimensions = " "$LIBRARY_FILE" | head -1)
echo "  ✓ Patched!"
echo ""
echo "New setting:"
echo "  $NEW"
echo ""

echo "=== Next Steps ==="
echo ""
echo "1. Clear the image cache to force re-fetch at higher resolution:"
echo "   rm -rf ~/.cache/mopidy/tidal/image"
echo ""
echo "2. Restart Mopidy:"
echo "   sudo systemctl restart mopidy"
echo ""
echo "3. Artwork will now be fetched at 1280x1280 (if available from Tidal)"
echo ""
echo "Note: Not all albums have 1280px artwork; the library will fall back to"
echo "      750, 640, or 480 if higher resolution is unavailable."
echo ""
