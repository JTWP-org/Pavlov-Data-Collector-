# JTWP scripts/servers fixes

All files in this package are intended for:

`/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/`

Key fixes:
- All generated intermediate files now stay in `scripts/servers/`.
- Pavlov API input/output now uses `global/pavlov_api` instead of the old `pavlov_api-backup`.
- Removed the accidental bare executable path from `LIVEserversIMG.sh`.
- Removed the hard-coded Discord webhook from `LIVEserversIMG.sh`; it now reads `JTWP_CMD_OUTPUT_WEBHOOK_URL` from `.env`.
- `generate-server-image.py` now generates paginated `live-servers-1.png`, `live-servers-2.png`, etc., matching `LIVEserversIMG.sh`.
- Added text truncation so long map/provider values do not run into adjacent columns.
- `LIVEserversArray.sh` now reads `scripts/servers/stringArray.txt`.
- `send-server-list.sh` is now a compatibility wrapper around `send-discord.sh`, avoiding duplicate Discord-send logic.
- Added environment overrides for testing/portability where useful.
- Shell files pass `bash -n`.
- Python image generator passes `py_compile`.
- Image generator was smoke-tested using the uploaded `servers.tsv`.
