# systemd setup


Put this in a file named something like `curlbot.service` in /etc/systemd/system:

```
[Unit]
Description=curlybot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/bash ~/curlybot_v2/run_curlybot.sh
WorkingDirectory=/home/pi/kdoroschak
Restart=always
RestartSec=120

[Install]
WantedBy=multi-user.target
```

Then do 

```sh
sudo systemctl enable curlybot
sudo systemctl start curlybot
```