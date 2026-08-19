    # 🎛️ JTWP Pavlov RCON Bridge

    This guide documents the file-trigger RCON bridge and all commands currently defined in `rcon_commands.json`.
    just simply make a json in the modsave folder with the cmd u want to run and the tool will delete it and make a
    new one with the output inside it 

### 🧭 What This Guide Covers

-   🎛️ **RCON commands** --- trigger Pavlov RCON commands from ModSave
    JSON files.

-   📥 **RCON resource trigger** --- use `IN-RCON.json` to retrieve the
    latest command definitions.

-   🔄 **IN → OUT workflow** --- understand how request and response
    files are handled.

-   🔐 **Authentication** --- configure RCON passwords safely.

-   ⚙️ **Configuration** --- configure the bridge through `config.json`.

-   ⚡ **Service management** --- start, restart, inspect, and
    troubleshoot the watcher.

    > \[!IMPORTANT\] Pavlov RCON authentication uses the **lowercase
    > hexadecimal MD5 checksum** of the password on the wire. The
    > `async-pavlov` library used by this project already performs that
    > MD5 conversion internally. **Keep the normal/plaintext RCON
    > password in `.env`. Do not pre-hash it for
    > `rcon_trigger_watcher.py`.**

    ## 🔐 RCON Passwords

    Example `.env`:

    ``` bash
    PAVLOVSERVER_RCON_PASSWORD=your_actual_rcon_password
    PAVLOVSERVER0_RCON_PASSWORD=your_actual_rcon_password
    PAVLOVSERVER1_RCON_PASSWORD=your_actual_rcon_password
    ```

    Protect the file:

    ``` bash
    chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
    ```

    `async-pavlov` hashes the password internally before authentication.

    ## 🧮 Manual MD5 Helper

    The repository can include:

    ``` text
    scripts/rcon-md5.sh
    ```

    Make it executable:

    ``` bash
    chmod +x scripts/rcon-md5.sh
    ```

    Run it:

    ``` bash
    ./scripts/rcon-md5.sh 'your-password'
    ```

    Install system-wide:

    ``` bash
    sudo install -m 755 scripts/rcon-md5.sh /usr/local/bin/rcon-md5
    ```

    Then:

    ``` bash
    rcon-md5 'your-password'
    ```
    u can use netcat to connnect to rcon from terminal like this 

    ```
    nc 127.0.0.1 PORT
    ```
    u can use the loopback ip 127.0.0.1 because the server is hosted on the same machine 

    > \[!NOTE\] This helper is for testing/manual raw RCON work. The
    > JTWP watcher should still receive the **plaintext** password
    > through `.env`.

    ------------------------------------------------------------------------

    ## 📁 ModSave Trigger Paths

    ``` text
    /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon
    /home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon
    /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon
    ```

    The folder determines which Pavlov server receives the command.

    ## 🔄 RCON File Trigger Flow

    The ModKit creates an input file:

    ``` text
    IN-serverinfo.json
    ```

    The watcher:

    1.  detects the `IN-*.json`;
    2.  removes any stale matching `OUT-*.json`;
    3.  validates the command and arguments;
    4.  sends the RCON command;
    5.  atomically writes `OUT-*.json`;
    6.  removes the `IN-*.json`.

    Example:

    ``` text
    IN-serverinfo.json
            ↓
    ServerInfo
            ↓
    OUT-serverinfo.json
    ```

    ## 🧾 RCON Response Examples

    ``` json
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

    ``` json
    {
      "server_id": "pavlovserver1",
      "request": "giveitem",
      "success": false,
      "error": "Missing required field: unique_id"
    }
    ```

    ## 📚 Supported RCON Commands

    All commands below are currently marked `"supported": true`.

      -----------------------------------------------------------------------------------------------------------------------------------------
      Command                     Arguments           Input                               Output                               Description
      --------------------------- ------------------- ----------------------------------- ------------------------------------ ----------------
      `AddMapRotation`            map_name_or_id,     `IN-addmaprotation.json`            `OUT-addmaprotation.json`            Adds the
                                  game_mode                                                                                    specified map
                                                                                                                               with the
                                                                                                                               specified game
                                                                                                                               mode to the
                                                                                                                               bottom of the
                                                                                                                               map rotation.

      `AddMod`                    unique_id           `IN-addmod.json`                    `OUT-addmod.json`                    Adds the
                                                                                                                               specified player
                                                                                                                               to the moderator
                                                                                                                               list, making
                                                                                                                               them an admin.

      `Ban`                       unique_id           `IN-ban.json`                       `OUT-ban.json`                       Kicks and
                                                                                                                               permanently bans
                                                                                                                               the specified
                                                                                                                               player from the
                                                                                                                               server.

      `Banlist`                   None                `IN-banlist.json`                   `OUT-banlist.json`                   Lists the
                                                                                                                               currently banned
                                                                                                                               player UniqueIDs
                                                                                                                               from
                                                                                                                               blacklist.txt.

      `ClearEmptyVehicles`        None                `IN-clearemptyvehicles.json`        `OUT-clearemptyvehicles.json`        Removes all
                                                                                                                               vehicles that
                                                                                                                               are not occupied
                                                                                                                               by a player.

      `Disconnect`                None                `IN-disconnect.json`                `OUT-disconnect.json`                Forces the
                                                                                                                               server to close
                                                                                                                               the RCON
                                                                                                                               connection.

      `EnableCompMode`            enabled             `IN-enablecompmode.json`            `OUT-enablecompmode.json`            Enables or
                                                                                                                               disables
                                                                                                                               competitive
                                                                                                                               mode.

      `EnableVerboseLogging`      enabled             `IN-enableverboselogging.json`      `OUT-enableverboselogging.json`      Enables or
                                                                                                                               disables verbose
                                                                                                                               logging.

      `EnableWhitelist`           enabled             `IN-enablewhitelist.json`           `OUT-enablewhitelist.json`           Enables or
                                                                                                                               disables
                                                                                                                               whitelist usage.

      `Gag`                       unique_id, enabled  `IN-gag.json`                       `OUT-gag.json`                       Gags or ungags
                                                                                                                               the specified
                                                                                                                               player.

      `GiveAll`                   team_id, item_id    `IN-giveall.json`                   `OUT-giveall.json`                   Gives an item to
                                                                                                                               all players on a
                                                                                                                               team.

      `GiveCash`                  unique_id,          `IN-givecash.json`                  `OUT-givecash.json`                  Gives the
                                  cash_amount                                                                                  specified amount
                                                                                                                               of cash to the
                                                                                                                               specified
                                                                                                                               player.

      `GiveItem`                  unique_id, item_id  `IN-giveitem.json`                  `OUT-giveitem.json`                  Equips the
                                                                                                                               specified item
                                                                                                                               to the specified
                                                                                                                               player in the
                                                                                                                               corresponding
                                                                                                                               item slot.

      `GiveTeamCash`              team_id,            `IN-giveteamcash.json`              `OUT-giveteamcash.json`              Adds the
                                  cash_amount                                                                                  specified amount
                                                                                                                               of cash to each
                                                                                                                               member of the
                                                                                                                               specified team.

      `Help`                      None                `IN-help.json`                      `OUT-help.json`                      Returns the full
                                                                                                                               list of commands
                                                                                                                               and their
                                                                                                                               parameters.

      `InspectAll`                None                `IN-inspectall.json`                `OUT-inspectall.json`                Returns a list
                                                                                                                               of InspectPlayer
                                                                                                                               blocks for all
                                                                                                                               players on the
                                                                                                                               server.

      `InspectPlayer`             unique_id           `IN-inspectplayer.json`             `OUT-inspectplayer.json`             Returns a
                                                                                                                               detailed status
                                                                                                                               for the
                                                                                                                               specified
                                                                                                                               player.

      `InspectTeam`               team_id             `IN-inspectteam.json`               `OUT-inspectteam.json`               Returns a list
                                                                                                                               of InspectPlayer
                                                                                                                               blocks for all
                                                                                                                               players on the
                                                                                                                               specified team.

      `ItemList`                  None                `IN-itemlist.json`                  `OUT-itemlist.json`                  Lists all items
                                                                                                                               in the game and
                                                                                                                               the current map.

      `Kick`                      unique_id           `IN-kick.json`                      `OUT-kick.json`                      Kicks the
                                                                                                                               specified player
                                                                                                                               from the server.

      `Kill`                      unique_id           `IN-kill.json`                      `OUT-kill.json`                      Kills the
                                                                                                                               specified
                                                                                                                               player.

      `MapList`                   None                `IN-maplist.json`                   `OUT-maplist.json`                   Returns the
                                                                                                                               current map
                                                                                                                               rotation from
                                                                                                                               Game.ini.

      `ModeratorList`             None                `IN-moderatorlist.json`             `OUT-moderatorlist.json`             Returns a list
                                                                                                                               of UniqueIDs of
                                                                                                                               all moderators
                                                                                                                               from mods.txt.

      `PauseMatch`                \[amount\]          `IN-pausematch.json`                `OUT-pausematch.json`                Pauses the
                                                                                                                               currently
                                                                                                                               running match
                                                                                                                               for the
                                                                                                                               specified amount
                                                                                                                               of seconds.

      `RefreshList`               None                `IN-refreshlist.json`               `OUT-refreshlist.json`               Returns a list
                                                                                                                               of all connected
                                                                                                                               player names and
                                                                                                                               their
                                                                                                                               corresponding
                                                                                                                               UniqueIDs.

      `RemoveMapRotation`         map_name_or_id,     `IN-removemaprotation.json`         `OUT-removemaprotation.json`         Removes the
                                  game_mode                                                                                    first occurrence
                                                                                                                               of the specified
                                                                                                                               map and game
                                                                                                                               mode combination
                                                                                                                               from the map
                                                                                                                               rotation.

      `RemoveMod`                 unique_id           `IN-removemod.json`                 `OUT-removemod.json`                 Removes the
                                                                                                                               specified player
                                                                                                                               from the
                                                                                                                               moderator list.

      `ResetSND`                  None                `IN-resetsnd.json`                  `OUT-resetsnd.json`                  Resets the
                                                                                                                               currently
                                                                                                                               running SND
                                                                                                                               match.

      `RotateMap`                 None                `IN-rotatemap.json`                 `OUT-rotatemap.json`                 Immediately
                                                                                                                               changes the
                                                                                                                               current map to
                                                                                                                               the next map in
                                                                                                                               the map
                                                                                                                               rotation.

      `ServerInfo`                None                `IN-serverinfo.json`                `OUT-serverinfo.json`                Returns server
                                                                                                                               information such
                                                                                                                               as server name,
                                                                                                                               player count,
                                                                                                                               current map and
                                                                                                                               mode, and more.

      `SetBalanceTableURL`        github_url          `IN-setbalancetableurl.json`        `OUT-setbalancetableurl.json`        Sets the balance
                                                                                                                               table to load
                                                                                                                               from the
                                                                                                                               specified URL.

      `SetBotsEnabled`            enabled             `IN-setbotsenabled.json`            `OUT-setbotsenabled.json`            Enables bots in
                                                                                                                               the server and
                                                                                                                               fills the server
                                                                                                                               to the player
                                                                                                                               limit with bots.

      `SetCash`                   unique_id,          `IN-setcash.json`                   `OUT-setcash.json`                   Sets the cash of
                                  cash_amount                                                                                  the specified
                                                                                                                               player to the
                                                                                                                               specified
                                                                                                                               amount.

      `SetLimitedAmmoType`        ammo_type           `IN-setlimitedammotype.json`        `OUT-setlimitedammotype.json`        Sets the ammo
                                                                                                                               limitation type.

      `SetMaxPlayers`             amount              `IN-setmaxplayers.json`             `OUT-setmaxplayers.json`             Sets the amount
                                                                                                                               of slots on the
                                                                                                                               server.

      `SetPin`                    \[pin_number\]      `IN-setpin.json`                    `OUT-setpin.json`                    Sets the server
                                                                                                                               pin to the
                                                                                                                               specified pin
                                                                                                                               number.

      `SetPlayerSkin`             unique_id, skin_id  `IN-setplayerskin.json`             `OUT-setplayerskin.json`             Sets the player
                                                                                                                               skin of the
                                                                                                                               specified
                                                                                                                               player.

      `SetTimeLimit`              amount              `IN-settimelimit.json`              `OUT-settimelimit.json`              Sets the time
                                                                                                                               limit of the
                                                                                                                               current match to
                                                                                                                               the specified
                                                                                                                               amount in
                                                                                                                               seconds.

      `ShowNametags`              enabled             `IN-shownametags.json`              `OUT-shownametags.json`              Enables or
                                                                                                                               disables name
                                                                                                                               tags above
                                                                                                                               friendly
                                                                                                                               players.

      `ShutdownServer`            None                `IN-shutdownserver.json`            `OUT-shutdownserver.json`            Immediately
                                                                                                                               shuts down the
                                                                                                                               server.

      `Slap`                      unique_id, amount   `IN-slap.json`                      `OUT-slap.json`                      Deals the
                                                                                                                               specified amount
                                                                                                                               of damage
                                                                                                                               directly to the
                                                                                                                               specified
                                                                                                                               player's health
                                                                                                                               and ignores
                                                                                                                               armor.

      `SwitchMap`                 map_id,             `IN-switchmap.json`                 `OUT-switchmap.json`                 Immediately
                                  \[game_mode\]                                                                                switches to the
                                                                                                                               specified map
                                                                                                                               and game mode.

      `SwitchTeam`                unique_id, team_id  `IN-switchteam.json`                `OUT-switchteam.json`                Kills and moves
                                                                                                                               the specified
                                                                                                                               player into the
                                                                                                                               specified team.

      `Teleport`                  source_unique_id,   `IN-teleport.json`                  `OUT-teleport.json`                  Teleports the
                                  target_unique_id                                                                             specified source
                                                                                                                               player to the
                                                                                                                               position of the
                                                                                                                               specified target
                                                                                                                               player.

      `TTTAlwaysEnableSkinMenu`   enabled             `IN-tttalwaysenableskinmenu.json`   `OUT-tttalwaysenableskinmenu.json`   Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Enables or
                                                                                                                               disables the
                                                                                                                               skin menu
                                                                                                                               mid-round.

      `TTTEndRound`               team_id             `IN-tttendround.json`               `OUT-tttendround.json`               Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Ends the round.

      `TTTFlushKarma`             None                `IN-tttflushkarma.json`             `OUT-tttflushkarma.json`             Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Resets the karma
                                                                                                                               of all players
                                                                                                                               to 1200.

      `TTTGiveCredits`            unique_id, amount   `IN-tttgivecredits.json`            `OUT-tttgivecredits.json`            Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Adds the
                                                                                                                               specified amount
                                                                                                                               of TTT credits
                                                                                                                               to the specified
                                                                                                                               player.

      `TTTPauseTimer`             enabled             `IN-tttpausetimer.json`             `OUT-tttpausetimer.json`             Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Pauses the
                                                                                                                               timer.

      `TTTSetKarma`               unique_id, amount   `IN-tttsetkarma.json`               `OUT-tttsetkarma.json`               Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Sets the karma
                                                                                                                               of the specified
                                                                                                                               player to the
                                                                                                                               specified
                                                                                                                               amount.

      `TTTSetRole`                unique_id, role_id  `IN-tttsetrole.json`                `OUT-tttsetrole.json`                Trouble in
                                                                                                                               Terrorist Town:
                                                                                                                               Sets the TTT
                                                                                                                               role of the
                                                                                                                               specified player
                                                                                                                               to the specified
                                                                                                                               role.

      `UGCAddMod`                 ugc_mod_id          `IN-ugcaddmod.json`                 `OUT-ugcaddmod.json`                 Adds the
                                                                                                                               specified mod to
                                                                                                                               the server.

      `UGCClearModList`           None                `IN-ugcclearmodlist.json`           `OUT-ugcclearmodlist.json`           Removes all mods
                                                                                                                               from the server.

      `UGCModList`                None                `IN-ugcmodlist.json`                `OUT-ugcmodlist.json`                Lists all mods
                                                                                                                               currently on the
                                                                                                                               server.

      `UGCRemoveMod`              ugc_mod_id          `IN-ugcremovemod.json`              `OUT-ugcremovemod.json`              Removes the
                                                                                                                               specified mod
                                                                                                                               from the server.

      `Unban`                     unique_id           `IN-unban.json`                     `OUT-unban.json`                     Unbans the
                                                                                                                               specified player
                                                                                                                               so that they can
                                                                                                                               join again.

      `UpdateServerName`          name                `IN-updateservername.json`          `OUT-updateservername.json`          Changes the
                                                                                                                               server name to
                                                                                                                               the specified
                                                                                                                               name.
      -----------------------------------------------------------------------------------------------------------------------------------------

    ## 📥 `IN-RCON.json` --- RCON Resource Trigger

    `IN-RCON.json` is a **special file trigger** handled by
    `rcon_trigger_watcher.py`. Unlike normal `IN-*.json` files, it does
    **not** send a command to Pavlov RCON.

    It provides the ModKit with a simple way to request the latest
    `rcon_commands.json` resource.

    \### 🔄 Trigger Flow

    ``` text
    IN-RCON.json
         ↓
    rcon_trigger_watcher.py
         ↓
    wget latest rcon_commands.json from GitHub
         ↓
    validate downloaded JSON
         ↓
    replace local rcon_commands.json
         ↓
    reload command definitions
         ↓
    OUT--RCON.json
    ```

    > \[!IMPORTANT\] `IN-RCON.json` must be intercepted as a resource
    > trigger **before** the normal `IN-*.json` RCON handler. If an
    > older watcher handles it as a normal command, it will return
    > `Unknown RCON command key: rcon`.

    \### 📁 Trigger Location

    Create the file in the same server-specific ModSave RCON folder used
    for normal requests:

    ``` text
    /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-RCON.json
    /home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-RCON.json
    /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-RCON.json
    ```

    The trigger contents can simply be valid empty JSON:

    ``` json
    {}
    ```

    \### 🌐 Resource Download

    When the watcher detects the trigger, it uses `wget` to retrieve:

    ``` text
    https://raw.githubusercontent.com/JTWP-org/Pavlov-Data-Collector-/refs/heads/main/resource/rcon_commands.json
    ```

    The downloaded file is validated as JSON before replacing the
    existing local copy.

    The validated resource is saved to:

    ``` text
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/rcon_commands.json
    ```

    If the download is invalid or fails, the existing local
    `rcon_commands.json` is left untouched.

    \### 📤 Response File

    After a successful refresh, the watcher writes:

    ``` text
    OUT--RCON.json
    ```

    to the same ModSave RCON folder that requested it.

    The double hyphen in `OUT--RCON.json` is intentional.

    `OUT--RCON.json` contains the **downloaded RCON command resource
    directly** rather than the normal RCON response wrapper. This makes
    it easy for the ModKit to load and inspect the available command
    definitions.

    \### 🗑️ Trigger Cleanup

    The watcher removes:

    ``` text
    IN-RCON.json
    ```

    before running `wget`, preventing the same request from being
    processed repeatedly.

    Any stale `OUT--RCON.json` for the request is removed before the new
    response is generated.

    \### 🧪 Manual Test

    For `pavlovserver1`:

    ``` bash
    echo '{}' > \
    /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-RCON.json
    ```

    Then check the response:

    ``` bash
    jq . \
    /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/OUT--RCON.json
    ```

    You can also confirm that the local resource was updated:

    ``` bash
    jq empty \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/rcon_commands.json \
    && echo "✅ Local RCON resource is valid"
    ```

    \### 👀 Watch the Service

    ``` bash
    sudo journalctl -u jtwp-rcon-trigger-watcher -f
    ```

    A successful request should produce messages similar to:

    ``` text
    [RCON-RESOURCE] IN-RCON.json detected.
    [RCON-RESOURCE] Downloading latest command resource with wget...
    [RCON-RESOURCE] Local rcon_commands.json updated.
    [RCON-RESOURCE] Wrote OUT--RCON.json.
    ```

    \### ❌ `Unknown RCON command key: rcon`

    If the response looks like:

    ``` json
    {
      "request": "rcon",
      "success": false,
      "error": "Unknown RCON command key: rcon"
    }
    ```

    the running watcher is treating `IN-RCON.json` as a normal RCON
    request. This usually means the service is still running an older
    version of `rcon_trigger_watcher.py`.

    Check which script systemd starts:

    ``` bash
    sudo systemctl cat jtwp-rcon-trigger-watcher
    ```

    Confirm the installed watcher contains the resource-trigger code:

    ``` bash
    grep -n "RCON-RESOURCE\|IN-RCON.json" \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/rcon_trigger_watcher.py
    ```

    Then restart it after updating:

    ``` bash
    sudo systemctl restart jtwp-rcon-trigger-watcher
    ```

    \### ⚙️ Resource Trigger Configuration

    The feature can be configured under `rcon_bridge` in `config.json`:

    ``` json
    {
      "rcon_bridge": {
        "rcon_resource_trigger_enabled": true,
        "rcon_resource_trigger_file": "IN-RCON.json",
        "rcon_resource_output_file": "OUT--RCON.json",
        "rcon_resource_url": "https://raw.githubusercontent.com/JTWP-org/Pavlov-Data-Collector-/refs/heads/main/resource/rcon_commands.json",
        "rcon_resource_local_file": "rcon_commands.json",
        "rcon_resource_timeout_seconds": 30
      }
    }
    ```

    `wget` must be installed on the host:

    ``` bash
    command -v wget
    ```

    If it is missing:

    ``` bash
    sudo apt install wget -y
    ```

    ------------------------------------------------------------------------

    ## 🧪 RCON Input Examples

    \### `SetBotsEnabled`

    `IN-setbotsenabled.json`

    ``` json
    {
      "enabled": true
    }
    ```

    \### `GiveItem`

    `IN-giveitem.json`

    ``` json
    {
      "unique_id": "12345678901234567",
      "item_id": "syringe"
    }
    ```

    \### `SwitchMap`

    `IN-switchmap.json`

    ``` json
    {
      "map_id": "datacenter",
      "game_mode": "SND"
    }
    ```

    \### `SetLimitedAmmoType`

    `IN-setlimitedammotype.json`

    ``` json
    {
      "ammo_type": 2
    }
    ```

    ## ⚙️ RCON Configuration

    ``` json
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

    ``` bash
    source /home/steam/jtwp-collector/venv/bin/activate
    pip install -r requirements.txt
    ```

    ## ⚡ RCON Watcher Service

    ``` bash
    sudo install -m 644 jtwp-rcon-trigger-watcher.service /etc/systemd/system/jtwp-rcon-trigger-watcher.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now jtwp-rcon-trigger-watcher
    ```

    Check status:

    ``` bash
    sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
    ```

    Follow logs:

    ``` bash
    sudo journalctl -u jtwp-rcon-trigger-watcher -f
    ```

    \### 🔧 Useful Service Commands

