# Custom Branding

pibox supports custom branding to personalize the look of your jukebox installation. You can replace the default logo and icons with your own images.

## How It Works

- **Default branding** is bundled with the pibox package
- **Custom branding** is loaded at runtime from the mopidy data directory
- Custom images override defaults — no rebuild required

## Prerequisites

Install ImageMagick on the system where you want to generate custom branding:

```bash
# Debian/Ubuntu
sudo apt install imagemagick

# macOS
brew install imagemagick
```

## Generating Custom Branding

Use the `update-branding.sh` script to generate all required images from a single source file:

```bash
./scripts/update-branding.sh /path/to/your-logo.png
```

For best results, use a **square PNG with a transparent background**.

### System installations

For a system installation (mopidy running as the `mopidy` user), set
`MOPIDY_DATA_DIR` to point at the system data directory:

```bash
MOPIDY_DATA_DIR=/var/lib/mopidy/pibox ./scripts/update-branding.sh /path/to/your-logo.png
```

## Generated Images

The script creates these images:

| Image                  | Size      | Description                          |
|------------------------|-----------|--------------------------------------|
| favicon.png            | 48×48     | Browser tab icon                     |
| icon-192.png           | 192×192   | PWA manifest icon (small)            |
| icon-512.png           | 512×512   | PWA manifest icon (large)            |
| apple-touch-icon.png   | 180×180   | iOS home screen icon                 |
| logo.png               | 196×196   | Main logo on session page            |
| logo-black.png         | 196×196   | Logo for "nothing playing" state     |
| progress-indicator.png | max 512px | Progress bar indicator on /view page |

## Reverting to Default Branding

To restore the original default branding, delete the custom branding directory:

```bash
rm -rf ~/.local/share/mopidy/pibox/branding/
```

Or for system installations:

```bash
sudo rm -rf /var/lib/mopidy/pibox/branding/
```

## Manual Branding

You can also manually place images in the branding directory without using the script. Ensure the images match the sizes listed above for best display quality.

```bash
mkdir -p ~/.local/share/mopidy/pibox/branding/
cp my-logo.png ~/.local/share/mopidy/pibox/branding/logo.png
cp my-logo.png ~/.local/share/mopidy/pibox/branding/logo-black.png
# ... etc
```

## Applying Changes

After updating branding:

1. **No restart required** — images are served dynamically
2. **Clear browser cache** or wait up to 1 hour for cached images to expire
3. Alternatively, open in an incognito/private window to see changes immediately
