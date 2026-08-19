#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, sys, time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import requests
from collector import Collector, DEFAULT_CONFIG, NetSession, ServerCfg, TS_RE, load_json

@dataclass

def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding existing variables."""
    if not path.is_file():
        return

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


class TailState:
    path: Path
    offset: int = 0
    inode: Optional[int] = None
    def initialize(self, start_at_end: bool):
        if self.path.exists():
            st = self.path.stat()
            self.inode = st.st_ino
            self.offset = st.st_size if start_at_end else 0
    def read_new_lines(self):
        if not self.path.exists():
            self.offset = 0; self.inode = None
            return []
        st = self.path.stat()
        if self.inode is None or st.st_ino != self.inode or st.st_size < self.offset:
            self.inode = st.st_ino; self.offset = 0
        if st.st_size == self.offset:
            return []
        with self.path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            lines = f.readlines()
            self.offset = f.tell()
        return lines

class LiveConnectionWatcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.collector = Collector(cfg)
        wc = cfg.get("connection_watcher", {})
        self.poll = float(wc.get("poll_interval_seconds", 0.5))
        self.start_at_end = bool(wc.get("start_at_end", True))
        self.timeout = int(wc.get("webhook_timeout_seconds", 8))
        self.retries = int(wc.get("webhook_retries", 2))
        self.connection_webhook = os.getenv("JTWP_CONNECTION_WEBHOOK_URL", "").strip()
        self.rcon_webhook = os.getenv("JTWP_RCON_WEBHOOK_URL", "").strip() or os.getenv("JTWP_SECURITY_WEBHOOK_URL", "").strip()
        self.http = requests.Session()
        self.http.headers.update({"User-Agent":"JTWP-Live-Watcher/1.1"})
        self.tails={}; self.by_endpoint={}; self.by_conn={}; self.by_name={}; self.active_rcon={}; self.platforms={}
        self.collector.load_global_admins()
        for s in self.collector.servers:
            self.collector.collect_bans(s)
            t=TailState(s.log_path/"Pavlov.log"); t.initialize(self.start_at_end)
            sid=s.server_id
            self.tails[sid]=t; self.by_endpoint[sid]={}; self.by_conn[sid]={}; self.by_name[sid]={}; self.active_rcon[sid]={}
            if s.platform_override in {"SHACK","PCVR"}:
                self.platforms[sid]=s.platform_override
            else:
                state=load_json(self.collector.data_root/"servers"/sid/"server.json",{})
                self.platforms[sid]=state.get("platform") or "PCVR"

    def run(self):
        print("JTWP live connection/RCON watcher started.")
        while True:
            did=False
            for s in self.collector.servers:
                for raw in self.tails[s.server_id].read_new_lines():
                    did=True; self.process_line(s, raw.rstrip("\n"))
            if not did: time.sleep(self.poll)

    def process_line(self, server, raw):
        m=TS_RE.match(raw)
        if not m: return
        ts,body=m.group("ts"),m.group("body").strip(); sid=server.server_id
        if "PavlovLog: SHACK SERVER BUILD" in body: self.platforms[sid]="SHACK"

        fail=re.search(r"Rcon:\s*User Failed authentication! Closing connection to client ((?:\d{1,3}\.){3}\d{1,3}):(\d+)",body)
        if "Rcon:" in body:
            self.collector.handle_rcon(server,ts,body,self.active_rcon[sid])
        if fail:
            ip,port=fail.group(1),int(fail.group(2))
            ih=self.collector.players.ip_hash(ip)
            matches=self.collector.players.players_for_ip_hash(ih)
            self.send_rcon_alert(server,ts,ih,port,matches)
            return

        join=re.search(r"LogNet:\s*Join succeeded:\s*(.+)$",body)
        name=join.group(1).strip() if join else None
        prior=bool(name and name in self.by_name[sid] and self.by_name[sid][name].counted_join)
        self.collector.handle_connection_line(server,self.platforms[sid],ts,body,self.by_endpoint[sid],self.by_conn[sid],self.by_name[sid])
        if not name: return
        sess=self.by_name[sid].get(name)
        if not sess or prior or not sess.counted_join or not sess.product_id: return
        self.collector.load_global_admins(); self.collector.collect_bans(server)
        self.collector.apply_admin_flags(); self.collector.apply_ban_flags_from_snapshots()
        self.collector.players.flush_indexes()
        if self.connection_webhook: self.send_connection_alert(server,sess,ts)

    def post(self,url,payload,label):
        if not url: return
        last=None
        for attempt in range(self.retries+1):
            try:
                r=self.http.post(url,json=payload,timeout=self.timeout)
                if 200<=r.status_code<300: return
                last=f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.RequestException as e: last=str(e)
            if attempt<self.retries: time.sleep(attempt+1)
        print(f"{label} webhook failed: {last}",file=sys.stderr)

    @staticmethod
    def yn(v): return "Yes" if v is True else "No" if v is False else "Unknown"

    def send_rcon_alert(self,server,ts,ih,port,matches):
        mt="None" if not matches else "\n".join(f"• {x.get('player_name') or 'Unknown'} (`{x.get('product_id')}`)" for x in matches[:10])
        payload={"username":"JTWP Security","embeds":[{"title":"Failed RCON Authentication","description":f"A failed RCON authentication was detected on `{server.server_id}`.","fields":[
            {"name":"IP Hash","value":f"`{ih}`","inline":False},
            {"name":"Source Port","value":f"`{port}`","inline":True},
            {"name":"Players Seen On Same IP","value":mt,"inline":False}],
            "footer":{"text":f"JTWP • {ts}"}}]}
        self.post(self.rcon_webhook,payload,"RCON")

    def send_connection_alert(self,server,sess,ts):
        pdir=self.collector.players.player_dir(sess.product_id)
        player=load_json(pdir/"player.json",{}); stats=load_json(pdir/"stats.json",{})
        c=stats.get("combat",{}); a=stats.get("activity",{}); w=stats.get("weapons",{})
        bg=(player.get("network",{}).get("current_background") or {})
        payload={"username":"JTWP Connection Watcher","embeds":[{"title":"Player Connected","description":f"**{sess.player_name or 'Unknown'}** joined `{server.server_id}`","fields":[
            {"name":"Identity","value":f"Product ID: `{sess.product_id}`\nUnique ID: `{sess.unique_id}`\nPlatform: `{self.platforms[server.server_id]}`","inline":False},
            {"name":"Status","value":f"Admin: `{self.yn(player.get('admin'))}`\nBanned: `{self.yn(player.get('banned'))}`\nConnections: `{a.get('times_connected',0)}`\nMatches: `{a.get('matches',0)}`","inline":True},
            {"name":"Combat","value":f"Kills: `{c.get('kills',0)}`\nDeaths: `{c.get('deaths',0)}`\nHeadshots: `{c.get('headshots',0)}`\nFavorite: `{w.get('favorite') or 'Unknown'}`","inline":True},
            {"name":"Network","value":f"Organisation: `{bg.get('organisation') or 'Unknown'}`\nCountry: `{bg.get('country_code') or 'Unknown'}`\nProxy: `{self.yn(bg.get('proxy'))}` | VPN: `{self.yn(bg.get('vpn'))}` | Hosting: `{self.yn(bg.get('hosting'))}`","inline":False}],
            "footer":{"text":f"JTWP • {ts}"}}]}
        self.post(self.connection_webhook,payload,"connection")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.json")
    args = ap.parse_args()

    p = Path(args.config).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"Config not found: {p}")

    load_env_file(p.parent / ".env")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    if "servers" in cfg:
        merged["servers"] = cfg["servers"]

    LiveConnectionWatcher(merged).run()


if __name__ == "__main__":
    main()
