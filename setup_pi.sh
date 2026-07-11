#!/usr/bin/env bash
#
# One-time provisioning for the bus-departure LED matrix display.
#
# Run ONCE on the Raspberry Pi, as root:
#     sudo bash setup_pi.sh
#
# Idempotent: safe to re-run. A reboot is required afterwards for the
# CPU-isolation and audio changes to take effect.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="transport_display.service"
VENV="${SCRIPT_DIR}/env"  # rgbmatrix bindings live here (see step 3)
CONFIG_SERVICE_NAME="transport_display_config.service"
WEBENV="${SCRIPT_DIR}/webenv"  # FastAPI/uvicorn for the config web UI (step 4)
# Unprivileged user the config web UI runs as. Defaults to whoever invoked
# `sudo` (SUDO_USER), falling back to "pi". Override for an unusual setup with:
#     SERVICE_USER=alice sudo -E bash setup_pi.sh
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-pi}}"
# Adafruit installer commit to fetch (runs as root, so pinned rather than
# `main`: re-runs stay reproducible and upstream changes can't silently alter
# what we execute). Bump deliberately after testing a newer revision.
RGB_MATRIX_INSTALLER_COMMIT="35fa2e669a5f441c56f057d91085e35cf1876145"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run as root:  sudo bash setup_pi.sh" >&2
    exit 1
fi

# Locate the boot config dir (Bookworm uses /boot/firmware, older uses /boot).
if [[ -f /boot/firmware/config.txt ]]; then
    BOOT_DIR=/boot/firmware
else
    BOOT_DIR=/boot
fi
CONFIG_TXT="${BOOT_DIR}/config.txt"
CMDLINE_TXT="${BOOT_DIR}/cmdline.txt"

echo "==> Boot config dir: ${BOOT_DIR}"

echo "==> [1/8] Installing system dependencies"
apt-get update
apt-get install -y git python3 python3-dev python3-pip python3-venv python3-pillow python3-requests curl

echo "==> [2/8] Setting timezone to Europe/Zurich (clock + countdown correctness)"
timedatectl set-timezone Europe/Zurich || echo "    (could not set timezone; continuing)"

echo "==> [3/8] Installing the RGB matrix library via Adafruit's installer"
echo "    When prompted, choose:"
echo "      - Interface board:  Adafruit RGB Matrix Bonnet"
echo "      - Quality vs convenience:  QUALITY  (matches the GPIO4<->GPIO18 mod)"
echo "      - Reboot now?       NO  (this script reboots at the end)"
# Adafruit's installer (rgb-matrix.py) refuses to install into Debian's
# externally-managed system Python and installs the bindings into whatever
# interpreter runs it. So we run it from a venv created with
# --system-site-packages (which still sees apt-installed Pillow/requests), and
# the service then uses this same venv's Python (see step 6).
if [[ -x "${VENV}/bin/python3" ]] && "${VENV}/bin/python3" -c "import rgbmatrix" 2>/dev/null; then
    echo "    rgbmatrix already installed in ${VENV}; skipping Adafruit installer."
else
    python3 -m venv --system-site-packages "${VENV}"
    "${VENV}/bin/python3" -m pip install --upgrade pip
    "${VENV}/bin/python3" -m pip install adafruit-python-shell
    BUILD_DIR="$(mktemp -d)"
    curl -fsSL "https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/${RGB_MATRIX_INSTALLER_COMMIT}/rgb-matrix.py" \
        -o "${BUILD_DIR}/rgb-matrix.py"
    # Run with the venv's interpreter so the bindings land in the venv.
    ( cd "${BUILD_DIR}" && "${VENV}/bin/python3" rgb-matrix.py )
    rm -rf "${BUILD_DIR}"
fi

echo "==> [4/8] Setting up the config web UI venv (FastAPI/uvicorn)"
# A separate venv keeps the web deps off the display runtime. --system-site-packages
# lets it reuse apt Pillow/requests for the layout preview render.
if [[ -x "${WEBENV}/bin/python3" ]] && "${WEBENV}/bin/python3" -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "    web venv already provisioned in ${WEBENV}; skipping."
else
    python3 -m venv --system-site-packages "${WEBENV}"
    "${WEBENV}/bin/python3" -m pip install --upgrade pip
    "${WEBENV}/bin/python3" -m pip install -r "${SCRIPT_DIR}/requirements-web.txt"
fi

