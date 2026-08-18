# 🤖 Discord Bot Setup Guide

This guide explains how to create a Discord bot, obtain its bot token,
invite it to your Discord server, and configure it for use with the
**JTWP RCON / administration bot tools**.

> 🔐 **Never share your bot token.**
>
> A Discord bot token authenticates the bot account. Anyone who obtains
> it may be able to operate the bot with the permissions you granted it.
> Do not post it in Discord, GitHub, screenshots, logs, or public
> configuration files.

------------------------------------------------------------------------

# 📋 What You Need

Before starting, you should have:

-   A Discord account.
-   A Discord server where you have permission to add/manage
    applications.
-   Access to the server running the JTWP tools.
-   The JTWP project installed and configured.
-   A `.env` file for storing the bot token.
-   Your Discord server, channel, and role IDs for the JTWP
    configuration.

The JTWP bot configuration expects the token through:

``` text
JTWP_DISCORD_BOT_TOKEN
```

The token should be stored in the project's `.env` file rather than
directly inside `config.json`.

------------------------------------------------------------------------

# 1️⃣ Create a Discord Application

Open the official Discord Developer Portal:

https://discord.com/developers/applications

Sign in with the Discord account that will own/manage the application.

Click:

``` text
New Application
```

Give the application a recognizable name, for example:

``` text
JTWP RCON Bot
```

Then create the application.

The Discord application is the container for your bot account and its
configuration.

------------------------------------------------------------------------

# 2️⃣ Create the Bot User

Inside your new application, open:

``` text
Bot
```

Create/add the bot user if Discord has not already created one for the
application.

You can configure things such as:

-   Bot username
-   Bot icon/avatar
-   Public/private installation settings
-   Gateway intents

For example:

``` text
JTWP RCON
```

------------------------------------------------------------------------

# 3️⃣ 🔑 Get the Bot Token

On the application's **Bot** page, locate the token controls.

Discord may require you to use **Reset Token** to generate/reveal a
token.

Copy the bot token.

It will look like a long random credential.

## 🚨 Treat the token like a password

Do **not**:

-   ❌ Put it in `config.json`
-   ❌ Commit it to GitHub
-   ❌ Paste it into Discord
-   ❌ Include it in screenshots
-   ❌ Post it in support messages
-   ❌ Store it in public logs
-   ❌ Hard-code it into `discord_bot.py`

If a token is accidentally exposed, return to the Discord Developer
Portal and reset it immediately. The old token should no longer be
treated as valid.

------------------------------------------------------------------------

# 4️⃣ Save the Token in `.env`

The JTWP Discord bot expects:

``` text
JTWP_DISCORD_BOT_TOKEN
```

Open your project `.env` file:

``` bash
nano /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Add:

``` bash
JTWP_DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
```

For example:

``` text
JTWP_DISCORD_BOT_TOKEN=PASTE_YOUR_TOKEN_HERE
```

Save the file.

## 🔒 Protect `.env`

Recommended permissions:

``` bash
chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Check:

