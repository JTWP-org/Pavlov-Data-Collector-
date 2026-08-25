🗃️ JTWP Collector

The Collector is the main data-processing and organization system for JTWP.

Its job is to take all of the raw information produced by the Pavlov servers and turn it into organized data that the rest of JTWP can use.

It handles a lot of different jobs, so instead of thinking of the Collector as just a log reader, it's better to think of it as the system that builds and maintains the JTWP database.

📜 1. Log Processing

The Collector reads Pavlov's logs and looks for information that JTWP cares about.

It processes things like:

Pavlov server logs
Stats logs
Connection events
Player information
Combat events
RCON activity
HTTP errors
Runtime errors
Custom mod events
Gun/loot events

It takes information that originally looks like random log lines and converts it into structured JSON records.

Raw Logs
⬇️
Collector
⬇️
Organized Data

📦 2. Log Archiving

The Collector also manages the server's log archives.

It handles:

Pavlov-backup-*.log
Stats-*.log
Active Pavlov.log
Active Stats.log

It can safely copy and rotate the active logs so they can be processed without losing the server's current logging.

This gives JTWP a permanent history instead of relying only on whatever logs currently exist on the Pavlov server.

🗄️ 3. Historical Log Indexing

The Collector can also scan old log archives.

This allows old server backups to be added to JTWP even if they came from older server installations or completely different directory structures.

It recursively searches the configured historical archive folders for Pavlov:

Saved/Logs
Saved/Stats

Those historical folders are treated as read-only.

The Collector reads them but doesn't modify the original files.

🔁 4. Duplicate Protection

Historical archives can contain duplicate copies of the same logs.

The Collector uses SHA-256 hashes to identify files it has already processed.

Basically:

Log File
⬇️
Calculate SHA-256
⬇️
Already Processed?

Yes → Skip it

No → Process it

This prevents the same log from accidentally adding the same information twice.

👤 5. Player Database

One of the Collector's biggest jobs is building the player database.

Players are primarily organized around their:

Product ID

Each player can have their own records containing things like:

Product ID
Current name
Previous names
Unique ID
Steam ID
Platform
Servers seen on
First seen
Last seen
Admin status
Ban status
Network information
Player preferences
Linked accounts

This allows information found across many different logs to eventually be connected back to the same player.

🪪 6. Player Identity Tracking

The Collector tries to figure out who each player actually is.

It can build relationships between:

Product ID
Player name
Previous player names
Unique ID
Steam ID
Platform

For example:

Steam ID
⬇️
Product ID
⬇️
Player Record

Or:

Player Name
⬇️
Product ID
⬇️
Player Record

This is important because names can change, while the Product ID gives JTWP a much stronger player identifier.

🔎 7. Player Indexes

The Collector builds indexes so other JTWP scripts don't have to search through thousands of player folders.

It maintains indexes for things like:

🔤 Name → Product ID
🪪 Unique ID → Product ID
🆔 Product ID → Player
🌐 IP Hash → Product ID
🎮 Steam ID → Product ID
💬 Discord ID → Product ID

So instead of scanning the entire database, another service can quickly ask:

"Who owns this Steam ID?"

or:

"What Product IDs have used this name?"

🔌 8. Connection History

The Collector processes player connection information from the Pavlov logs.

It can track things like:

Player connections
Disconnects
Product IDs
Network endpoints
Connection start time
Connection end time
Session duration
IP information
Server connected to

The Collector also protects against Pavlov writing multiple cleanup/close lines for the same connection.

One real connection should still count as one connection.

⏱️ 9. Time Played

Completed connection sessions can be used to calculate how long a player has actually been online.

The Collector can rebuild:

Total connections
Completed sessions
Total time online
Human-readable playtime

For example:

184523 seconds

can become:

2d 3h 15m 23s

This is calculated from the player's stored connection history.

⚔️ 10. Combat Tracking

The Collector handles long-term Pavlov combat statistics.

