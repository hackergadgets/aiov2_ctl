# aiov2_ctl

A lightweight **power and feature control client** for the HackerGadgets **AIO v2** board (GPIO-based fork).

This tool controls onboard hardware (GPS, LoRa, SDR, USB power rails) via **direct GPIO access using `pinctrl`**, and supports both **CLI** and **system tray GUI** modes.

---

## What this tool does

`aiov2_ctl` directly toggles GPIO pins mapped to hardware enable lines in order to:

- Enable / disable onboard hardware modules
- Query current on/off state
- Monitor overall board power usage
- Provide a tray-based GUI for quick toggling
- Optionally auto-start the GUI on login (XDG desktops)

---

## Requirements

- HackerGadgets uConsole **AIO v2 Upgrade Kit**  
  https://hackergadgets.com/products/uconsole-upgrade-kit?variant=47038702682286
- uConsole running **Debian / Raspberry Pi OS** (Bookworm or Trixie recommended)
- Python **3.9+**
- `pinctrl` available on the system (used for direct GPIO control)
- Desktop environment with system tray support (for GUI mode)

---

## 1) System dependencies

Install required system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-pyqt6 git
```

---

## 2) Install aiov2_ctl (system-wide)

The recommended install location is `/usr/local/bin`.

Clone the repository anywhere (e.g. your home directory), then install:

```bash
git clone https://github.com/hackergadgets/aiov2_ctl.git
cd aiov2_ctl

sudo pip3 install --break-system-packages -r requirements.txt
sudo aiov2_ctl --install
```

Sanity check:

```bash
aiov2_ctl
aiov2_ctl --status
```

---

## 3) CLI usage

Show current GPIO state:

```bash
aiov2_ctl
```

Show detailed status (including battery / power rail info):

```bash
aiov2_ctl --status
```

Enable or disable a feature:

```bash
aiov2_ctl <FEATURE> <on|off>
```

Supported features:

- `GPS`
- `LORA`
- `SDR`
- `USB`

Examples:

```bash
aiov2_ctl GPS on
aiov2_ctl LORA off
aiov2_ctl SDR on
```

---

## 4) Power monitoring

Live power monitor (Ctrl+C to exit):

```bash
aiov2_ctl --power
```

Compact live GPIO + power line (single-line view):

```bash
aiov2_ctl --watch
```

---

## 5) GUI mode (system tray)

Start the tray-based GUI:

```bash
aiov2_ctl --gui
```

### Behaviour

- **Left-click**: opens a small status window (Wayland-safe)
- **Right-click**: opens tray menu to toggle hardware
- Power usage is updated once per second
- GUI must **not** be run as root

---

## 6) Autostart GUI on login (recommended)

For desktop environments that support **XDG autostart** (LXQt, XFCE, GNOME, etc.), this is handled automatically.

### Enable autostart

```bash
aiov2_ctl --autostart
```

Creates:

```
~/.config/autostart/aiov2_ctl.desktop
```

### Disable autostart

```bash
aiov2_ctl --no-autostart
```

### Notes

- Autostart is **per-user**, not system-wide
- Never run autostart commands as root
- Uses `/usr/local/bin/aiov2_ctl --gui`
- Includes a small startup delay to allow GPIO and desktop services to settle

---

## 7) Updating aiov2_ctl

Pull the latest version and reinstall automatically:

```bash
aiov2_ctl --update
```

Behaviour:

- Git operations are **never** run as root
- The tool escalates **only** for the install step
- Clean exit if already up to date

---

## Safety notes

- GPIO writes happen immediately
- Assumes exclusive control of AIO v2 GPIO pins
- Battery telemetry comes directly from kernel `power_supply`
- Power deltas below **~0.05 W** are considered noise

Maintained for **HackerGadgets uConsole AIO v2** users.
