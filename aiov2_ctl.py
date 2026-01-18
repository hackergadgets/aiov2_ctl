#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import json

# ==============================
# Configuration
# ==============================
GPIO_MAP = {
    "GPS": 27,
    "LORA": 16,
    "SDR": 7,
    "USB": 23,
}

FEATURE_META = {
    "GPS":  {"device": "/dev/ttyAMA0", "type": "serial"},
    "LORA": {"type": "spi"},
    "SDR":  {"type": "usb"},
    "USB":  {"type": "usb"},
}

# ==============================
# GPIO Helpers
# ==============================
class GpioController:
    @staticmethod
    def run(cmd):
        try:
            return subprocess.check_output(cmd, text=True).strip()
        except Exception:
            return None

    @staticmethod
    def set_gpio(pin, state):
        subprocess.call([
            "pinctrl",
            "set",
            str(pin),
            "op",
            "dh" if state else "dl",
        ])

    @staticmethod
    def get_gpio(pin):
        out = GpioController.run(["pinctrl", "get", str(pin)])
        return bool(out and "hi" in out)

# ==============================
# Telemetry
# ==============================
class Telemetry:
    @staticmethod
    def gpsd_devices():
        try:
            out = subprocess.check_output(["gpspipe", "-r"], text=True, timeout=1)
            for line in out.splitlines():
                if '"class":"DEVICES"' in line:
                    return json.loads(line)
        except Exception:
            pass
        return None

    @staticmethod
    def gps_status():
        devices = Telemetry.gpsd_devices()
        if not devices or not devices.get("devices"):
            return {"state": "no-device"}

        status = {"state": "active", "tpv": None, "sky": None}
        try:
            proc = subprocess.Popen(
                ["gpspipe", "-w"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            start = time.time()
            while time.time() - start < 1.0:
                line = proc.stdout.readline()
                if not line:
                    break
                if '"class":"TPV"' in line:
                    status["tpv"] = json.loads(line)
                elif '"class":"SKY"' in line:
                    status["sky"] = json.loads(line)
                if status["tpv"] or status["sky"]:
                    break
            proc.terminate()
        except Exception:
            pass
        return status

    @staticmethod
    def power_rails():
        """
        Returns per-rail power data from /sys/class/power_supply
        Units:
          voltage: V
          current: A
          power:   W
        """
        base = "/sys/class/power_supply"
        rails = {}

        if not os.path.isdir(base):
            return rails

        for dev in os.listdir(base):
            path = os.path.join(base, dev)
            try:
                with open(os.path.join(path, "voltage_now")) as f:
                    volt = int(f.read()) / 1e6
                with open(os.path.join(path, "current_now")) as f:
                    cur = int(f.read()) / 1e6

                power = round(abs(volt * cur), 2)

                rails[dev] = {
                    "voltage": round(volt, 2),
                    "current": round(cur, 2),
                    "power": power,
                }
            except Exception:
                continue

        return rails

    @staticmethod
    def total_power():
        rails = Telemetry.power_rails()
        return round(sum(r["power"] for r in rails.values()), 2) if rails else None

    @staticmethod
    def io_users(path):
        try:
            out = subprocess.check_output(["lsof", path], text=True)
            return list({line.split()[0] for line in out.splitlines()[1:]})
        except Exception:
            return []

# ==============================
# Status Assembly
# ==============================
def feature_status(name, pin):
    on = GpioController.get_gpio(pin)
    info = {"enabled": on, "gpio": pin}

    if name == "GPS" and on:
        info["gps"] = Telemetry.gps_status()
        dev = FEATURE_META["GPS"].get("device")
        info["device"] = dev
        info["users"] = Telemetry.io_users(dev)

    return info

# ==============================
# CLI Output
# ==============================
def show_basic():
    print("Feature Status")
    print("====================")
    for f, p in GPIO_MAP.items():
        state = "ON" if GpioController.get_gpio(p) else "OFF"
        print(f"{f:<5} GPIO{p}: {state}")

def show_detailed():
    print("Detailed Feature Status")
    print("========================")

    total = Telemetry.total_power()
    print(f"Overall Power: {total if total is not None else 'n/a'} W")
    print("------------------------")

    for f, p in GPIO_MAP.items():
        data = feature_status(f, p)
        print(f"{f} (GPIO{p})")
        for k, v in data.items():
            print(f"  {k}: {v}")
        print()

# ==============================
# Live Power Mode (Per-rail)
# ==============================
def show_power_live():
    try:
        while True:
            rails = Telemetry.power_rails()
            os.system("clear")

            print("Power Monitor (Ctrl+C to quit)")
            print("-----------------------------")

            total = 0.0
            for name, r in rails.items():
                print(
                    f"{name:<14} "
                    f"{r['voltage']:>5.2f} V  "
                    f"{r['current']:>5.2f} A  "
                    f"({r['power']:>5.2f} W)"
                )
                total += r["power"]

            print("-----------------------------")
            print(f"Total: {total:.2f} W")
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting power monitor.")

# ==============================
# Watch Mode (Compact)
# ==============================
def show_watch():
    print("Live Status (Ctrl+C to quit)")
    print("----------------------------")
    try:
        while True:
            states = [
                f"{f}:{'ON' if GpioController.get_gpio(p) else 'OFF'}"
                for f, p in GPIO_MAP.items()
            ]
            total = Telemetry.total_power()
            line = "  ".join(states)
            line += f"  Power:{total if total is not None else 'n/a'}W"
            print(line, end="\r", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting watch mode.")

# ==============================
# GUI (Tray)
# ==============================
def run_gui():
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Error: Do not run the GUI as root.")
        sys.exit(1)

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No display available")
        sys.exit(1)

    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QIcon, QAction

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = QSystemTrayIcon(QIcon.fromTheme("utilities-system-monitor"))
    tray.setToolTip("AIO v2 Controller")

    menu = QMenu()
    actions = {}

    for f in GPIO_MAP:
        a = QAction(f)
        a.setCheckable(True)
        a.triggered.connect(lambda c, f=f: GpioController.set_gpio(GPIO_MAP[f], c))
        menu.addAction(a)
        actions[f] = a

    menu.addSeparator()
    power_action = QAction("Power: -- W")
    power_action.setEnabled(False)
    menu.addAction(power_action)

    menu.addSeparator()
    menu.addAction("Quit", app.quit)

    tray.setContextMenu(menu)

    def update_menu():
        for f, p in GPIO_MAP.items():
            actions[f].blockSignals(True)
            actions[f].setChecked(GpioController.get_gpio(p))
            actions[f].blockSignals(False)
        total = Telemetry.total_power()
        power_action.setText(f"Power: {total if total is not None else 'n/a'} W")

    timer = QTimer()
    timer.setInterval(1000)
    timer.timeout.connect(update_menu)
    timer.start()

    tray.show()
    sys.exit(app.exec())

# ==============================
# Entrypoint
# ==============================
def main():
    if len(sys.argv) == 1:
        show_basic()
        return

    arg = sys.argv[1]

    if arg == "--status":
        show_detailed()
        return
    if arg == "--power":
        show_power_live()
        return
    if arg == "--watch":
        show_watch()
        return
    if arg == "--gui":
        run_gui()
        return

    if len(sys.argv) == 3:
        feature = sys.argv[1].upper()
        state = sys.argv[2].lower() == "on"
        if feature in GPIO_MAP:
            GpioController.set_gpio(GPIO_MAP[feature], state)
            return

    print("Usage: aiov2_ctl [--status|--power|--watch|--gui|<feature> on|off]")

if __name__ == "__main__":
    main()
