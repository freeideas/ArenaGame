# Deployment

Endless Arena runs on **contabix** (reached as `ordinarydata.com`, public address 154.12.248.173), from `/home/ace/Desktop/prjx/ArenaGame/`, as the systemd unit `arena` on **127.0.0.1:8780**. Caddy forwards **<https://arena.endlessmind.com/>** to it, the same way it forwards `maze3d.endlessmind.com` to Monster Maze (port 8770). DNS for endlessmind.com is on Cloudflare.

## Updating

Check the checkout is clean, then `git pull --ff-only`. Page files (`app/`) are read on every request and need no restart; browsers may keep an old copy for up to five minutes. Server changes need `sudo systemctl restart arena`, which ends the round in progress: pages reconnect by themselves.

## Setting it up

1. DNS (done 2026-10-07): an `A` record `arena.endlessmind.com` -> `154.12.248.173`, not proxied, added through the Cloudflare API with the token at `passwords/cloudflare.com/api-token` in the machine's credential store (`~/creds`).
2. `uv sync` in the checkout (it needs `../EveryGame/realm-py`, an editable path dependency, so EveryGame must be checked out beside this repo).
3. `sudo cp deploy/arena.service /etc/systemd/system/ && sudo systemctl enable --now arena`
4. Caddy: add the block in `deploy/Caddyfile.snippet` next to Monster Maze's, add `arena.endlessmind.com` to `@allowed_domains`, back up the Caddyfile first, then `sudo caddy validate --config /etc/caddy/Caddyfile` and `sudo systemctl reload caddy`.

## Data

`data/` (gitignored) holds the realm's secret phrase (`realm-secret.txt`: the realm's identity, keep a copy), its data (`realm-data.json`) `players.json` (lifetime frags by player ID) and `guests.json` (names guests chose, by guest ID). Losing `players.json` loses only the frag totals.

## Limits

One process holds the arena in memory and sends each player 20 updates a second. Tens of players at once is comfortable; the service is capped at 512 MB.
