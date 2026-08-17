🎛️ RCON file bridge

Check status:

sudo systemctl status jtwp-rcon-trigger-watcher --no-pager

Restart:

sudo systemctl restart jtwp-rcon-trigger-watcher

Watch live logs:

sudo journalctl -u jtwp-rcon-trigger-watcher -f

Last 100 lines:

sudo journalctl -u jtwp-rcon-trigger-watcher -n 100 --no-pager

Test ServerInfo:

echo '{}' > /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-serverinfo.json

Read the response:

cat /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/OUT-serverinfo.json

Pretty-print it:

python3 -m json.tool /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/OUT-serverinfo.json

Test bots:

echo '{"enabled":false}' > /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-setbotsenabled.json

See every current RCON response:

cat /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/OUT-*.json

Delete old responses:

rm -f /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/OUT-*.json

For pavlovserver1, just change the beginning to:

/home/steam/pavlovserver1/...
🔌 Direct RCON testing

Connect directly:

nc 127.0.0.1 9000

Check whether RCON is listening:

nc -vz 127.0.0.1 9000

Show listening Pavlov/RCON ports:

sudo ss -ltnp | grep -i pavlov

Or check your three ports:

sudo ss -ltnp | grep -E ':9000|:9100|:9200'
📦 Full collector

Run the full collection:

sudo systemctl start jtwp-collector

Status:

sudo systemctl status jtwp-collector --no-pager

Logs:

sudo journalctl -u jtwp-collector -n 100 --no-pager

Run directly:

cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
/home/steam/jtwp-collector/venv/bin/python3 collector.py -c config.json
🌐 Pavlov public API only

Refresh without processing all the logs:

cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
/home/steam/jtwp-collector/venv/bin/python3 update_pavlov_api.py -c config.json

View summary:

python3 -m json.tool /home/steam/jtwp-collector-data/global/pavlov_api/summary.json

Last update:

cat /home/steam/jtwp-collector-data/global/pavlov_api/last_update.json

List API data:

ls -lah /home/steam/jtwp-collector-data/global/pavlov_api/
👤 Connection watcher
sudo systemctl status jtwp-connection-watcher --no-pager
sudo systemctl restart jtwp-connection-watcher
sudo journalctl -u jtwp-connection-watcher -f
🔐 SSH watcher
sudo systemctl status jtwp-ssh-watcher --no-pager
sudo systemctl restart jtwp-ssh-watcher
sudo journalctl -u jtwp-ssh-watcher -f

View failed hosts:

python3 -m json.tool /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json

Watch SSH events:

tail -f /home/steam/jtwp-collector-data/global/ssh/events.jsonl
🩺 Check the whole JTWP system

Show all JTWP services:

systemctl --type=service --all | grep -i jtwp

Check the three continuous services at once:

systemctl is-active jtwp-connection-watcher jtwp-rcon-trigger-watcher jtwp-ssh-watcher

Restart all watchers:

sudo systemctl restart jtwp-connection-watcher jtwp-rcon-trigger-watcher jtwp-ssh-watcher

Follow all watcher logs together:

sudo journalctl -u jtwp-connection-watcher -u jtwp-rcon-trigger-watcher -u jtwp-ssh-watcher -f

After editing a .service file:

sudo systemctl daemon-reload
🐍 Check your Python files

Syntax-check the RCON watcher:

/home/steam/jtwp-collector/venv/bin/python3 -m py_compile rcon_trigger_watcher.py

Syntax-check the collector:

/home/steam/jtwp-collector/venv/bin/python3 -m py_compile collector.py

Check both:

/home/steam/jtwp-collector/venv/bin/python3 -m py_compile collector.py rcon_trigger_watcher.py connection_watcher.py ssh_watcher.py update_pavlov_api.py
📁 Useful data commands

See recently modified collector files:

find /home/steam/jtwp-collector-data -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' | sort -r | head -50

Total data size:

du -sh /home/steam/jtwp-collector-data

Search everything for a player name:

grep -Rni "PLAYER_NAME" /home/steam/jtwp-collector-data/

Search for errors:

grep -RniE '"error"|"primary_failure"|"fallback_failure"' /home/steam/jtwp-collector-data/

And one especially useful command while we're testing the bridge:

watch -n 1 'find /home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon -maxdepth 1 -type f -printf "%TY-%Tm-%Td %TH:%TM:%TS %f\n" | sort'

That gives you a live view of IN- and OUT- RCON files as the ModKit and bridge create/remove them.
