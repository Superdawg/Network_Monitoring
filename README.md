# Network Monitoring and Recovery

This suite is intended to be used on a Raspberry Pi controlling a power outlet
that powers a modem.  It will confirm whether internet access is available and
then act accordingly.

The `network_check.py` script is invoked on a schedule (default: every 30
minutes via the bundled systemd timer) to avoid rebooting the modem too
aggressively.  Since the connection could be down for reasons unrelated to the
modem, keep in mind that this tool will cycle the outlet regardless of root
cause.  Excessive cycling can cause wear, so consider tuning `--retry-count`
and `--retry-interval` appropriately.

If the internet is sufficiently deemed to be "down" (>50% packet loss to >50%
of targets) then `network_check.py` will invoke `gpio_control` (or any other
command you specify) to cycle the power outlet and reboot the modem.

## Default values

| Argument | Default | Notes |
|---|---|---|
| `--addresses` | `1.1.1.1 4.2.2.2 8.8.8.8` | Space-separated list of IPv4 addresses to ping |
| `--retry-count` | `2` | Rounds of pings before acting on failure |
| `--retry-interval` | `30` | Seconds between retries; consider `900` (15 min) in production |
| `--exec-on-fail` | _(none)_ | Command to run on confirmed failure |
| `--email-recipients` | _(none)_ | Space-separated list of email addresses to notify on failure |
| `--email-relay` | `localhost` | SMTP relay host to use when sending notifications |

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

# Edit the service file to set your email address and preferred GPIO pin
# before installing:
#   ExecStart=... --email-recipients you@example.com --exec-on-fail "..."
$EDITOR network_check.service

sudo make install

# Verify the timer is active
sudo systemctl list-timers --all | grep network_check
```

> **Important:** Edit `network_check.service` and replace `user@email.com`
> with a real address before running `sudo make install`.  The service will
> work without it, but you won't receive failure notifications.

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
- **Email queuing:** If the internet is down for an extended period, multiple
  failure emails may queue on the local MTA and be delivered in bulk once
  connectivity is restored.

## Equipment used

- ~$52 USD — [Raspberry Pi 3b+](https://www.amazon.com/CanaKit-Raspberry-Power-Supply-Listed/dp/B07BC6WH7V)
- ~$30 USD — [IOT Relay Power Strip](https://www.adafruit.com/product/2935)
- ~$8 USD  — [32GB Samsung EVO microSD card](https://www.amazon.com/Samsung-MicroSDHC-Adapter-MB-ME32GA-AM/dp/B06XWN9Q99)
