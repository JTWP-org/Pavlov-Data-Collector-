# Guide Cleanup Notes

## Main redundancy removed

- Replaced the old release-style `FULL_CODE_UPDATE` document with one canonical
  installation/update procedure.
- Made `SERVICES.md` the canonical systemd guide.
- Made `SCRIPTS.md` the canonical helper-script installation guide.
- Made `API_SETUP.md` the canonical `.env` / API / secret guide.
- Kept `USEFUL_COMMANDS.md` as a cheat sheet rather than another setup guide.
- Added `README.md` to define where future instructions belong.

## Missing instructions added

- Full expected project layout, including preserved `scripts/` and `servers/`.
- OS dependencies and Python virtual-environment setup.
- `requirements.txt` installation.
- Safe first-run and update order.
- Python `compileall` validation before service restarts.
- Collector data-directory creation and permission checks.
- Correct collector timer stop/disable procedure.
- Stop/disable commands for the JTWP service stack.
- `systemd-analyze verify`, `systemctl cat`, and runtime-property checks.
- Guidance for `.tmp`/`os.replace` permission/path failures.
- Current environment-variable naming and a command to discover `os.getenv`
  variables directly from source.
- Additional maintenance/data scripts.
- Shell/Python script syntax checks.
- `pavlovserver2` RCON setup pattern.
- RCON listening-port check with `ss`.
- Recursive grep examples.
- One-pass health check.

## Important cleanup policy

Some detailed guides still contain a few repeated commands on purpose when the
command is necessary to test that component. Large duplicated setup procedures
are no longer supposed to be maintained in multiple files.

## Second pass additions

Added six missing canonical guides:

- `BACKUP_AND_RESTORE.md`
- `DATA_LAYOUT.md`
- `TROUBLESHOOTING.md`
- `SECURITY_AND_SUDOERS.md`
- `LIVE_SERVERS.md`
- `CONFIG_REFERENCE.md`

Also updated `README.md`, `INSTALL_AND_UPDATE.md`, `API_SETUP.md`,
`SCRIPTS.md`, and `SERVICES.md` so those new documents are linked from the
places where users will naturally look for them.
