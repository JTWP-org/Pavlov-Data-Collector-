Yep. Think of these three as the security watchers around your JTWP system, but each one watches a different type of activity.

🛡️ DDoS Monitor

The DDoS watcher watches network traffic coming into the server.

Its main jobs are:

Captures inbound packet metadata using tcpdump.

Counts packets and bytes during short windows, currently defaulting to 5 seconds.

Tracks:

packets per second

bytes per second

number of unique sources

highest packet rate from a single source

destination ports being targeted


Detects suspicious traffic when multiple thresholds are exceeded.

Supports severity levels:

medium

high

critical


Uses a cooldown so one flood doesn't generate events constantly.

Keeps raw source IP addresses only in memory during packet processing.

Converts source IPs into HMAC-SHA256 IP hashes before saving anything.

Saves DDoS/security information under:


global/network/ddos/

It produces things like:

network_stats.json
events.jsonl
last_event.json
hosts.json

The especially useful part is its correlation system.

When a suspicious source is detected:

Network traffic
      ↓
Raw IP
      ↓
HMAC IP hash
      ↓
 ┌───────────────┐
 │ Correlation   │
 └───────────────┘
   ↓      ↓     ↓
Player   RCON   SSH
records records records

So it can say:

> We've seen this same IP hash associated with a Pavlov player.



or:

> This hash has previously failed RCON authentication.



or:

> This hash has previously failed SSH authentication.



But the code correctly warns that a shared IP doesn't prove that particular player caused the traffic.

One important distinction: this DDoS watcher is currently detection-only.

It explicitly records:

automatic_blocking: false

So:

DDoS Monitor = Detect + Measure + Correlate + Record

It does not automatically ban/block attackers.


---

🔐 SSH Monitor

The SSH watcher protects the Linux server's SSH login system.

Instead of watching network packets, it follows the OpenSSH/systemd logs.

It recognizes failed SSH events like:

Failed password
Failed publickey
Invalid user
Maximum authentication attempts exceeded

When one happens it pulls out:

Username
Source IP
Source port
Failure type
Timestamp

Then it hashes the source IP using the same JTWP HMAC secret used elsewhere.

That means the SSH watcher can correlate an attacker against JTWP records too.

For example:

SSH login failure
       ↓
IP
       ↓
IP Hash
       ↓
JTWP Player Database
       ↓
Possible matching player records

SSH history

It maintains a history for each source hash including:

First seen
Last seen
Total failed attempts
Usernames attempted
Source ports
IP enrichment
Player matches
Blocked status
Blocked time

Normal security information goes into:

global/ssh/

including:

events.jsonl
failed_hosts.json
ssh.log

Unlike the DDoS watcher, SSH does retain the raw IP, but it isolates it in the private dataset:

private/ssh_ips.json

and attempts to restrict permissions to:

600

with the private directory at:

700

🌎 IP intelligence

The SSH watcher also uses your collector's Enricher.

So an SSH source can get information such as:

Organization
Country
Network type
Hosting
Proxy
VPN
Tor
Risk
Confidence

That can help distinguish:

normal ISP connection
        vs
VPN
        vs
datacenter
        vs
suspicious hosting provider

🚫 SSH auto-blocking

This one can automatically defend the server.

You have:

auto_block_enabled
auto_block_after
auto_block_command
auto_block_use_sudo

If configured like:

auto_block_after = 20

the comments indicate blocking begins on failure #21.

The flow becomes:

SSH failure
     ↓
Increase failed_attempts
     ↓
Threshold exceeded?
     ↓
Whitelist?
     ↓
Private/local IP?
     ↓
Already blocked?
     ↓
Run:
/usr/local/bin/block-ip <IP>
     ↓
Record blocked state

You also have an environment whitelist:

JTWP_SSH_AUTOBLOCK_WHITELIST

so trusted addresses can be protected from automatic blocking.

📊 SSH Discord status

