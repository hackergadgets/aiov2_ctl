import sys
import os
import subprocess

# Configuration
# GPIO Pin Definitions
GPIO_MAP = {
    "GPS": 27,
    "LORA": 16,
    "SDR": 7,
    "USB": 23
}

class GpioController:
    """Handle GPIO control logic"""
    
    @staticmethod
    def run_command(cmd):
        """Run shell command and return output"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            # In non-Raspberry Pi environments or when command fails, might need silent handling or logging
            # print(f"Run command error {' '.join(cmd)}: {e}")
            return None
        except Exception as e:
            print(f"Unknown error: {e}")
            return None

    @staticmethod
    def set_gpio(pin, state):
        """Set GPIO pin state (True for High/ON, False for Low/OFF)"""
        op = "dh" if state else "dl"
        cmd = ["pinctrl", "set", str(pin), "op", op]
        GpioController.run_command(cmd)
        state_str = "ON" if state else "OFF"
        print(f"GPIO {pin} set to {state_str}")

    @staticmethod
    def get_gpio_status(pin):
        """Get GPIO pin status. Returns True for High, False for Low"""
        cmd = ["pinctrl", "get", str(pin)]
        output = GpioController.run_command(cmd)
        if output:
            # Output usually contains "hi" or "lo"
            if "hi" in output:
                return True
            elif "lo" in output:
                return False
        return False

    @staticmethod
    def show_all_status():
        """Show status of all features"""
        print("Current Feature Status:")
        print("==========================")
        for feature, pin in GPIO_MAP.items():
            is_on = GpioController.get_gpio_status(pin)
            status_str = "ON" if is_on else "OFF"
            print(f"{feature:<5} (GPIO{pin}): {status_str}")
        print("==========================")

def run_gui():
    """Run System Tray GUI"""
    try:
        from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget
        from PyQt6.QtGui import QIcon, QAction, QCursor
        from PyQt6.QtCore import QTimer, Qt
    except ImportError:
        print("Error: PyQt6 not installed. Please run 'pip install PyQt6' or use command line mode in headless environment.")
        sys.exit(1)

    class AioTrayApp:
        def __init__(self):
            self.app = QApplication(sys.argv)
            self.app.setQuitOnLastWindowClosed(False)

            # Create Icon
            self.tray_icon = QSystemTrayIcon()
            # Use standard system icon or placeholder
            icon = QIcon.fromTheme("preferences-system", QIcon.fromTheme("applications-system"))
            if icon.isNull():
                 style = self.app.style()
                 icon = style.standardIcon(style.StandardPixmap.SP_ComputerIcon)
            
            self.tray_icon.setIcon(icon)
            self.tray_icon.setVisible(True)
            self.tray_icon.setToolTip("AIO V2 Controller")

            # Dummy Widget for Wayland popup menu parent
            self.dummy_widget = QWidget()
            self.dummy_widget.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
            self.dummy_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.dummy_widget.setWindowOpacity(0) # Invisible
            self.dummy_widget.resize(1, 1)

            # Create Menu
            self.menu = QMenu(self.dummy_widget)
            self.actions = {}

            # Add Feature Actions
            for feature in GPIO_MAP.keys():
                action = QAction(feature, self.menu)
                action.setCheckable(True)
                action.triggered.connect(lambda checked, f=feature: self.toggle_feature(f, checked))
                self.menu.addAction(action)
                self.actions[feature] = action

            self.menu.addSeparator()

            # Add Quit Action
            quit_action = QAction("Quit", self.menu)
            quit_action.triggered.connect(self.app.quit)
            self.menu.addAction(quit_action)

            self.tray_icon.setContextMenu(self.menu)
            
            # Handle Left Click
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
            
            # Refresh status before menu shows
            self.menu.aboutToShow.connect(self.update_status)
            # Hide dummy widget when menu closes
            self.menu.aboutToHide.connect(self.dummy_widget.hide)

            # Initial status update
            self.update_status()

        def on_tray_icon_activated(self, reason):
            """Left click to show menu"""
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                # Wayland workaround: Delay showing menu slightly
                QTimer.singleShot(100, self.show_menu)

        def show_menu(self):
            # Wayland workaround: Ensure parent gets focus
            self.dummy_widget.move(QCursor.pos())
            self.dummy_widget.setWindowOpacity(1) # Visible
            self.dummy_widget.show()
            self.dummy_widget.activateWindow()
            # Use popup instead of exec to run non-blocking
            self.menu.popup(QCursor.pos())

        def update_status(self):
            """Read status from hardware and update menu"""
            for feature, pin in GPIO_MAP.items():
                is_on = GpioController.get_gpio_status(pin)
                
                # Block signals to avoid triggering toggle handler
                self.actions[feature].blockSignals(True)
                self.actions[feature].setChecked(is_on)
                self.actions[feature].blockSignals(False)

        def toggle_feature(self, feature, checked):
            """Toggle feature switch"""
            pin = GPIO_MAP.get(feature)
            if pin is not None:
                GpioController.set_gpio(pin, checked)
                # Update status to confirm change
                self.update_status()

        def run(self):
            sys.exit(self.app.exec())

    app = AioTrayApp()
    app.run()

def show_usage():
    print("Usage:")
    print(f"  python {sys.argv[0]}                    # View all feature status")
    print(f"  python {sys.argv[0]} <feature> <on/off> # Set feature switch")
    print(f"  python {sys.argv[0]} --gui              # Start System Tray GUI")
    print("")
    print("Features: " + ", ".join(GPIO_MAP.keys()))
    print("Examples:")
    print(f"  python {sys.argv[0]} GPS on             # Turn ON GPS")
    print(f"  python {sys.argv[0]} LORA off           # Turn OFF LoRa")

def main():
    if len(sys.argv) == 1:
        # No arguments, show status
        GpioController.show_all_status()
    elif len(sys.argv) == 2:
        if sys.argv[1] == '--gui':
            run_gui()
        else:
            print("Error: Invalid argument")
            show_usage()
            sys.exit(1)
    elif len(sys.argv) == 3:
        feature = sys.argv[1].upper()
        state_str = sys.argv[2].lower()
        
        if feature not in GPIO_MAP:
            print(f"Error: Unknown feature '{sys.argv[1]}'")
            show_usage()
            sys.exit(1)
            
        if state_str not in ['on', 'off']:
            print(f"Error: State must be 'on' or 'off'")
            show_usage()
            sys.exit(1)
            
        state = (state_str == 'on')
        pin = GPIO_MAP[feature]
        GpioController.set_gpio(pin, state)
    else:
        print("Error: Incorrect number of arguments")
        show_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
