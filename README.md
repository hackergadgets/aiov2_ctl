# aiov2_ctl
This is a client for power management of the aiov2.

## Usage:
**View all feature status**

`python aiov2_ctl.py` 

**Set feature switch**              

`python aiov2_ctl.py <feature> <on/off>`

**Features:**  GPS, LORA, SDR, USB

**Examples:**
Turn ON GPS
  
`python aiov2_ctl.py GPS on` 
  
Turn OFF LoRa

`python aiov2_ctl.py LORA off`

**Start System Tray GUI**

`python aiov2_ctl.py --gui`

After running the command, a system tray icon will show on the task bar. Right click the icon, a menu will popup. Click on the item to turn it on/off.

![](img/system_tray.png)