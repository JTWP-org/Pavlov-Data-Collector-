# Additional JTWP script fixes

- `block-ip.sh`: fixed outbound UFW rule (`deny out to`) instead of accidentally adding the inbound rule twice.
- `generate-server-image.py`: changed stale `global/pavlov_api-backup` input directory to current `global/pavlov_api`.
- `update-pavlov-api.sh`: corrected project/venv/config/.env paths for the current `/home/steam/jtwp-collector/Pavlov-Data-Collector-` layout.
- `set-rcon-loop.py`: changed atomic JSON writes to unique same-directory temporary files to avoid `.tmp` collisions.
- `clear-pavlov-mods.sh`: removed `pavlovserver2` from the hard-coded server map because the current collector configuration supplied earlier only defines pavlovserver, pavlovserver0, and pavlovserver1.
- Normalized duplicate-upload filenames (`(1)`, `(2)`) in this package.
- All Python files pass `python3 -m py_compile`.
- All shell files pass `bash -n`.
