# Password Vault — MVP Status & Remaining Work

Snapshot of the hardening and polish pass on v3.4: what landed, what is
deliberately left, and how to verify any of it.

**Verified at the time of writing:** the full suite passes, `pyflakes`
reports nothing, and every dialog opens in both themes and both languages —
that last part is now a test rather than a manual pass.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m pyflakes main.py password_vault tests
```

---

## Done

### Security & data integrity
- **Formula injection** — CSV and Excel exports escape cells beginning with
  `=`, `+`, `-`, or `@`, and unescape them on import.
- **Link guard** — only `http` and `https` URLs are opened; anything else is
  refused with a notice instead of handing the string to the OS.
- **Single instance** — a named mutex on Windows (`flock` elsewhere) stops a
  second copy from running, so two windows can no longer overwrite each
  other's vault. The existing window is focused instead.
- **Lock hygiene** — auto-lock closes every open dialog, so no plaintext is
  left on screen; activity is tracked application-wide, so the Mini Vault and
  dialogs no longer let the vault lock while the user is typing.
- **Guarded writes** — every vault write reports failure to the user and
  queues the change for the next flush, instead of letting the exception
  escape a Tk callback and leave the change silently unpersisted.
- **Consistent restore** — restoring a backup commits the salt before the
  ciphertext and puts the previous salt back if the write fails, so the salt
  and the vault file can never disagree. Restoring into an unlocked vault
  rolls the in-memory vault back on failure.
- **Backup import limits** — a backup file above the size ceiling is refused
  before it is parsed.
- **Settings validation** — a value with the wrong type or outside its range
  falls back to its default rather than breaking startup.
- **Clipboard** — a failed copy is reported, and auto-clear only clears when
  the clipboard still holds the value this app put there.
- **Login failure clears the key** — a wrong master password used to leave
  the derived key set, which kept the idle timer armed on the login screen;
  the auto-lock then fired against a locked vault and placed a second login
  frame over the first. `_auto_lock` also returns early when already locked.
- **Password change cannot write over a locked vault** — the worker takes
  its key and vault snapshot on the Tk thread. Reading `app.data` itself
  meant a lock landing mid-flight re-encrypted `None`, which serializes as
  `"null"`, over every entry. The new key is only adopted if the session is
  still the one that started the change.
- **Restore validates the shape of the backup** — `normalize_vault` runs on
  every decrypted vault. A hand-edited backup decrypts cleanly and can still
  be the wrong shape; it used to be assigned straight onto the live vault and
  fail later in the UI, after the file was written and, at login, after the
  salt had been rotated. Unknown keys are preserved for forward
  compatibility.
- **Lockout survives a restart** — the failure streak and the lockout
  deadline are persisted to `settings.json`, so quitting the app no longer
  clears a lockout and returns a fresh set of attempts. A stored deadline
  further out than the longest penalty this app issues came from a clock
  change and is discarded.
- **Host arguments cannot start as flags** — `_sanitize_shell_arg` strips a
  leading hyphen. Every client here reads its arguments as options first, so
  a host imported from an untrusted file could otherwise arrive as a flag.
- **The Recycle Bin removes exactly one row** — matching on the id alone
  took every id-less row with it, so restoring one entry deleted before ids
  existed silently discarded the rest.

### Correctness
- **Trash retention reaches the disk.** The purge was applied to the
  in-memory copy only, so an entry the app had promised to delete after
  `TRASH_DAYS` could sit in the ciphertext indefinitely on a vault nobody
  edits — the opposite of what a retention period is for. It is written
  back only when something actually expired, which keeps the original
  point of filtering in memory: an ordinary startup still costs no
  re-encryption, and an item can only cross the boundary once. A failed
  write is housekeeping, so it logs and lets the vault open anyway.
- **Remote credentials are no longer rewritten on their way to a client.**
  `_sanitize_shell_arg` was an allowlist that *deleted* anything outside a
  small set from the username and host: `svc+deploy` connected as
  `svcdeploy`, and a non-Latin username was erased to an empty string, so
  the client prompted as though no user had been given. It existed to stop
  command injection, but every client is launched with an argument list,
  which no shell parses. A value carrying a shell metacharacter is now
  refused with a message naming it.
- **MobaXterm gets correctly quoted arguments.** Its `-newtab` takes one
  command string; the old code wrapped the username in literal single
  quotes on the assumption that string was not shell-parsed. It is —
  verified against MobaXterm 26.3 by having it run a script that printed
  its own argv — so `shlex.quote` is the right quoting and a username with
  a space or an apostrophe now survives.
- **MobaXterm leads the client list**, so it is what Enter picks.
- **The staged password outlives the client's startup.** It was cleared
  after a flat 10 seconds, which is shorter than MobaXterm takes to
  cold-start; the client then asked for a password the clipboard no longer
  held. The floor is now 60 seconds, and a longer configured clipboard
  timeout is respected.
- Import/export round-trips `modified_at`, `pinned`, and datetime cells, and
  uses one field map for both directions.
- Duplicate detection, the security score, and password age were reworked:
  the score counts only the *extra* uses of a reused password, and a future
  timestamp reads as `Future?` rather than `Today`.
- The generator honours the requested length even when it is shorter than the
  number of selected character classes.
- Restoring from the Recycle Bin regenerates the id on collision, so two
  entries can never share one.
- The Security Dashboard re-reads the vault so its score and breach results
  reflect the current state.
- Generator options persist between sessions.
- Search filtering is one shared helper, so the main window and the Mini
  Vault cannot disagree about what a query matches.

### Interface
- **The Mini Vault's cards are plain Tk widgets too**, and share the main
  list's cache. `CardPool` in `ui/widgets.py` owns the reuse and the
  invalidation for both lists, with one `card_signature` deciding what
  counts as a change — a second copy would be a second place for those
  rules to drift apart. Filtering the Mini Vault, which is what its search
  box does on every keystroke, went from 190 ms to 50 ms. Showing an
  unfiltered list costs the same as before: the paint happens either way,
  and building seven small widgets was never the expensive part there.

  Extracting it caught a bug that was about to ship. A theme change
  refreshed the Mini Vault without clearing its cache, so it re-showed
  cards still holding the previous palette while the main window updated
  around them. One line, and only findable by switching the theme with
  the window open.
- **The entry list is 36x faster.** A repaint used to cost about a quarter
  of a second per row, on the surface that repaints on startup, on every
  settled search keystroke, on a category switch, and after every add,
  edit, delete and pin. A sixty-entry vault took fifteen seconds.

  | entries | before | after |
  |---------|--------|-------|
  | 5       | 1.5 s  | 0.16 s |
  | 10      | 2.8 s  | 0.30 s |
  | 20      | 5.1 s  | 0.41 s |
  | 60      | 15.3 s | 0.42 s |
  | 100     | 15.2 s | 0.38 s |

  Three changes, in the order they were measured. *Cheaper rows*: a
  CustomTkinter widget draws itself onto its own canvas, which costs 9x a
  plain `tk.Label` for text and 35-50x for a button or frame; a card was
  43 of them and is now 14 plain widgets plus the CTkFrame that gives it
  its rounded tint. *A smaller page*: 60 to 20, sized to a screenful plus
  headroom. *Reuse*: cards are built once and hidden and shown rather than
  destroyed and rebuilt, which is what took the last 2 s down to 0.4.

  Nothing about a card's behaviour changed. `icon_button` is a `tk.Label`
  with hover, a hand cursor and a click binding, and `tip()` layers on top
  because it binds with `add="+"`. What was lost is the corner radius on
  the small borderless icons, where at 24px with no fill it was never
  apparent.

  Three approaches were measured and rejected first: detaching the scroll
  container while filling it (1%, noise), building the holder loose and
  attaching it to the canvas afterwards (no consistent difference), and
  replacing `CTkScrollableFrame` with a hand-rolled canvas scroller (17%).
  The cost is painting widgets inside a canvas at all — the same cards
  outside a scroller paint in 654 ms against 3173 ms inside one. Reuse is
  what gets past that floor, by not doing the work.

  The two prices paid. Plain widgets keep whatever colour they were given,
  so `_apply_appearance()` repaints the list and the Mini Vault on a mode
  change. And `refresh_entries` now owns a cache, so every path that
  changes an entry has to invalidate it — `_card_signature` covers that by
  comparing everything a card draws, and `tests/test_card_cache.py` tests
  the invalidation rather than the speed.

  Reproduce any of it with `python tools/benchmark_ui.py`.
- **A forgotten master password is now stated, once, at creation.** The
  encrypted backup was the only way back into a vault whose password had
  been forgotten — no escrow, no reset, which is the point — but it lived
  in a menu the user had no reason to open. A vault could be filled with
  passwords for months with nothing having said there was no way back in.
  The prompt fires once when a vault is created, offers to make the backup
  there and then, and records that it asked so it never nags.
  `last_backup_at` is recorded when one is written.
- **Nothing blocks the window any more.** Deriving a key is ~300ms of
  deliberate PBKDF2 work, and it ran on the Tk thread at every unlock,
  every encrypted backup and every restore — freezing the window before it
  could even repaint the click. All three now derive in a worker and show a
  busy state; `_run_busy` in the backup dialog carries the pattern. The
  restore also validates the new master password *before* decrypting rather
  than after, so a mistyped field costs nothing.
- **Card colour strips are `(light, dark)` pairs.** They were single values
  tuned against a dark card, so in light mode the accent sat on a pale tint
  at nearly the same luminance and read as a smear rather than an edge. The
  light member of each pair is the darker, more saturated iOS colour; a test
  asserts that relationship rather than trusting the eye.
- **The floating widget follows the theme.** A raw `tk.Canvas` takes one
  colour string, not a pair, and CustomTkinter has no hook to tell it about
  a mode switch — so the bubble polls once a second. It is the one surface
  that outlives a theme change, since it stays up while the main window is
  hidden.
- **A failed deferred save now says so.** Pinning an entry on a full disk
  looked like it worked, and the only symptom was the pin being gone at the
  next unlock. Reported once per run of failures, and never while quitting.
- **Light and dark themes** — every colour is a `(light, dark)` pair, with a
  resolver for raw tkinter widgets (menus, canvases, tooltips) and a theme
  switch in Settings.
- Hidden passwords use a fixed-width mask, so the rendered width says nothing
  about the real length; revealing wraps the full value instead of truncating.
- Long titles are elided with the full text in a tooltip.
- Destructive confirmations no longer fire on `Enter` — deleting takes a
  deliberate click.
- Nested dialogs hand the modal grab back correctly on close.
- Exiting asks for confirmation, including from the floating widget menu.
- Dialogs have a size floor and are clamped to the visible desktop, so display
  scaling and secondary monitors no longer clip or hide them.
- Export errors reuse one status line instead of stacking labels.
- The Recycle Bin header count and Empty button update as items are removed.

### Keyboard
- `Enter` submits from any single-line field in the entry dialog.
- `Tab` and `Shift+Tab` leave the Notes box instead of indenting inside it.
- `Esc` clears the search box.
- `Ctrl+N/F/L/E/I` and `Ctrl+C/V/X/A` are matched by physical key, so they
  keep working under a non-Latin keyboard layout (Arabic, Russian, etc.).

### Packaging & docs
- **The master-password change is recoverable.** The target salt is
  journalled before the vault is re-encrypted under its key, so the window
  where the ciphertext and the salt disagree is no longer opaque: the login
  screen tries both salts and the vault opens either way. Previously, a
  failed rotation *and* a failed rollback left a file no password could
  open, logged as critical with nothing to do about it. Completing an
  interrupted rotation happens at the next successful unlock.
- **The executable no longer carries readable source.** The spec added the
  package `.py` files as data because the dialogs are imported lazily and
  static analysis misses them — but `hiddenimports` already covers that.
  Verified by building both ways: 21 embedded `.py` entries before, 0 after,
  and `PasswordVault.exe --self-test` resolves all 19 lazy modules in the
  built exe. `tests/test_packaging.py` keeps that list and the spec's from
  drifting apart.
- **Bitwarden JSON and 1Password 1PUX import.** A column map cannot
  express folders and vaults joined by id, several URIs per item, per-item
  custom fields and sections, or typed items beyond logins, so both are
  read directly. Secure notes, cards and identities import as notes-only
  entries with their type recorded, because only a login has a password
  and skipping the rest would discard most of a vault in silence.

  1PUX is a zip, which raised the question this file had been holding open:
  where do attachments go, in an app that stores no files? They are named
  in the entry's notes and located — "still in the .1pux file" — rather
  than extracted. Writing decrypted documents onto disk beside an encrypted
  vault would be the opposite of the point, and dropping them without a
  word is what the rest of the importer exists to avoid.
- The build spec lists the lazily imported dialog modules and
  `instance_lock` as hidden imports; the README points at the spec instead of
  a hand-written PyInstaller command that would miss them.
- `requirements-dev.txt` for test and build tooling.
- README and `FEATURES.txt` brought up to v3.4.
- **Security claims match the code.** The docs advertised AES-256 where
  Fernet is AES-128-CBC plus HMAC-SHA256; a "Secure Memory Wipe" that the
  code itself notes is impossible for Python strings; an 8-character master
  password minimum against a 12-character check; two theme modes against
  three; and a password auto-copy that was deliberately removed. Brute-force
  protection now says what it does and does not cover. Corrected in README,
  `FEATURES.txt`, and the About dialog.

### Tests
`tests/` covers encryption round-trips and schema migration, trash retention,
the oversized-vault and oversized-backup guards, the encrypted backup format
and each of its rejection paths, restore rollback, import/export fidelity and
formula escaping, URL scheme validation, strength/age/duplicate/score logic,
generator length handling, settings validation, the single-instance lock, the
theme tokens, the vault shape guard and its fallbacks, the persisted lockout
state, the Recycle Bin removal helper, and the pure UI helpers.
`tests/test_unlock_flow.py` runs the whole unlock path with nothing
stubbed — real PBKDF2, real Fernet, real files — including recovery from an
interrupted master-password change, because that is a property of the login
screen rather than of the crypto helpers.

cryptography-dependent tests skip themselves when the library is unavailable;
`test_theme` and `test_widgets` import `customtkinter` directly, so it is a
hard test dependency rather than an optional one.

---

## Done — the three large items

All three landed, in the order this file recommended. The UI smoke harness
was built first, because each of them edits UI code that had no test at all.

### 0. UI smoke harness (`tests/test_dialogs_smoke.py`)
Opens every dialog in both themes and in both languages, asserts each one is
actually **mapped** (not merely constructed), and covers the grab stack, the
Enter-cancels rule on destructive confirmations, and that auto-lock leaves no
window on screen. This is the gate the three items below were built against.

One finding from writing it: a Tk root per test exhausts the interpreter's
Tcl support after about forty roots and then fails somewhere unrelated, so
the app is built once per session and reset between tests.

### 1. Dialog unification
`dialog_header` and `button_row` in `ui/widgets.py` carry the chrome every
dialog was repeating by hand, and `app._confirm` replaced five copies of the
destructive-confirmation dialog.

Two of those copies — the Recycle Bin's "Delete Forever" and "Empty Trash" —
built their toplevel directly and took the grab through `modal_child`, a
second mechanism that never appeared in `_grab_stack`. That divergence is
gone rather than documented, and `modal_child` with it.

### 2. External import profiles (`import_profiles.py`)
Chrome/Edge, Bitwarden, LastPass, 1Password, KeePass and Firefox, each with a
fixture in `tests/fixtures/` holding a real header row.

The two open questions are answered in that module's docstring. In short:
detect from the header row but *show* the guess in the import dialog with an
override, and fold columns this app has no home for — TOTP secrets, custom
fields — into the entry's notes rather than dropping them. Export bookkeeping
(`type`, `reprompt`) is reported as unmapped instead, because folding it in
put "Item type: login" on every entry.

Detection ranks by signature coverage and then by specificity: Chrome's
column set is a subset of LastPass's, so a LastPass file satisfies both
completely and only the second term separates them.

### 3. Arabic localization and RTL (`i18n.py`)
The English string is its own key, so call sites stay readable and a missing
entry falls back to English rather than to a key. Placeholders are named, so
a translation can reorder them.

Direction helpers (`anchor_start`, `side_start`, `pad`, …) live beside the
catalog because Tk has no writing direction: `anchor`, `justify`, `side` and
every padding pair are absolute and fixed at widget creation. That is also
why changing language rebuilds the window — there is no way to re-flow an
existing tree.

`tests/test_i18n_coverage.py` is what keeps this honest. It fails on any
user-facing literal that does not reach `t()`, on any string with no Arabic
entry, and on any catalog key nothing uses. Adding an untranslated string
later is invisible in English, so the check has to be static.

---

## Remaining — large, each needs a decision before starting

Nothing at this size is outstanding. Rendering the entry list was the last
one and is in *Done* above. The next candidates, none started:

- **A third interface language** is now purely a data change: add a catalog
  to `CATALOG` and a code to `LANGUAGE_CODES`. The coverage test already
  iterates over every catalog, so a new one is held to the same completeness
  as Arabic from the moment it is added.

---

## Remaining — smaller, known and deliberate

- **Tk has no bidi algorithm.** Segoe UI handles the joining, but a string
  mixing Arabic with Latin is rendered in logical order rather than
  reordered visually. The fields where that actually showed — URL, host and
  port — are now pinned to left alignment through `ltr_justify()`, so their
  own content reads correctly while their labels still mirror. A note or a
  title that mixes both scripts remains unreordered, and fixing that
  properly means a bidi implementation Tk does not have.
