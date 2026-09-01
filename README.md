# 🔐 Password Vault

A modern, secure, and elegant password manager for Windows — built with **Python** and **CustomTkinter** in Apple design style, with both light and dark themes.

**Version:** 3.4 | **Developer:** Eslam Atwa

---

## What sets it apart

Most of this is an ordinary password manager. These are the parts that are
not, and the reasoning behind them:

- **Built for servers, not just websites.** One domain account opens dozens
  of machines whose names change every session. SSH and RDP are offered on
  every entry, several sessions can be opened at once, and window patterns
  let one entry claim `*.corp.local` — none of which a browser extension
  would help with.
- **It never asks for administrator rights.** Not the installer, not the
  app, not a single feature. The installer offers a per-user install so it
  does not need them, and where that costs something — a window running
  elevated cannot be typed into — the limit is documented rather than
  worked around.
- **It refuses rather than rewrites.** A username with an unusual character
  is reported, not silently stripped; a host it cannot parse is named, not
  guessed at; an auto-type match it is not sure of opens a chooser instead
  of picking one. Silently changing a credential fails in a way that looks
  like the server's fault.
- **The speed is measured, not asserted.** Rendering the entry list went
  from 15.3 s to 0.42 s, and `tools/benchmark_ui.py` is in the repo so the
  claim can be checked. Three other approaches were tried and rejected for
  making no measurable difference.
- **751 tests, and they find things.** Several real defects here were caught
  by writing tests rather than by planning: a password left on the clipboard
  forever, a batch that kept opening sessions after the vault locked, a
  window guard that could never fire.

  They are also honest about their limits. Three tests in this project have
  been green while covering nothing — one fed a function the same wrong
  value the code compared against, one edited a read-only box the save path
  never reads, one asserted a Windows call succeeded while it silently
  returned zero. And the two worst auto-type problems were found by using
  the app, not by running the suite: a chooser that hauled the whole window
  up, and a vault whose other passwords could not be reached at all.

---

## ✨ Features

### 🔒 Security
- **Authenticated Encryption (Fernet)** — All passwords are encrypted locally using the `cryptography` library. Fernet is AES-128-CBC for confidentiality plus HMAC-SHA256 for integrity, so a tampered vault fails to open instead of decrypting to garbage.
- **PBKDF2HMAC Key Derivation** — Master password is hashed with 480,000 iterations of SHA-256.
- **Brute Force Protection** — Configurable max login attempts (3–15) with lockout duration (15s–5min), escalating with the failure streak. The streak and the deadline are persisted, so closing and reopening the app does not clear a lockout. This protects the login screen only — an attacker holding a copy of `vault.dat` attacks it offline, where the 480,000 KDF iterations are the real defence.
- **Auto-Lock** — Vault automatically locks after a configurable period of inactivity (1–30 min or Never).
- **Auto-Clear Clipboard** — Optionally clear copied passwords from clipboard after 10–60 seconds.
- **Atomic File Saves** — Data is written to a temp file first, preventing corruption on crash.
- **Master Password Validation** — Enforces minimum 12 characters, uppercase, lowercase, digits, and a strength score of Strong or better.
- **Single Instance Lock** — Only one copy of the app can run, so two windows can never overwrite each other's vault.
- **Security Dashboard** — Overall vault score plus weak, reused, and stale password reports.
- **Breach Check** — Checks passwords against Have I Been Pwned using k-anonymity, so no password or full hash ever leaves the machine.
- **Encrypted Backup & Restore** — Export the whole vault to a separately-encrypted file and restore it, including from the login screen.
- **Safe Export** — CSV and Excel exports neutralize spreadsheet formula injection.
- **Link Guard** — Only `http` and `https` links are ever opened.
- **Lock Hygiene** — Auto-lock closes every open dialog so no plaintext stays on screen.

