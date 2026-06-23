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

echo "==> [1/6] Installing system dependencies"
apt-get update
apt-get install -y git python3 python3-dev python3-pip python3-pillow python3-requests curl

echo "==> [2/6] Setting timezone to Europe/Zurich (clock + countdown correctness)"
timedatectl set-timezone Europe/Zurich || echo "    (could not set timezone; continuing)"

echo "==> [3/6] Installing the RGB matrix library via Adafruit's script"
echo "    When prompted, choose:"
echo "      - Interface board:  Adafruit RGB Matrix Bonnet"
echo "      - Quality vs convenience:  QUALITY  (matches the GPIO4<->GPIO18 mod)"
echo "      - Reboot now?       NO  (this script reboots at the end)"
if python3 -c "import rgbmatrix" 2>/dev/null; then
    echo "    rgbmatrix already importable; skipping Adafruit installer."
else
    TMP_SCRIPT="$(mktemp)"
    curl -fsSL https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh -o "${TMP_SCRIPT}"
    bash "${TMP_SCRIPT}"
    rm -f "${TMP_SCRIPT}"
fi

echo "==> [4/6] Disabling onboard sound (required by the E<->8 / GPIO4<->18 mods)"
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

echo "==> [5/6] Isolating CPU core 3 for the panel refresh thread"
if grep -qs "isolcpus=" "${CMDLINE_TXT}"; then
    echo "    isolcpus already present in cmdline.txt; leaving as-is"
else
    # cmdline.txt is a single line of space-separated kernel args.
    sed -i 's/$/ isolcpus=3/' "${CMDLINE_TXT}"
    echo "    appended isolcpus=3"
fi

echo "==> [6/6] Installing and enabling the systemd service"
# Render the unit so WorkingDirectory/ExecStart point at wherever this repo lives.
sed "s#^WorkingDirectory=.*#WorkingDirectory=${SCRIPT_DIR}#" \
    "${SCRIPT_DIR}/${SERVICE_NAME}" > "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
echo "    ${SERVICE_NAME} enabled and (re)started"

echo
echo "==============================================================="
echo " Setup complete. A REBOOT is required for the CPU-isolation and"
echo " audio changes to take effect:"
echo
echo "     sudo reboot"
echo
echo " After reboot, verify with:"
echo "     cat /proc/cmdline        # should contain isolcpus=3"
echo "     lsmod | grep snd         # should be empty"
echo "     systemctl status ${SERVICE_NAME}"
echo "     journalctl -u ${SERVICE_NAME} -f"
echo "==============================================================="
