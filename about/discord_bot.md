🤖 What the Discord bot handles

Area	What the bot does

🔐 Permissions & Security	Checks Discord roles for ADMIN, SENIOR_ADMIN, and OWNER; restricts sensitive commands to the configured control channel; limits which RCON commands regular admins can execute. 
📝 Command Auditing	Records Discord actions to global/discord/commands.jsonl, including who ran the command, permission level, success/failure, and command-specific details.
📡 Webhook Log Forwarding	Watches command/moderation JSONL logs and forwards new entries to Discord webhooks. It remembers file offsets so restarting the bot doesn't normally resend the entire log. 
🎮 RCON Control	Connects directly to configured Pavlov servers through RCON and executes normal Pavlov and RCON Plus commands. /rcon has autocomplete and supports custom commands. Ban is deliberately blocked so bans go through moderation instead. 
👤 Player Database Access	Resolves players using name/ProductID/UniqueID and reads player records, name history, stats, weapon stats, network records, and complete player dumps. 
🏆 Badges	Loads the badge definitions from resource/badges.json, displays earned badges, awards badges manually, stores badge ownership, and automatically gives the Discord-link badge when appropriate. 
🔗 Account Linking	Links a Discord user to a JTWP player record, optionally retrieves Steam information, creates pending verification requests, allows admins to approve links, permits unlinking, and rebuilds Discord/Steam lookup indexes. 
📊 Personal Account Data	Lets linked users retrieve their own JTWP player data and their latest 10 play sessions without exposing private IP/network information. 
⚖️ Moderation Cases	Creates and stores moderation cases for reports, warnings, and bans. Cases have unique IDs and maintain their own JSON records. 
🗳️ Moderation Voting	Admins can approve, reject, or escalate cases. Cases can also be categorized and assigned specific JTWP rules. 
⚠️ Warnings	/warn creates a formal warning case for a resolved player and posts it through the moderation system. 
🔨 Ban Management	Creates proposed ban cases, applies temporary bans and permanent bans, records active bans, and tracks them independently by moderation case/server. 
⏰ Automatic Unbans	Runs a background expiry checker. Temporary bans survive bot restarts and are automatically removed through RCON when they expire. 
📢 Player Reports	/report player opens a Discord modal where users enter the player, incident description, evidence, and optional Discord ID. The bot creates a moderation case from it. 
🔒 Verified Network Connections	Admins can add/remove trusted ipHASH values and attach labels/notes to them. The verified connection list is separate from Discord/player account verification. 
🛡️ DDoS Dashboard	Calls /usr/local/bin/jtwp-read-ddos-stats, builds a Discord network-security embed, shows traffic/rates/top destination ports/detection status, and continuously updates one persistent Discord message. 
🗂️ Player Index Access	Allows admins to download lists of player names, ProductIDs, UniqueIDs, and IP hashes. It can also report counts/status of the collector's indexes and rebuild backups. 
📦 Data Export	OWNER can run the collector's export-data.py script from Discord. 
💾 Data Backup	OWNER can run backup-data.py directly through Discord. 
🚀 Run Collector	OWNER can manually execute collector.py from Discord rather than waiting for its scheduled run. 
🌐 Pavlov API Update	OWNER can manually run update_pavlov_api.py. 
🔄 Restart JTWP Stack	/jtwp restart invokes /usr/local/bin/restart-jtwp using passwordless sudo. 
🖥️ Pavlov Service Control	OWNER can execute allowed systemctl operations against configured Pavlov server services—such as start, stop, restart, enable, disable, and status. 
🧹 Clear Pavlov Mods	OWNER can invoke /usr/local/bin/clear-pavlov-mods for a selected Pavlov server. 
🔗 Server URL Management	OWNER can attach/update a public URL in a server's stored server.json, including who changed it and when. 
📂 Server Data Viewer	Admins can dump non-private server information such as maps, mods, bans, rounds, and server settings while deliberately excluding sensitive RCON/SSH/network host files. 
🔁 RCON Loop Control	OWNER can start/stop the RCON polling loop and specify its polling interval. Admins can view its current control/output state. 


⚖️ Moderation is almost a subsystem of its own

The ModerationSystem inside this file handles considerably more than just the slash commands. It maintains case files, reports, warnings, bans, offender records, active temporary bans, moderation audit logs, Discord case messages, voting, rule/category selection, target notifications, RCON ban/unban execution, and restart-safe scheduled unbanning. 

So the rough flow is:

Player/User → Discord Bot → Moderation Case → Admin Review → Rule/Category → Decision → RCON action → Player history/audit log → Discord webhook

🔗 Account system

The account system currently handles:

Discord account → JTWP ProductID → optional Steam account → pending admin review → verified profile

When a link request happens, the bot updates the player's player.json, rebuilds by_discord_id.json and by_steam_id.json, logs the event, awards the Discord badge, and can send an admin webhook notification about the pending request. 

It also deliberately separates account verification from network/IP-hash verification. A player's Discord account being verified does not automatically make their RCON/network connection trusted. 

🛡️ Background work the bot performs automatically

This is probably the part that's easiest to overlook. Even when nobody is entering a slash command, discord_bot.py can continuously run three major jobs:

Command/moderation webhook tailers check JSONL files about every 2 seconds and send new audit events to Discord.

Temporary-ban expiry processing periodically checks active bans and automatically sends the required unban actions when they expire.

DDoS dashboard updates periodically reads the external DDoS statistics helper and edits the persistent Discord status message. 

🎮 Current command areas

The current source exposes commands around:

/report • /moderation • /warn • /banlog • /rcon • /player • /badges • /badge • /index • /account • /network • /data • /jtwp • /server • /loop

For example, /player alone handles player resolution, network records, name history, stats, weapons, profiles, and complete administrative lookups. 

🧠 Simplest way to describe this script

If the Collector is the part that builds and organizes the database, then the Discord Bot is the part that lets people and admins safely interact with that database and control the rest of JTWP.

In really simple terms:

Collector = gathers the information

Connection Watcher = watches players coming and going

RCON Monitor = watches RCON activity

SSH Monitor = watches SSH activity

DDoS Monitor = watches network traffic

Discord Bot = the control panel that lets humans view, manage, moderate, verify, and control all of it

And importantly, the bot itself does not appear to be the primary collector of Pavlov logs. Mostly it reads the data produced by the other JTWP components, presents it in Discord, modifies administrative state, and triggers actions in the other systems. 