It reads KillData from the Pavlov logs and determines:

Killer
Victim
Weapon
Headshot
Killer team
Victim team

It can then determine what kind of event happened.

💀 11. Kills & Deaths

The Collector tracks things like:

⚔️ Normal kills
💀 Deaths
🎯 Headshots
☠️ Suicides
🚨 Team kills
🤖 Bot kills
🤖 Deaths caused by bots
❓ Kills where team relationship couldn't be verified

These become part of the player's long-term combat statistics.

🔫 12. Weapon Statistics

The Collector also keeps track of what weapons players use for kills.

For each player it can build information such as:

Weapon
Kills with that weapon
Headshots with that weapon
Total weapon kills
Favorite weapon

For example:

AK-47 — 450 kills
M4 — 320 kills
1911 — 75 kills

⬇️

Favorite Weapon: AK-47

🏆 13. Badge System

The Collector can automatically award certain player badges when conditions are met.

The current Collector includes badges related to things such as:

💬 Discord linking
🌐 VPN/proxy connections
🚨 Team killing
💀 Reaching 1,000 kills

Badge awards are stored with information about when and why the badge was given.

📊 14. Match & Round Statistics

The Collector processes Pavlov's Stats.log information.

It can create records for individual rounds containing things like:

Map
Game mode
Match duration
Player count
Team
Team score
Player statistics

It can also add individual match records to each player's history.

This gives JTWP both:

Server Round History

and

Player Match History

🗺️ 15. Maps & Mods

The Collector processes UGC/mod information found in the server data.

For example:

UGC6279197

can be looked up through mod.io and turned into useful information such as:

Mod ID
Mod name
Thumbnail
Description/summary
Downloads
Update information

The results are cached so JTWP doesn't have to constantly request the same information again.

⚙️ 16. Game.ini / Server Configuration

The Collector reads information from each Pavlov server's configuration.

This allows JTWP to build records containing things such as:

Server configuration
Server name
Map rotation
Additional mods
Other useful Pavlov settings

This gives JTWP information about how each server is actually configured, not just what appears in the logs.

👑 17. Admin Tracking

The Collector reads the server's admin information.

It can use files such as:

mods.txt
RconPlus MenuAccesscfg.txt

Admin information from the servers can then be combined into the JTWP player database.

A player's record can therefore contain:

admin: true

when the player is recognized as an administrator.

🔨 18. Ban Tracking

The Collector also reads Pavlov's blacklist information.

It can determine:

Which IDs are banned
Which server they're banned from
Whether a player is banned on multiple servers

The player's record can then contain both:

Overall banned state
Servers the player is banned from
🌐 19. IP Privacy & Hashing

The Collector handles player IP information carefully.

Raw IP addresses are separated into the private data area.

Everywhere else JTWP uses an:

HMAC-SHA256 IP Hash

Basically:

Raw IP
⬇️
Secret Key + HMAC-SHA256
⬇️
Stable IP Hash

That allows JTWP to recognize the same address again without placing the actual IP into normal player records.

🌎 20. IP Information / Enrichment

When an IP is observed, the Collector can gather additional network information.

That can include:

🌎 Country
🏢 Organization/provider
🖥️ Network type
🏭 Hosting/datacenter detection
🕵️ Proxy detection
🔐 VPN detection
🧅 TOR detection
⚠️ Risk information
📊 Confidence information

The Collector uses multiple lookup providers and can fall back to another provider if one fails.

Results are cached so the same IP doesn't need to be looked up every time the Collector runs.

🔗 21. IP Correlation

Because JTWP uses stable IP hashes, the Collector can build relationships between network activity and players.

For example:

IP Hash
⬇️
Player A
Player B

The same hashing system can also help other JTWP monitors compare activity from:

Pavlov connections
RCON
SSH
Other security monitoring

A matching IP hash means the same network address was observed, but it does not automatically prove that a particular player performed another action.

🎮 22. RCON Tracking

The Collector processes RCON-related information found in the logs.

