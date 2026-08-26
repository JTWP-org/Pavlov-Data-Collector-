🔌 JTWP Connection Watcher

The Connection Watcher is the real-time side of the JTWP system. It continuously watches the Pavlov servers, tracks players and connections, monitors admins, gathers live RCON information, and handles RCON security.

📜 Live Pavlov Log Watching

Continuously watches each server's active Pavlov.log.

👀 Reads new log entries as they're written
💾 Remembers its position in the log
🔄 Handles log rotation and truncation
⚡ Processes new events in real time
🔗 Live Connection Tracking

Tracks every connection as it moves through the Pavlov connection process.

It can associate a connection with:

🌐 IP Hash
🔌 IpConnection_*
👤 Player Name
🆔 ProductID
🎮 UniqueID
🖥️ Platform
🖧 Server

Pending connections are updated as more information becomes available until the player is fully identified.

🟢 Player Join Detection

Detects when a player successfully joins a server using events such as:

Player <ProductID> Joined

and

Join succeeded

When a player joins, the watcher can:

👤 Identify the player
🆔 Associate their ProductID
🎮 Associate their UniqueID
🖥️ Determine their platform
🛡️ Refresh admin status
🔨 Refresh ban status
📊 Update the live player database
🔔 Send a Discord connection notification
🔴 Player Disconnect Detection

Detects several types of disconnects, including:

🚪 Normal disconnects
⏱️ Connection timeouts
🔌 Connection closes
🧹 Network cleanup events

It also calculates how long the player was connected and records a player_left event.

⚠️ Failed Connection Detection

Separates actual players from connections that never successfully joined.

Recognized failures include:

PendingConnectionLost
ConnectionTimeout
InvalidNetworkVersion
ConnectionClosedBeforeJoin

This prevents failed connection attempts from being treated as successful player sessions.

👥 Live Online Player Database

The watcher maintains:

global/connections/online_players.json

This contains the current players and pending connections for every monitored server.

Player information can include:

👤 Player Name
🆔 ProductID
🎮 UniqueID
🖥️ Platform
🔐 IP Hash
🔌 Connection ID
🛡️ Admin Status
🔨 Ban Status
🕐 Connection Time
🟢 Join Time
📡 Ping
💰 Cash
🏆 Score
☠️ KDA
🔵 Team
💀 Dead/Alive State
📚 Connection Event History

Permanent connection events are written to:

global/connections/events.jsonl

This creates a chronological history containing events such as:

🟢 Player joined
🔴 Player left
⚠️ Connection failed
⏱️ Connection timeout

So the watcher doesn't just know who is online now — it builds a history of what happened.

🥽 PCVR / SHACK Detection

The watcher automatically determines the server platform.

It can identify:

🟦 PCVR
🟩 SHACK

The SHACK server-build marker in the logs is used when available; otherwise the configured/detected server platform is used.

🎮 Live RCON Player Monitoring
🔄 Background InspectAll Loop

Each RCON-enabled server can receive its own background monitoring thread.

When enough players are online, the watcher periodically runs:

InspectAll

If the server doesn't meet the configured minimum player count, the loop sleeps instead of continuously sending unnecessary RCON requests.

📊 Live Player RCON Information

InspectAll results are matched back to players already identified by the Connection Watcher.

This adds live information such as:

🏆 Score
☠️ KDA
💰 Cash
🔵 Team
💀 Dead state
🔇 Gag state
📡 Ping
📡 Ping Monitoring

The watcher calculates player ping statistics including:

📍 Current Ping
📊 Average Ping
⬇️ Minimum Ping
⬆️ Maximum Ping
🔢 Number of Samples

Individual samples can also be recorded in:

global/connections/ping_samples.jsonl

This allows player latency to be tracked over time.

🛡️ Admin Monitoring
👮 Admin Presence Monitoring

The watcher uses its actual live-player database to determine whether an admin is currently on each server.

This means admin monitoring is tied directly to real player connections instead of relying only on loopOutput.json or a separate InspectAll result.

🚨 No Admin Online Alert

If:

Players are online + No admin is online

for longer than the configured delay, the watcher creates an admin alert.

It can then:

🚨 Create an alert record
🔔 Send a Discord notification
👮 Ping the configured admin role
⏱️ Admin Response Tracking

If an admin joins after an alert, the watcher records:

👮 Which admin responded
🕐 When the alert started
🟢 When the admin joined
⏱️ Response time
✅ Whether they responded inside the configured response window
🕒 Admin Session / Time Tracking

Admin connections are tracked separately.

The system records:

🟢 Admin join time
🔴 Admin leave time
⏱️ Session duration
🔢 Number of admin sessions
🕒 Total admin time
🖧 Time spent on each server
📉 Negative Score Detection

Live RCON scores are monitored.

If a player's score drops below the configured threshold:

🚨 An admin alert is created
🔔 Discord can be notified
👤 The offending player is identified

