#!/bin/bash
#
# update-branding.sh - Generate custom branding images for mopidy-pibox
#
# Usage: ./scripts/update-branding.sh /path/to/source-image.png
#
# This script takes a source image (preferably PNG with transparency) and
# generates all the branded image assets used by mopidy-pibox. The generated
# images are placed in the mopidy data directory where they will be served
# at runtime, overriding the bundled default images.
#
# Custom branding directory: ~/.local/share/mopidy/pibox/branding/
#
# Generated images and their expected sizes:
#
#   Image                    Size        Description
#   ---------------------    ---------   ------------------------------------
#   favicon.png              48x48       Browser tab icon
#   icon-192.png             192x192     PWA manifest icon (small)
#   icon-512.png             512x512     PWA manifest icon (large)
#   apple-touch-icon.png     180x180     iOS home screen icon
#   logo.png                 196x196     Main logo on session page
#   logo-black.png           196x196     Logo for "nothing playing" state
#   progress-indicator.png   max 512px   Progress bar indicator on /view page
#                                        (aspect ratio preserved)
#
# Square images are scaled to fit within the target dimensions while
# preserving aspect ratio, centered on a transparent canvas.
#
# The progress-indicator.png is scaled down only if larger than 512px,
# otherwise it retains its original dimensions and aspect ratio.
#
# No rebuild is required after running this script - images are loaded
# dynamically at runtime.
#
# To revert to default branding, delete the branding directory:
#   rm -rf ~/.local/share/mopidy/pibox/branding/
#
# Requires: ImageMagick (convert command)
#

set -e

# Default mopidy data directory
DATA_DIR="${MOPIDY_DATA_DIR:-$HOME/.local/share/mopidy/pibox}"
BRANDING_DIR="$DATA_DIR/branding"

# Check for ImageMagick
if ! command -v convert &> /dev/null; then
    echo "Error: ImageMagick is required but not installed."
    echo "Install with: sudo apt install imagemagick"
    exit 1
fi

# Check arguments
if [ $# -ne 1 ]; then
    echo "Usage: $0 <source-image.png>"
    echo ""
    echo "Generate custom branding images from a source file."
    echo "The source should be a PNG with transparency for best results."
    echo ""
    echo "Images will be saved to: $BRANDING_DIR/"
    echo ""
    echo "Set MOPIDY_DATA_DIR to override the default data directory."
    exit 1
fi

SOURCE_IMAGE="$1"

if [ ! -f "$SOURCE_IMAGE" ]; then
    echo "Error: Source image not found: $SOURCE_IMAGE"
    exit 1
fi

# Verify it's a valid image
if ! identify "$SOURCE_IMAGE" &> /dev/null; then
    echo "Error: Cannot read image file: $SOURCE_IMAGE"
    exit 1
fi

echo "Source image: $SOURCE_IMAGE"
identify "$SOURCE_IMAGE" | head -1

# Create branding directory
mkdir -p "$BRANDING_DIR"
echo ""
echo "Output directory: $BRANDING_DIR"

# Function to generate a square image with the source centered and fit
generate_square() {
    local size=$1
    local output=$2
    
    echo "  Generating $(basename "$output") (${size}x${size})..."
    convert "$SOURCE_IMAGE" \
        -resize "${size}x${size}" \
        -background none \
        -gravity center \
        -extent "${size}x${size}" \
        "$output"
}

# Function to generate progress indicator (preserve aspect ratio, max dimension)
generate_progress_indicator() {
    local max_size=$1
    local output=$2
    
    echo "  Generating $(basename "$output") (max ${max_size}px, aspect preserved)..."
    convert "$SOURCE_IMAGE" \
        -resize "${max_size}x${max_size}>" \
        -background none \
        "$output"
}

echo ""
echo "Generating branding images..."
generate_square 48 "$BRANDING_DIR/favicon.png"
generate_square 180 "$BRANDING_DIR/apple-touch-icon.png"
generate_square 192 "$BRANDING_DIR/icon-192.png"
generate_square 512 "$BRANDING_DIR/icon-512.png"
generate_square 196 "$BRANDING_DIR/logo.png"
generate_square 196 "$BRANDING_DIR/logo-black.png"
generate_progress_indicator 512 "$BRANDING_DIR/progress-indicator.png"

echo ""
echo "Done! Generated images:"
ls -lh "$BRANDING_DIR/"*.png

echo ""
echo "Custom branding is now active. Refresh your browser to see the changes."
echo ""
echo "To revert to default branding:"
echo "  rm -rf $BRANDING_DIR"