It can maintain records for:

Successful RCON connections
Failed RCON attempts
Known RCON hosts
Failed RCON hosts
IP hashes
First seen
Last seen
Number of attempts

RCON IP hashes can also be compared with known player IP hashes.

🌐 23. HTTP Error Tracking

The Collector looks for HTTP/network-related problems in Pavlov's logs.

Instead of those errors disappearing into thousands of log lines, they can be extracted into organized records.

This makes it easier to find repeated network or API problems later.

⚠️ 24. Runtime Error Tracking

The Collector also looks for useful runtime/server errors.

This allows JTWP to build a history of server problems instead of having to manually search every log whenever something goes wrong.

🧩 25. Custom Mod Events

The Collector also understands custom information written into the Pavlov logs.

That can include custom:

🔫 Gun events
🎁 Loot events
🧩 Mod events

This allows JTWP's own mods and server systems to feed information into the same database.

🌍 26. Pavlov Public Server API

The Collector can also pull information from the configured public Pavlov server-list API.

It can:

Download the server list
Store server information
Find unique server hosts
Enrich host information
Build indexes
Cache network-host information

So the Collector isn't limited only to JTWP's own Pavlov servers.

It can also maintain information about the wider public Pavlov server list when that feature is enabled.

🔄 27. Rebuild & Repair Tools

The Collector can rebuild parts of the database without having to destroy everything else.

It has separate operations for things such as:

🪪 Rebuild Identities

Rebuild:

Names
Unique IDs
Steam IDs
Product ID relationships

without replaying unrelated counters.

🔌 Rebuild Connections

Rebuild:

Connection history
IP observations
Session information

while preserving unrelated player data.

⚔️ Rebuild Combat

Reset and rebuild:

Kills
Deaths
Headshots
Team kills
Suicides
Weapon statistics
Combat event files

without destroying connection or identity information.

🏆 Backfill Badges

Checks existing player records and awards automatic badges that players already qualify for.

These tools make it possible to fix or upgrade one part of the database without rebuilding everything from scratch.

🧠 What the Collector Is Really Doing

The easiest way to understand the Collector is:

📥 Collect

Gather information from:

Pavlov logs
Stats logs
Historical archives
Server configuration
Admin lists
Ban lists
mod.io
IP lookup services
Pavlov's public API
🔍 Understand

Figure out:

Who the player is
What happened
Which server it happened on
When it happened
Whether the event has already been processed
How the information connects with existing records
🧮 Calculate

Build:

Player statistics
Combat statistics
Weapon statistics
Match counts
Connection counts
Time online
Network history
Badges
🗃️ Organize

Create and maintain:

Player records
Server records
Match records
Round records
Network records
RCON records
Event records
Indexes
Historical processing state
🔗 Connect

Build relationships between:

Names ↔ Product IDs

Steam IDs ↔ Product IDs

Unique IDs ↔ Product IDs

Discord IDs ↔ Product IDs

IP Hashes ↔ Product IDs

Players ↔ Servers

Players ↔ Matches

Players ↔ Combat Events

🚀 Why the Collector Is Allowed to Be Slow

The Collector is doing the heavy work for JTWP.

A normal run can involve:

Archive Logs
⬇️
Find Historical Logs
⬇️
Check SHA-256 Duplicates
⬇️
Read Stats
⬇️
Build Player Identities
⬇️
Read Pavlov Logs
⬇️
Process Connections
⬇️
Process Combat
⬇️
Process RCON / HTTP / Runtime Events
⬇️
Process Server Configs / Admins / Bans
⬇️
Perform IP & Mod Lookups
⬇️
Calculate Player Statistics
⬇️
Rebuild / Update Indexes
⬇️
Write Everything to the JTWP Database

So the Collector isn't supposed to be the fast, real-time part of JTWP.

That's what the smaller watchers are for.

The Collector's job is to take its time, go through everything, connect everything together, and make sure the JTWP database is organized and useful.