The alert state resets if their score recovers.

🔴 Teamkill Alerts

The watcher checks stored player combat statistics.

If a player's recorded teamkills meet the configured threshold, it can:

🚨 Create an admin alert
🔔 Notify Discord
👤 Identify the player
🔢 Include their recorded teamkill count
🗃️ Admin History

Admin monitoring maintains several datasets:

global/admins/monitor_state.json
global/admins/events.jsonl
global/admins/sessions.jsonl
global/admins/alerts.jsonl
global/admins/admin_stats.json

Together these provide admin presence, alert, response, session, and accumulated activity history.

🔐 RCON Security
📝 RCON Event Collection

RCON log events are still passed into the main Collector's RCON handler.

That means the Connection Watcher provides the live monitoring, while the existing RCON database continues to be maintained.

📢 RCON Command Discord Auditing

Normal RCON commands can be sent to a dedicated Discord audit webhook.

High-frequency/background commands can be excluded, such as:

InspectAll
ServerInfo
RefreshList

This keeps Discord from being flooded by automated RCON traffic.

🚫 Failed RCON Authentication Detection

The watcher detects failed RCON login attempts.

It can:

🔐 Hash the source IP
🔢 Count authentication failures
🕐 Track when they happened
🖧 Track which server was attacked
👤 Compare the IP Hash against known players
📚 Store the security event
📈 RCON Attack / Rate Monitoring

Failed authentication attempts are tracked using rolling time windows.

The system supports several severity levels:

🟡 Elevated
🟠 High
🔴 Critical
🚨 Attack

This allows a sudden RCON authentication spike to be distinguished from occasional failed passwords.

🧱 Automatic RCON IP Blocking

If one source exceeds the configured failure threshold within the configured time window, the watcher can automatically execute:

/usr/local/bin/block-ip

The system also supports:

✅ IP whitelist
🔐 IP Hash tracking
🔢 Failure thresholds
⏱️ Rolling block windows
📚 Block history
🕐 Block timestamps
🔎 RCON IP ↔ Player Correlation

One of the more useful security features is IP Hash correlation.

The watcher can compare an RCON source's IP Hash against IP Hashes previously associated with Pavlov players.

This can potentially connect:

RCON Connection
      ↓
   IP Hash
      ↓
Player IP History
      ↓
   ProductID
      ↓
 Player Record

So an RCON authentication source may be associated with known player records without exposing the raw IP in the public data.

✅ Verified RCON Connections

Manually verified RCON connections can be stored in:

verified_connections.json

This allows known/authorized RCON sources to be distinguished from unknown sources.

📚 RCON Security History

The watcher maintains security information including:

❌ Authentication failures
📈 Failure rates
🚨 Attack severity
🔐 IP Hashes
👤 Player matches
🧱 Blocked sources
🕐 Block timestamps
📊 Peak authentication-failure rates
✅ Verified connections
📊 Live Discord RCON Security Status

The watcher can maintain a single persistent RCON security status message in Discord.

Instead of constantly creating new messages, it:

Creates Message → Saves Message ID → PATCHes Existing Message → Repeats

If the Discord message gets deleted, the watcher creates a replacement and stores the new message ID.

This keeps the security channel clean while still providing continuously updated information.

🔒 Discord IP Protection

Raw network addresses are protected before security information is sent to Discord.

IPv4 and IPv6 addresses found in Discord-facing/audit text are replaced with:

[REDACTED-IP]

Internally, the system can still use the IP Hash for correlation without publicly exposing the original IP address.

⚙️ Overall Connection Watcher
🔌 Connection Watcher
│
├── 📜 Live Log Watcher
│
├── 🔗 Connection Tracking
│   ├── 🟡 Pending Connection
│   ├── 🔑 Login
│   ├── 🟢 Join
│   ├── 🔴 Leave
│   ├── ⏱️ Timeout
│   └── ⚠️ Failed Connection
│
├── 👥 Online Player Database
│
├── 🎮 RCON InspectAll Monitor
│   ├── 🏆 Score
│   ├── ☠️ KDA
│   ├── 💰 Cash
│   ├── 🔵 Team
│   └── 📡 Ping
│
├── 🛡️ Admin Monitor
│   ├── 👮 Admin Presence
│   ├── 🚨 No-Admin Alerts
│   ├── ⏱️ Response Time
│   ├── 🕒 Admin Hours
│   ├── 📉 Negative Score
│   └── 🔴 Teamkills
│
├── 🔐 RCON Security
│   ├── ❌ Failed Authentication
│   ├── 📈 Rate Detection
│   ├── 🔎 IP Hash Correlation
│   ├── 🧱 Automatic Blocking
│   ├── ✅ Verified Connections
│   └── 📊 Discord Security Status
│
└── 🔔 Discord Notifications

In short: connection_watcher.py handles the live, real-time side of JTWP — connections, online players, RCON player data, admin monitoring, security monitoring, and Discord alerts.
