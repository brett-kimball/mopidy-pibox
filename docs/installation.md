# Installation Guide

This guide covers a fresh installation of mopidy-pibox and mopidy-tidal on a
Raspberry Pi running Debian Trixie (no desktop environment).

---

## 1. System packages

### Add the Mopidy APT repository

```bash
sudo apt install -y curl gnupg2 apt-transport-https ca-certificates lsb-release

curl -fsSL https://apt.mopidy.com/mopidy.gpg \
    | gpg --dearmor \
    | sudo tee /etc/apt/trusted.gpg.d/mopidy.gpg > /dev/null

# Trixie packages are not yet in the mopidy repo; use bookworm — they are compatible.
echo "deb https://apt.mopidy.com/ bookworm main" \
    | sudo tee /etc/apt/sources.list.d/mopidy.list

sudo apt update
```

### Install Mopidy and runtime dependencies

```bash
sudo apt install -y \
    mopidy \
    python3-pykka \
    python3-gi \
    python3-venv \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    git
```

---

## 2. Python virtual environment

Create a venv that inherits the APT-managed packages (mopidy, pykka, gi):

```bash
sudo python3 -m venv --system-site-packages /opt/mopidy-plugins
```

---

## 3. Install mopidy-tidal

Install from the fork with full dependencies (tidalapi is not in APT):

```bash
sudo /opt/mopidy-plugins/bin/pip install \
    git+https://github.com/brett-kimball/mopidy-tidal.git
```

---

## 4. Install mopidy-pibox

Install the pre-built wheel (no extra dependencies needed — all come from APT):

```bash
LATEST=$(curl -fsSL https://raw.githubusercontent.com/brett-kimball/mopidy-pibox/main/wheels/LATEST)
sudo /opt/mopidy-plugins/bin/pip install --no-deps \
    "https://github.com/brett-kimball/mopidy-pibox/raw/main/wheels/$LATEST"
```

---

## 5. Configure the systemd service

The APT-installed `mopidy.service` uses `/usr/bin/mopidy`, which won't see the
plugins installed in the venv. Override the `ExecStart` to use the venv binary:

```bash
sudo mkdir -p /etc/systemd/system/mopidy.service.d/
```

Create `/etc/systemd/system/mopidy.service.d/venv.conf`:

```ini
[Service]
ExecStart=
ExecStart=/opt/mopidy-plugins/bin/mopidy --config /etc/mopidy/mopidy.conf
```

Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mopidy
```

---

## 6. Configure Mopidy

Edit `/etc/mopidy/mopidy.conf`. A minimal working configuration:

```ini
[core]
data_dir = /var/lib/mopidy
cache_dir = /var/cache/mopidy

[logging]
verbosity = 1

[audio]
output = alsasink device=hw:X,Y   # replace X,Y — see `aplay -l`

[http]
enabled = true
hostname = 0.0.0.0
port = 6680

[tidal]
enabled = true
quality = LOSSLESS
login_method = AUTO

[pibox]
enabled = true
site_title = My Pibox
default_skip_threshold = 3
```

To find the correct ALSA device for your HDMI output:

```bash
aplay -l
```

Look for the HDMI entry and use its card and device numbers as `hw:card,device`.

---

## 7. Tidal authentication (first run)

mopidy-tidal authenticates via OAuth. On first run you will be given a URL to
visit in a browser to authorise the device. Run Mopidy interactively as the
`mopidy` user to do this:

```bash
sudo -u mopidy /opt/mopidy-plugins/bin/mopidy --config /etc/mopidy/mopidy.conf
```

Follow the URL printed to the console, authorise in your browser, then press
`Ctrl-C`. From this point on the token is saved and the service runs
unattended:

```bash
sudo systemctl start mopidy
sudo systemctl enable mopidy
```

---

## 8. Verify

Check that both extensions are loaded:

```bash
sudo journalctl -u mopidy.service | grep -E "pibox|tidal|ERROR|WARNING"
```

The web interface should be accessible at `http://<pi-ip>:6680/pibox/`.

---

## Updating

### Update mopidy-pibox

```bash
sudo /opt/mopidy-plugins/bin/pip cache purge
LATEST=$(curl -fsSL https://raw.githubusercontent.com/brett-kimball/mopidy-pibox/main/wheels/LATEST)
sudo /opt/mopidy-plugins/bin/pip install --force-reinstall --no-deps \
    "https://github.com/brett-kimball/mopidy-pibox/raw/main/wheels/$LATEST"
sudo systemctl restart mopidy
```

### Update mopidy-tidal

```bash
sudo /opt/mopidy-plugins/bin/pip install --force-reinstall \
    git+https://github.com/brett-kimball/mopidy-tidal.git
sudo systemctl restart mopidy
```

---

## Multiple instances

To run more than one Mopidy instance (e.g. two rooms, two HDMI outputs), see
[scripts/systemd/README.md](../scripts/systemd/README.md).

---

## Custom branding

To replace the default logo and icons, see [branding.md](branding.md).
