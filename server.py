#!/usr/bin/env python3
"""
Part No. Generator — hardened local server.

Reads host, port and bind address from config.txt (created by setup.bat).
Auto-creates data.sqlite from seed_data.py if the file is missing.
Reads are public; writes require a per-session token.
No external dependencies beyond the Python standard library.
"""

import base64
import json
import secrets
import sqlite3
import threading
import time
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import seed_data

# ---------- Paths ----------
BASE_DIR  = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "part_no_generator_html_v1.html"
DB_FILE   = BASE_DIR / "data.sqlite"
CONFIG_FILE = BASE_DIR / "config.txt"

DEFAULT_PW_B64 = seed_data.DEFAULT_PW_B64
MAX_BODY = 2 * 1024 * 1024           # 2 MB request cap
SESSION_TTL = 4 * 60 * 60            # 4 hours


# ---------- Config ----------
def read_config():
    cfg = {"host": "part-generator.eng", "port": 1030, "bind": "127.0.0.1"}
    if CONFIG_FILE.exists():
        for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "host" and v:
                cfg["host"] = v
            elif k == "port":
                try:
                    cfg["port"] = int(v)
                except ValueError:
                    pass
            elif k == "bind" and v:
                cfg["bind"] = v
    return cfg


CFG = read_config()
PORT = CFG["port"]
HOSTNAME = CFG["host"]
BIND_ADDR = CFG["bind"]
LAN_MODE = BIND_ADDR not in ("127.0.0.1", "localhost")
ALLOWED_HOSTS = None if LAN_MODE else {"localhost", "127.0.0.1", HOSTNAME}

_lock = threading.Lock()
_sessions = {}


# ---------- Schema ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS valves (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, name TEXT, catalogue TEXT, code TEXT);
CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, name TEXT, code TEXT);
CREATE TABLE IF NOT EXISTS sizes (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, name TEXT, code TEXT);
CREATE TABLE IF NOT EXISTS treatments (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, name TEXT, code TEXT);
CREATE TABLE IF NOT EXISTS materials (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, material_group TEXT, designation TEXT, spec TEXT, code TEXT, form TEXT);
CREATE TABLE IF NOT EXISTS part_headers (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, header TEXT);
CREATE TABLE IF NOT EXISTS part_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, cells TEXT);
CREATE TABLE IF NOT EXISTS years (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, value TEXT);
CREATE TABLE IF NOT EXISTS project_types (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER, value TEXT);
"""

SEED_TABLES = ("valves","classes","sizes","treatments","materials",
               "part_headers","part_rows","years","project_types")


def connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def build_db_if_missing():
    """Create data.sqlite from seed_data.py if it doesn't exist yet."""
    if DB_FILE.exists():
        return False
    print(f"[init] data.sqlite not found — building from seed_data.py")
    create_fresh_db()
    return True


def create_fresh_db():
    """Drop and recreate data.sqlite with all seed data. Keeps no existing rows."""
    if DB_FILE.exists():
        DB_FILE.unlink()
    conn = connect()
    try:
        c = conn.cursor()
        c.executescript(SCHEMA)
        c.execute("INSERT OR IGNORE INTO meta (key,value) VALUES ('password_b64',?)",
                  (DEFAULT_PW_B64,))
        _seed_all(c)
        conn.commit()
    finally:
        conn.close()
    print(f"[init] data.sqlite built ({len(seed_data.MATERIALS)} materials, "
          f"{len(seed_data.PART_ROWS)} part rows, {len(seed_data.VALVES)} valves)")


def _seed_all(c):
    for i, r in enumerate(seed_data.VALVES):
        c.execute("INSERT INTO valves (sort_order,name,catalogue,code) VALUES (?,?,?,?)", (i, *r))
    for i, r in enumerate(seed_data.CLASSES):
        c.execute("INSERT INTO classes (sort_order,name,code) VALUES (?,?,?)", (i, *r))
    for i, r in enumerate(seed_data.SIZES):
        c.execute("INSERT INTO sizes (sort_order,name,code) VALUES (?,?,?)", (i, *r))
    for i, r in enumerate(seed_data.TREATMENTS):
        c.execute("INSERT INTO treatments (sort_order,name,code) VALUES (?,?,?)", (i, *r))
    for i, r in enumerate(seed_data.MATERIALS):
        c.execute("INSERT INTO materials (sort_order,material_group,designation,spec,code,form) "
                  "VALUES (?,?,?,?,?,?)", (i, *r))
    for i, h in enumerate(seed_data.PART_HEADERS):
        c.execute("INSERT INTO part_headers (sort_order,header) VALUES (?,?)", (i, h))
    for i, row in enumerate(seed_data.PART_ROWS):
        c.execute("INSERT INTO part_rows (sort_order,cells) VALUES (?,?)",
                  (i, json.dumps(list(row), ensure_ascii=False)))
    for i, y in enumerate(seed_data.YEARS):
        c.execute("INSERT INTO years (sort_order,value) VALUES (?,?)", (i, y))
    for i, p in enumerate(seed_data.PROJECT_TYPES):
        c.execute("INSERT INTO project_types (sort_order,value) VALUES (?,?)", (i, p))