Restart the watcher after updating its Python file or configuration:

``` bash
sudo systemctl restart jtwp-rcon-trigger-watcher
```

Check its current status:

``` bash
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

View recent logs:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -n 100 --no-pager
```

Follow logs live:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

------------------------------------------------------------------------

------------------------------------------------------------------------

## 🛡️ Security Notes

    - Never commit the real `.env`.
    - Use strong, unique RCON passwords.
    - Restrict RCON ports with the firewall where possible.
    - The bridge only executes commands defined in `rcon_commands.json`.
    - Commands such as `ShutdownServer`, `Ban`, `Kick`, `SetPin`, and map/mod mutation commands are administrative operations.


---

# 🖥️ Adding Another Pavlov Server

For another server such as `pavlovserver2`, add its server entry to
`config.json`, use its own RCON port, and give it its own password variable:

```dotenv
PAVLOVSERVER2_RCON_PASSWORD=YOUR_RCON_PASSWORD
```

The ModSave trigger directory follows the same structure:

```text
/home/steam/pavlovserver2/Pavlov/Saved/Config/ModSave/JTWP/Rcon
```

After changing server definitions:

```bash
sudo systemctl restart jtwp-rcon-trigger-watcher.service
sudo journalctl -u jtwp-rcon-trigger-watcher.service -n 100 -f
```

# 🔌 Basic Connectivity Test

Before debugging the bridge, verify that something is listening on the RCON
port:

```bash
ss -lntp | grep ':9000'
```

Replace `9000` with the configured server's RCON port.

A local raw connection can be opened with:

```bash
nc 127.0.0.1 PORT
```

The Python watcher should still receive the normal plaintext RCON password from
its configured environment variable; do not pre-hash that value.
