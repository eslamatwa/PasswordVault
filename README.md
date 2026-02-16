# 🔐 Password Vault

A modern, secure, and elegant password manager for Windows — built with **Python** and **CustomTkinter** in Apple Dark Mode style.

**Version:** 2.0 | **Developer:** Eslam Atwa

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

### 🎨 User Interface
- **Apple Dark Mode Style** — Sleek, modern UI with iOS-inspired colors and rounded corners.
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

### 🪟 Floating Widget & Mini Vault
- **Floating Widget** — Minimizes to a small draggable bubble (always on top) for quick access.
- **Mini Vault** — A compact, always-on-top window to search, copy, and edit passwords without opening the full app.
  - Category filtering
  - Copy username/password
  - Edit entries directly
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
| 🎨 **Appearance** | Default Card Color | Choose default color for new entries |
| 🚀 **Behavior** | Start Minimized | Launch to floating widget instead of full window |

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
pip install -r requirements.txt
pip install pyinstaller
```

### Step 2: Build the Executable
```bash
pyinstaller --noconfirm --onefile --windowed --icon=icon.ico --name=PasswordVault --add-data "icon.ico;." main.py
```
This creates `dist/PasswordVault.exe` — a single standalone executable.

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

## 📂 Data Storage

| File | Location | Purpose |
|------|----------|---------|
| `vault.dat` | `%APPDATA%\PasswordVault\` | Encrypted password database |
| `vault.salt` | `%APPDATA%\PasswordVault\` | Encryption salt |
| `settings.json` | `%APPDATA%\PasswordVault\` | User preferences |

> Data is stored in `%APPDATA%` (typically `C:\Users\<you>\AppData\Roaming\PasswordVault\`) to ensure persistence across app updates and proper backup support.

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern UI framework (dark mode) |
| `cryptography` | AES encryption (Fernet + PBKDF2) |
| `pyperclip` | Clipboard copy/paste |
| `pyinstaller` | Build standalone executable (dev only) |

---

## 🔒 Security Notes

- All data is stored **locally** in `vault.dat` (AES-256 encrypted).
- Encryption salt is stored in `vault.salt`.
- The encryption key is derived from your **Master Password** using PBKDF2HMAC (SHA-256, 480K iterations).
- ⚠️ **Do not lose your Master Password!** There is no way to recover your data without it.
- Passwords are generated using Python's `secrets` module (cryptographically secure).
- Clipboard can be auto-cleared after a configurable timeout.

---

## 📝 License

This project is open-source and available under the **MIT License**.