def ensure_meta_table():
    conn = connect()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM meta WHERE key='password_b64'").fetchone()
        if row is None:
            conn.execute("INSERT INTO meta (key,value) VALUES ('password_b64',?)", (DEFAULT_PW_B64,))
            conn.commit()
            print("[init] default admin password set (admin123)")
    finally:
        conn.close()


def get_password_b64():
    conn = connect()
    try:
        r = conn.execute("SELECT value FROM meta WHERE key='password_b64'").fetchone()
        return r["value"] if r else DEFAULT_PW_B64
    finally:
        conn.close()


def set_password_b64(pw_b64):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO meta (key,value) VALUES ('password_b64',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (pw_b64,),
        )
        conn.commit()
    finally:
        conn.close()


def _table_exists(conn, name):
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return r is not None


def read_db_as_json():
    conn = connect()
    try:
        missing = [t for t in SEED_TABLES if not _table_exists(conn, t)]
        if missing:
            raise RuntimeError(
                "data.sqlite is missing these tables: " + ", ".join(missing) +
                "  — run setup.bat and choose Repair/Reset DB."
            )

        def rows(sql):
            return conn.execute(sql).fetchall()

        return {
            "valves": [{"name": r["name"], "catalogue": r["catalogue"], "code": r["code"]}
                       for r in rows("SELECT * FROM valves ORDER BY sort_order")],
            "classes": [{"name": r["name"], "code": r["code"]}
                        for r in rows("SELECT * FROM classes ORDER BY sort_order")],
            "sizes": [{"name": r["name"], "code": r["code"]}
                      for r in rows("SELECT * FROM sizes ORDER BY sort_order")],
            "treatments": [{"name": r["name"], "code": r["code"]}
                           for r in rows("SELECT * FROM treatments ORDER BY sort_order")],
            "materials": [{"group": r["material_group"], "designation": r["designation"],
                           "spec": r["spec"], "code": r["code"], "form": r["form"]}
                          for r in rows("SELECT * FROM materials ORDER BY sort_order")],
            "partHeaders": [r["header"] for r in rows("SELECT * FROM part_headers ORDER BY sort_order")],
            "partRows": [json.loads(r["cells"]) for r in rows("SELECT * FROM part_rows ORDER BY sort_order")],
            "years": [r["value"] for r in rows("SELECT * FROM years ORDER BY sort_order")],
            "projectTypes": [r["value"] for r in rows("SELECT * FROM project_types ORDER BY sort_order")],
        }
    finally:
        conn.close()


def write_db_from_json(db):
    conn = connect()
    try:
        c = conn.cursor()
        c.execute("BEGIN")
        for t in SEED_TABLES:
            c.execute(f"DELETE FROM {t}")

        for i, v in enumerate(db.get("valves", [])):
            c.execute("INSERT INTO valves (sort_order,name,catalogue,code) VALUES (?,?,?,?)",
                      (i, v.get("name",""), v.get("catalogue",""), v.get("code","")))
        for i, v in enumerate(db.get("classes", [])):
            c.execute("INSERT INTO classes (sort_order,name,code) VALUES (?,?,?)",
                      (i, v.get("name",""), v.get("code","")))
        for i, v in enumerate(db.get("sizes", [])):
            c.execute("INSERT INTO sizes (sort_order,name,code) VALUES (?,?,?)",
                      (i, v.get("name",""), v.get("code","")))
        for i, v in enumerate(db.get("treatments", [])):
            c.execute("INSERT INTO treatments (sort_order,name,code) VALUES (?,?,?)",
                      (i, v.get("name",""), v.get("code","")))
        for i, v in enumerate(db.get("materials", [])):
            c.execute("INSERT INTO materials (sort_order,material_group,designation,spec,code,form) "
                      "VALUES (?,?,?,?,?,?)",
                      (i, v.get("group",""), v.get("designation",""), v.get("spec",""),
                       v.get("code",""), v.get("form","")))
        for i, h in enumerate(db.get("partHeaders", [])):
            c.execute("INSERT INTO part_headers (sort_order,header) VALUES (?,?)", (i, h))
        for i, row in enumerate(db.get("partRows", [])):
            c.execute("INSERT INTO part_rows (sort_order,cells) VALUES (?,?)",
                      (i, json.dumps(list(row), ensure_ascii=False)))
        for i, y in enumerate(db.get("years", [])):
            c.execute("INSERT INTO years (sort_order,value) VALUES (?,?)", (i, y))
        for i, p in enumerate(db.get("projectTypes", [])):
            c.execute("INSERT INTO project_types (sort_order,value) VALUES (?,?)", (i, p))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- Sessions ----------