### 🎨 User Interface
- **Light & Dark Themes** — Full iOS-inspired palettes for both, switchable from Settings, or set to System to follow Windows.
- **English & Arabic** — Switchable in Settings. Arabic mirrors the entire layout: the sidebar, every label anchor and every padding pair flip to read right-to-left. The window is rebuilt when the language changes, because Tk fixes those values when a widget is created.
- **Card Color Customization** — Choose from 9 color presets (Blue, Green, Red, Orange, Purple, Teal, Yellow, Pink) for each entry.
- **Default Card Color** — Set a default color for all new entries in Settings.
- **Password Strength Meter** — Visual indicator shows password strength in real-time (Very Weak → Very Strong).
- **Tooltips** — Hover over any button or feature to see a brief description of what it does.
- **Category Emoji Icons** — Each category gets an automatic emoji (💬 Social, 💼 Work, 🏦 Banking, etc.).
- **Show/Hide Password** — Toggle password visibility on login screen and in the edit dialog.

### 🔑 Password Management
- **Password Generator** — Cryptographically secure random password generator with customizable options:
  - Adjustable length (6–40 characters)
  - Toggle uppercase, lowercase, digits, and special characters
  - Real-time strength preview
  - Defaults configurable from Settings
- **Categories** — Organize entries into custom categories (General, Social, Work, Banking, Gaming, etc.).
- **Search & Filter** — Instant search with a category filter dropdown.
- **One-Click Copy** — Copy usernames and passwords to clipboard instantly.
- **Notes** — Add optional notes to any entry.
- **Edit & Delete** — Full CRUD operations with confirmation dialogs.
- **Recycle Bin** — Deleted entries are recoverable for 30 days. Once that passes they are removed from the encrypted file itself on the next unlock, not merely hidden from the list.
- **Duplicate Warning** — The edit dialog flags a password already used by another entry.
- **CSV & Excel Import/Export** — Round-trips titles, categories, URLs, notes, timestamps, and pinned state.

### ⌨️ Keyboard
| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New password |
| `Ctrl+F` | Focus search |
| `Ctrl+L` | Lock vault |
| `Ctrl+E` | Export data |
| `Ctrl+I` | Import data |
| `Enter` | Submit the focused dialog |
| `Esc` | Close a dialog, or clear the search box |

Shortcuts and `Ctrl+C/V/X/A` are matched by physical key, so they keep working under a non-Latin keyboard layout (Arabic, Russian, etc.).

Three more work **anywhere in Windows**, not only inside the app, once
Auto-Type is switched on. They are configurable, and these are the defaults:

| Shortcut | Action |
|----------|--------|
| `Ctrl+Alt+V` | Type the username and password into the window in front |
| `Ctrl+Alt+U` | Type the username only |
| `Ctrl+Alt+P` | Type the password only |

### 🖱️ Right-Click Context Menu
- **Full Context Menu** — Right-click any entry card (in main vault or Mini Vault) for quick actions:
  - 📋 Copy Username / 🔑 Copy Password
  - 🌐 Open URL in Browser / Open URL + Copy Username
  - 🖥️ **SSH Session** — Launch SSH with PuTTY, MobaXterm, or Windows SSH
  - 🖥️ **RDP Session** — Launch Remote Desktop connection
  - ✏️ Edit / 📌 Pin / 🗑️ Delete

### 🔑 SSH Keys

Plenty of servers take a key rather than a password. An entry can point at
one, or hold one.

- **A key file on this machine** — browsed to and used where it lies. The
  app never copies it.
- **A key kept in the vault** — generate one and the private half lives
  inside the encrypted vault. The public half is shown for pasting into
  `~/.ssh/authorized_keys`, and can be recovered from the private half at
  any time rather than being stored twice.
- **The passphrase box appears only when the key has a passphrase.**
  Deciding that needs the key body parsed, not its header: `ssh-keygen`
  writes `-----BEGIN OPENSSH PRIVATE KEY-----` either way. Asking for a
  passphrase that does not exist teaches people to type their account
  password into a field nothing will read.
- **The right secret is staged.** With a key in play the clipboard gets
  the *passphrase*, not the account password — and if the key has no
  passphrase, nothing is copied at all, because nothing will be asked
  for.

A stored key has to become a file for the length of one connection, since
every client takes a path and none takes bytes. That file is stripped of
inherited permissions and granted to the current user alone — **OpenSSH
refuses a key whose permissions are loose, with a "Bad permissions" error
that reads as a broken key** — and it is deleted 45 seconds later.