``` bash
ls -l /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

You generally want the file accessible only to the account that needs
it.

------------------------------------------------------------------------

# 5️⃣ Test That the Token Is Loaded

You can load the `.env` into your current shell with:

``` bash
set -a
source /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
set +a
```

Then verify that the variable exists **without printing the token**:

``` bash
[[ -n "${JTWP_DISCORD_BOT_TOKEN:-}" ]] && echo "✅ Discord bot token loaded" || echo "❌ Discord bot token missing"
```

Expected result:

``` text
✅ Discord bot token loaded
```

Do not use:

``` bash
echo "$JTWP_DISCORD_BOT_TOKEN"
```

unless you specifically need to expose the secret on your own terminal.

------------------------------------------------------------------------

# 6️⃣ 📨 Enable Message Content Access

The JTWP bot uses prefix-style commands such as:

``` text
!serverinfo
!inspectall
!liveservers
```

For a bot that reads message text to process prefix commands, configure
the appropriate Gateway Intent on the application's **Bot** page.

Look for:

``` text
Privileged Gateway Intents
```

and enable the **Message Content Intent** when required by your bot
implementation.

Your Python bot must also request the corresponding intent.

> ⚠️ Discord applies additional rules to privileged intents for
> sufficiently large/verified bots. Check Discord's current Developer
> Portal requirements if you distribute the bot broadly.

------------------------------------------------------------------------

# 7️⃣ 🔗 Install / Invite the Bot

Use the installation/OAuth2 area of the Discord Developer Portal to
generate an installation link for your bot.

The bot needs the appropriate bot/app installation scope and only the
Discord permissions required by the features you intend to use.

Avoid granting `Administrator` merely because it is convenient.

A JTWP RCON bot commonly needs permissions such as:

``` text
View Channels
Send Messages
Embed Links
Attach Files
Read Message History
```

Depending on your specific bot features, additional permissions may be
required.

### 🛡️ Principle of least privilege

Give the bot only the permissions it actually needs.

The Linux-side JTWP owner/admin authorization is separate from Discord's
channel permissions.

------------------------------------------------------------------------

# 8️⃣ Add the Bot to Your Server

Open the generated installation/invite URL.

Choose the Discord server where you want the JTWP bot installed.

Approve the requested permissions.

After installation, the bot should appear in the server member list.

It may remain **offline** until `discord_bot.py` or its systemd service
is running.

------------------------------------------------------------------------

# 9️⃣ 🆔 Enable Discord Developer Mode

JTWP configuration uses Discord IDs for things such as:

-   Control channel
-   Admin role
-   Owner role

Enable Discord **Developer Mode** in your Discord client settings.

Once Developer Mode is enabled, Discord provides options to copy IDs
from channels, roles, users, servers, and other objects.

------------------------------------------------------------------------

# 🔟 Get the Control Channel ID

Choose the Discord channel where administrative bot commands should be
accepted.

Copy that channel's ID.

Your `config.json` uses:

``` json
"control_channel_id": "YOUR_CHANNEL_ID"
```

Example structure:

``` json
"discord_bot": {
  "enabled": true,
  "prefix": "!",
  "control_channel_id": "YOUR_CHANNEL_ID"
}
```

Channel restriction is important because it prevents administrative
commands from being accepted everywhere in the Discord server when that
restriction is enabled.

------------------------------------------------------------------------

# 1️⃣1️⃣ Create the Admin and Owner Roles

Create Discord roles for controlling access to the JTWP bot.

For example:

``` text
JTWP Admin
JTWP Owner
```

Copy each role ID.

Configure them in `config.json`:

``` json
"roles": {
  "admin": "ADMIN_ROLE_ID",
  "owner": "OWNER_ROLE_ID"
}
```

Your Discord bot configuration can then look similar to:

``` json
"discord_bot": {
  "enabled": true,
  "prefix": "!",
  "control_channel_id": "YOUR_CHANNEL_ID",

  "roles": {
    "admin": "ADMIN_ROLE_ID",
    "owner": "OWNER_ROLE_ID"
  },

  "token_env": "JTWP_DISCORD_BOT_TOKEN"
}
```

------------------------------------------------------------------------

# 👑 OWNER vs 🛡️ ADMIN

JTWP uses role separation because not every Discord user who can query
the server should be able to control the host.

## 🛡️ ADMIN

Admin users can be restricted to safe/read-oriented RCON commands such
as:

``` text
serverinfo
inspectall
maplist
inspectplayer
inspectteam
help
itemlist
banlist
ugcmodlist
```

The exact allowlist is controlled by your configuration.

Example:

``` json
"admin_allowed_rcon_commands": [
  "serverinfo",
  "inspectall",
  "maplist",
  "inspectplayer",
  "inspectteam",
  "help",
  "itemlist",
  "banlist",
  "ugcmodlist"
]
```

## 👑 OWNER

Owner access can include more powerful operations such as:

-   unrestricted configured RCON commands;
-   starting/stopping/restarting services;
-   enabling/disabling services;
-   maintenance commands;
-   running the collector;
-   running data/API updates;
-   clearing Pavlov mods;
-   backup/export/clear-data operations.

> ⚠️ Give the OWNER role only to people who should be trusted with
> host-level administrative capabilities exposed by your bot
> configuration.

------------------------------------------------------------------------

# 🎮 RCON Configuration

The Discord bot communicates with the Pavlov RCON configuration defined
for your servers.

Example:

``` json
{
  "log_path": "/home/steam/pavlovserver/Pavlov/Saved/Logs/",
  "platform": "auto",

  "rcon": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 9000,
    "password_env": "PAVLOVSERVER_RCON_PASSWORD"
  }
}
```

Notice that the RCON password is also referenced through an environment
variable.

Your `.env` can therefore contain:

``` bash
JTWP_DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
PAVLOVSERVER_RCON_PASSWORD=YOUR_RCON_PASSWORD
```

Do not put the actual RCON password into public documentation.

------------------------------------------------------------------------

# 🔐 Recommended `.env` Structure

A simplified example:

``` bash
# Discord
JTWP_DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN

# Pavlov RCON
PAVLOVSERVER_RCON_PASSWORD=YOUR_RCON_PASSWORD

# Stable private IP hashing
JTWP_IP_HASH_SECRET=YOUR_EXISTING_HASH_SECRET
```

Your real installation may contain additional secrets and API keys.

Keep `.env` private.

------------------------------------------------------------------------

# ⚙️ Enable the Discord Bot in `active.json`

The master Discord bot switch must be enabled:

``` json
"discord_bot": {
  "enabled": true
}
```

Then enable only the bot features you intend to use.

Example:

``` json
"discord_bot": {
  "enabled": true,

  "permissions": {
    "enabled": true,
    "admin_role": true,
    "owner_role": true,
    "channel_restriction": true
  },

  "rcon": {
    "enabled": true,
    "admin_limited_commands": true,
    "owner_all_commands": true,
    "response_embeds": true,
    "command_logging": true
  }
}
```

For a new installation, configure roles and channel restrictions
**before** exposing powerful RCON or system-control features.

------------------------------------------------------------------------

# ⚙️ systemctl Commands

The JTWP bot can optionally expose Linux service controls:

``` text
status
start
stop
restart
enable
disable
```

The relevant `active.json` section is:

``` json
"systemctl": {
  "enabled": true,
  "owner_only": true,
  "status": true,
  "start": true,
  "stop": true,
  "restart": true,
  "enable": true,
  "disable": true,
  "command_logging": true
}
```

> 🚨 Keep `owner_only` enabled for host-management commands.

Discord permissions alone are not a substitute for correctly restricting
host-level operations in the bot.

------------------------------------------------------------------------

# ▶️ Start the JTWP Discord Bot

If you installed the JTWP bot as a systemd service:

``` bash
sudo systemctl start jtwp-discord-bot.service
```

To automatically start it after reboot:

``` bash
sudo systemctl enable jtwp-discord-bot.service
```

Or enable and start it together:

``` bash
sudo systemctl enable --now jtwp-discord-bot.service
```

------------------------------------------------------------------------

# 👀 Watch the Bot Logs

Follow logs live:

``` bash
sudo journalctl -u jtwp-discord-bot.service -n 100 -f
```

You should eventually see the bot successfully connect/login.

Press:

``` text
Ctrl+C
```

to stop watching the journal.

This does **not** stop the bot service.

------------------------------------------------------------------------

# 📊 Check Bot Status

Run:

``` bash
sudo systemctl status jtwp-discord-bot.service --no-pager
```

You want to see the service running without repeated Python exceptions.

------------------------------------------------------------------------

# 🧪 Test the Bot

Go to your configured control channel.

Start with a safe/read-only command supported by your installation.

For example:

``` text
!serverinfo
```

or:

``` text
!help
```

If the bot responds, your basic path is working:

``` text
Discord
   ↓
Bot token
   ↓
discord_bot.py
   ↓
Role/channel permission checks
   ↓
RCON
   ↓
Pavlov server
   ↓
Discord response
```

------------------------------------------------------------------------

# ❌ Bot Is Online but Commands Do Nothing

Check the live journal while sending a command:

``` bash
sudo journalctl -u jtwp-discord-bot.service -f
```

Common causes include:

-   Message Content Intent is not configured as required.
-   Wrong command prefix.
-   Wrong control channel ID.
-   Wrong Admin role ID.
-   Wrong Owner role ID.
-   Command is disabled in `active.json`.
-   RCON is disabled.
-   RCON password is missing.
-   Command is not registered by the running bot version.
-   Bot lacks Discord channel permissions.
-   The service has not been restarted after configuration changes.

------------------------------------------------------------------------

# ❌ Bot Is Offline

Check:

``` bash
sudo systemctl status jtwp-discord-bot.service --no-pager
```

Then:

``` bash
sudo journalctl -u jtwp-discord-bot.service -n 100 --no-pager
```

Check that the token environment variable exists without printing it:

``` bash
set -a
source /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
set +a

