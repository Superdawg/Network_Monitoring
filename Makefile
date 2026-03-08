# ── Toolchain ─────────────────────────────────────────────────────────────────
CC      ?= gcc
CFLAGS  ?= -Wall -Wextra -Wpedantic -O2
LDFLAGS ?= -lpigpio -lrt -lpthread

# ── Install paths ─────────────────────────────────────────────────────────────
SYSTEMD_DIR = /usr/lib/systemd/system
SBINDIR     = /usr/sbin
BINDIR      = /usr/bin

# ── Service configuration ─────────────────────────────────────────────────────
# Override any of these on the command line, e.g.:
#   sudo make install EMAIL_RECIPIENTS="you@example.com" GPIO_PIN=23
#
PING_ADDRESSES    ?= 75.75.75.75 8.8.8.8 1.1.1.1
RETRY_INTERVAL    ?= 30
RETRY_COUNT       ?= 2
GPIO_PIN          ?= 23
GPIO_DELAY        ?= 30
EMAIL_RECIPIENTS  ?=
NOTIFY_STATE_FILE ?= /var/run/network_check.state
NOTIFY_COOLDOWN       ?= 3600
REBOOT_COOLDOWN       ?= 7200
TRACEROUTE_ADDRESS    ?=
REBOOT_HOP_THRESHOLD  ?= 2

# Build the optional --email-recipients argument only when a value is provided.
ifneq ($(EMAIL_RECIPIENTS),)
  EMAIL_ARG = --email-recipients $(EMAIL_RECIPIENTS)
else
  EMAIL_ARG =
endif

# Build the optional --traceroute-address argument only when a value is provided.
# --reboot-hop-threshold is bundled here because it is meaningless without a
# traceroute address.
ifneq ($(TRACEROUTE_ADDRESS),)
  TRACEROUTE_ARG = --traceroute-address $(TRACEROUTE_ADDRESS) --reboot-hop-threshold $(REBOOT_HOP_THRESHOLD)
else
  TRACEROUTE_ARG =
endif

# ── Targets ───────────────────────────────────────────────────────────────────
PROGS = gpio_control

.PHONY: all clean install uninstall lint lint-c lint-py

all: $(PROGS)

$(PROGS): $(PROGS).c
	@echo "Building $@"
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

# Generate the service file from the template, substituting configuration.
# This file is .gitignore'd so real credentials never land in version control.
network_check.service: network_check.service.in
	sed \
	  -e 's|@@PING_ADDRESSES@@|$(PING_ADDRESSES)|' \
	  -e 's|@@RETRY_INTERVAL@@|$(RETRY_INTERVAL)|' \
	  -e 's|@@RETRY_COUNT@@|$(RETRY_COUNT)|' \
	  -e 's|@@EMAIL_ARG@@|$(EMAIL_ARG)|' \
	  -e 's|@@GPIO_DELAY@@|$(GPIO_DELAY)|' \
	  -e 's|@@GPIO_PIN@@|$(GPIO_PIN)|' \
	  -e 's|@@NOTIFY_STATE_FILE@@|$(NOTIFY_STATE_FILE)|' \
	  -e 's|@@NOTIFY_COOLDOWN@@|$(NOTIFY_COOLDOWN)|' \
	  -e 's|@@REBOOT_COOLDOWN@@|$(REBOOT_COOLDOWN)|' \
	  -e 's|@@TRACEROUTE_ARG@@|$(TRACEROUTE_ARG)|' \
	  $< > $@

# ── Linting ───────────────────────────────────────────────────────────────────
lint: lint-c lint-py

lint-c:
	@echo "--- C lint (cppcheck) ---"
	cppcheck --enable=all --suppress=missingIncludeSystem $(PROGS).c
	@echo "--- C lint (gcc warnings) ---"
	$(CC) $(CFLAGS) -fsyntax-only $(PROGS).c

lint-py:
	@echo "--- Python lint (flake8) ---"
	flake8 --max-line-length=100 network_check.py
	@echo "--- Python lint (pylint) ---"
	pylint --max-line-length=100 network_check.py

# ── Install / Uninstall ───────────────────────────────────────────────────────
install: $(PROGS) network_check.service
	@echo "Installing gpio_control to $(SBINDIR)"
	install -m 4755 -o root -g root gpio_control $(SBINDIR)/gpio_control
	@echo "Installing network_check to $(BINDIR)"
	install -m 0755 -o nobody -g nogroup network_check.py $(BINDIR)/network_check
	@echo "Installing systemd units to $(SYSTEMD_DIR)"
	install -m 0644 -o root -g root network_check.timer   $(SYSTEMD_DIR)/network_check.timer
	install -m 0644 -o root -g root network_check.service $(SYSTEMD_DIR)/network_check.service
	@echo "Enabling and starting the network_check timer"
	systemctl daemon-reload
	systemctl enable network_check.timer
	systemctl start  network_check.timer

uninstall:
	@echo "Disabling and removing network_check timer"
	-systemctl stop    network_check.timer
	-systemctl disable network_check.timer
	rm -f $(SYSTEMD_DIR)/network_check.timer
	rm -f $(SYSTEMD_DIR)/network_check.service
	systemctl daemon-reload
	@echo "Removing installed binaries"
	rm -f $(SBINDIR)/gpio_control
	rm -f $(BINDIR)/network_check

clean:
	rm -vf $(PROGS) network_check.service
