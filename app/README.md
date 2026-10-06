# app/ — the pages

Everything here is served as-is by the server at `https://arena.endlessmind.com/<path>`. One page, one subdirectory, each with its own `index.html`, CSS and JS beside it and a `README.md` saying what the page does and how.

```
index.html      the root: sends you to welcome/
welcome/        what the game is, Play, who is in the arena now
play/           the game
shared/         map.json and base styles, used by both pages and by the server (map.json)
vendor/         three.js, pinned
```

Rules: every URL in a page is page-relative (`../shared/map.json`, `../play/`). Directory URLs are the public ones; the server redirects `play` to `play/`. Plain HTML, CSS and ES modules; no build step. `README.md` files are never served.
