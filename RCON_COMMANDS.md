# 🎛️ JTWP Pavlov RCON Bridge

This guide documents the file-trigger RCON bridge and all commands currently defined in `rcon_commands.json`.

> [!IMPORTANT]
> Pavlov RCON authentication uses the **lowercase hexadecimal MD5 checksum** of the password on the wire.
> The `async-pavlov` library used by this project already performs that MD5 conversion internally.
> **Keep the normal/plaintext RCON password in `.env`. Do not pre-hash it for `rcon_trigger_watcher.py`.**

## 🔐 RCON Passwords

Example `.env`:

```bash
PAVLOVSERVER_RCON_PASSWORD=your_actual_rcon_password
PAVLOVSERVER0_RCON_PASSWORD=your_actual_rcon_password
PAVLOVSERVER1_RCON_PASSWORD=your_actual_rcon_password
```

Protect the file:

```bash
chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

`async-pavlov` hashes the password internally before authentication.

## 🧮 Manual MD5 Helper

The repository can include:

```text
scripts/rcon-md5.sh
```

Make it executable:

```bash
chmod +x scripts/rcon-md5.sh
```

Run it:

```bash
./scripts/rcon-md5.sh 'your-password'
```

Install system-wide:

```bash
sudo install -m 755 scripts/rcon-md5.sh /usr/local/bin/rcon-md5
```

Then:

```bash
rcon-md5 'your-password'
```

> [!NOTE]
> This helper is for testing/manual raw RCON work. The JTWP watcher should still receive the **plaintext** password through `.env`.

---

## 📁 ModSave Trigger Paths

```text
/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon
/home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon
```

The folder determines which Pavlov server receives the command.

## 🔄 IN → RCON → OUT

The ModKit creates an input file:

```text
IN-serverinfo.json
```

The watcher:

1. detects the `IN-*.json`;
2. removes any stale matching `OUT-*.json`;
3. validates the command and arguments;
4. sends the RCON command;
5. atomically writes `OUT-*.json`;
6. removes the `IN-*.json`.

Example:

```text
IN-serverinfo.json
        ↓
ServerInfo
        ↓
