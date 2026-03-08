PROGS    = gpio_control
CC       ?= gcc
CFLAGS   ?= -Wall -Wextra -Wpedantic -O2
LDFLAGS  ?= -lpigpio -lrt -lpthread

SYSTEMD_DIR = /usr/lib/systemd/system
SBINDIR     = /usr/sbin
BINDIR      = /usr/bin

.PHONY: all clean install uninstall lint lint-c lint-py

all: $(PROGS)

$(PROGS): $(PROGS).c
	@echo "Building $@"
	$(CC) $(CFLAGS) $@.c -o $@ $(LDFLAGS)

# ── Linting ─────────────────────────────────────────────────────────────────

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

install: $(PROGS)
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
	rm -vf $(PROGS)