Format mismatches are refused before launching rather than after: PuTTY
reads only its own `.ppk`, and its own complaint about an OpenSSH key
sounds like the key is corrupt.

### ⌨️ Auto-Type

Fills the username and password into whatever window is in front — a
browser, MobaXterm, an RDP session, anything. Off until you switch it on.

- **Three shortcuts**, all configurable by pressing the combination rather
  than spelling it out: fill both fields, username only, password only. The
  last two are for sites that ask on separate pages.
- **Window patterns per entry** — `*.corp.local`, `intranet`, `10.0.0.*`,
  one per line. This is how a domain account covers machines that were never
  worth storing individually. A pattern of only `*` is refused; it would
  claim every window on the machine.
- **A typing order per entry** — `{USERNAME}{TAB}{PASSWORD}{ENTER}` by
  default, editable for two-page logins:
  `{USERNAME}{ENTER}{DELAY 800}{PASSWORD}{ENTER}`. A sequence that cannot
  be carried out is refused when you save the entry, not when you are
  standing in front of a login box waiting for it.
- **It asks when it is not sure.** Two accounts for one site, or a window
  nothing claims, opens a chooser. A wrong guess does not fail — it types a
  password into somewhere it does not belong.

The chooser is a small window of its own, always on top, and deliberately
not one of the app's modal dialogs — those are `transient` children, and a
transient window drags its owner up with it, so asking for one password
brought the whole vault to the front. It offers:

- **The whole vault, ranked.** Matches first, then general accounts, then
  everything else behind a divider. Ranking decides the order, not who is
  allowed in — a chooser you opened on purpose has to be able to reach any
  password, including by typing its name.
- **A line saying what will be typed** — `your username → Tab → your
  password`, or just the username if that is the shortcut you pressed.
  Otherwise the only way to find out is to press the button and watch.
- **Separate copy buttons** for the username and the password, because one
  button labelled "Copy" does not say which of the two it took.
- **"Remember this window"**, which is the answer to the case matching
  cannot solve. An entry called *wavz mail* at `mail.wavz.com.eg` will
  never match a window called `Outlook - Google Chrome` — nothing in one
  appears in the other, and no cleverer matcher changes that. Tick the box
  once and `Outlook` is added to that entry's patterns; from then on it
  types without asking.

Five checks stand between the key press and the keystrokes: the vault must
be unlocked, the window must not be the vault's own, an entry must match
confidently, the window must be confirmed back in front, and it must still
be the same window before *every* step — a sequence takes a second or two,
and the half that lands after an alt-tab is usually the password.

**It is not a keylogger, and the code makes that structural.** Windows is
asked for the one combination via `RegisterHotKey`, so the app is told about
that key and nothing else. The alternative, a low-level keyboard hook, would
receive every keystroke on the machine.

**Known limit:** a window running as administrator cannot be typed into.
Windows blocks input from a normal program, and this app never asks for
admin. That is a deliberate trade, not an oversight.

### 🖥️ SSH & RDP Integration
- **SSH Session Dialog** — Interactive dialog with:
  - Host/IP input (auto-filled from entry URL)
  - Username (auto-filled from entry)
  - Port selection (auto-detected from URL)
  - **SSH Client chooser** — Auto-detects MobaXterm, PuTTY and Windows OpenSSH, in that order, so MobaXterm is the default when installed
  - Password auto-copied to clipboard on connect, held for at least 60 seconds — long enough for a client to finish starting and prompt for it

  Credentials are passed to the client exactly as typed. Each client is
  launched with an argument list, which no shell parses; MobaXterm's
  `-newtab` takes a single command string that its own shell splits, so
  that one is built with `shlex.quote`. A host or username containing a
  shell metacharacter is refused with a message naming the character
  rather than being silently rewritten.
- **Several sessions at once** — *Open Multiple SSH Sessions* takes the
  servers from the vault by tickbox, or from a list you type or paste
  (`[user@]host[:port]`, one per line, `#` comments and blank lines
  ignored). Pick the client once and the account once; a chosen entry fills
  in the username on any line that does not name one.

  Launches are spaced a few hundred milliseconds apart rather than fired at
  once, because a cold-starting MobaXterm drops tabs when ten arrive
  together. A batch stops if the vault locks partway through.

  **Passwords are not staged automatically here.** One clipboard cannot hold
  ten, and rotating them on a timer would mean it holding whichever secret
  happened to be current when you pressed Ctrl+V. A panel stays up with one
  button per server: click the row for the tab you are in, and that one
  password goes over under the usual auto-clear.

