# 🔐 Password Vault

A modern, secure, and simple password manager for Windows, built with Python and CustomTkinter.

![Screenshot](https://i.imgur.com/example.png)

## ✨ Features

- **Modern UI:** Dark mode, rounded corners, and smooth animations.
- **Secure Encryption:** Uses **Fernet (AES)** encryption to store passwords locally.
- **Floating Widget:** Minimizes to a draggable floating bubble (always on top) for quick access.
- **Categories:** Organize passwords with emoji icons (General, Social, Work, etc.).
- **Search:** Instant search across all entries.
- **Clipboard:** One-click copy for usernames and passwords.
- **Notes:** Add optional notes to each entry.

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/PasswordVault.git
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

- `customtkinter` (UI framework)
- `cryptography` (Encryption)
- `pyperclip` (Clipboard management)
- `Pillow` (Image handling)
- `pystray` (System tray integration)

## 🔒 Security Note

- All data is stored locally in `vault.dat`.
- The encryption key is derived from your **Master Password** using PBKDF2HMAC.
- **Do not lose your Master Password!** There is no way to recover your data without it.

## 📝 License

This project is open-source and available under the MIT License.

