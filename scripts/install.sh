#!/bin/bash
# =============================================================================
# install.sh -- Bootstrap mopidy-pibox and mopidy-tidal on a fresh Debian host.
#
# Handles full bootstrap (adds mopidy APT repo, installs mopidy via APT) or
# upgrading an existing install. Tested on Debian Bookworm and Trixie (arm64).
#
# Strategy: create a Python venv at /opt/mopidy-plugins with --system-site-packages
# so it inherits APT-managed packages (mopidy, pykka, python3-gi) and installs
# our plugins into the venv without touching system packages.
#
# Usage:
#   sudo ./install.sh               # install / upgrade
#   sudo ./install.sh --reinstall   # force reinstall both packages
#
# =============================================================================

set -euo pipefail

VENV=/opt/mopidy-plugins
PIBOX_REPO_RAW="https://raw.githubusercontent.com/brett-kimball/mopidy-pibox/main"
PIBOX_WHEELS_URL="${PIBOX_REPO_RAW}/wheels"
TIDAL_REPO="https://github.com/brett-kimball/mopidy-tidal.git"

# Resolve flags
REINSTALL=false
for arg in "$@"; do
    [[ "$arg" == "--reinstall" ]] && REINSTALL=true
done

# Must run as root
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root: sudo $0 $*"
    exit 1
fi

echo "=== mopidy-pibox / mopidy-tidal installer ==="
echo ""

# ---- Bootstrap mopidy via APT if not already present --------------------
if ! python3 -c "import mopidy" 2>/dev/null; then
    echo "Mopidy not found -- adding mopidy APT repo and installing..."

    apt-get install -y --no-install-recommends \
        curl gnupg2 apt-transport-https ca-certificates \
        python3-venv python3-gi git lsb-release

    # Add mopidy GPG key
    curl -fsSL https://apt.mopidy.com/mopidy.gpg \
        | gpg --dearmor -o /etc/apt/trusted.gpg.d/mopidy.gpg

    # Detect codename; fall back to bookworm if trixie not in repo yet
    CODENAME=$(lsb_release -sc 2>/dev/null || echo "bookworm")
    if ! curl -fsSL "https://apt.mopidy.com/mopidy.list" 2>/dev/null | grep -q "$CODENAME"; then
        echo "  Codename '$CODENAME' not found in mopidy repo -- using bookworm packages (compatible)"
        CODENAME="bookworm"
    fi

    echo "deb https://apt.mopidy.com/ ${CODENAME} main" \
        > /etc/apt/sources.list.d/mopidy.list

    apt-get update -qq
    apt-get install -y mopidy python3-pykka python3-gi
    echo "  Mopidy installed via APT."
    echo ""
else
    echo "Mopidy already installed. OK."
    echo ""
fi

# ---- Verify prerequisites -----------------------------------------------
for mod in mopidy pykka gi; do
    if ! python3 -c "import $mod" 2>/dev/null; then
        echo "ERROR: python3 cannot import '$mod'. Check your APT install."
        exit 1
    fi
done
echo "Prerequisites: mopidy, pykka, python3-gi all present. OK."
echo ""

# ---- Ensure required system packages ------------------------------------
echo "Checking required system packages..."
REQUIRED_PKGS=(
    python3-venv
    libcairo2-dev
    gstreamer1.0-plugins-bad
    gstreamer1.0-libav
    curl
    git
)
MISSING=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "  Installing: ${MISSING[*]}"
    apt-get install -y "${MISSING[@]}"
else
    echo "  All required system packages present. OK."
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
echo "Installing mopidy-pibox from pre-built wheel..."
PIBOX_WHEEL=$(curl -fsSL "${PIBOX_WHEELS_URL}/LATEST")
PIBOX_WHEEL_URL="${PIBOX_WHEELS_URL}/${PIBOX_WHEEL}"
echo "  Wheel: ${PIBOX_WHEEL}"
if [[ "$REINSTALL" == "true" ]]; then
    "$PIP" install --force-reinstall --no-deps "${PIBOX_WHEEL_URL}"
else
    "$PIP" install --no-deps "${PIBOX_WHEEL_URL}"
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

   Option A -- point ExecStart at the venv mopidy binary:

     ExecStart=/opt/mopidy-plugins/bin/mopidy --config /etc/mopidy/mopidy.conf

   Option B -- set PYTHONPATH in the unit (keeps /usr/bin/mopidy):

     Environment=PYTHONPATH=/opt/mopidy-plugins/lib/python3.13/site-packages

   After editing, reload systemd:

     sudo systemctl daemon-reload
     sudo systemctl restart mopidy

2. Configure mopidy-tidal (first run, one time per instance):

     sudo -u mopidy /opt/mopidy-plugins/bin/mopidy --config /etc/mopidy/mopidy.conf

   Follow the Tidal OAuth prompts, then Ctrl-C and restart as a service.

3. Clear the Tidal image cache after the hi-res artwork patch takes effect:

     rm -rf /var/cache/mopidy/tidal/image   # adjust path per instance cache_dir

4. To update plugins in future:

     sudo ./scripts/install.sh --reinstall

EOF