- **RDP Session Dialog** — Launch Remote Desktop with:
  - Host/IP input (auto-filled from entry URL)
  - Port configuration — there is no username field, because `mstsc` takes no username on its command line and Windows prompts for it itself
  - Password auto-copied to clipboard on connect, ready to paste into that prompt

### 🪟 Floating Widget & Mini Vault
- **Floating Widget** — Minimizes to a small draggable bubble (always on top) for quick access.
- **Mini Vault** — A compact, always-on-top window to search, copy, and edit passwords without opening the full app.
  - Category filtering
  - Copy username/password
  - Edit entries directly
  - **Right-click context menu** with SSH/RDP/Copy/Edit actions
- **Start Minimized** — Option to launch the app directly to the floating widget (configurable in Settings).

### ⚙️ Settings (Full Page)
A complete iOS-style settings page with persistent configuration:

| Category | Setting | Description |
|----------|---------|-------------|
| 🔒 **Security** | Auto-Lock Timer | Lock after 1, 2, 5, 10, 15, 30 min or Never |
| 🛡️ **Security** | Max Login Attempts | 3, 5, 10, or 15 failed attempts before lockout |
| ⏱️ **Security** | Lockout Duration | 15 sec, 30 sec, 1 min, 2 min, or 5 min |
| 📋 **Security** | Clear Clipboard | Off, or auto-clear after 10, 15, 30, 60 sec |
| 📏 **Generator** | Default Length | Slider from 6 to 40 characters |
| 🔤 **Generator** | Character Types | Toggle Uppercase / Lowercase / Digits / Symbols |
| 🎨 **Appearance** | Theme | System, Light, or Dark |
| 🌐 **Appearance** | Language | English or Arabic (العربية) — Arabic mirrors the layout right-to-left |
| 🎨 **Appearance** | Default Card Color | Choose default color for new entries |
| 🚀 **Behavior** | Start Minimized | Launch to floating widget instead of full window |
| 🖥️ **Remote** | Extra SSH Client | Point at a client the automatic search does not find — a portable copy, or one installed somewhere unusual |
| ⌨️ **Auto-Type** | Enable Auto-Type | Off by default; registers the global shortcuts when on |
| ⌨️ **Auto-Type** | Three shortcuts | Fill both fields, username only, password only — set by pressing the keys |

Settings are validated on load: a value with the wrong type or outside its allowed range falls back to the default instead of breaking startup.

All settings are saved to `%APPDATA%\PasswordVault\settings.json`.

### 📥 Importing From Another Password Manager
Exports from these applications are read directly — no reformatting needed:

| Source | Recognised columns |
|--------|--------------------|
| Chrome / Edge | `name, url, username, password, note` |
| Bitwarden | `folder, favorite, name, notes, fields, login_uri, login_username, login_password, login_totp` |
| LastPass | `url, username, password, totp, extra, name, grouping, fav` |
| 1Password | `Title, Url, Username, Password, OTPAuth, Favorite, Tags, Notes` |
| KeePass | `Account, Login Name, Password, Web Site, Comments, Group` |
| Firefox | `url, username, password, httpRealm, …` |
| Bitwarden **JSON** | the full export, not a column map — see below |
| 1Password **.1pux** | the full archive, not a column map — see below |

The format is detected from the header row and shown in the import dialog,
with a dropdown to override it if the guess is wrong. Folders, groupings and
tags become categories; favourites become pinned entries.

**Nothing is dropped in silence.** A TOTP secret or a custom field has no
dedicated home in this app, so it is appended to the entry's notes under its
original name rather than discarded. Any column that cannot be carried at all
is listed in the dialog *before* you import.

**Bitwarden JSON** and **1Password .1pux** are read directly rather than
through a column map, because a CSV cannot express what those formats hold:
folders and vaults joined by id, several URIs per item, per-item custom
fields and sections, and typed items beyond logins. Secure notes, cards and
identities are imported as notes-only entries with their type recorded —
skipping them silently would be the worst outcome.

