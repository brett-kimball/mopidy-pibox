# Running multiple Mopidy + Pibox instances with systemd

This folder contains example files and a template to run multiple Mopidy instances on one host.

Strategy
- Create a separate Mopidy config file per instance (eg `/etc/mopidy/instance1.conf`, `/etc/mopidy/instance2.conf`).
- Each config sets a unique `[pibox] site_title` (and other per-instance settings).
- Install a per-instance systemd unit that points Mopidy to the chosen config file.

Example workflow

1. Copy the example config to /etc and edit it:

```bash
sudo cp scripts/systemd/instance1.conf.example /etc/mopidy/instance1.conf
sudo chown root:root /etc/mopidy/instance1.conf
sudo chmod 0644 /etc/mopidy/instance1.conf
# Edit /etc/mopidy/instance1.conf and set site_title, default_playlists, etc.
sudo $EDITOR /etc/mopidy/instance1.conf
```

2. Install the unit file for this instance (replace placeholders):

```bash
# Copy template to systemd and substitute values
sudo cp scripts/systemd/mopidy-instance.service.template /etc/systemd/system/mopidy-instance1.service
sudo sed -i 's/%INSTANCE%/instance1/g' /etc/systemd/system/mopidy-instance1.service
sudo sed -i 's|%CONFIG_PATH%|/etc/mopidy/instance1.conf|g' /etc/systemd/system/mopidy-instance1.service

# Reload systemd, enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now mopidy-instance1.service
sudo journalctl -u mopidy-instance1.service -f
```

3. Repeat for additional instances, using `instance2`, `instance3`, etc.

Notes
- The packaged Mopidy unit (installed by the distro package) is typically named `mopidy.service`. Don't overwrite it — create new unit names for each instance.
- If Mopidy is installed in a non-standard location adjust the `ExecStart` path in the unit template.
- You can run each instance on different HTTP ports by setting `http/port = 6681` (and other backend ports) in each instance config.

Security and permissions
- The example unit runs as the `mopidy` user. Ensure that user has access to the configured `cache_dir` and `data_dir` paths, or run under a dedicated user if preferred.