The SSH watcher is also building its own security dashboard.

It calculates things like:

Failures / minute
Failures / 5 minutes
Failures / hour
Failures / day
Peak failures / minute
Blocked hosts
Blocks today
Most targeted usernames
Most common source ports
Most active source hashes

And it assigns statuses such as:

🟢 NORMAL
🟡 ELEVATED
🟠 HIGH
🔴 CRITICAL
🚨 ATTACK / FLOOD

So:

SSH Monitor = Detect + Enrich + Correlate + Record + Auto-block + Report


---

🎮 RCON Monitor

The RCON monitor watches access to your Pavlov RCON interfaces.

Where SSH protects Linux itself, RCON protects the game-server administration interface.

For your setup, that means RCON activity against the configured Pavlov instances/ports.

The RCON monitor's big job is distinguishing:

Successful RCON authentication

vs

Failed RCON authentication

and then keeping history about the hosts attempting to access RCON.

Conceptually:

Someone connects to RCON
        ↓
RCON authentication attempt
        ↓
 ┌───────────────┐
 │ Success?      │
 └───────────────┘
      ↓       ↓
    YES       NO
      ↓       ↓
known_hosts  failed_hosts

🔑 Failed RCON access

For failed authentication attempts it can maintain information like:

IP hash
First seen
Last seen
Failed attempts
Server attempted

That gives you a historical record of someone repeatedly trying to guess or access your RCON password.

✅ Successful RCON access

Successful hosts are also important.

Instead of assuming:

> Successful = safe



JTWP records them.

That means you can later answer things such as:

> Has this source ever successfully authenticated to one of my RCON ports?



This matters if an admin credential were compromised.

🔗 RCON correlation

The DDoS script you pasted specifically searches RCON data under:

servers/<server>/rcon/known_hosts.json
servers/<server>/rcon/failed_hosts.json

It reads:

server_id
kind
first_seen
last_seen
successful_connections
failed_attempts

That means RCON is part of your shared security identity system.

For example:

IP HASH
   │
   ├── Player connection
   │
   ├── RCON failure
   │
   ├── RCON success
   │
   ├── SSH failure
   │
   └── DDoS event

That's probably one of the more important features of the entire collector.

You're not treating every security system as an isolated log.

You're building a shared history around the same pseudonymous network identifier.

So:

RCON Monitor = Watch RCON Access + Track Successes/Failures + Hash Sources + Build Host History + Feed Correlation


---

🧠 The difference between all three

Monitor	Watches	Main purpose	Can block?

🛡️ DDoS	Network packets	Detect traffic floods/abuse	❌ Currently no
🔐 SSH	Linux SSH authentication	Detect login attacks	✅ Yes
🎮 RCON	Pavlov RCON authentication/activity	Detect/administer RCON access	Depends on RCON monitor configuration


Together they're basically your JTWP security layer:

INTERNET
                       │
        ┌──────────────┼──────────────┐
        ↓              ↓              ↓
   🛡️ DDoS         🔐 SSH         🎮 RCON
   Watcher          Watcher         Monitor
        │              │              │
        └──────────────┼──────────────┘
                       ↓
                  HMAC IP HASH
                       ↓
              ┌─────────────────┐
              │ JTWP Correlation│
              └─────────────────┘
                ↓       ↓       ↓
             Players   SSH     RCON
                       ↓
                 Collector Data
                       ↓
                  Discord Bot
                       ↓
                    Admins

The simplest descriptions would be:

🛡️ DDoS Monitor — Watches traffic hitting the machine and detects possible floods.

🔐 SSH Monitor — Watches people trying to log into Linux and can automatically block repeated attackers.

🎮 RCON Monitor — Watches people accessing Pavlov's administrative RCON interfaces and records successful and failed access attempts.

🤖 Discord Bot — Takes all that information and turns it into something your admins can actually view, search, control, and respond to.
