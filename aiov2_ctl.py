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
    def usb_power():
        base = "/sys/class/power_supply"
        if not os.path.isdir(base):
            return None
        for dev in os.listdir(base):
            try:
                with open(f"{base}/{dev}/current_now") as f:
                    cur = int(f.read())
                with open(f"{base}/{dev}/voltage_now") as f:
                    volt = int(f.read())
                return round(abs(cur * volt) / 1e12, 2)
            except Exception:
                pass
        return None

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

    pw = Telemetry.usb_power()
    if pw is None:
        print("Overall Power: n/a")
    else:
        print(f"Overall Power: {pw} W")
    print("------------------------")

    for f, p in GPIO_MAP.items():
        data = feature_status(f, p)
        print(f"{f} (GPIO{p})")
        for k, v in data.items():
            print(f"  {k}: {v}")
        print()

# ==============================
# GUI (Tray + Status Window)
# ==============================
def run_gui():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No display available")
        sys.exit(1)

    from PyQt6.QtWidgets import (
        QApplication,
        QSystemTrayIcon,
        QMenu,
        QWidget,
        QVBoxLayout,
        QLabel,
    )
    from PyQt6.QtGui import QIcon, QAction, QCursor
    from PyQt6.QtCore import QTimer

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon = QIcon.fromTheme("drive-removable-media")
    if icon.isNull():
        icon = QIcon.fromTheme("computer")
    if icon.isNull():
        icon = QIcon.fromTheme("utilities-system-monitor")
    if icon.isNull():
        icon = QIcon("/usr/share/icons/hicolor/48x48/apps/utilities-terminal.png")

    tray = QSystemTrayIcon(icon)
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
    quit_action = QAction("Quit")
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)

    # Status window (left click)
    window = QWidget()
    window.setWindowTitle("AIO v2 Status")
    layout = QVBoxLayout(window)
    status_label = QLabel()
    layout.addWidget(status_label)

    def refresh_window():
        lines = []
        pw = Telemetry.usb_power()
        lines.append(f"Overall Power: {pw if pw is not None else 'n/a'} W")
        lines.append("")
        for f, p in GPIO_MAP.items():
            state = "ON" if GpioController.get_gpio(p) else "OFF"
            lines.append(f"{f}: {state}")
        status_label.setText("\n".join(lines))

    def on_activate(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            refresh_window()
            window.show()
            window.raise_()
            window.activateWindow()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            tray.contextMenu().popup(QCursor.pos())

    tray.activated.connect(on_activate)

    def update_menu():
        for f, p in GPIO_MAP.items():
            actions[f].blockSignals(True)
            actions[f].setChecked(GpioController.get_gpio(p))
            actions[f].blockSignals(False)
        pw = Telemetry.usb_power()
        power_action.setText(f"Power: {pw if pw is not None else 'n/a'} W")

    timer = QTimer()
    timer.setInterval(1000)
    timer.timeout.connect(update_menu)
    timer.start()

    update_menu()
    tray.show()
    sys.exit(app.exec())

# ==============================
# Entrypoint
# ==============================
def main():
    if len(sys.argv) == 1:
        show_basic()
        return
    if sys.argv[1] == "--status":
        show_detailed()
        return
    if sys.argv[1] == "--gui":
        run_gui()
        return
    if len(sys.argv) == 3:
        feature = sys.argv[1].upper()
        state = sys.argv[2].lower() == "on"
        if feature in GPIO_MAP:
            GpioController.set_gpio(GPIO_MAP[feature], state)
            return
    print("Usage: aiov2_ctl [--status|--gui|<feature> on|off]")


if __name__ == "__main__":
    main()
