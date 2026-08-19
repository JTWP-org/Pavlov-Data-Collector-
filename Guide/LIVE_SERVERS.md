# 🌐 JTWP Live Pavlov Server Output Guide

This guide covers the live-server text/image pipeline under:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/
```

The `scripts/servers/` structure should be kept intact.

## 📁 Expected Structure

```text
scripts/servers/
├── build-string-array.sh
├── generate-server-image.py
├── LIVEserversArray.sh
├── LIVEserversIMG.sh
├── send-discord.sh
├── send-server-list.sh
├── serversRAW.json
├── servers.tsv
└── stringArray.txt
```

Generated files may not exist until the builder runs.

## 🌍 Source Data

The live-server builder consumes the Pavlov public API snapshot:

```text
/home/steam/jtwp-collector-data/global/pavlov_api/servers.json
```

Refresh it with:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

/home/steam/jtwp-collector/venv/bin/python3 \
    update_pavlov_api.py -c config.json
```

## 🔐 Discord Webhook

The server sender uses:

```text
JTWP_CMD_OUTPUT_WEBHOOK_URL
```

Keep it in:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Example:

```dotenv
JTWP_CMD_OUTPUT_WEBHOOK_URL=YOUR_DISCORD_WEBHOOK_URL
```

Do not hard-code the webhook into `LIVEserversIMG.sh` or another script.

## 🧱 Build the Server Files

Run:

```bash
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/build-string-array.sh
```

The cleaned scripts keep generated intermediate files in:

```text
scripts/servers/
```

Outputs include:

```text
serversRAW.json
servers.tsv
stringArray.txt
```

`servers.tsv` contains columns used by the image renderer such as:

```text
Players
Build
Name
Map
Region
Company
```

## 📝 Send the Text Server List

If the build already exists:

```bash
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/LIVEserversArray.sh
```

The sender uses `stringArray.txt`.

Server blocks are separated by:

```text
********************
```

so `send-discord.sh` can split large output without cutting one server block in
half.

## 🖼️ Generate and Send Images

Run:

```bash
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/LIVEserversIMG.sh
```

The script:

1. checks `.env`;
2. checks `servers.tsv`;
3. runs `generate-server-image.py`;
4. finds the generated `live-servers-*.png`;
5. sends each image through `send-discord.sh`.

Generated images are stored under the current Pavlov API output directory:

```text
/home/steam/jtwp-collector-data/global/pavlov_api/
```

Typical output:

```text
live-servers-1.png
live-servers-2.png
...
```

## 🧪 Build Without Sending Discord

The corrected builder supports:

```bash
JTWP_SKIP_DISCORD_SEND=1 \
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/build-string-array.sh
```

This is useful when testing formatting locally.

## 🧪 Test the Image Renderer Directly

```bash
/home/steam/jtwp-collector/venv/bin/python3 \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/generate-server-image.py \
    --tsv /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/servers.tsv \
    --output-dir /home/steam/jtwp-collector-data/global/pavlov_api
```

## 📦 Python Dependency

The image generator uses Pillow.

Install the project's requirements:

```bash
source /home/steam/jtwp-collector/venv/bin/activate

pip install -r \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/requirements.txt
```

Check Pillow:

```bash
/home/steam/jtwp-collector/venv/bin/python3 - <<'PY'
from PIL import Image
print("Pillow OK")
PY
```

## 🔎 Check Generated Files

```bash
ls -lh \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/
```

Preview the TSV:

```bash
column -ts $'\t' \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/servers.tsv \
    | head -30
```

Count servers:

```bash
jq '.servers | length' \
    /home/steam/jtwp-collector-data/global/pavlov_api/servers.json
```

## 🧹 Old Layout Warning

Older copies of these scripts referenced locations such as:

```text
global/pavlov_api-backup
project-root servers.tsv
project-root stringArray.txt
```

The cleaned layout uses:

```text
global/pavlov_api
scripts/servers/servers.tsv
scripts/servers/stringArray.txt
```

Do not mix old and new copies of the live-server scripts.

## 🚨 Webhook Exposure

If a Discord webhook URL ever appeared directly inside a script, screenshot,
chat, Git history or public repository, rotate that webhook.

Simply moving the value into `.env` does not invalidate an already exposed
credential.
