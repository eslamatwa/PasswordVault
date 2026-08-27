# 🔐 Password Vault

A modern, secure, and elegant password manager for Windows — built with **Python** and **CustomTkinter** in Apple design style, with both light and dark themes.

**Version:** 3.4 | **Developer:** Eslam Atwa

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

### 🖱️ Right-Click Context Menu
- **Full Context Menu** — Right-click any entry card (in main vault or Mini Vault) for quick actions:
  - 📋 Copy Username / 🔑 Copy Password
  - 🌐 Open URL in Browser / Open URL + Copy Username
  - 🖥️ **SSH Session** — Launch SSH with PuTTY, MobaXterm, or Windows SSH
  - 🖥️ **RDP Session** — Launch Remote Desktop connection
  - ✏️ Edit / 📌 Pin / 🗑️ Delete

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

The format is detected from the header row and shown in the import dialog,
with a dropdown to override it if the guess is wrong. Folders, groupings and
tags become categories; favourites become pinned entries.

**Nothing is dropped in silence.** A TOTP secret or a custom field has no
dedicated home in this app, so it is appended to the entry's notes under its
original name rather than discarded. Any column that cannot be carried at all
is listed in the dialog *before* you import.

**Bitwarden JSON** is read directly rather than through a column map, because
a CSV cannot express what that format holds: folders joined by id, several
URIs per item, per-item custom fields, and typed items beyond logins. Secure
notes, cards and identities are imported as notes-only entries with their
type recorded — skipping them silently would be the worst outcome. A
password-protected Bitwarden export cannot be read; the dialog says so and
tells you to export again without encryption.

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
│   ├── instance_lock.py             # Single-instance mutex / lock file
│   └── ui/
│       ├── __init__.py
│       ├── widgets.py               # Tooltip, iOS-style group/field/combo, search bar
│       ├── mini_vault.py            # Mini Vault (compact always-on-top viewer)
│       ├── floating.py              # Floating Widget (draggable bubble)
│       └── dialogs/
│           ├── __init__.py
│           ├── about.py             # About dialog
│           ├── backup.py            # Encrypted backup export / restore
│           ├── change_password.py   # Master password change (threaded re-encrypt)
│           ├── data_io.py           # CSV / Excel export & import
│           ├── generator.py         # Password generator
│           ├── security_dashboard.py# Score, weak/reused/old lists, breach check
│           └── trash.py             # Recycle Bin
├── tools/
│   └── benchmark_ui.py             # Entry-list render benchmark
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
python -m pytest -q          # unit tests
python -m pyflakes main.py password_vault tests
```

The suite covers encryption round-trips and schema migration, the vault shape
guard, restore rollback, CSV/Excel import-export fidelity and formula escaping,
one fixture per supported import format, URL scheme validation, password
strength/age/duplicate/score logic, generator length handling, settings
validation, the persisted lockout state, the single-instance lock, and the pure
UI helpers.

Two of them are worth calling out:

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

Tk-dependent tests skip themselves automatically when no display is available.

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
- **Rendering the list is not.** A card is 43 CustomTkinter widgets and a
  CTk widget costs 9–46x a plain Tk one, so a repaint runs about a quarter
  of a second per row — and the list repaints on search, category switch,
  and every add, edit, delete or pin. Measure it on your own machine with:

  ```bash
  python tools/benchmark_ui.py
  ```

  This is the next thing to fix; the options and the recommendation are
  written up in [MVP.md](MVP.md) under *Rendering the entry list*.

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

## 📝 License

This project is open-source and available under the **MIT License**.