echo "==> [5/8] Disabling onboard sound (required by the E<->8 / GPIO4<->18 mods)"
# (a) blacklist the kernel module
BLACKLIST=/etc/modprobe.d/blacklist-rgb-matrix.conf
if ! grep -qs "snd_bcm2835" "${BLACKLIST}"; then
    echo "blacklist snd_bcm2835" >> "${BLACKLIST}"
    echo "    blacklisted snd_bcm2835"
else
    echo "    snd_bcm2835 already blacklisted"
fi
# (b) turn off the device-tree audio param
if grep -qs "^dtparam=audio=on" "${CONFIG_TXT}"; then
    sed -i 's/^dtparam=audio=on/dtparam=audio=off/' "${CONFIG_TXT}"
    echo "    set dtparam=audio=off"
elif ! grep -qs "^dtparam=audio=off" "${CONFIG_TXT}"; then
    echo "dtparam=audio=off" >> "${CONFIG_TXT}"
    echo "    appended dtparam=audio=off"
else
    echo "    dtparam=audio=off already set"
fi

echo "==> [6/8] Isolating CPU core 3 for the panel refresh thread"
if grep -qs "isolcpus=" "${CMDLINE_TXT}"; then
    echo "    isolcpus already present in cmdline.txt; leaving as-is"
else
    # cmdline.txt is a single line of space-separated kernel args.
    sed -i 's/$/ isolcpus=3/' "${CMDLINE_TXT}"
    echo "    appended isolcpus=3"
fi

echo "==> [7/8] Installing and enabling the display systemd service"
# Render the unit so WorkingDirectory + ExecStart point at this repo and its venv.
sed -e "s#^WorkingDirectory=.*#WorkingDirectory=${SCRIPT_DIR}#" \
    -e "s#^ExecStart=.*#ExecStart=${VENV}/bin/python3 -m src#" \
    "${SCRIPT_DIR}/${SERVICE_NAME}" > "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
echo "    ${SERVICE_NAME} enabled and (re)started"

echo "==> [8/8] Installing the config web UI (sudoers rule + service)"
# Let the unprivileged web UI restart/start/stop ONLY the display service
# (nothing else). start/stop back the web UI's on/off power button.
SUDOERS_FILE="/etc/sudoers.d/transport_display_config"
SUDOERS_LINE="${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart ${SERVICE_NAME}, /usr/bin/systemctl start ${SERVICE_NAME}, /usr/bin/systemctl stop ${SERVICE_NAME}"
TMP_SUDOERS="$(mktemp)"
printf '%s\n' "${SUDOERS_LINE}" > "${TMP_SUDOERS}"
if visudo -cf "${TMP_SUDOERS}" >/dev/null; then
    install -m 0440 -o root -g root "${TMP_SUDOERS}" "${SUDOERS_FILE}"
    echo "    installed ${SUDOERS_FILE}"
else
    echo "    ERROR: generated sudoers rule failed validation; not installing" >&2
fi
rm -f "${TMP_SUDOERS}"

# Render the config unit so paths/user match this repo + the web venv.
sed -e "s#^WorkingDirectory=.*#WorkingDirectory=${SCRIPT_DIR}#" \
    -e "s#^ExecStart=.*#ExecStart=${WEBENV}/bin/python3 -m server#" \
    -e "s#^User=.*#User=${SERVICE_USER}#" \
    "${SCRIPT_DIR}/${CONFIG_SERVICE_NAME}" > "/etc/systemd/system/${CONFIG_SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${CONFIG_SERVICE_NAME}"
systemctl restart "${CONFIG_SERVICE_NAME}"
echo "    ${CONFIG_SERVICE_NAME} enabled and (re)started on http://$(hostname).local:8080"

echo
echo "==============================================================="
echo " Setup complete. A REBOOT is required for the CPU-isolation and"
echo " audio changes to take effect:"
echo
echo "     sudo reboot"
echo
echo " After reboot, verify with:"
echo "     cat /proc/cmdline          # should contain isolcpus=3"
echo "     lsmod | grep snd_bcm2835   # should be empty (HDMI audio may remain)"
echo "     systemctl status ${SERVICE_NAME}"
echo "     journalctl -u ${SERVICE_NAME} -f"
echo
echo " Config web UI (edit stations/colors/fonts from a browser on the LAN):"
echo "     http://$(hostname).local:8080"
echo "     systemctl status ${CONFIG_SERVICE_NAME}"
echo "==============================================================="
