#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import json
from statistics import mean

def rerun_with_sudo(extra_args=None):
    cmd = ["sudo", sys.executable, os.path.realpath(__file__)]
    if extra_args:
        cmd += extra_args
    else:
        cmd += sys.argv[1:]

    os.execvp("sudo", cmd)


def run_cmd(cmd, cwd=None):
    try:
        subprocess.check_call(cmd, cwd=cwd)
        return True
    except subprocess.CalledProcessError:
        return False

def git_pull(repo):
    try:
        out = subprocess.check_output(
            ["git", "pull", "--ff-only"],
            cwd=repo,
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
        return out
    except subprocess.CalledProcessError as e:
        return None

def get_git_root():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except subprocess.CalledProcessError:
        return None


def get_git_branch(repo):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            text=True
        ).strip()
    except subprocess.CalledProcessError:
        return None



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

BATTERY_SUPPLY = "axp20x-battery"
AC_SUPPLY = "axp22x-ac"

# ==============================
# Help text
# ==============================
HELP_TEXT = f"""
aiov2_ctl — HackerGadgets uConsole AIOv2 control + telemetry tool

USAGE:
  aiov2_ctl
  aiov2_ctl --status
  aiov2_ctl --power
  aiov2_ctl --watch
  aiov2_ctl --gui
  aiov2_ctl --measure <FEATURE> [--seconds N] [--interval S] [--settle S]
  aiov2_ctl <FEATURE> on|off
  aiov2_ctl --install
  aiov2_ctl --update
  aiov2_ctl --help

FEATURES:
  {', '.join(GPIO_MAP.keys())}

COMMANDS:
  --status     One-shot system + battery snapshot
  --power      Live power monitor (Ctrl+C to exit)
  --watch      Compact live GPIO + power line
  --gui        System tray controller
  --measure    Measure power delta of a feature
  --install    Install tool to /usr/local/bin
  --update     Pull latest version from git and reinstall

NOTES:
  • Battery power is the truth source
  • <0.05 W deltas are below noise floor
  • --status is a one-shot snapshot
  • GUI left-click opens status window
  • GUI right-click opens menu
"""

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
    def _read_int(path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except Exception:
            return None

    @staticmethod
    def ac_online():
        v = Telemetry._read_int(
            f"/sys/class/power_supply/{AC_SUPPLY}/online"
        )
        return bool(v) if v is not None else None

    @staticmethod
    def battery_status():
        try:
            with open(
                f"/sys/class/power_supply/{BATTERY_SUPPLY}/status"
            ) as f:
                return f.read().strip()
        except Exception:
            return None

    @staticmethod
    def battery_capacity():
        return Telemetry._read_int(
            f"/sys/class/power_supply/{BATTERY_SUPPLY}/capacity"
        )

    @staticmethod
    def battery_v_i_w():
        v = Telemetry._read_int(
            f"/sys/class/power_supply/{BATTERY_SUPPLY}/voltage_now"
        )
        i = Telemetry._read_int(
            f"/sys/class/power_supply/{BATTERY_SUPPLY}/current_now"
        )
        if v is None or i is None:
            return None

        v /= 1e6
        i /= 1e6

        return {
            "voltage": round(v, 2),
            "current": round(i, 2),      # signed
            "power": round(v * i, 2),    # signed
        }

    @staticmethod
    def power_summary():
        viw = Telemetry.battery_v_i_w()
        if not viw:
            return None

        ac = Telemetry.ac_online()
        status = Telemetry.battery_status() or "n/a"
        cap = Telemetry.battery_capacity()

        cur = viw["current"]

        if cur > 0.05:
            direction = "charging"
        elif cur < -0.05:
            direction = "discharging"
        else:
            direction = "idle"

        if ac and direction == "charging":
            mode = "AC powering system + battery"
        elif ac:
            mode = "AC powering system"
        else:
            mode = "Battery powering system"

        return {
            "source": "AC" if ac else "BAT",
            "status": status,
            "capacity": cap,
            "direction": direction,
            "mode": mode,
            "voltage": viw["voltage"],
            "current": round(abs(cur), 2),
            "power": round(abs(viw["power"]), 2),
        }

# ==============================
# Status (snapshot)
# ==============================
def show_status():
    print("AIO v2 Status")
    print("====================")

    for f, p in GPIO_MAP.items():
        state = "ON" if GpioController.get_gpio(p) else "OFF"
        print(f"{f:<5} GPIO{p}: {state}")

    print("--------------------")

    summary = Telemetry.power_summary()
    if not summary:
        print("Power: n/a")
        return

    print(f"Source    : {summary['source']}")
    print(f"Status    : {summary['status']}")
    print(f"Capacity  : {summary['capacity']}%")
    print(f"Direction : {summary['direction']}")
    print(f"Mode      : {summary['mode']}")
    print(f"Voltage   : {summary['voltage']} V")
    print(f"Current   : {summary['current']} A")
    print(f"Power     : {summary['power']} W")

# ==============================
# Sampling / Measurement
# ==============================
def sample_battery_power(seconds=3.0, interval=0.2):
    currents, powers = [], []
    voltage = None

    end = time.time() + seconds
    while time.time() < end:
        viw = Telemetry.battery_v_i_w()
        if viw:
            voltage = viw["voltage"]
            currents.append(viw["current"])
            powers.append(viw["power"])
        time.sleep(interval)

    if not currents:
        return None

    return {
        "voltage": voltage,
        "current_mean": round(mean(currents), 2),
        "power_mean": round(mean(powers), 2),
        "samples": len(currents),
    }

def measure_feature(feature, seconds=3.0, settle=1.0, interval=0.2):
    feature = feature.upper()
    if feature not in GPIO_MAP:
        print(f"Unknown feature '{feature}'")
        return 2

    pin = GPIO_MAP[feature]
    orig = GpioController.get_gpio(pin)

    print(f"Measure: {feature} (GPIO{pin})")
    print(f"Power source: {'AC online' if Telemetry.ac_online() else 'Battery'}")
    print(f"Current state: {'ON' if orig else 'OFF'}")

    if orig:
        on = sample_battery_power(seconds, interval)
        GpioController.set_gpio(pin, False)
        time.sleep(settle)
        off = sample_battery_power(seconds, interval)
        GpioController.set_gpio(pin, True)
    else:
        off = sample_battery_power(seconds, interval)
        GpioController.set_gpio(pin, True)
        time.sleep(settle)
        on = sample_battery_power(seconds, interval)
        GpioController.set_gpio(pin, False)

    if not on or not off:
        print("Sampling failed.")
        return 1

    print("\nResults")
    print("----------------")
    print(f"OFF: {off['power_mean']:.2f} W")
    print(f"ON : {on['power_mean']:.2f} W")
    print(f"Δ   {on['power_mean'] - off['power_mean']:+.2f} W")
    return 0

# ==============================
# Live modes
# ==============================
def show_power_live():
    try:
        while True:
            summary = Telemetry.power_summary()
            os.system("clear")
            print("Power Monitor (Ctrl+C)")
            print("----------------------")

            if not summary:
                print("Telemetry unavailable")
            else:
                print(f"Source: {summary['source']} | {summary['status']}")
                print(
                    f"Battery: {summary['capacity']}% | "
                    f"{summary['current']} A ({summary['direction']})"
                )
                print(
                    f"Battery rail: {summary['voltage']} V | "
                    f"{summary['power']} W"
                )
                print(f"Mode: {summary['mode']}")

            time.sleep(1)
    except KeyboardInterrupt:
        pass

def show_watch():
    try:
        while True:
            states = [
                f"{f}:{'ON' if GpioController.get_gpio(p) else 'OFF'}"
                for f, p in GPIO_MAP.items()
            ]

            summary = Telemetry.power_summary()
            if summary:
                print(
                    "  ".join(states)
                    + f"  Src:{summary['source']}"
                    + f"  Batt:{summary['status']}"
                    + f"  {summary['capacity']}%"
                    + f"  {summary['power']:.2f}W",
                    end="\r",
                    flush=True,
                )
            else:
                print("  ".join(states) + "  Power:n/a", end="\r", flush=True)

            time.sleep(1)
    except KeyboardInterrupt:
        pass

# ==============================
# GUI (Tray + Left-click window)
# ==============================
def run_gui():
    if os.geteuid() == 0:
        print("Do not run GUI as root.")
        sys.exit(1)

    from PyQt6.QtWidgets import (
        QApplication, QSystemTrayIcon, QMenu,
        QWidget, QVBoxLayout, QLabel, QCheckBox
    )
    from PyQt6.QtGui import QAction, QIcon, QCursor
    from PyQt6.QtCore import Qt, QTimer

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setDesktopFileName("aiov2_ctl")

    tray = QSystemTrayIcon(QIcon.fromTheme("utilities-system-monitor"))
    tray.setToolTip("AIO v2 Controller")

    # -------- Right-click menu --------
    menu = QMenu()
    actions = {}

    for f in GPIO_MAP:
        a = QAction(f)
        a.setCheckable(True)
        a.triggered.connect(
            lambda checked, f=f: GpioController.set_gpio(GPIO_MAP[f], checked)
        )
        menu.addAction(a)
        actions[f] = a

    menu.addSeparator()
    power_action = QAction("Power: -- W")
    power_action.setEnabled(False)
    menu.addAction(power_action)

    menu.addSeparator()
    menu.addAction("Quit", app.quit)
    tray.setContextMenu(menu)

    # -------- Left-click window --------
    window = QWidget()
    window.setWindowTitle("AIO v2 Status")
    window.setWindowFlags(Qt.WindowType.Tool)
    layout = QVBoxLayout(window)

    power_label = QLabel("Power: -- W")
    layout.addWidget(power_label)

    checkboxes = {}
    for f in GPIO_MAP:
        cb = QCheckBox(f)
        cb.toggled.connect(
            lambda checked, f=f: GpioController.set_gpio(GPIO_MAP[f], checked)
        )
        layout.addWidget(cb)
        checkboxes[f] = cb

    def refresh():
        summary = Telemetry.power_summary()
        if summary:
            power_label.setText(
                f"{summary['mode']} | {summary['power']} W | {summary['capacity']}%"
            )
            power_action.setText(f"Power: {summary['power']} W")
        else:
            power_label.setText("Power: n/a")
            power_action.setText("Power: n/a")

        for f, p in GPIO_MAP.items():
            state = GpioController.get_gpio(p)

            checkboxes[f].blockSignals(True)
            checkboxes[f].setChecked(state)
            checkboxes[f].blockSignals(False)

            actions[f].blockSignals(True)
            actions[f].setChecked(state)
            actions[f].blockSignals(False)

    def on_activate(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            refresh()
            window.move(QCursor.pos())
            window.show()
            window.raise_()
            window.activateWindow()

    tray.activated.connect(on_activate)

    timer = QTimer()
    timer.timeout.connect(refresh)
    timer.start(1000)

    tray.show()
    sys.exit(app.exec())


def install_self():
    dst = "/usr/local/bin/aiov2_ctl"

    repo = get_git_root()
    if repo:
        src = os.path.join(repo, "aiov2_ctl.py")
    else:
        src = os.path.realpath(__file__)

    if os.path.realpath(src) == os.path.realpath(dst):
        print("Already installed (source and destination are the same).")
        return 0

    if os.geteuid() != 0:
        print("Install requires sudo.")
        print("Run: sudo aiov2_ctl --install")
        return 1

    print(f"Installing {src} → {dst}")
    subprocess.check_call(["cp", src, dst])
    subprocess.check_call(["chmod", "+x", dst])

    print("Install complete.")
    return 0

def update_self():
    repo = get_git_root()
    if not repo:
        print("Not inside a git repository. Cannot update.")
        return 1

    branch = get_git_branch(repo)
    if not branch:
        print("Could not determine git branch.")
        return 1

    print(f"Updating from git ({branch})…")

    result = git_pull(repo)
    if result is None:
        print("Git pull failed. Resolve manually.")
        return 1

    if "Already up to date" in result:
        print("Already up to date.")
        return 0

    print("Update pulled:")
    print(result)

    print("Reinstalling updated version…")

    if os.geteuid() != 0:
        rerun_with_sudo(["--install"])
        return 0

    return install_self()

# ==============================
# Entrypoint
# ==============================
def main():
    if len(sys.argv) == 1:
        for f, p in GPIO_MAP.items():
            print(f"{f}: {'ON' if GpioController.get_gpio(p) else 'OFF'}")
        return

    arg = sys.argv[1]

    if arg in ("--help", "-h"):
        print(HELP_TEXT)

    elif arg == "--install":
        sys.exit(install_self())

    elif arg == "--update":
        sys.exit(update_self())

    elif arg == "--status":
        show_status()

    elif arg == "--power":
        show_power_live()

    elif arg == "--watch":
        show_watch()

    elif arg == "--gui":
        run_gui()

    elif arg == "--measure":
        if len(sys.argv) < 3:
            print("Usage: aiov2_ctl --measure <FEATURE>")
            sys.exit(1)
        feature = sys.argv[2]
        sys.exit(measure_feature(feature))

    elif len(sys.argv) == 3:
        feature = arg.upper()
        state = sys.argv[2].lower()

        if feature not in GPIO_MAP or state not in ("on", "off"):
            print("Use --help")
            sys.exit(1)

        GpioController.set_gpio(GPIO_MAP[feature], state == "on")

    else:
        print("Use --help")

if __name__ == "__main__":
    main()
