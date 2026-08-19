# JTWP sudoers rules

These files reproduce the individual `/etc/sudoers.d/` rules shown from the
JTWP server.

Install them individually with `visudo` validation.

Example:

    sudo visudo -cf jtwp-clear-data
    sudo install -o root -g root -m 0440 jtwp-clear-data /etc/sudoers.d/jtwp-clear-data

Validate the complete sudo configuration afterward:

    sudo visudo -c

Then inspect the effective permissions for `steam`:

    sudo -l -U steam

## Files

- `jtwp-clear-data` — permits only `clear-data.sh --yes`.
- `jtwp-collector` — permits `scripts/run-collector.sh`.
- `jtwp-rcon` — permits `/usr/local/bin/restart-jtwp`.
- `jtwp-restart` — also permits `/usr/local/bin/restart-jtwp`; this duplicates
  the `jtwp-rcon` rule because both files currently exist on the server.
- `jtwp-ssh-autoblock` — retained as an empty compatibility file because the
  server copy shown contained no rule.
- `zz-jtwp-block-ip` — permits the root-owned block/unblock helpers with an
  argument.

The wildcard rules in `zz-jtwp-block-ip` should only be used if
`/usr/local/bin/block-ip` and `/usr/local/bin/unblock-ip` validate their input
and are owned by root and not writable by `steam`.
