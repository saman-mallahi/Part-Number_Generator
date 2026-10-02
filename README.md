# Part No. Generator

A lightweight, self-hosted web tool for generating **Part Numbers** and **Drawing Numbers** for engineered valves and actuators.

Built for the **Engineering Department of PSM (Petro Sazeh Mihan) Company**.

> **Note on origins:** the application was designed and specified by the PSM Engineering Department, and the code was written with the assistance of AI. It is provided as-is for internal use.

---

## What it does

The tool builds two identifiers:

- **Part No.** — identifies a specific component (Body, Bonnet, Stem, Seat, …) of a given valve type, material, pressure class, and size.
- **Drawing NO.** — a project-scoped identifier tying a part to a year, project type, project code, and item number.

Reference data (valve types, materials, classes, sizes, special treatments, and the part-list matrix) lives in a local SQLite database and is editable by an administrator through the app itself.

### Part No. formula

```
Part No. = Valve Code + "-" + Part Code + "-" + Material Code[N][R] + "-" + Class Code + "-" + Size Code + Option Code
```

Where `[N]` appends `N` when NACE is ticked and `[R]` appends `R` when Norm. is ticked.

### Drawing NO. formula

```
Drawing NO. = Year + "-" + Project Type + "-" + Project Code + "-" + Item NO. + "-" + Part Code
```

---

## Features

- **Live generation** — both identifiers update as you pick values.
- **Server-backed** — the reference tables are shared across every user of the installation, not stored per-browser.
- **Admin mode** — the tables are read-only until unlocked with a password. Only the admin can edit, add, reorder, or delete rows.
- **Local-first** — the server binds to `127.0.0.1` by default. Nothing is exposed to the network unless LAN mode is enabled during setup.
- **Windows-hosted** — a small Python server runs on a Windows machine; users open a single URL in their browser.
- **No external dependencies** — pure Python standard library, no `pip install` required.
- **Built-in help** — the app includes full documentation accessible from the **? Help** button.

---

## Requirements