[[ -n "${JTWP_DISCORD_BOT_TOKEN:-}" ]] && echo "TOKEN LOADED" || echo "TOKEN MISSING"
```

------------------------------------------------------------------------

# 🔄 Restart After Configuration Changes

After changing:

-   `.env`
-   `config.json`
-   `active.json`
-   Discord bot Python code
-   custom command definitions

restart the service:

``` bash
sudo systemctl restart jtwp-discord-bot.service
```

Then watch:

``` bash
sudo journalctl -u jtwp-discord-bot.service -n 100 -f
```

------------------------------------------------------------------------

# 🔑 Token Rotation

If you believe the token was exposed:

1.  Open the Discord Developer Portal.
2.  Select the JTWP bot application.
3.  Open **Bot**.
4.  Reset/regenerate the bot token.
5.  Replace the old value in `.env`.
6.  Restart the bot service.

For example:

``` bash
sudo systemctl restart jtwp-discord-bot.service
```

Do not continue using a token that has been publicly exposed.

------------------------------------------------------------------------

# 🚫 Do Not Use a Self-Bot

The JTWP tools should use an actual Discord **bot account** created
through a Discord application.

Do not place a normal Discord user-account token into:

``` text
JTWP_DISCORD_BOT_TOKEN
```

Discord prohibits automating normal user accounts ("self-bots"). Use the
official bot account/token system.

------------------------------------------------------------------------

# 🛡️ Recommended Security Checklist

Before considering the bot ready:

-   [ ] Bot was created through the Discord Developer Portal.
-   [ ] Bot token is stored in `.env`.
-   [ ] `.env` is not committed to Git.
-   [ ] `.env` permissions are restricted.
-   [ ] Message Content Intent is configured if required by the
    prefix-command implementation.
-   [ ] Control channel ID is configured.
-   [ ] Admin role ID is configured.
-   [ ] Owner role ID is configured.
-   [ ] Admin RCON commands are allowlisted.
-   [ ] Host/service controls are OWNER-only.
-   [ ] Destructive custom commands are OWNER-only.
-   [ ] RCON passwords are stored as environment variables.
-   [ ] Bot has only the Discord permissions it actually needs.
-   [ ] Bot logs do not expose secrets.
-   [ ] The bot service is enabled if it should start automatically.
-   [ ] A safe command has been tested before enabling powerful
    commands.

------------------------------------------------------------------------

# 🚀 Quick Setup Summary

``` text
1. Create Discord Application
          ↓
2. Create Bot
          ↓
3. Copy Bot Token
          ↓
4. Save token in .env
          ↓
5. Configure Message Content Intent if required
          ↓
6. Install bot in Discord server
          ↓
7. Copy control-channel ID
          ↓
8. Copy Admin + Owner role IDs
          ↓
9. Configure config.json
          ↓
10. Configure active.json
          ↓
11. Enable/start jtwp-discord-bot.service
          ↓
12. Watch journalctl
          ↓
13. Test a safe command
          ↓
14. Enable additional RCON/admin tools
```

------------------------------------------------------------------------

# 🔗 Official Discord Resources

Use Discord's official Developer Portal to create and configure the
application:

https://discord.com/developers/applications

For security, always use a real bot account and bot token rather than
automating a normal Discord user account.

------------------------------------------------------------------------

## ✅ Final Notes

The Discord bot is an administrative interface into the JTWP tools.

A normal Discord chatbot has relatively little authority. An
RCON/administration bot can potentially interact with Pavlov servers
and, depending on which JTWP features you enable, host services and
maintenance scripts.

Because of that, configure access in layers:

``` text
Discord permissions
        +
Control channel restriction
        +
ADMIN / OWNER roles
        +
JTWP active.json switches
        +
RCON command allowlists
        +
Linux permissions
```

🔐 **Keep the token private.**

🛡️ **Keep powerful commands restricted.**

🧪 **Start with safe commands and enable additional administration
features only after testing them.**