def new_session():
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    return token


def session_ok(token):
    if not token:
        return False
    exp = _sessions.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True


def prune_sessions():
    now = time.time()
    for t in [t for t, exp in _sessions.items() if exp < now]:
        _sessions.pop(t, None)


# ---------- HTTP ----------

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    ),
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PartNoGen/1.0"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _host_ok(self):
        if ALLOWED_HOSTS is None:
            return True
        host = (self.headers.get("Host") or "").split(":", 1)[0].strip().lower()
        return host in ALLOWED_HOSTS

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            raise ValueError("bad content-length")
        if n <= 0:
            return {}
        if n > MAX_BODY:
            raise ValueError("request too large")
        raw = self.rfile.read(n)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _pw_matches(self, plain):
        if not isinstance(plain, str):
            return False
        try:
            stored = base64.b64decode(get_password_b64()).decode("utf-8")
        except Exception:
            return False
        return compare_digest(stored, plain)

    def _serve_html(self):
        if not HTML_FILE.exists():
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"{HTML_FILE.name} not found next to server.py".encode())
            return
        data = HTML_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            self._send_json(403, {"error": "forbidden host"})
            return
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._serve_html()
            return
        if path == "/api/db":
            with _lock:
                try:
                    self._send_json(200, {"db": read_db_as_json()})
                except Exception as e:
                    print("read_db error:", e)
                    self._send_json(500, {"error": str(e)})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            self._send_json(403, {"error": "forbidden host"})
            return
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_json()
        except Exception:
            self._send_json(400, {"ok": False, "error": "bad request"}); return

        if path == "/api/verify":
            with _lock:
                ok = self._pw_matches(body.get("password"))
                if ok:
                    prune_sessions()
                    token = new_session()
                    self._send_json(200, {"ok": True, "token": token})
                else:
                    self._send_json(200, {"ok": False})
            return

        if path == "/api/db":
            token = self.headers.get("X-Session-Token", "")
            if not session_ok(token):
                self._send_json(401, {"ok": False, "error": "unauthorized"}); return
            db = body.get("db")
            if not isinstance(db, dict):
                self._send_json(400, {"ok": False, "error": "missing db payload"}); return
            with _lock:
                try:
                    write_db_from_json(db)
                except Exception as e:
                    print("write_db error:", e)
                    self._send_json(500, {"ok": False, "error": str(e)}); return
            print(f"[{self.log_date_time_string()}] data.sqlite updated")
            self._send_json(200, {"ok": True}); return

        if path == "/api/password":
            token = self.headers.get("X-Session-Token", "")
            if not session_ok(token):
                self._send_json(401, {"ok": False, "error": "unauthorized"}); return
            if not self._pw_matches(body.get("oldPassword")):
                self._send_json(401, {"ok": False, "error": "current password is incorrect"}); return
            np = str(body.get("newPassword") or "")
            if len(np) < 4:
                self._send_json(400, {"ok": False, "error": "new password must be at least 4 characters"}); return
            with _lock:
                set_password_b64(base64.b64encode(np.encode("utf-8")).decode("ascii"))
            print(f"[{self.log_date_time_string()}] admin password changed")
            self._send_json(200, {"ok": True}); return

        self._send_json(404, {"error": "not found"})


def main():
    print("Part No. Generator starting...")
    try:
        built = build_db_if_missing()
        if not built:
            ensure_meta_table()
    except Exception as e:
        print("ERROR: could not prepare database:", e); return

    try:
        srv = ThreadingHTTPServer((BIND_ADDR, PORT), Handler)
    except OSError as e:
        print(f"ERROR: cannot bind to {BIND_ADDR}:{PORT} — {e}")
        print("Another program may be using that port. Close it and try again,")
        print("or edit config.txt to use a different PORT value.")
        return

    print(f"  URL:  http://{HOSTNAME}" + ("" if PORT == 80 else f":{PORT}"))
    print(f"  Also: http://localhost:{PORT}")
    print(f"  DB:   {DB_FILE}")
    if LAN_MODE:
        print(f"  Bound to {BIND_ADDR} — accessible from the LAN.")
        print(f"  Other users open:  http://<this-machine-ip>:{PORT}")
    else:
        print(f"  Bound to 127.0.0.1 — only this machine can reach it.")
    print("Press Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        srv.server_close()


if __name__ == "__main__":
    main()