- **Windows** (the launcher and setup are `.bat` scripts)
- **Python 3.7+** — download from [python.org](https://www.python.org/downloads/). During install, tick **"Add Python to PATH"**.

No third-party packages are needed.

---

## Installation

Clone or download this repository to a folder on the machine that will host the app.

```
📂 PartNoGenerator/
├── setup.bat
├── start.bat
├── server.py
├── part_no_generator_html_v1.html
└── data.sqlite       ← you provide this (see below)
```

### 1. Prepare `data.sqlite`

Place a `data.sqlite` file next to `server.py`. The server expects these tables:

| Table | Purpose |
|---|---|
| `meta` | key/value store — holds `password_b64` |
| `valves` | valve types (name, catalogue, code) |
| `classes` | pressure classes |
| `sizes` | nominal sizes |
| `treatments` | special treatments |
| `materials` | material specs |
| `part_headers` | Part List column headers |
| `part_rows` | Part List rows (`cells` is a JSON array) |
| `years` | Year dropdown values |
| `project_types` | Project Type letters |

If the `meta` table is missing, the server creates it automatically and sets the default admin password to `admin123`.

If `years` or `project_types` are empty, the app falls back to built-in defaults so the dropdowns still work.

### 2. Run the setup (once, as Administrator)

Right-click **`setup.bat`** → **Run as administrator**. It will:

1. Ask for the address (default: `part-generator.eng`).
2. Ask whether you want the URL with or without `:1030`.
3. Ask whether other computers on the network should reach the app.
4. Write `config.txt`.
5. Add the hosts entry.
6. Set up port forwarding and/or a firewall rule as needed.
7. Flush the DNS cache.

You only run setup once. To change the address later, re-run it.

### 3. Start the server

Double-click **`start.bat`**. A console window opens and stays open. It prints the URL — by default:

```
http://part-generator.eng
```

Open that URL in a browser. To stop the server, close the console window or press <kbd>Ctrl</kbd>+<kbd>C</kbd>.

---

## Usage

### For regular users

1. Open the URL in a browser.
2. Pick a **Year**, **Project Type**, and type a **Project Code**.
3. Type an **Item NO.**
4. Pick the **Valve Type**, then the **Part Name**, **Material**, **Class**, and **Size**.
5. Tick **NACE** and/or **Norm.** if applicable.
6. Pick an **Option** if a special treatment is needed.
7. The **Part No.** and **Drawing NO.** appear at the bottom, ready to copy.

### For the administrator

1. Open the **Reference Tables** tab.
2. Click **Edit** and enter the admin password (default `admin123`).
3. The badge switches from **User Mode** (green) to **Admin Mode** (red).
4. Edit cells directly, add/delete/move rows as needed.
5. Click **Save** to write changes to `data.sqlite` — every user sees them on their next page load.
6. Click **Lock** when finished.

Passwords can be changed from **Change Password** inside Admin Mode.

The full documentation is also available in the app under the **? Help** button.

---

## Files

| File | Purpose |
|---|---|
| `setup.bat` | One-time setup: hosts entry, port forwarding, firewall, config. Requires Administrator. |
| `start.bat` | Launches the Python server. Run this every session. |
| `server.py` | The backend — serves the HTML, exposes a small JSON API, and manages SQLite. |
| `part_no_generator_html_v1.html` | The user interface. |
| `config.txt` | Generated by setup. Holds hostname, port, and bind mode. |
| `data.sqlite` | The reference database. **Not committed to the repo** — created or supplied at install time. |

---

## Security

The server is designed to be conservative:

- **Binds to `127.0.0.1` by default** — unreachable from the network.
- **Host header allowlist** — blocks DNS-rebinding attacks in local-only mode.
- **Public reads, gated writes** — anyone can view the reference tables; only an unlocked admin can save changes.
- **Session tokens** — issued at unlock, expire after 4 hours.
- **Constant-time password comparison** — prevents timing side channels.
- **Request size cap** — 2 MB per request.
- **Serves exactly one file** — no directory traversal.
- **Security headers** — CSP, `X-Frame-Options: DENY`, `Referrer-Policy`.
- **Atomic database writes** — a crash mid-save leaves `data.sqlite` intact.

**LAN mode is meant for trusted internal networks.** Do not expose this server to the public internet. If remote access is needed, place it behind a VPN or a TLS-terminating reverse proxy.

---

## Backup and restore

The entire app state is in `data.sqlite`. To back up:

1. Stop the server (close the console window).
2. Copy `data.sqlite` to a safe location.
3. Restart the server.

To restore: replace `data.sqlite` with your backup and restart the server. Keep regular backups — this file contains every reference table and the admin password.

---

## Forgot the admin password?

Stop the server and run the following in Python from the app folder:

```python
import sqlite3
c = sqlite3.connect("data.sqlite")
c.execute("UPDATE meta SET value=? WHERE key='password_b64'", ("YWRtaW4xMjM=",))
c.commit(); c.close()
```

This resets the password to `admin123`. Restart the server afterwards.

To set a different password, replace `YWRtaW4xMjM=` with the base64 of your chosen password:

```python
import base64
base64.b64encode(b"YourNewPassword").decode()
```

---

## Editing the database directly

You can open `data.sqlite` with any SQLite tool — [DB Browser for SQLite](https://sqlitebrowser.org/) is a good free option. **Stop the server first**, make your edits, save, then restart the server.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `start.bat` says the configuration file is missing | Run `setup.bat` first (as Administrator). |
| `setup.bat` complains it needs Administrator | Right-click it → **Run as administrator**. |
| "Python was not found" | Install Python 3 and tick **Add Python to PATH**. |
| Browser can't find the address | Re-run `setup.bat`, then run `ipconfig /flushdns`. |
| Port 80 is already in use | Re-run `setup.bat` and choose the option that keeps `:1030` in the URL. |
| Other computers can't connect (LAN mode) | Confirm the firewall rule exists, and check that both machines are on the same network. |
| Tables appear empty | The `data.sqlite` file may be missing or invalid. Check the console window for a specific error message. |

Full troubleshooting guidance is available in the in-app Help.

---

## Development notes

- The frontend is a single HTML file with inline CSS and JavaScript — no build step.
- The backend is a single Python file using only the standard library.
- Reference tables are exchanged as JSON between the browser and the server.
- All identifiers, table names, and API endpoints are stable; adding columns means extending both `read_db_as_json()` and `write_db_from_json()` in `server.py`, plus updating the `schemas` map in the HTML.

---

## Credits

**Developed for the PSM (Petro Sazeh Mihan) Engineering Department.**

Specification, requirements, and design: PSM Engineering Department.
Implementation: with the assistance of AI.

---

## License

See [LICENSE](LICENSE).