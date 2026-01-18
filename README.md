# aiov2_ctl

A lightweight **power and feature control client** for the HackerGadgets **AIO v2** board (GPIO-based fork).

This version controls onboard hardware (GPS, LoRa, SDR, USB power rails) via **direct GPIO access using `pinctrl`**, and supports both **CLI** and **system tray GUI** modes.

---

## What this tool does

`aiov2_ctl` directly toggles GPIO pins mapped to hardware enable lines in order to:

- Enable / disable hardware modules
- Query current on/off state
- Provide a tray-based GUI for quick toggling

---

## Requirements

- HackerGadgets uConsole AIO v2 Upgrade Kit (https://hackergadgets.com/products/uconsole-upgrade-kit?variant=47038702682286)
- uConsole running Debian / Raspberry Pi OS (Bookworm or Trixie recommended)
- Python 3.9 or newer
- pinctrl available on the system (used for direct GPIO control of the AIO v2 board)

---

## 1) System dependencies

Install required system packages:

`sudo apt update`

`sudo apt install -y python3 python3-pip python3-pyqt6 git`

---

## 2) Install aiov2_ctl (system-wide, no virtualenv)

The recommended install location is `/usr/local/bin`.

Clone the repository anywhere (e.g. your home directory), then install the script system-wide:

```
git clone https://github.com/hackergadgets/aiov2_ctl.git
cd aiov2_ctl
sudo pip3 install --break-system-packages -r requirements.txt
sudo cp aiov2_ctl.py /usr/local/bin/aiov2_ctl
sudo chmod +x /usr/local/bin/aiov2_ctl
```

Sanity check:

```
aiov2_ctl
aiov2_ctl --status
```

---

## 3) CLI usage

View current status of all features:

`aiov2_ctl`

View detailed status (including overall power and GPS info):

`aiov2_ctl --status`

Enable or disable a feature:

`aiov2_ctl <FEATURE> <on|off>`

Supported features:

- GPS
- LORA
- SDR
- USB

Examples:

```
aiov2_ctl GPS on
aiov2_ctl LORA off
aiov2_ctl SDR on
```

---

## 4) GUI mode (system tray)

Start the tray-based GUI:

`aiov2_ctl --gui`  

Behaviour:
- Left click: opens a small status window (Wayland-safe)
- Right click: opens the tray menu to toggle hardware
- Overall board power draw is shown live (polled once per second)

![System Tray](img/system_tray.png)

---

## 5) Autostart GUI on login (recommended)

For desktop sessions that support XDG autostart (LXQt, XFCE, GNOME, etc.)

```
mkdir -p ~/.config/autostart
nano ~/.config/autostart/aiov2_ctl.desktop
```

Paste:

```
[Desktop Entry]
Type=Application
Name=AIO v2 Controller
Comment=GPIO tray controller
Exec=/usr/bin/python3 /usr/local/bin/aiov2_ctl --gui
Terminal=false
XDG_AUTOSTART_DELAY=5
```

Save and reboot.

---

## Optional: delay GUI startup

If GPIO or desktop services initialize slowly, change `Exec=` to:

```Exec=bash -c "sleep 5 && /usr/bin/python3 /usr/local/bin/aiov2_ctl --gui"```
