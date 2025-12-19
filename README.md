# aiov2_ctl
This is a client for control the aiov2.
## Usage:
**View all feature status**
  `python aiov2_ctl.py` 

**Set feature switch**              
  `python aiov2_ctl.py <feature> <on/off>`

**Features:**  GPS, LORA, SDR, USB

**Start System Tray GUI**
  `python aiov2_ctl.py --gui`


**Examples:**
Turn ON GPS
  `python aiov2_ctl.py GPS on` 
Turn OFF LoRa
  `python aiov2_ctl.py LORA off`