Two things worth knowing:

- A **password-protected Bitwarden export** cannot be read; the dialog says
  so and tells you to export again without encryption.
- **1PUX attachments are named, not extracted.** This app stores no files,
  and writing decrypted documents onto disk beside an encrypted vault would
  defeat the point. The entry's notes list what was attached and say the
  files are still inside the `.1pux`, so nothing disappears quietly.

### ℹ️ About Dialog
- Version info, developer name, encryption details
- Full feature list summary
- Accessible from the Settings menu (⚙️ → About)

### 🔄 Installer Update Support
- Running the installer on a machine with an existing installation shows **"Update"** instead of "Install"
- Displays old version → new version info
- Reassures that passwords and settings are safe during update

---

## 🛠️ Installation

### Option 1: Installer (Recommended)
1. Download **`PasswordVault_Setup.exe`** from the [Releases](https://github.com/eslamatwa/PasswordVault/releases) page.
2. Run the installer — choose between:
   - **Program Files** (requires admin) — system-wide installation
   - **User folder** (no admin needed) — per-user installation
3. The installer creates:
   - 🖥️ **Desktop shortcut**
   - 📂 **Start Menu shortcut**
4. Launch **Password Vault** from your Desktop or Start Menu.

> **Updating?** Just run the new installer — it will detect the existing installation and update it. Your passwords and settings are stored separately in `%APPDATA%` and will NOT be affected.

### Option 2: Run from Source
1. **Clone the repository:**
   ```bash
   git clone https://github.com/eslamatwa/PasswordVault.git
   cd PasswordVault
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python main.py
   ```

---

## 🏗️ Building from Source

### Prerequisites
- **Python 3.10+** installed
- **PyInstaller** for building the executable
- **Inno Setup 6** for creating the Windows installer ([Download](https://jrsoftware.org/isdl.php))

### Step 1: Install Dependencies
```bash
pip install -r requirements-dev.txt
```

### Step 2: Build the Executable
```bash
pyinstaller PasswordVault.spec --noconfirm
```
This creates `dist/PasswordVault.exe` — a single standalone executable. Always
build from the spec: the dialog modules are imported lazily and are listed as
hidden imports there, so a hand-written command will silently miss them.

### Step 3: Create the Installer (Optional)
1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php)
2. Compile the installer script:
   ```bash
   # Using Inno Setup command-line compiler
   iscc setup.iss
   ```
   Or open `setup.iss` in the Inno Setup GUI and click **Compile**.

3. The installer will be created at `installer/PasswordVault_Setup.exe`.

### Verifying a build
The spec does **not** ship the package's `.py` files inside the executable —
the dialogs are imported lazily, and `hiddenimports` is what makes them
resolvable in a frozen build. Because a missing entry there only fails when
a user clicks the menu item, the built exe can check itself:

```bash
dist\PasswordVault.exe --self-test
```

It imports every lazily-loaded module and exits `0` when they all resolve,
non-zero with the failures on stderr otherwise.

### Build Output
```
PasswordVault/
├── dist/
│   └── PasswordVault.exe       # Standalone executable
├── installer/
│   └── PasswordVault_Setup.exe # Windows installer
└── ...
```

---

## 🏗️ Project Structure

```
PasswordVault/
├── main.py                          # Entry point — UI logic & PasswordVault class
├── password_vault/                  # Core package (modular architecture)
│   ├── __init__.py                  # APP_VERSION, APP_AUTHOR, logging setup
│   ├── crypto.py                    # Encryption, key derivation, save/load data
│   ├── security.py                  # Strength, age, duplicates, HIBP, score, generator
│   ├── settings.py                  # Settings persistence + validation
│   ├── theme.py                     # Light/dark palettes & card presets
│   ├── i18n.py                      # Translation catalog + RTL direction helpers
│   ├── export_import.py             # CSV & Excel export/import helpers
│   ├── import_json.py               # Bitwarden JSON export reader
│   ├── import_profiles.py           # Column maps for other password managers
│   ├── import_1pux.py               # 1Password .1pux archive reader
│   ├── instance_lock.py             # Single-instance mutex / lock file
│   ├── autotype.py                  # Auto-type controller: the checks between key and keystroke
│   ├── autotype_match.py            # Which entry a window is asking for
│   ├── autotype_sequence.py         # {USERNAME}{TAB}{PASSWORD} parsing
│   ├── autotype_win.py              # RegisterHotKey + SendInput, the only Windows-specific part
│   ├── hotkeys.py                   # Reading and validating a shortcut
│   └── ui/
│       ├── __init__.py
│       ├── widgets.py               # Tooltip, iOS-style fields, card pool, rounded pills
│       ├── bulk_targets.py          # Parsing a typed list of servers
│       ├── mini_vault.py            # Mini Vault (compact always-on-top viewer)
│       ├── floating.py              # Floating Widget (draggable bubble)
│       └── dialogs/
│           ├── __init__.py
│           ├── about.py             # About dialog
│           ├── autotype_picker.py   # Choosing an entry when the window is ambiguous
│           ├── bulk_ssh.py          # Open several SSH sessions at once
│           ├── backup.py            # Encrypted backup export / restore
│           ├── change_password.py   # Master password change (threaded re-encrypt)
│           ├── data_io.py           # CSV / Excel export & import
│           ├── generator.py         # Password generator
│           ├── security_dashboard.py# Score, weak/reused/old lists, breach check
│           └── trash.py             # Recycle Bin
├── tools/
│   ├── benchmark_ui.py             # Entry-list render benchmark
│   └── sign.ps1                    # Authenticode signing for a release build
├── tests/                           # Unit tests (pytest / unittest)
├── icon.ico                         # Application icon
├── PasswordVault.spec               # PyInstaller build spec
├── setup.iss                        # Inno Setup installer script
├── requirements.txt                 # Python dependencies
└── README.md
```

---

## 📂 Data Storage

| File | Location | Purpose |
|------|----------|---------|
| `vault.dat` | `%APPDATA%\PasswordVault\` | Encrypted password database |
| `vault.salt` | `%APPDATA%\PasswordVault\` | Encryption salt (32-byte) |
| `settings.json` | `%APPDATA%\PasswordVault\` | User preferences |
| `vault.log` | `%APPDATA%\PasswordVault\` | Application event log |

> Data is stored in `%APPDATA%` (typically `C:\Users\<you>\AppData\Roaming\PasswordVault\`) to ensure persistence across app updates and proper backup support.

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern UI framework (light/dark) |
| `cryptography` | Authenticated encryption (Fernet + PBKDF2) |
| `pyperclip` | Clipboard copy/paste |
| `openpyxl` | Excel (.xlsx) export/import |
| `pytest` | Test runner (dev only) |
| `pyflakes` | Static analysis (dev only) |
| `pyinstaller` | Build standalone executable (dev only) |

---

## 🧪 Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
python -m pyflakes main.py password_vault tests tools
```

**751 tests.** They cover encryption round-trips and schema migration, the
vault shape guard, restore rollback, CSV/Excel import-export fidelity and
formula escaping, one fixture per supported import format, URL scheme
validation, password strength/age/duplicate/score logic, generator length
handling, settings validation, the persisted lockout state, the
single-instance lock, and the pure UI helpers.

The suite drives a real Tk application rather than mocking one, so it needs a
display and takes a few minutes. It keeps to itself while it runs:

- **Windows are placed at +30000+30000**, not hidden. Several tests ask
  whether a card or a dialog is actually on screen, so they have to stay
  mapped — they are just mapped where nobody is looking. `focus_force` and
  `lift` are disabled so nothing takes the keyboard from whatever you are
  doing.
- **`APPDATA` is redirected before the package is imported**, which keeps the
  suite out of `%APPDATA%/PasswordVault` — the vault files *and* `vault.log`.
  It has to happen at import time, because the log handler is attached when
  `password_vault` is first imported and the first handler wins.

`tests/test_offscreen.py` and `tests/test_logging.py` hold both of those to
their word; if a test window appears on your desktop, one of them should be
failing.

Several are worth calling out:

- **`test_dialogs_smoke.py`** opens every dialog in both themes and both
  languages and asserts each one is actually mapped, not merely constructed.
  It also covers the modal grab stack, the rule that `Enter` never confirms a
  destructive action, and that auto-lock leaves no window on screen.
- **`test_i18n_coverage.py`** fails on any user-facing string that does not
  reach the translator, any string with no Arabic entry, and any catalog key
  nothing uses. An untranslated string is invisible in English, so the check
  has to be static.
- **`test_hibp.py`** stubs only the network call, so the k-anonymity
  guarantee is asserted rather than assumed: the request carries the
  five-character prefix and never the suffix or the password. A failed
  request must report "unknown", never "safe".
- **`test_autotype_match.py`** is mostly about refusing. An entry called
  "es" must not match Files, Notes and Settings; two accounts for one site
  must not be guessed between; a username alone is never enough evidence. A
  wrong match does not fail, it types a password somewhere it does not
  belong.
- **`test_bulk_targets.py`** parses a typed server list without a window,
  because a misread line is not a failed connection — it is a session opened
  to the *wrong machine* with a domain account.
- **`test_entry_validation.py`** exists because the entry dialog's error
  messages had never once been triggered by a test, and all three of them
  crashed instead of appearing. A guard nothing has ever tripped is not a
  guard.

Tk-dependent tests skip themselves automatically when no display is available.

### A note on tests that pass without testing anything

Three tests in this project have been green while covering nothing at all:
one fed a function the same wrong value the code compared against, one edited
a read-only box the save path never reads, and one asserted a Windows call
succeeded when it had been silently returning zero. None would have been
caught by reading them. They were found by running the real API and comparing
the numbers that came back — which is why the manual checklist in
`MVP.md` is still the gate for anything that types a password.

---

## ⚡ Performance Notes

- **Key derivation is deliberately slow** — 480,000 PBKDF2 iterations is
  about 300 ms on a typical desktop, and that cost is the point: it is what
  an attacker pays for every guess against a stolen `vault.dat`.
- **It never runs on the UI thread.** Unlocking, creating an encrypted
  backup, restoring one, and changing the master password all derive in a
  worker and show a busy state, so the window keeps repainting.
- **The data side is fast.** On a 5,000-entry vault, encrypting the whole
  file takes ~36 ms, the security score ~44 ms, and a search filter ~7 ms.
- **The entry list repaints in well under half a second**, at any vault
  size. It used to take fifteen seconds at sixty entries. Three things got
  it there: rows built from plain Tk widgets rather than CustomTkinter
  ones (a CTk widget costs 9–50x a plain one, because it draws itself onto
  its own canvas), a page capped at 20 cards, and cards that are kept and
  re-shown rather than destroyed and rebuilt on every refresh.

  ```bash
  python tools/benchmark_ui.py
  ```

  The Mini Vault works the same way and shares the cache: `CardPool` in
  `ui/widgets.py` owns the reuse and the invalidation for both lists.

  The small buttons on a card are labels too. They keep their rounded
  corners by wearing a cached `tk.PhotoImage` of a pill, drawn under the
  text with `compound="center"` — 15% more than a plain label, against
  14x for the CTkButton it replaced. A consequence worth knowing: those
  buttons have no `fg_color`, so anything that wants to recolour one has
  to go through `flash_button` rather than configuring it directly.

  Two consequences worth knowing: plain widgets do not follow the
  appearance mode on their own, so both lists are repainted when the theme
  or language changes; and they hold a cache, so anything that edits an
  entry invalidates that entry's card.

---

## 🔑 If You Forget the Master Password

**There is no reset, and no one can recover the vault for you.** The master
password is never stored anywhere — it only exists as the input to the key
derivation — so there is no copy to recover, no escrow, and no support
address that can help. That is what makes the vault safe from everyone else
too.

The **encrypted backup** is the only way back in. It is a separate file with
its own password, so forgetting one does not lose the other:

1. Create one from **⚙️ → 🛟 Encrypted Backup** while you still have access.
2. Keep the `.pvbak` file *and* its password somewhere safe and separate.
3. To restore, click **🛟 Restore from backup** on the login screen — it
   works without the old master password, and you set a new one during the
   restore.

The app asks you to make one the first time you create a vault, and asks
only that once. If you dismissed it, the menu item is always there.

If you have no backup and have forgotten the password, the entries cannot be
recovered — the only path forward is to delete `%APPDATA%\PasswordVault\`
and start again.

---

## 🔒 Security Notes

- All data is stored **locally** in `vault.dat`, encrypted with Fernet (AES-128-CBC + HMAC-SHA256).
- Encryption salt is stored in `vault.salt` (32-byte, backwards-compatible with 16-byte).
- Changing the master password journals the target salt to `vault.salt.pending` before re-encrypting. If the change is interrupted between writing the vault and rotating the salt, the login screen tries both salts, so the vault stays openable and the rotation is completed at the next unlock.
- The encryption key is derived from your **Master Password** using PBKDF2HMAC (SHA-256, 480K iterations).
- **Constant-time comparison** (`hmac.compare_digest`) is used for master password verification to prevent timing attacks.
- **Atomic file saves** — data is written to a temp file first, then atomically replaced to prevent corruption on crash.
- ⚠️ **Do not lose your Master Password!** There is no way to recover your data without it.
- Passwords are generated using Python's `secrets` module (cryptographically secure).
- Clipboard can be auto-cleared after a configurable timeout.
- All application events are logged to `vault.log` for diagnostics. **Passwords are never logged.**
- Vault and salt files are created with owner-only permissions (`icacls` on Windows, `0600` elsewhere).
- Breach checking uses the Have I Been Pwned range API: only the first 5 characters of the SHA-1 hash are sent, never the password or its full hash.
- Changing the master password rotates the salt, so an old vault copy gives no PBKDF2 head start against the new password.
- Restoring a backup keeps the salt and the ciphertext consistent: if the write fails, the previous salt is put back so the vault stays openable.
- Only `http` and `https` URLs are opened; any other scheme is refused so a crafted entry cannot invoke a protocol handler.
- Exported CSV/Excel values are escaped so a cell starting with `=`, `+`, `-`, or `@` cannot execute as a spreadsheet formula.

---


## Signing the build

The build is unsigned, and on Windows 11 that has consequences:
SmartScreen warns about it, and **Smart App Control blocks it outright**
when it is enabled. On a machine with Smart App Control on, the file will
not run at all until it is either signed with a certificate Windows
trusts *and* has reputation for, or explicitly allowed.

`tools/sign.ps1` does the signing once you have a certificate:

```
.\tools\sign.ps1 -Thumbprint <hash>
.\tools\sign.ps1 -PfxPath .\codesign.pfx
```

It needs `signtool.exe` from the Windows SDK
(`winget install Microsoft.WindowsSDK.10.0.26100`), signs SHA-256, and
timestamps through an RFC 3161 server. **The timestamp is not optional:**
without one, every copy already shipped stops verifying the day the
certificate expires. With one, the signature outlives the certificate.

### What each kind of certificate actually gets you

| | Unknown-publisher warning | Smart App Control |
|---|---|---|
| Unsigned | Yes | **Blocked** |
| Self-signed | Yes, and looks worse | **Blocked** |
| OV certificate | Gone | Only once reputation accumulates |
| EV certificate / Azure Trusted Signing | Gone | Passes from the start |

A **self-signed certificate does not help here**, which is worth stating
plainly because it is the obvious thing to reach for. Smart App Control
wants a signature that chains to a trusted root and carries reputation; a
certificate you made yourself has neither. Making Windows trust it means
installing it into the trusted root store, which tells that machine to
trust anything signed with that key — a worse position than shipping
unsigned — and Smart App Control would still block the file for want of
reputation. `-SelfSigned` exists in the script only to prove the plumbing
works, and it removes the throwaway key afterwards.

The practical options are **Azure Trusted Signing** (a Microsoft service,
cheap monthly, identity verification required) or an **EV code-signing
certificate** from a CA. A plain OV certificate removes the publisher
warning but leaves Smart App Control to be won over by download volume.

### Running it anyway, on your own machine

Turning Smart App Control off is **one-way**: once disabled it cannot be
re-enabled without reinstalling Windows. Do not reach for it to get past
a build you made five minutes ago. Unblock the single file instead —
Properties → Unblock, or allow it from the Smart App Control prompt.


## 📝 License

This project is open-source and available under the **MIT License**.
