JTWP System Breakdown

The JTWP system is not one large script.

It is made up of several separate scripts and services that work together. Each component has a specific responsibility, which keeps the system organized and prevents one script from trying to handle everything.

The six main components are:

- Collector
- Connection Watcher
- Discord Bot
- SSH Monitor
- RCON Monitor
- DDoS Monitor

---

Collector

The Collector is the main data-processing and organization part of the system.

Unlike the real-time watchers, the Collector handles the heavy processing of Pavlov's current and historical logs.

It takes raw log information and turns it into structured data that the rest of JTWP can use.

The Collector handles things such as:

- Player connections
- Player names
- Product IDs
- Steam/Oculus IDs
- Kills and deaths
- Headshots
- Team kills
- Suicides
- Weapon statistics
- Player statistics
- Server information
- Maps and mods
- Admin information
- Ban information
- RCON activity
- HTTP/network errors

Building Player Records

One of the Collector's main jobs is building the player database.

The player's Product ID is used as the primary identifier.

Information from many different servers and log files can be combined into one organized player record.

For example:

Product ID
↓
Names Used
↓
Connections
↓
Kills / Deaths
↓
Headshots / Team Kills / Suicides
↓
Weapon Statistics
↓
Server History
↓
IP Hashes
↓
Admin / Ban Information

Building Indexes

The Collector also builds indexes that allow other parts of JTWP to quickly find information.

For example:

Player Name → Product ID

Instead of searching through thousands of player folders, another script can use the index to immediately locate the correct player record.

Why the Collector Can Be Slow

The Collector may have to:

Read thousands of log files
↓
Parse millions of log lines
↓
Identify events
↓
Match events to players
↓
Calculate statistics
↓
Combine historical information
↓
Build player records
↓
Rebuild indexes
↓
Write everything back to disk

This can take time, and that's okay.

The Collector is designed to be thorough, not instant.

It currently runs once a day at 3:00 AM.

Collector = History + Statistics + Organization

---

Connection Watcher

The Connection Watcher is the real-time player connection side of JTWP.

Unlike the Collector, it continuously watches the active Pavlov server logs while the servers are running.

It looks for things such as:

- Login requests
- Player names
- Product IDs
- Steam/Oculus IDs
- IP addresses
- Join requests
- Successful joins
- Team assignments
- Disconnects

Piecing Connections Together

Pavlov doesn't always put all of a player's connection information on one line.

For example:

Login Request
→ Finds the player's name and ID.

Network Connection
→ Finds the IP address.

Join Request
→ Shows that the player is attempting to join.

Join Succeeded
→ Confirms the connection.

Team Assignment
→ Helps confirm that the player fully entered the server.

The Connection Watcher takes those separate pieces and connects them together.

Once enough information is available, everything can be associated with the player's Product ID.

IP Handling

The watcher can temporarily use the raw IP address to gather network information.

That can include:

- ISP/provider
- Country and region
- VPN detection
- Proxy detection
- TOR detection
- Hosting/datacenter detection

The IP can then be converted into an HMAC-SHA256 hash.

That allows JTWP to recognize the same address later without putting the raw IP into normal public player records.

Connection Watcher = Live Player Connections

---

Discord Bot

The Discord Bot is the control and communication side of JTWP.

It provides an easier way to interact with the system without having to SSH into the Linux server and manually search files.

The basic flow is:

Discord User
↓
Discord Bot
↓
JTWP Services / Data / RCON
↓
Result Returned to Discord

The Discord Bot can handle things such as:

- Player lookups
- Player statistics
- Server information
- Server status
- RCON commands
- Administration commands
- Service management
- Restart commands
- System status
- Reports
- Notifications

Permissions

Commands can also have different permission levels.

For example:

Public
Normal commands available to users.

Admin
Administration commands available to authorized staff.

Owner
Sensitive system-management commands restricted to the owner.

Using JTWP Data

The Discord Bot doesn't need to calculate all of the information itself.

For example:

Player Lookup
↓
Bot checks player index
↓
Finds Product ID
↓
Reads player record
↓
Formats information
↓
Returns result to Discord

The bot acts as the interface while the other components do the actual monitoring and data collection.

Discord Bot = User Interface + Administration

---

SSH Monitor

The SSH Monitor watches authentication activity against the Linux server itself.

This is separate from players connecting to Pavlov.

The Connection Watcher monitors game connections.

