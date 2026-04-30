# Kiosk Display Setup

This guide sets up a headless kiosk that automatically starts Chromium in
full-screen mode on login, displaying the pibox `/view` page to the HDMI
output. No keyboard, mouse, or other input devices are required.

This was developed and tested on a Raspberry Pi 4 running Debian, and is
equally applicable to a Pi 3 with a single HDMI output.

---

## How it works

- The console user auto-logs in on TTY1 via a systemd getty override
- `.bashrc` detects the TTY1 login and launches `cage` (a Wayland kiosk
  compositor) with a Chromium kiosk session
- No desktop environment is installed or required
- The mouse cursor is hidden by replacing the default Xcursor images with
  transparent ones (cage does not support hiding the pointer natively)

---

## 1. Install dependencies

```bash
sudo apt install -y \
    cage \
    chromium \
    x11-apps \
    imagemagick \
    scrot
```

- `cage` — the Wayland kiosk compositor
- `chromium` — the browser
- `x11-apps` — provides `xcursorgen`, needed to generate the transparent cursor
- `imagemagick` — needed to create the transparent cursor PNG
- `scrot` — screenshot utility, useful for debugging display issues

---

## 2. Configure console auto-login

Create a systemd drop-in to auto-login your kiosk user on TTY1. Replace
`USERNAME` with the actual username (e.g. `phyc`):

```bash
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
```

Create `/etc/systemd/system/getty@tty1.service.d/autologin.conf`:

```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin USERNAME --noclear %I $TERM
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

---

## 3. Create the kiosk script

Create `/home/USERNAME/kiosk.sh`:

```bash
#!/bin/bash
export XCURSOR_THEME=Adwaita

exec chromium \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --password-store=basic \
    --ozone-platform=wayland \
    --enable-features=UseOzonePlatform \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --ignore-gpu-blocklist \
    --disable-software-rasterizer \
    --force-gpu-mem-available-mb=256 \
    --disable-smooth-scrolling \
    --no-sandbox \
    http://localhost:6680/pibox/view >/var/tmp/cage.out 2>&1
```

Make it executable:

```bash
chmod +x /home/USERNAME/kiosk.sh
```

---

## 4. Add the kiosk launch to .bashrc

Append to `/home/USERNAME/.bashrc`:

```bash
# START KIOSK
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  export WLR_NO_HARDWARE_CURSORS=1
  exec cage -s -- /home/USERNAME/kiosk.sh
fi
```

The guard conditions ensure:
- `[ -z "$DISPLAY" ]` — only runs on a bare TTY, not inside an existing display session or over SSH
- `[ "$(tty)" = "/dev/tty1" ]` — only runs on the auto-login TTY, not other terminals

`WLR_NO_HARDWARE_CURSORS=1` tells cage to render the cursor in software
rather than using a hardware cursor plane. This is required on some Pi
hardware and also makes the transparent cursor trick below work correctly.

`-s` tells cage to allow VT switching (so you can still switch to another
TTY via Ctrl+Alt+F2 for SSH/maintenance without killing the session).

---

## 5. Hide the mouse cursor

cage has no built-in option to hide the pointer. The workaround is to replace
the cursor images in the Adwaita theme with transparent ones.

### Generate a transparent Xcursor file

Install the cursor generation tools:

```bash
sudo apt install -y x11-apps xcursorgen imagemagick
```

Create a working directory:

```bash
mkdir -p ~/transparent-cursor/cursors
cd ~/transparent-cursor
```

Create a 1×1 transparent PNG:

```bash
convert -size 1x1 xc:transparent cursor.png
```

Create the cursor config file `cursor.cfg`:

```
1 0 0 cursor.png
```

Generate the Xcursor file:

```bash
xcursorgen cursor.cfg cursors/default
```

### Replace the Adwaita cursor images

Back up the originals and replace with the transparent one:

```bash
sudo cp /usr/share/icons/Adwaita/cursors/default \
    /usr/share/icons/Adwaita/cursors/default.orig

sudo cp ~/transparent-cursor/cursors/default \
    /usr/share/icons/Adwaita/cursors/default
```

Many cursor names are symlinks to `default`. Verify and replace any that
are not:

```bash
ls -la /usr/share/icons/Adwaita/cursors/ | grep -v " -> "
```

For any listed that are real files (not symlinks), copy the transparent
cursor over them too:

```bash
sudo cp ~/transparent-cursor/cursors/default \
    /usr/share/icons/Adwaita/cursors/FILENAME
```

The most common ones that need replacing are `default`, `arrow`, and
`left_ptr`. On this installation, `arrow` and `left_ptr` were already
symlinks to `default`, so only `default` needed replacing.

### Revert if needed

```bash
sudo cp /usr/share/icons/Adwaita/cursors/default.orig \
    /usr/share/icons/Adwaita/cursors/default
```

---

## 6. Reboot and verify

```bash
sudo reboot
```

After reboot the Pi should:
1. Boot to a login prompt on the console
2. Auto-login as USERNAME on TTY1
3. cage starts and Chromium opens full-screen to `http://localhost:6680/pibox/view`

To check for errors if the display doesn't come up:

```bash
cat /var/tmp/cage.out
```

---

## Maintenance

To access a shell without disrupting the kiosk, SSH in normally — the TTY
guard in `.bashrc` ensures the kiosk only starts on TTY1, not SSH sessions.

To kill the kiosk from another TTY:

```bash
pkill cage
```

It will not restart automatically; a reboot (or re-login on TTY1) is needed
to bring it back.
