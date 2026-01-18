#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import json
from statistics import mean, pstdev

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

# uConsole power reality
BATTERY_SUPPLY = "axp20x-battery"
AC_SUPPLY = "axp22x-ac"

# ==============================
# Help text
# ==============================
HELP_TEXT = f"""
aiov2_ctl — AIO v2 control + telemetry tool

USAGE:
  aiov2_ctl
  aiov2_ctl --status
  aiov2_ctl --power
  aiov2_ctl --watch
  aiov2_ctl --gui
  aiov2_ctl --measure <FEATURE> [--seconds N] [--interval S] [--settle S]
  aiov2_ctl <FEATURE> on|off
  aiov2_ctl --help

FEATURES:
  {', '.join(GPIO_MAP.keys())}

COMMANDS:

  (no arguments)
      Show basic ON/OFF status of all GPIO-controlled features.

  --status
      Detailed status:
        - GPIO state
        - GPS telemetry (if enabled)
        - IO users holding devices
        - Total system power (best-effort)

  --power
      Live power monitor (battery truth).
      Shows:
        - AC / battery status
        - Battery voltage, current, watts

  --watch
      Compact one-line live status (SSH-friendly).

  --measure <FEATURE>
      Measure incremental power draw of a feature.
      Uses battery rail only (truth source).

      Options:
        --seconds N   Sample duration (default: 3)
        --interval S  Sample interval (default: 0.2)
        --settle S    Settle delay after toggle (default: 1)

      Example:
        aiov2_ctl --measure SDR
        aiov2_ctl --measure GPS --seconds 5

  --gui
      System tray controller (non-root, requires display).

  <FEATURE> on|off
      Manually toggle a GPIO.

NOTES:
  • Battery readings come from axp20x-battery
  • Per-feature power <0.05 W is below noise floor
  • GPS telemetry requires gpsd + gpspipe
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
            "pinctrl", "set", str(pin), "op", "dh" if state else "dl"
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
        v = Telemetry._read_int(f"/sys/class/power_supply/{AC_SUPPLY}/online")
        return bool(v) if v is not None else None

    @staticmethod
    def battery_status():
        try:
            with open(f"/sys/class/power_supply/{BATTERY_SUPPLY}/status") as f:
                return f.read().strip()
        except Exception:
            return None

    @staticmethod
    def battery_v_i_w():
        v_uv = Telemetry._read_int(f"/sys/class/power_supply/{BATTERY_SUPPLY}/voltage_now")
        i_ua = Telemetry._read_int(f"/sys/class/power_supply/{BATTERY_SUPPLY}/current_now")
        if v_uv is None or i_ua is None:
            return None

        v = v_uv / 1e6
        i = i_ua / 1e6
        return {
            "voltage": round(v, 2),
            "current": round(i, 2),
            "power": round(abs(v * i), 2),
        }

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
    def io_users(path):
        try:
            out = subprocess.check_output(["lsof", path], text=True)
            return list({line.split()[0] for line in out.splitlines()[1:]})
        except Exception:
            return []

# ==============================
# Sampling / Measurement
# ==============================
def sample_battery_power(seconds=3.0, interval=0.2):
    currents, powers = [], []
    voltage = None

    end = time.time() + max(0.1, seconds)
    while time.time() < end:
        viw = Telemetry.battery_v_i_w()
        if viw:
            voltage = viw["voltage"]
            currents.append(viw["current"])
            powers.append(viw["power"])
        time.sleep(max(0.05, interval))

    if not currents:
        return None

    return {
        "voltage": voltage,
        "current_mean": round(mean(currents), 2),
        "current_sd": round(pstdev(currents), 2) if len(currents) > 1 else 0.0,
        "power_mean": round(mean(powers), 2),
        "power_sd": round(pstdev(powers), 2) if len(powers) > 1 else 0.0,
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
    print(f"Power source: {'AC online' if Telemetry.ac_online() else 'AC offline'} | Battery: {Telemetry.battery_status() or 'n/a'}")
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
        print("Error: telemetry sampling failed.")
        return 1

    d_cur = round(on["current_mean"] - off["current_mean"], 2)
    d_pwr = round(on["power_mean"] - off["power_mean"], 2)

    print("\nResults (battery net draw)")
    print("--------------------------")
    print(f"OFF: {off['power_mean']:.2f} W")
    print(f"ON : {on['power_mean']:.2f} W")
    print("--------------------------")
    print(f"Δ   {d_pwr:+.2f} W ({d_cur:+.2f} A)")
    return 0

# ==============================
# Live / Status
# ==============================
def show_power_live():
    try:
        while True:
            viw = Telemetry.battery_v_i_w()
            os.system("clear")
            print("Power Monitor (Ctrl+C to quit)")
            print("-----------------------------")
            print(f"Source: {'AC online' if Telemetry.ac_online() else 'Battery'} | Status: {Telemetry.battery_status() or 'n/a'}")
            if viw:
                print(f"{viw['voltage']:.2f} V  {viw['current']:.2f} A  ({viw['power']:.2f} W)")
            time.sleep(1)
    except KeyboardInterrupt:
        pass

def show_watch():
    try:
        while True:
            states = [f"{f}:{'ON' if GpioController.get_gpio(p) else 'OFF'}" for f, p in GPIO_MAP.items()]
            viw = Telemetry.battery_v_i_w()
            pwr = viw["power"] if viw else "n/a"
            print("  ".join(states) + f"  Power:{pwr}W", end="\r", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        pass

# ==============================
# Entrypoint
# ==============================
def main():
    if len(sys.argv) == 1:
        for f, p in GPIO_MAP.items():
            print(f"{f:<5} GPIO{p}: {'ON' if GpioController.get_gpio(p) else 'OFF'}")
        return

    arg = sys.argv[1]

    if arg in ("--help", "-h"):
        print(HELP_TEXT)
        return
    if arg == "--power":
        show_power_live()
        return
    if arg == "--watch":
        show_watch()
        return
    if arg == "--measure":
        seconds, interval, settle = 3.0, 0.2, 1.0
        feature = sys.argv[2]
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--seconds":
                seconds = float(sys.argv[i+1]); i += 2
            elif sys.argv[i] == "--interval":
                interval = float(sys.argv[i+1]); i += 2
            elif sys.argv[i] == "--settle":
                settle = float(sys.argv[i+1]); i += 2
            else:
                i += 1
        sys.exit(measure_feature(feature, seconds, settle, interval))

    if len(sys.argv) == 3:
        feature = sys.argv[1].upper()
        state = sys.argv[2].lower() == "on"
        if feature in GPIO_MAP:
            GpioController.set_gpio(GPIO_MAP[feature], state)
            return

    print("Usage: aiov2_ctl --help")

if __name__ == "__main__":
    main()
