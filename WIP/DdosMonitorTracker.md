this is partially done but needs to be automated and we need to adjust the values on the monitor .. we will also have a webhook that triggers that includes the ipHASH's of the actors causing it and will 
  have info on the DDOS 

  here is an example of the planned webhook

  
```
  ⚠️ Possible DDoS Activity Detected
A network traffic spike triggered the JTWP DDoS detector.

Severity: medium
Detection Only: true
Automatic Blocking: false

Traffic Window
Packets: 25192
Window: 5.0 seconds
Packet Rate: 5038.22 packets/sec
Unique Sources: 15
Highest Single Source: 5002.82 packets/sec
🚨 Primary High-Volume Source
IP Hash
c6f64abec4ab1385910de834d7fbd518e25f8288e06a2506d7ef7db8a0115577

Traffic
Packets: 25015
Rate: 5002.82 packets/sec
Destination Ports: 44358

Correlation
Player History: ❌ None
RCON History: ❌ None
SSH History: ❌ None

⚠️ This source generated the highest packet rate and should be investigated first.
🔎 Correlated Source #1
IP Hash
bfb8f25b70a1ec476341515222116fd0896fee6b89e4df071a9d05a3cf336e19

Traffic During Event
Packets: 52
Rate: 10.4 packets/sec

Previous Activity
Player Match: ❌
RCON Match: ✅
SSH Match: ❌

RCON History
pavlovserver0 — known | Success: 2 | Failed: 0
pavlovserver — known | Success: 10 | Failed: 0
pavlovserver — failed | Success: 0 | Failed: 6
🔎 Correlated Source #2
IP Hash
c0b82f2d5dccaaba27973464c1bf5e5d1aea4ce323db8bbdf78a0d90c0466363

Traffic During Event
Packets: 3
Rate: 0.6 packets/sec

Previous Activity
Player Match: ❌
RCON Match: ✅
SSH Match: ✅

RCON History
pavlovserver0 — known | Success: 4615 | Failed: 0
pavlovserver1 — known | Success: 31 | Failed: 0
pavlovserver — known | Success: 3231 | Failed: 0

SSH History
Failed Attempts: 3
Blocked: false
🧠 Investigation Summary
Primary Source
c6f64abec4ab1385910de834d7fbd518e25f8288e06a2506d7ef7db8a0115577

Generated 25015 / 25192 packets observed during this event.

Historical Correlations: 2 source(s)

⚠️ An IP-hash correlation means the same network address was previously observed by another JTWP data source. It does not prove that a Player, RCON user, or SSH user generated the suspicious traffic.
JTWP Network Abuse Monitor • Correlation does not prove attribution•Yesterday at 3:21 AM
```
