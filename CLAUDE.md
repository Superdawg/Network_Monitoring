# CLAUDE.md — Development Guidelines for Network_Monitoring

## Project overview

A Raspberry Pi tool that monitors internet connectivity by pinging known hosts
and cycles a GPIO-controlled power outlet to reboot the modem on confirmed
failure.  The C binary (`gpio_control`) drives the GPIO pin; the Python script
(`network_check.py`) handles detection, state tracking, and notifications.

## Repository structure

| File | Purpose |
|---|---|
| `network_check.py` | Main monitoring script (Python 3) |
| `gpio_control.c` | GPIO pulse utility, compiled to `/usr/sbin/gpio_control` |
| `network_check.service.in` | systemd service template (contains `@@PLACEHOLDERS@@`) |
| `network_check.timer` | systemd timer (fires the service on schedule) |
| `Makefile` | Build, lint, install, and uninstall |
| `requirements.txt` | Python dependencies (`pingparsing`) |

`network_check.service` is **generated** at install time from the template and
is excluded from version control (see `.gitignore`).

## Code style

### Python
- Follow PEP 8.  Max line length is **100 characters**.
- Linting is enforced via `make lint-py` (flake8 + pylint).
- Run `make lint-py` and resolve all warnings before committing.
- Use `# TODO:` for known deferred work; use plain comments for design notes.
- Do not use bare `except Exception` — catch the specific exception type.

### C
- Compile with `-Wall -Wextra -Wpedantic`.
- Linting via `make lint-c` (cppcheck + `gcc -fsyntax-only`).
- Always initialise buffers before use (especially before `strcat`).
- Use `GPIO_SIZE` (not `sizeof(array)`) when iterating over the GPIO pin list.
- Call `gpioTerminate()` before any exit path.

## Makefile conventions

- `all` must be the **first** (default) target.
- All non-file targets must be listed in `.PHONY`.
- Compiler flags go in `CFLAGS`; linker flags in `LDFLAGS` — never inline them.
- Install paths (`SBINDIR`, `BINDIR`, `SYSTEMD_DIR`) are variables so they can
  be overridden.
- Service configuration (addresses, cooldowns, email, GPIO) lives in Makefile
  variables with `?=` defaults and is substituted into the service template at
  install time via `sed`.  Never hardcode site-specific values in tracked files.

## Adding a new configurable parameter

When adding a new argument to `network_check.py` that belongs in the service:

1. Add the argument to `parseArgs()` in `network_check.py`.
2. Add a corresponding `@@PLACEHOLDER@@` to `network_check.service.in`.
3. Add a `VAR ?= default` variable to the **Service configuration** section of
   the Makefile.
4. Add a `-e 's|@@PLACEHOLDER@@|$(VAR)|'` substitution to the
   `network_check.service` target in the Makefile.
5. Update the **Default values** table in `README.md`.
6. Update the example `sudo make install` command in `README.md` if the
   parameter is commonly overridden.

## Documentation

- Keep the **Default values** table in `README.md` in sync with `parseArgs()`
  defaults and Makefile variable defaults — all three should agree.
- Update `README.md` whenever behaviour, defaults, or install steps change.
- The synopsis comment at the top of `network_check.py` must list all accepted
  arguments.

## Commit messages

- Use an imperative subject line (≤72 chars): *"Add foo"*, *"Fix bar"*.
- Leave a blank line after the subject, then a paragraph explaining **why**
  the change was made and any non-obvious consequences.
- Co-author line: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

## Known open issues (C code)

The following bugs exist in `gpio_control.c` and have not yet been fixed:

- `sizeof(gpio)` on line 56 returns bytes (40), not elements (10) — use
  `GPIO_SIZE` instead.
- `char csv_pins[1024]` is uninitialised before `strcat()` — add
  `csv_pins[0] = '\0';` after declaration.
- `print_csv_pins` is declared `const char *` but has no `return` statement.
- Default `pin = 18` is not in the validated allowlist and is never checked.
- `gpioTerminate()` is never called before exit.
