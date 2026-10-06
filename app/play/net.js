// The connection to the server: one WebSocket at the site's /ws, JSON messages as in
// specs/protocol.md. Says hello with the stored guest ID, stores the one the server gives back,
// and reconnects with a growing wait (1, 2, 4 ... up to 15 s) when the socket drops.

const GUEST_KEY = "arena-guest";

function storedGuest() {
  try {
    const g = localStorage.getItem(GUEST_KEY);
    return g && /^[0-9a-f]{32}$/i.test(g) ? g : null;
  } catch {
    return null; // private window: a new guest each time
  }
}

/**
 * Open the connection.
 * @param {object} on handlers
 * @param {(m: any) => void} on.message every message from the server (hello included)
 * @param {(status: {up: boolean, wait?: number, tries?: number}) => void} on.status connected, or not and retrying in `wait` s
 * @param {() => void} [on.open] after hello has been sent on a new connection
 */
export function connect(on) {
  // The play page is at <root>/play/, so the site's /ws is one level up from here.
  const url = new URL("../ws", location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  let socket = null;
  let tries = 0;

  function open() {
    socket = new WebSocket(url.href);
    socket.onopen = () => {
      tries = 0;
      on.status({ up: true });
      send({ t: "hello", guest: storedGuest() });
      on.open?.();
    };
    socket.onmessage = (event) => {
      let m;
      try { m = JSON.parse(event.data); } catch { return; }
      if (m.t === "hello" && m.guest) {
        try { localStorage.setItem(GUEST_KEY, m.guest); } catch { /* fine */ }
      }
      on.message(m);
    };
    socket.onclose = () => {
      const wait = Math.min(15, 2 ** tries);
      tries++;
      on.status({ up: false, wait, tries });
      setTimeout(open, wait * 1000);
    };
    socket.onerror = () => { /* onclose follows */ };
  }

  function send(message) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  open();
  return { send };
}
