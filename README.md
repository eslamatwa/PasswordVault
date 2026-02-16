# 🔐 Password Vault

A modern, secure, and elegant password manager for Windows — built with **Python** and **CustomTkinter** in Apple Dark Mode style.

## ✨ Features

### 🔒 Security
- **AES Encryption (Fernet)** — All passwords are encrypted locally using `cryptography` library.
- **PBKDF2HMAC Key Derivation** — Master password is hashed with 480,000 iterations of SHA-256.
- **Brute Force Protection** — After 5 failed login attempts, the vault locks for 30 seconds.
- **Auto-Lock** — Vault automatically locks after 5 minutes of inactivity.
- **Atomic File Saves** — Data is written to a temp file first, preventing corruption on crash.
- **Master Password Validation** — Enforces minimum 8 characters, uppercase, lowercase, and digits.

### 🎨 User Interface
- **Apple Dark Mode Style** — Sleek, modern UI with rounded corners and smooth design.
- **Card Color Customization** — Choose from 9 color presets (Blue, Green, Red, Orange, Purple, Teal, Yellow, Pink) for each entry card.
- **Password Strength Meter** — Visual indicator shows password strength in real-time (Very Weak → Very Strong).
- **Tooltips** — Hover over any button or feature to see a brief description of what it does.
- **Category Emoji Icons** — Each category gets an automatic emoji (💬 Social, 💼 Work, 🏦 Banking, etc.).
- **Show/Hide Password** — Toggle password visibility on login screen and in the edit dialog.

### 🔑 Password Management
- **Password Generator** — Cryptographically secure random password generator with customizable options:
  - Adjustable length (6–40 characters)
  - Toggle uppercase, lowercase, digits, and special characters
  - Real-time strength preview
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

### ⚙️ Settings
- **Change Master Password** — Update your master password with strength validation.
- **Lock Vault** — Manually lock the vault at any time.

## 🛠️ Installation

### Option 1: Installer (Recommended)
1. Download **`PasswordVault_Setup.exe`** from the [Releases](https://github.com/eslamatwa/PasswordVault/releases) page.
2. Run the installer — it will create:
   - 🖥️ **Desktop shortcut**
   - 📂 **Start Menu shortcut**
3. Launch **Password Vault** from your Desktop or Start Menu.

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

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern UI framework (dark mode) |
| `cryptography` | AES encryption (Fernet + PBKDF2) |
| `pyperclip` | Clipboard copy/paste |

## 🔒 Security Notes

- All data is stored **locally** in `vault.dat` (encrypted).
- Encryption salt is stored in `vault.salt`.
- The encryption key is derived from your **Master Password** using PBKDF2HMAC (SHA-256, 480K iterations).
- ⚠️ **Do not lose your Master Password!** There is no way to recover your data without it.
- Passwords are generated using Python's `secrets` module (cryptographically secure).

## 📝 License

This project is open-source and available under the **MIT License**.
