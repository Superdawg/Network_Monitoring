# Network Monitoring and Recovery

This suite is intended to be used on a Raspberry Pi controlling a power outlet
that powers a modem.  It will confirm whether internet access is available and
then act accordingly.

The `network_check.py` script is invoked on a schedule (default: every 30
minutes via the bundled systemd timer) to detect outages quickly.  Because
run frequency and reboot/notification frequency are decoupled via cooldown
timers, the script can safely be run much more often — every 5 minutes, for
example — without risking modem over-cycling or email floods.

If the internet is sufficiently deemed to be "down" (>50% packet loss to >50%
of targets) then `network_check.py` will invoke `gpio_control` (or any other
command you specify) to cycle the power outlet and reboot the modem.

Outage state is persisted to a JSON file across invocations.  On the **first**
detected failure the reboot cooldown clock starts but no reboot is issued,
avoiding unnecessary cycles for brief transient outages.  Subsequent failures
reboot the modem at most once per `--reboot-cooldown` period.  When
connectivity is restored, a recovery email is sent summarising the outage
duration and number of reboots performed, and the state file is removed.

## Default values

| Argument | Default | Notes |
|---|---|---|
| `--addresses` | `1.1.1.1 4.2.2.2 8.8.8.8` | Space-separated list of IPv4 addresses to ping |
| `--retry-count` | `2` | Rounds of pings before acting on failure |
| `--retry-interval` | `30` | Seconds between retries; consider `900` (15 min) in production |
| `--exec-on-fail` | _(none)_ | Command to run on confirmed failure |
| `--email-recipients` | _(none)_ | Space-separated list of email addresses to notify on failure and recovery |
| `--email-relay` | `localhost` | SMTP relay host to use when sending notifications |
| `--notify-state-file` | `/var/run/network_check.state` | Path to the JSON file used to track outage state across invocations |
| `--notify-cooldown` | `3600` | Minimum seconds between repeat failure emails (1 hour) |
| `--reboot-cooldown` | `7200` | Minimum seconds between modem reboots (2 hours); first failure only starts the clock |

## Example

Check `10.10.10.10` a maximum of **two** times with a **five** second sleep in
between, then trigger GPIO pin 23 for 15 seconds on failure:

```shell
./network_check.py --addresses 10.10.10.10 \
                   --retry-count 1 \
                   --retry-interval 5 \
                   --exec-on-fail "/usr/sbin/gpio_control -d 15 -p 23"
```

> **Note:** `--retry-count 1` means one retry (two total rounds of pings).

## Requirements

- Python 3
- `pingparsing` from PyPI (not packaged in Fedora/RHEL)
- `pigpio` C library (`libpigpio-dev` on Debian/Raspberry Pi OS)

## Getting up and running on Raspberry Pi OS (Bookworm)

> These instructions were last verified against Raspberry Pi OS Bookworm
> (Debian 12).  For older Buster/Bullseye systems the steps are similar but
> `pip3 install` behaved differently — see the Known Issues section.

```sh
sudo apt-get install -y git libpigpio-dev python3-pip python3-venv

git clone https://github.com/Superdawg/Network_Monitoring.git
cd Network_Monitoring

# Install Python dependencies into a virtual environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Build the gpio_control binary
make

# Install, passing your site-specific config on the command line.
# EMAIL_RECIPIENTS is optional — omit it if you don't want notifications.
sudo make install EMAIL_RECIPIENTS="you@example.com" GPIO_PIN=23 GPIO_DELAY=30 \
                  REBOOT_COOLDOWN=7200 NOTIFY_COOLDOWN=3600

# Verify the timer is active
sudo systemctl list-timers --all | grep network_check
```

> **Note:** `network_check.service` is generated from `network_check.service.in`
> during `make install` and is excluded from version control so credentials
> don't accidentally get committed.  If you omit `EMAIL_RECIPIENTS`, the
> `--email-recipients` argument is simply left out of the generated service.

## Linting

```sh
# Requires: cppcheck, flake8, pylint
make lint

# Individual targets:
make lint-c   # cppcheck + gcc -fsyntax-only
make lint-py  # flake8 + pylint
```

## Makefile targets

| Target | Description |
|---|---|
| `make` / `make all` | Build `gpio_control` |
| `make install` | Install binaries + systemd units, enable and start timer |
| `make uninstall` | Stop/disable timer, remove installed files |
| `make clean` | Remove build artifacts |
| `make lint` | Run all linters (C and Python) |
| `make lint-c` | C linting only (cppcheck + gcc warnings) |
| `make lint-py` | Python linting only (flake8 + pylint) |

## Acceptable GPIO pins

`gpio_control` only accepts the following Broadcom GPIO numbers:

`5, 6, 16, 17, 22, 23, 24, 25, 26, 27`

These correspond to the generic `GPIO<n>` pins on the Raspberry Pi GPIO header.
See the [official GPIO reference](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio)
for pinout details.

## Known Issues

- **Non-Debian systems:** The `nogroup` group used by `make install` does not
  exist on RHEL/CentOS/Fedora.  Change the group to `nobody` in the Makefile
  or pass `make install` with an override.
- **Raspberry Pi OS Bookworm:** `sudo pip3 install` is blocked by PEP 668.
  Use a virtual environment (`.venv`) as shown in the setup instructions above,
  or pass `--break-system-packages` if you prefer a system-wide install.
- **IPv6 / hostnames:** `--addresses` only accepts IPv4 addresses.  Hostnames
  and IPv6 addresses will fail validation.
- **Email delivery delay:** Failure and recovery emails are queued on the local
  MTA and won't be delivered until connectivity is restored.  The timestamp
  in each subject line indicates when the event actually occurred.

## Equipment used

- ~$52 USD — [Raspberry Pi 3b+](https://www.amazon.com/CanaKit-Raspberry-Power-Supply-Listed/dp/B07BC6WH7V)
- ~$30 USD — [IOT Relay Power Strip](https://www.adafruit.com/product/2935)
- ~$8 USD  — [32GB Samsung EVO microSD card](https://www.amazon.com/Samsung-MicroSDHC-Adapter-MB-ME32GA-AM/dp/B06XWN9Q99)
