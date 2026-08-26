# 🔐 Password Vault

A modern, secure, and elegant password manager for Windows — built with **Python** and **CustomTkinter** in Apple design style, with both light and dark themes.

**Version:** 3.4 | **Developer:** Eslam Atwa

---

## ✨ Features

### 🔒 Security
- **AES-256 Encryption (Fernet)** — All passwords are encrypted locally using `cryptography` library.
- **PBKDF2HMAC Key Derivation** — Master password is hashed with 480,000 iterations of SHA-256.
- **Brute Force Protection** — Configurable max login attempts (3–15) with lockout duration (15s–5min).
- **Auto-Lock** — Vault automatically locks after a configurable period of inactivity (1–30 min or Never).
- **Auto-Clear Clipboard** — Optionally clear copied passwords from clipboard after 10–60 seconds.
- **Atomic File Saves** — Data is written to a temp file first, preventing corruption on crash.
- **Master Password Validation** — Enforces minimum 8 characters, uppercase, lowercase, and digits.
- **Single Instance Lock** — Only one copy of the app can run, so two windows can never overwrite each other's vault.
- **Security Dashboard** — Overall vault score plus weak, reused, and stale password reports.
- **Breach Check** — Checks passwords against Have I Been Pwned using k-anonymity, so no password or full hash ever leaves the machine.
- **Encrypted Backup & Restore** — Export the whole vault to a separately-encrypted file and restore it, including from the login screen.
- **Safe Export** — CSV and Excel exports neutralize spreadsheet formula injection.
- **Link Guard** — Only `http` and `https` links are ever opened.
- **Lock Hygiene** — Auto-lock closes every open dialog so no plaintext stays on screen.

### 🎨 User Interface
- **Light & Dark Themes** — Full iOS-inspired palettes for both, switchable from Settings.
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
- **Recycle Bin** — Deleted entries are recoverable for a retention period before being purged.
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
  - **SSH Client chooser** — Auto-detects installed clients: PuTTY, MobaXterm, Windows OpenSSH
  - Password auto-copied to clipboard on connect
- **RDP Session Dialog** — Launch Remote Desktop with:
  - Host/IP input (auto-filled from entry URL)
  - Username and port configuration
  - Password auto-copied to clipboard on connect

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
| 🎨 **Appearance** | Theme | Light or Dark |
| 🎨 **Appearance** | Default Card Color | Choose default color for new entries |
| 🚀 **Behavior** | Start Minimized | Launch to floating widget instead of full window |

Settings are validated on load: a value with the wrong type or outside its allowed range falls back to the default instead of breaking startup.

All settings are saved to `%APPDATA%\PasswordVault\settings.json`.

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
│   ├── export_import.py             # CSV & Excel export/import helpers
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
| `cryptography` | AES encryption (Fernet + PBKDF2) |
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

The suite covers encryption round-trips and schema migration, restore rollback,
CSV/Excel import-export fidelity and formula escaping, URL scheme validation,
password strength/age/duplicate/score logic, generator length handling,
settings validation, the single-instance lock, and the pure UI helpers. The
Tk-dependent tests skip themselves automatically when no display is available.

---

## 🔒 Security Notes

- All data is stored **locally** in `vault.dat` (AES-256 encrypted).
- Encryption salt is stored in `vault.salt` (32-byte, backwards-compatible with 16-byte).
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
