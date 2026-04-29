#!/bin/bash
# =============================================================================
# install.sh — Install mopidy-pibox and mopidy-tidal on a host that already
# has Mopidy installed system-wide via APT.
#
# Strategy: create a Python venv at /opt/mopidy-plugins with --system-site-packages
# so it inherits APT-managed packages (mopidy, pykka, python3-gi) and installs
# our plugins into the venv without touching system packages.
#
# After install, update each Mopidy systemd unit's ExecStart to use the venv's
# mopidy binary, or set PYTHONPATH — see the note at the bottom.
#
# Usage:
#   sudo ./install.sh               # install / upgrade
#   sudo ./install.sh --reinstall   # force reinstall both packages
#
# Requirements:
#   - mopidy installed via APT (provides mopidy, pykka, python3-gi)
#   - python3-venv available (sudo apt install python3-venv)
#   - git available
# =============================================================================

set -euo pipefail

VENV=/opt/mopidy-plugins
PIBOX_REPO="https://github.com/brett-kimball/mopidy-pibox.git"
TIDAL_REPO="https://github.com/brett-kimball/mopidy-tidal.git"

# Resolve flags
REINSTALL=false
for arg in "$@"; do
    [[ "$arg" == "--reinstall" ]] && REINSTALL=true
done

# Must run as root so the venv is writable by root; plugin files
# will be readable by the mopidy user.
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root: sudo $0 $*"
    exit 1
fi

echo "=== mopidy-pibox / mopidy-tidal installer ==="
echo ""

# ---- Verify prerequisites ------------------------------------------------
if ! python3 -c "import mopidy" 2>/dev/null; then
    echo "ERROR: mopidy is not importable from system Python."
    echo "Install it first: sudo apt install mopidy"
    exit 1
fi

if ! python3 -c "import pykka" 2>/dev/null; then
    echo "ERROR: pykka is not importable from system Python."
    echo "Install it first: sudo apt install python3-pykka"
    exit 1
fi

if ! python3 -c "import gi" 2>/dev/null; then
    echo "ERROR: PyGObject (python3-gi) is not importable from system Python."
    echo "Install it first: sudo apt install python3-gi"
    exit 1
fi

echo "Prerequisites: mopidy, pykka, python3-gi all present. OK."
echo ""

# ---- Ensure build-time system deps for compiled wheels ------------------
echo "Checking system build dependencies (libcairo2-dev)..."
if ! dpkg -s libcairo2-dev &>/dev/null; then
    echo "  Installing libcairo2-dev via apt..."
    apt-get install -y libcairo2-dev
else
    echo "  libcairo2-dev already installed. OK."
fi
echo ""

# ---- Create or reuse venv -----------------------------------------------
if [[ ! -d "$VENV" ]]; then
    echo "Creating venv at $VENV (with --system-site-packages)..."
    python3 -m venv --system-site-packages "$VENV"
    echo "  Done."
else
    echo "Venv already exists at $VENV."
fi
echo ""

PIP="$VENV/bin/pip"

# ---- Install / upgrade mopidy-tidal -------------------------------------
echo "Installing mopidy-tidal from brett-kimball fork..."
if [[ "$REINSTALL" == "true" ]]; then
    "$PIP" install --force-reinstall "git+${TIDAL_REPO}"
else
    "$PIP" install "git+${TIDAL_REPO}"
fi
TIDAL_VER=$("$VENV/bin/python" -c "import mopidy_tidal; print(mopidy_tidal.__version__)" 2>/dev/null || echo "unknown")
echo "  mopidy-tidal installed: $TIDAL_VER"
echo ""

# ---- Install / upgrade mopidy-pibox -------------------------------------
echo "Installing mopidy-pibox from brett-kimball fork..."
if [[ "$REINSTALL" == "true" ]]; then
    "$PIP" install --force-reinstall "git+${PIBOX_REPO}"
else
    "$PIP" install "git+${PIBOX_REPO}"
fi
PIBOX_VER=$("$VENV/bin/python" -c "import pkg_resources; print(pkg_resources.get_distribution('Mopidy-Pibox').version)" 2>/dev/null || echo "unknown")
echo "  mopidy-pibox installed: $PIBOX_VER"
echo ""

# ---- Verify both extensions are discoverable ----------------------------
echo "Verifying Mopidy extension discovery..."
DISCOVERED=$("$VENV/bin/python" -c "
import pkg_resources
for ep in pkg_resources.iter_entry_points('mopidy.ext'):
    if ep.name in ('pibox', 'tidal'):
        print(f'  {ep.name}: {ep.dist}')
")
echo "$DISCOVERED"
echo ""

# ---- Print next steps ---------------------------------------------------
cat << 'EOF'
=== Installation complete ===

Next steps:

1. Update each Mopidy systemd service unit to use the venv's Python
   so it can see the installed plugins.

   Option A — point ExecStart at the venv mopidy binary:

     ExecStart=/opt/mopidy-plugins/bin/mopidy --config /etc/mopidy/mopidy-ball.conf

   Option B — set PYTHONPATH in the unit (keeps /usr/bin/mopidy):

     Environment=PYTHONPATH=/opt/mopidy-plugins/lib/python3.13/site-packages

   After editing, reload systemd:

     sudo systemctl daemon-reload
     sudo systemctl restart mopidy-ball   # or your instance name(s)

2. Configure mopidy-tidal (first run on each instance):

     sudo -u mopidy /opt/mopidy-plugins/bin/mopidy --config /etc/mopidy/mopidy-ball.conf

   Follow the Tidal OAuth prompts, then Ctrl-C and restart as a service.

3. Clear the Tidal image cache after the hi-res artwork patch takes effect:

     rm -rf /var/cache/mopidy/tidal/image   # adjust path per instance cache_dir

4. To update in future:

     sudo ./scripts/install.sh --reinstall

EOF