OUT-serverinfo.json
```

## 🧾 Example Output

```json
{
  "timestamp": "2026-08-17T00:00:00Z",
  "server_id": "pavlovserver1",
  "platform": "SHACK",
  "request": "serverinfo",
  "rcon_command": "ServerInfo",
  "success": true,
  "args": {},
  "response": {}
}
```

Errors are also returned as OUT files:

```json
{
  "server_id": "pavlovserver1",
  "request": "giveitem",
  "success": false,
  "error": "Missing required field: unique_id"
}
```

## 📚 Supported Commands

All commands below are currently marked `"supported": true`.

| Command | Arguments | Input | Output | Description |
|---|---|---|---|---|
| `AddMapRotation` | map_name_or_id, game_mode | `IN-addmaprotation.json` | `OUT-addmaprotation.json` | Adds the specified map with the specified game mode to the bottom of the map rotation. |
| `AddMod` | unique_id | `IN-addmod.json` | `OUT-addmod.json` | Adds the specified player to the moderator list, making them an admin. |
| `Ban` | unique_id | `IN-ban.json` | `OUT-ban.json` | Kicks and permanently bans the specified player from the server. |
| `Banlist` | None | `IN-banlist.json` | `OUT-banlist.json` | Lists the currently banned player UniqueIDs from blacklist.txt. |
| `ClearEmptyVehicles` | None | `IN-clearemptyvehicles.json` | `OUT-clearemptyvehicles.json` | Removes all vehicles that are not occupied by a player. |
| `Disconnect` | None | `IN-disconnect.json` | `OUT-disconnect.json` | Forces the server to close the RCON connection. |
| `EnableCompMode` | enabled | `IN-enablecompmode.json` | `OUT-enablecompmode.json` | Enables or disables competitive mode. |
| `EnableVerboseLogging` | enabled | `IN-enableverboselogging.json` | `OUT-enableverboselogging.json` | Enables or disables verbose logging. |
| `EnableWhitelist` | enabled | `IN-enablewhitelist.json` | `OUT-enablewhitelist.json` | Enables or disables whitelist usage. |
| `Gag` | unique_id, enabled | `IN-gag.json` | `OUT-gag.json` | Gags or ungags the specified player. |
| `GiveAll` | team_id, item_id | `IN-giveall.json` | `OUT-giveall.json` | Gives an item to all players on a team. |
| `GiveCash` | unique_id, cash_amount | `IN-givecash.json` | `OUT-givecash.json` | Gives the specified amount of cash to the specified player. |
| `GiveItem` | unique_id, item_id | `IN-giveitem.json` | `OUT-giveitem.json` | Equips the specified item to the specified player in the corresponding item slot. |
| `GiveTeamCash` | team_id, cash_amount | `IN-giveteamcash.json` | `OUT-giveteamcash.json` | Adds the specified amount of cash to each member of the specified team. |
| `Help` | None | `IN-help.json` | `OUT-help.json` | Returns the full list of commands and their parameters. |
| `InspectAll` | None | `IN-inspectall.json` | `OUT-inspectall.json` | Returns a list of InspectPlayer blocks for all players on the server. |
| `InspectPlayer` | unique_id | `IN-inspectplayer.json` | `OUT-inspectplayer.json` | Returns a detailed status for the specified player. |
| `InspectTeam` | team_id | `IN-inspectteam.json` | `OUT-inspectteam.json` | Returns a list of InspectPlayer blocks for all players on the specified team. |
| `ItemList` | None | `IN-itemlist.json` | `OUT-itemlist.json` | Lists all items in the game and the current map. |
| `Kick` | unique_id | `IN-kick.json` | `OUT-kick.json` | Kicks the specified player from the server. |
| `Kill` | unique_id | `IN-kill.json` | `OUT-kill.json` | Kills the specified player. |
| `MapList` | None | `IN-maplist.json` | `OUT-maplist.json` | Returns the current map rotation from Game.ini. |
| `ModeratorList` | None | `IN-moderatorlist.json` | `OUT-moderatorlist.json` | Returns a list of UniqueIDs of all moderators from mods.txt. |
| `PauseMatch` | [amount] | `IN-pausematch.json` | `OUT-pausematch.json` | Pauses the currently running match for the specified amount of seconds. |
| `RefreshList` | None | `IN-refreshlist.json` | `OUT-refreshlist.json` | Returns a list of all connected player names and their corresponding UniqueIDs. |
| `RemoveMapRotation` | map_name_or_id, game_mode | `IN-removemaprotation.json` | `OUT-removemaprotation.json` | Removes the first occurrence of the specified map and game mode combination from the map rotation. |
| `RemoveMod` | unique_id | `IN-removemod.json` | `OUT-removemod.json` | Removes the specified player from the moderator list. |
| `ResetSND` | None | `IN-resetsnd.json` | `OUT-resetsnd.json` | Resets the currently running SND match. |
| `RotateMap` | None | `IN-rotatemap.json` | `OUT-rotatemap.json` | Immediately changes the current map to the next map in the map rotation. |
| `ServerInfo` | None | `IN-serverinfo.json` | `OUT-serverinfo.json` | Returns server information such as server name, player count, current map and mode, and more. |
| `SetBalanceTableURL` | github_url | `IN-setbalancetableurl.json` | `OUT-setbalancetableurl.json` | Sets the balance table to load from the specified URL. |
| `SetBotsEnabled` | enabled | `IN-setbotsenabled.json` | `OUT-setbotsenabled.json` | Enables bots in the server and fills the server to the player limit with bots. |
| `SetCash` | unique_id, cash_amount | `IN-setcash.json` | `OUT-setcash.json` | Sets the cash of the specified player to the specified amount. |
| `SetLimitedAmmoType` | ammo_type | `IN-setlimitedammotype.json` | `OUT-setlimitedammotype.json` | Sets the ammo limitation type. |
| `SetMaxPlayers` | amount | `IN-setmaxplayers.json` | `OUT-setmaxplayers.json` | Sets the amount of slots on the server. |
| `SetPin` | [pin_number] | `IN-setpin.json` | `OUT-setpin.json` | Sets the server pin to the specified pin number. |
| `SetPlayerSkin` | unique_id, skin_id | `IN-setplayerskin.json` | `OUT-setplayerskin.json` | Sets the player skin of the specified player. |
| `SetTimeLimit` | amount | `IN-settimelimit.json` | `OUT-settimelimit.json` | Sets the time limit of the current match to the specified amount in seconds. |
| `ShowNametags` | enabled | `IN-shownametags.json` | `OUT-shownametags.json` | Enables or disables name tags above friendly players. |
| `ShutdownServer` | None | `IN-shutdownserver.json` | `OUT-shutdownserver.json` | Immediately shuts down the server. |
| `Slap` | unique_id, amount | `IN-slap.json` | `OUT-slap.json` | Deals the specified amount of damage directly to the specified player's health and ignores armor. |
| `SwitchMap` | map_id, [game_mode] | `IN-switchmap.json` | `OUT-switchmap.json` | Immediately switches to the specified map and game mode. |
| `SwitchTeam` | unique_id, team_id | `IN-switchteam.json` | `OUT-switchteam.json` | Kills and moves the specified player into the specified team. |
| `Teleport` | source_unique_id, target_unique_id | `IN-teleport.json` | `OUT-teleport.json` | Teleports the specified source player to the position of the specified target player. |
| `TTTAlwaysEnableSkinMenu` | enabled | `IN-tttalwaysenableskinmenu.json` | `OUT-tttalwaysenableskinmenu.json` | Trouble in Terrorist Town: Enables or disables the skin menu mid-round. |
| `TTTEndRound` | team_id | `IN-tttendround.json` | `OUT-tttendround.json` | Trouble in Terrorist Town: Ends the round. |
| `TTTFlushKarma` | None | `IN-tttflushkarma.json` | `OUT-tttflushkarma.json` | Trouble in Terrorist Town: Resets the karma of all players to 1200. |
| `TTTGiveCredits` | unique_id, amount | `IN-tttgivecredits.json` | `OUT-tttgivecredits.json` | Trouble in Terrorist Town: Adds the specified amount of TTT credits to the specified player. |
| `TTTPauseTimer` | enabled | `IN-tttpausetimer.json` | `OUT-tttpausetimer.json` | Trouble in Terrorist Town: Pauses the timer. |
| `TTTSetKarma` | unique_id, amount | `IN-tttsetkarma.json` | `OUT-tttsetkarma.json` | Trouble in Terrorist Town: Sets the karma of the specified player to the specified amount. |
| `TTTSetRole` | unique_id, role_id | `IN-tttsetrole.json` | `OUT-tttsetrole.json` | Trouble in Terrorist Town: Sets the TTT role of the specified player to the specified role. |
| `UGCAddMod` | ugc_mod_id | `IN-ugcaddmod.json` | `OUT-ugcaddmod.json` | Adds the specified mod to the server. |
| `UGCClearModList` | None | `IN-ugcclearmodlist.json` | `OUT-ugcclearmodlist.json` | Removes all mods from the server. |
| `UGCModList` | None | `IN-ugcmodlist.json` | `OUT-ugcmodlist.json` | Lists all mods currently on the server. |
| `UGCRemoveMod` | ugc_mod_id | `IN-ugcremovemod.json` | `OUT-ugcremovemod.json` | Removes the specified mod from the server. |
| `Unban` | unique_id | `IN-unban.json` | `OUT-unban.json` | Unbans the specified player so that they can join again. |
| `UpdateServerName` | name | `IN-updateservername.json` | `OUT-updateservername.json` | Changes the server name to the specified name. |

## 🧪 Input Examples

### `SetBotsEnabled`

`IN-setbotsenabled.json`

```json
{
  "enabled": true
}
```

### `GiveItem`

`IN-giveitem.json`

```json
{
  "unique_id": "12345678901234567",
  "item_id": "syringe"
}
```

### `SwitchMap`

`IN-switchmap.json`

```json
{
  "map_id": "datacenter",
  "game_mode": "SND"
}
```

### `SetLimitedAmmoType`

`IN-setlimitedammotype.json`

```json
{
  "ammo_type": 2
}
```

## ⚙️ `config.json`

```json
{
  "log_path": "/home/steam/pavlovserver1/Pavlov/Saved/Logs/",
  "platform": "auto",
  "rcon": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 9304,
    "password_env": "PAVLOVSERVER1_RCON_PASSWORD"
  }
}
```

## 📦 Install Dependencies

```bash
source /home/steam/jtwp-collector/venv/bin/activate
pip install -r requirements.txt
```

## ⚡ Install the RCON Watcher Service

```bash
sudo install -m 644 jtwp-rcon-trigger-watcher.service /etc/systemd/system/jtwp-rcon-trigger-watcher.service
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-rcon-trigger-watcher
```

Check status:

```bash
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

Follow logs:

```bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

## 🔐 Security Notes

- Never commit the real `.env`.
- Use strong, unique RCON passwords.
- Restrict RCON ports with the firewall where possible.
- The bridge only executes commands defined in `rcon_commands.json`.
- Commands such as `ShutdownServer`, `Ban`, `Kick`, `SetPin`, and map/mod mutation commands are administrative operations.