The SSH Monitor monitors Linux server access.

It can watch for things such as:

- Successful SSH logins
- Failed passwords
- Invalid usernames
- Authentication failures
- Repeated login attempts
- Source addresses
- Source ports

Security Records

SSH activity can be processed and stored so JTWP can track things such as:

- Number of attempts
- Usernames attempted
- First seen
- Last seen
- Source ports
- Network provider
- VPN/proxy status
- Whether the source has appeared elsewhere in JTWP

IP addresses can also be hashed using the same system used by the other JTWP components.

That allows activity to be compared across different monitors.

For example:

SSH Attempt
↓
IP Hash
↓
Compare Against JTWP Records

The same hash could potentially appear in player connections, RCON activity, or network-security events.

SSH Monitor = Linux Server Security

---

RCON Monitor

The RCON Monitor handles activity involving Pavlov's Remote Console system.

RCON gives JTWP a direct connection to the running Pavlov servers.

The logs mostly tell us what happened.

RCON can tell us what is happening right now.

The RCON system can process things such as:

- Authentication attempts
- Successful authentication
- Failed authentication
- Commands
- Command responses
- ServerInfo
- InspectAll
- Player information
- Map information
- Server state
- RCON errors

For example:

RCON Request
↓
ServerInfo
↓
Pavlov Responds
↓
Response Parsed
↓
Structured Data Written

RCON as a Bridge

Other JTWP components can also use the RCON system to communicate with Pavlov.

For example:

Discord Command
↓
Discord Bot
↓
RCON System
↓
Pavlov Server
↓
Response
↓
Discord

This gives JTWP both monitoring and control of the running game servers.

RCON Monitor = Live Pavlov Server Control + Server State

---

DDoS Monitor

The DDoS Monitor handles the network-security side of JTWP.

While the SSH Monitor watches login attempts, the DDoS Monitor watches the server's network activity for unusual traffic patterns.

It can look for things such as:

- Sudden traffic increases
- Large numbers of incoming connections
- Abnormal connection rates
- Repeated traffic from the same source
- Large numbers of different sources
- Traffic spikes against Pavlov ports
- Traffic spikes against RCON
- Unusual traffic against other exposed services

Detecting an Incident

The basic idea is:

Normal Network Traffic
↓
Large or Unusual Traffic Spike
↓
DDoS Monitor Detects It
↓
Incident Recorded
↓
Administrator Can Be Alerted

Instead of only saying that something happened, the monitor can keep information about the incident.

That could include:

- Start time
- End time
- Duration
- Targeted port
- Targeted service
- Connection rate
- Traffic rate
- Number of sources
- Peak activity
- Detection reason

Cross-System Correlation

The DDoS Monitor can use the same IP hashing system as the other JTWP components.

That means the same IP hash could potentially appear in:

Connection Watcher
→ Pavlov connection

SSH Monitor
→ SSH attempt

RCON Monitor
→ RCON activity

DDoS Monitor
→ Suspicious network activity

This allows JTWP to connect related activity across different parts of the system without exposing the raw IP in normal records.

Discord Alerts

The DDoS Monitor can also feed information into the Discord notification system.

For example:

Possible Attack Detected
↓
Incident Created
↓
JTWP Notification
↓
Discord
↓
Admins Alerted

DDoS Monitor = Network Security + Attack Detection

---

How Everything Works Together

At a high level:

Pavlov Logs
↓
Collector + Connection Watcher

The Collector handles the historical/heavy processing while the Connection Watcher handles new connections in real time.

---

Pavlov Servers
↓
RCON Monitor

The RCON Monitor provides live server information and control.

---

Linux Host
↓
SSH Monitor + DDoS Monitor

The SSH Monitor watches access to the machine while the DDoS Monitor watches network activity.

---

All of those components produce information that becomes part of the larger:

JTWP Data System

Then:

JTWP Data + Live Services
↓
Discord Bot
↓
Admins / Users

---

Quick Summary

Collector
→ History, statistics, player records, and data organization.

Connection Watcher
→ Real-time player connections.

Discord Bot
→ User interface and administration.

SSH Monitor
→ Linux server access and security.

RCON Monitor
→ Live Pavlov server information and control.

DDoS Monitor
→ Network monitoring and attack detection.

Each component has its own job, but the information from all of them can be brought together by JTWP to create one larger monitoring, data, security, and administration system.
