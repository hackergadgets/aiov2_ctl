# Remove installed binaries
```
sudo rm -f /usr/local/bin/aiov2_ctl
sudo rm -f /usr/local/bin/aiov2ctl
```

# Remove old opt install (if present)
`sudo rm -rf /opt/aiov2_ctl`

# Remove autostart entry
`rm -f ~/.config/autostart/aiov2_ctl.desktop`

```
which aiov2_ctl || echo "aiov2_ctl not found"
ls /opt/aiov2_ctl 2>/dev/null || echo "/opt clean"
```
