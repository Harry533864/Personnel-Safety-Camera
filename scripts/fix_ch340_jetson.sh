#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo: sudo bash $0" >&2
  exit 1
fi

echo "Kernel: $(uname -r)"
echo

echo "[1/5] Stop brltty, which can grab USB serial adapters..."
systemctl stop brltty 2>/dev/null || true
systemctl disable brltty 2>/dev/null || true
systemctl mask brltty 2>/dev/null || true
pkill -9 -f /sbin/brltty 2>/dev/null || true
ln -sf /dev/null /etc/udev/rules.d/85-brltty.rules
udevadm control --reload-rules 2>/dev/null || true

echo
echo "[2/5] Current CH340 USB device:"
lsusb | grep -iE '1a86:7523|ch340|ch341' || {
  echo "No CH340/CH341 device found. Unplug/replug the USB-RS485 adapter and run again."
  exit 1
}

echo
echo "[3/5] Available serial driver modules:"
find "/lib/modules/$(uname -r)" -type f \
  \( -name 'ch341.ko*' -o -name 'usbserial.ko*' -o -name 'cp210x.ko*' -o -name 'ftdi_sio.ko*' \) \
  -print | sort || true

echo
echo "[4/5] Try to bind a driver..."
if modinfo ch341 >/dev/null 2>&1; then
  echo ch341 > /etc/modules-load.d/ch341.conf
  modprobe usbserial || true
  modprobe ch341 || true
else
  echo "ch341 module is not installed for this kernel."
fi

if ! ls /dev/ttyUSB* >/dev/null 2>&1; then
  for iface in /sys/bus/usb/devices/*:*; do
    [ -e "$iface" ] || continue
    vid_file="${iface%:*}/idVendor"
    pid_file="${iface%:*}/idProduct"
    [ -f "$vid_file" ] || continue
    vid=$(cat "$vid_file")
    pid=$(cat "$pid_file")
    if [ "$vid" = "1a86" ] && [ "$pid" = "7523" ]; then
      name=$(basename "$iface")
      if [ -L "$iface/driver" ]; then
        driver=$(basename "$(readlink "$iface/driver")")
        printf '%s' "$name" > "/sys/bus/usb/drivers/$driver/unbind" 2>/dev/null || true
      fi
      printf '%s' "$name" > /sys/bus/usb/drivers_probe 2>/dev/null || true
      if [ -w /sys/bus/usb/drivers/ch341/bind ]; then
        printf '%s' "$name" > /sys/bus/usb/drivers/ch341/bind 2>/dev/null || true
      fi
    fi
  done
fi

udevadm trigger 2>/dev/null || true
udevadm settle 2>/dev/null || true
sleep 2

echo
echo "[5/5] Result:"
lsusb -t
echo
if ls /dev/ttyUSB* >/dev/null 2>&1; then
  ls -l /dev/ttyUSB*
  echo "OK: configure YSL301 serial port as /dev/ttyUSB0."
else
  echo "Still no /dev/ttyUSB*."
  echo "This kernel needs a matching ch341.ko module, or use a CP2102/FTDI USB-RS485 adapter."
  echo "Installed alternatives on this Jetson are usually cp210x.ko and ftdi_sio.ko."
  exit 2
fi
