🌉 JTWP RCON Bridge — Detailed Breakdown

The RCON Bridge is basically a translator between your Pavlov mod/server-side JSON files and Pavlov's RCON system.

Instead of the ModKit needing to directly open an RCON socket, authenticate, format commands, and parse responses, it can simply create a JSON file.

The overall flow is:

Pavlov Mod / ModSave
        │
        │ creates
        ▼
 IN-serverinfo.json
        │
        ▼
rcon_trigger_watcher.py
        │
        │ validates request
        │ connects to correct RCON server
        ▼
   Pavlov RCON
        │
        │ ServerInfo
        ▼
rcon_trigger_watcher.py
        │
        │ writes response
        ▼
OUT-serverinfo.json
        │
        ▼
   Pavlov Mod

Your watcher detects IN-*.json, validates the command and arguments, executes it through RCON, atomically creates the corresponding OUT-*.json, and removes the input trigger.

⚙️ Correct RCON Bridge Configuration

You're right that those defaults are outdated for your current directory layout.

You currently have defaults like:

DEFAULT_CONFIG = {
    "rcon_bridge": {
        "enabled": True,
        "poll_interval_seconds": 0.25,
        "command_file": "rcon_commands.json",
        "custom_command_file": "custom_commands.json",
        "game_modes_file": "game_modes.json",
        "default_maps_file": "default_maps.json",
        "limited_ammo_types_file": "limited_ammo_types.json",
        "remove_input_on_error": True,

Since your files actually live under resource/, I would change that to:

DEFAULT_CONFIG = {
    "rcon_bridge": {
        "enabled": True,

        "poll_interval_seconds": 0.25,

        "command_file": "resource/rcon_commands.json",

        "custom_command_file": "custom_commands.json",

        "game_modes_file": "resource/game_modes.json",

        "default_maps_file": "resource/default_maps.json",

        "limited_ammo_types_file": "resource/limitedAmmoTypes.json",

        "remove_input_on_error": True
    }
}

The important detail is your actual filename:

resource/limitedAmmoTypes.json

not:

resource/limited_ammo_types.json

Linux filenames are case-sensitive, so the config needs to match the real filename exactly.

Your resource directory therefore looks roughly like:

Pavlov-Data-Collector-/
│
├── rcon_trigger_watcher.py
├── config.json
├── custom_commands.json
├── .env
│
└── resource/
    ├── rcon_commands.json
    ├── game_modes.json
    ├── default_maps.json
    └── limitedAmmoTypes.json

Your existing documentation also establishes resource/ as the location for the bridge's static command/reference data.

🔌 1. What rcon_trigger_watcher.py Does

This is the actual bridge process.

It runs continuously in the background under:

jtwp-rcon-trigger-watcher.service

It isn't continuously sending RCON commands.

Most of the time it is simply looking for new:

IN-*.json

files.

The poll interval:

"poll_interval_seconds": 0.25

means approximately every ¼ second it checks whether there's work waiting.

So it's responsive without needing the Pavlov mod to directly communicate with the Python program.

📂 2. It Watches Every Configured Pavlov Server

Each Pavlov server gets its own trigger directory.

Your three directories are:

/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/

/home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon/

/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/

These are confirmed by the bridge documentation.

This is important because the directory determines which server receives the RCON command.

For example:

pavlovserver/
└── IN-serverinfo.json

means:

Run ServerInfo against pavlovserver.

While:

pavlovserver1/
└── IN-serverinfo.json

means:

Run ServerInfo against pavlovserver1.

That means the ModKit doesn't need to specify:

{
    "server": "pavlovserver1"
}

The location of the file already identifies the server.

🖥️ 3. Each Server Has Its Own RCON Connection

Your config.json connects the bridge directories to the appropriate RCON endpoint.

For example:

{
  "servers": [
    {
      "log_path": "/home/steam/pavlovserver/Pavlov/Saved/Logs/",
      "platform": "auto",
      "rcon": {
        "enabled": true,
        "host": "127.0.0.1",
        "port": 9000,
        "password_env": "PAVLOVSERVER_RCON_PASSWORD"
      }
    },
    {
      "log_path": "/home/steam/pavlovserver0/Pavlov/Saved/Logs/",
      "platform": "auto",
      "rcon": {
        "enabled": true,
        "host": "127.0.0.1",
        "port": 9100,
        "password_env": "PAVLOVSERVER0_RCON_PASSWORD"
      }
    },
    {
      "log_path": "/home/steam/pavlovserver1/Pavlov/Saved/Logs/",
      "platform": "auto",
      "rcon": {
        "enabled": true,
        "host": "127.0.0.1",
        "port": 9200,
        "password_env": "PAVLOVSERVER1_RCON_PASSWORD"
      }
    }
  ]
}

So conceptually:

pavlovserver
      │
      └── 127.0.0.1:9000

pavlovserver0
      │
      └── 127.0.0.1:9100

pavlovserver1
      │
      └── 127.0.0.1:9200
🔐 4. RCON Passwords Come From .env

The password itself should not be placed in config.json.

Instead:

"password_env": "PAVLOVSERVER_RCON_PASSWORD"

tells the watcher:

Look up the RCON password from this environment variable.

So your .env contains something like:

PAVLOVSERVER_RCON_PASSWORD=YOUR_PASSWORD
PAVLOVSERVER0_RCON_PASSWORD=YOUR_PASSWORD
PAVLOVSERVER1_RCON_PASSWORD=YOUR_PASSWORD

The bridge documentation specifically uses this arrangement so the passwords aren't stored in the public configuration.

📚 5. resource/rcon_commands.json

This is one of the most important parts.

resource/rcon_commands.json

acts as the bridge's RCON command definition database.

Instead of blindly taking a filename and sending arbitrary text to RCON, the watcher can look up the requested command.

For example:

IN-serverinfo.json

gives the request key:

serverinfo

The bridge looks that up and discovers that the actual Pavlov command is:

ServerInfo

So:

IN-serverinfo.json

        ↓

"serverinfo"

        ↓

resource/rcon_commands.json

        ↓

ServerInfo

        ↓

Pavlov RCON

This is a useful security boundary too: the bridge doesn't have to treat arbitrary file names as arbitrary shell/RCON commands.

🧾 6. Commands Without Arguments

ServerInfo doesn't need any arguments.

Therefore the trigger can simply contain:

{}

For example:

echo '{}' > /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-serverinfo.json

The watcher detects:

IN-serverinfo.json

and translates that into:

ServerInfo
📤 7. The Response

The watcher then creates:

OUT-serverinfo.json

An output is structured roughly like:

{
  "timestamp": "2026-08-17T00:00:00Z",
  "server_id": "pavlovserver",
  "platform": "SHACK",
  "request": "serverinfo",
  "rcon_command": "ServerInfo",
  "success": true,
  "args": {},
  "response": {}
}

Your bridge documentation defines that same response structure.

The actual RCON result goes into:

"response"

That lets the ModKit read one predictable JSON structure regardless of which RCON command was executed.

🕹️ 8. Commands With Arguments

The bridge becomes more useful when a command requires parameters.

For example:

IN-giveitem.json

might contain:

{
  "unique_id": "76561198000000000",
  "item_id": "syringe"
}

The bridge reads the command definition and knows it needs:

unique_id
item_id

It then constructs the appropriate RCON request.

Your documented GiveItem trigger uses exactly this structure.

🛡️ 9. Argument Validation

This is another reason rcon_commands.json exists.

Suppose the ModKit creates:

IN-giveitem.json

but only sends:

{
  "item_id": "syringe"
}

The bridge can determine that:

unique_id

is required.

Instead of sending a broken RCON command, it creates an error response such as:

{
  "server_id": "pavlovserver",
  "request": "giveitem",
  "success": false,
  "error": "Missing required field: unique_id"
}

That error behavior is built into the documented IN→OUT design.

So the ModKit still gets an answer.

That's a major advantage of this architecture.

🗺️ 10. resource/game_modes.json

This file gives the bridge a known list/reference for Pavlov game modes.

For example:

SND
TDM
DM
TTT
PUSH
CUSTOM

Commands involving a game mode can be checked against this resource instead of accepting completely arbitrary values.

An example is:

IN-switchmap.json

with:

{
  "map_id": "datacenter",
  "game_mode": "SND"
}

Your bridge documentation uses that exact SwitchMap trigger structure.

🗺️ 11. resource/default_maps.json

This provides the bridge with the known/default Pavlov map definitions used for commands involving maps.

For example, a request might contain:

{
  "map_id": "datacenter",
  "game_mode": "SND"
}

The bridge can use:

resource/default_maps.json

when validating/resolving the map.

🔫 12. resource/limitedAmmoTypes.json

Your actual file is:

resource/limitedAmmoTypes.json

So the config should use that exact spelling:

"limited_ammo_types_file": "resource/limitedAmmoTypes.json"

This reference is used by RCON operations dealing with Pavlov's limited-ammo mode/type values.

The config key can still be:

limited_ammo_types_file

Only the filename/path needs to match the actual file:

resource/limitedAmmoTypes.json
🧰 13. custom_commands.json

This is different from:

resource/rcon_commands.json

The distinction is important.

resource/rcon_commands.json

Describes Pavlov RCON commands.

Things like:

ServerInfo
InspectAll
GiveItem
SwitchMap
Ban
Kick
custom_commands.json

Describes JTWP/server-side commands.

Your bridge has used this for operations such as:

restartjtwp
runcollector
runpavlovapi
runssh
exportdata
backupdata
clearpavlovmods
cleardata

So think of them as:

rcon_commands.json
        │
        └── commands sent TO Pavlov RCON


custom_commands.json
        │
        └── commands performed BY the JTWP backend
🧹 14. remove_input_on_error

You have:

"remove_input_on_error": true

This is important.

Suppose:

IN-giveitem.json

is malformed.

If the bridge left it sitting there, then every 0.25 seconds the watcher could see it again and try to process it again.

With:

"remove_input_on_error": true

the failed trigger is removed.

So you don't get:

ERROR
ERROR
ERROR
ERROR
ERROR
...

from one bad input file.

🗑️ 15. Normal File Lifecycle

A successful request essentially goes through this lifecycle:

1. Mod creates:

   IN-serverinfo.json


2. Watcher sees:

   IN-serverinfo.json


3. Old response is removed if present:

   OUT-serverinfo.json


4. Watcher resolves:

   serverinfo
       ↓
   ServerInfo


5. Watcher validates arguments.


6. Watcher identifies server:

   /pavlovserver/.../Rcon/
            ↓
       pavlovserver


7. Config resolves RCON:

   pavlovserver
       ↓
   127.0.0.1:9000


8. Password is loaded:

   PAVLOVSERVER_RCON_PASSWORD


9. RCON connection is made.


10. Command is sent:

    ServerInfo


11. Pavlov responds.


12. Watcher creates:

    OUT-serverinfo.json


13. Watcher removes:

    IN-serverinfo.json


14. Mod reads:

    OUT-serverinfo.json

The documented implementation specifically removes stale output first, validates, executes, atomically writes the new output, and removes the input.

🔄 16. Special IN-RCON.json

You also have a special bridge trigger:

IN-RCON.json

This one doesn't execute the RCON command named RCON.

Instead, it refreshes the RCON command resource.

For example:

echo '{}' > /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-RCON.json

The watcher then downloads the current:

resource/rcon_commands.json

from your GitHub repository using wget, validates that the downloaded data is valid JSON, and only then replaces the local resource.

It then creates the special:

OUT--RCON.json

Yes, the double -- is intentional in the existing design.

That output contains the downloaded command definitions directly, allowing the ModKit to load the current RCON command catalog.

One thing we should correct

Your older documentation says the downloaded resource is saved to:

Pavlov-Data-Collector-/rcon_commands.json

Since you've now established that the real location is:

Pavlov-Data-Collector-/resource/rcon_commands.json

the refresh configuration/code should point there too. Otherwise the normal bridge and the resource updater could end up using two different copies.

🚦 17. How to Enable the Bridge in config.json

At minimum:

"rcon_bridge": {
  "enabled": true,
  "poll_interval_seconds": 0.25,

  "command_file": "resource/rcon_commands.json",
  "custom_command_file": "custom_commands.json",
  "game_modes_file": "resource/game_modes.json",
  "default_maps_file": "resource/default_maps.json",
  "limited_ammo_types_file": "resource/limitedAmmoTypes.json",

  "remove_input_on_error": true
}

And each server you want controllable must have:

"rcon": {
  "enabled": true,
  "host": "127.0.0.1",
  "port": 9000,
  "password_env": "PAVLOVSERVER_RCON_PASSWORD"
}

There are therefore two separate enable switches:

RCON Bridge
"rcon_bridge.enabled": true
             │
             └── allows bridge itself


Server RCON
"servers[].rcon.enabled": true
             │
             └── allows RCON for that server
⚡ 18. Enable the systemd Service

The Python bridge runs as:

jtwp-rcon-trigger-watcher.service

Your service is configured to run as steam, from the collector project directory, using the collector venv and .env.

Install the service with:

cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

sudo install -m 644 \
    jtwp-rcon-trigger-watcher.service \
    /etc/systemd/system/jtwp-rcon-trigger-watcher.service

sudo systemctl daemon-reload

Then enable it at boot and start it now:

sudo systemctl enable --now jtwp-rcon-trigger-watcher.service

Your existing installer performs the same daemon-reload and enable --now sequence.

🟢 19. Check Whether It's Running
sudo systemctl status jtwp-rcon-trigger-watcher.service

You want:

Active: active (running)

You can also do:

systemctl is-active jtwp-rcon-trigger-watcher.service

Expected:

active
👀 20. Watch It Live

This is probably the most useful command while testing:

sudo journalctl -u jtwp-rcon-trigger-watcher.service -f

Leave that terminal open.

Then create an RCON trigger from another terminal.

🧪 21. Full Manual Test

Start with the simplest possible command:

ServerInfo

For your first server:

cd /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/

Create:

echo '{}' > IN-serverinfo.json

Now:

ls -lah

You should shortly see:

OUT-serverinfo.json

and the original:

IN-serverinfo.json

should disappear.

Read the result:

jq . OUT-serverinfo.json

You should get something along the lines of:

{
  "timestamp": "...",
  "server_id": "pavlovserver",
  "platform": "SHACK",
  "request": "serverinfo",
  "rcon_command": "ServerInfo",
  "success": true,
  "args": {},
  "response": {
  }
}
🧪 22. Test Each Server
pavlovserver
echo '{}' > /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-serverinfo.json
pavlovserver0
echo '{}' > /home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-serverinfo.json
pavlovserver1
echo '{}' > /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-serverinfo.json

Then find all three outputs:

find /home/steam/pavlovserver* \
  -path '*/ModSave/JTWP/Rcon/OUT-serverinfo.json' \
  -print
🧠 The Simplest Way to Think About the Whole System

The bridge turns this:

JSON FILE

into this:

PAVLOV RCON COMMAND

and turns the answer back into:

JSON FILE

So your ModKit only needs to understand files:

         MOD
          │
          │ JSON
          ▼
     IN-*.json
          │
          ▼
┌─────────────────────┐
│ RCON TRIGGER WATCHER│
│                     │
│ • Detect request    │
│ • Identify server   │
│ • Find command      │
│ • Validate args     │
│ • Load password     │
│ • Connect RCON      │
│ • Execute command   │
│ • Capture response  │
└──────────┬──────────┘
           │
           ▼
       Pavlov RCON
           │
           ▼
┌─────────────────────┐
│ RCON TRIGGER WATCHER│
└──────────┬──────────┘
           │
           │ JSON
           ▼
      OUT-*.json
           │
           ▼
          MOD

And the resources give the bridge its rules:

resource/rcon_commands.json
        │
        └── What RCON commands exist
            + what arguments they require

resource/game_modes.json
        │
        └── Valid/known game modes

resource/default_maps.json
        │
        └── Known/default maps

resource/limitedAmmoTypes.json
        │
        └── Limited-ammo type definitions

custom_commands.json
        │
        └── JTWP backend/custom commands
