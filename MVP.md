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
- **A signing pipeline, and an honest note about what it can do.** The
  built exe is unsigned, and Smart App Control blocks unsigned binaries
  outright rather than warning about them. `tools/sign.ps1` signs and
  timestamps once a certificate exists — timestamped, so shipped copies
  keep verifying after the certificate expires.

  What it cannot do is make a self-signed certificate work. Smart App
  Control wants a trusted chain *and* reputation; a self-made certificate
  has neither, and the only way to fake the first half is installing it
  as a trusted root, which is a worse security position than shipping
  unsigned and still fails the second half. Recorded here because it is
  the obvious thing to try. Azure Trusted Signing or an EV certificate
  are the routes that actually work.

- **SSH and RDP are on every entry's menu now, greyed when they do not
  apply.** They had been added only when the entry looked like a remote
  host and left out otherwise, which reads as the feature being missing
  rather than not applicable — nothing on screen said the actions
  existed, why that entry could not use them, or what to change. A vault
  of ordinary logins showed no trace of SSH support at all, which is how
  it was reported.

  Disabled items now carry the reason, "(set a host or IP)". That is
  already how the same menu treats "Open URL in Browser" on an entry with
  no URL, so it is the consistent behaviour rather than a new idea. The
  rule itself is untouched: a webmail entry still does not get a live SSH
  action, and a test holds that line, since greying out is a presentation
  change and must not quietly become "offer SSH on anything with a URL".

  Both menus call one helper. The Mini Vault had its own copy of these
  items, which is exactly the drift worth removing.

- **The custom SSH client setting works now, and can be reached.** It
  shipped dead. Settings are validated against a whitelist on load and
  `ssh_client_path` was not in it, so every stored value was dropped with
  a warning nobody reads. The tests passed because they handed the dict
  straight to the detector and never went through `load_settings`, which
  is the part that broke it — a reminder that a test which skips the
  wiring tests only the half that was already right.

  It also had no UI, which made it half a feature even once fixed:
  editable only by hand-editing JSON. Settings has a *Remote Sessions*
  group with an **Extra SSH Client** field now.

  One decision inside it: the path is not checked for existence at load.
  Settings are read while the vault is still locked, so a client on a
  network drive that is not mounted yet would be silently forgotten
  forever. Detection checks the file when it actually needs it.

- **SSH keys, and an interface plan to fit them into.** Plenty of servers
  take a key, and the app handled none. An entry can now reference a key
  file or hold one the app generated; the private half of a generated key
  lives in the vault, and its public half is derived on demand rather
  than stored twice.

  The passphrase field appears only when the key actually has one, which
  needs the key *body* parsed — `ssh-keygen` writes the same header
  either way. Asking for a passphrase that does not exist teaches people
  to type their account password into a field nothing reads; staying
  silent when there is one leaves them at a prompt with an empty
  clipboard. And with a key in play the clipboard gets the passphrase,
  not the account password — or nothing at all when the key has none.

  Two things only running the real tools revealed. `ssh-keygen` refuses a
  key file whose permissions are loose, with "Bad permissions" — which
  reads as a broken key rather than an ACL, and would have made the
  stored-key path fail confusingly; materialised keys are now locked to
  the current user and verified against `ssh-keygen` itself. And
  generating a key *with* a passphrase needs `bcrypt`, which is not a
  dependency here, so generated keys have none: the vault is already the
  protection, and a passphrase on top stops nobody holding a decrypted
  vault.

  The entry dialog was the blocker. It had reached ten fields across five
  groups, and these would have added five more, so the interface plan was
  written first: common fields open, auto-type and SSH keys behind one
  *Advanced* disclosure whose header names what is set inside. Hidden is
  acceptable; silently in force is not.

- **A third guard found doing nothing.** The translation-coverage test
  read a hand-written list of UI files, so `ui/ssh_key_field.py` was
  simply not checked and shipped twenty-two untranslated strings with the
  test green. It globs the whole `ui` tree now. That is three this week —
  a guard that has to be remembered to be updated is not a guard.

- **Auto-Type.** A global shortcut types the username and password into
  whatever window is in front — browser, MobaXterm, RDP, anything. Chosen
  over a browser extension because the work here is servers: an extension
  covers the smallest part of it and is the largest, most dangerous thing
  in the project to build.

  `RegisterHotKey`, never a keyboard hook. Windows reports the one
  combination asked for and nothing else; a low-level hook would receive
  every keystroke on the machine, which is what a keylogger is and what
  antivirus software would call it.

  Five checks stand between the press and the keystrokes: unlocked, not
  our own window, a confident match, the target window confirmed back in
  front, and still that window before *every* step. The last is the one
  easy to omit — a sequence takes a second or two, and the half that lands
  after an alt-tab is usually the password.

  Per entry: window patterns (`*.corp.local`), a general-account flag, and
  an editable typing order for logins split across two pages. Refusing is
  the default everywhere: two accounts on one site open a chooser rather
  than a guess, and a pattern of only `*` is rejected outright.

  Nine defects came out of reviewing it, four of them silent: an INPUT
  struct 8 bytes short so `SendInput` sent nothing and returned zero;
  truncated 64-bit window handles; a sequence that kept typing after the
  vault locked; and a guard against typing into our own window that could
  never fire, because Tk wraps its toplevels and `winfo_id()` is never the
  handle `GetForegroundWindow` reports. Its test passed by feeding in the
  same wrong value the code compared against.

- **Two things only real use found.** The chooser was built on the app's
  modal dialog machinery, and a `transient` window drags its owner up —
  so asking for one password brought the entire vault to the front. And
  it offered only ranked matches plus general accounts, with its search
  filtering that list, so on an unmatched window every other password was
  unreachable. A test asserted that second behaviour, which is worse than
  the bug: a test that guards a defect makes it look deliberate.

  Both were reported from using the app while 686 tests were green. The
  fix for the first is a plain always-on-top window; for the second, the
  rest of the vault behind a divider. Ranking orders the list, it does not
  decide who is in it.

- **Remembering a window.** Matching reads the window title and nothing
  else, and some titles never mention what they belong to: an entry at
  `mail.wavz.com.eg` cannot be connected to a window called
  `Outlook - Google Chrome`. No better matcher fixes that. The chooser
  offers to remember the window against the entry instead — one tick, and
  it types without asking from then on.

- **Typed servers, and the menu items that stopped refusing them.** Two
  changes from the same report, and the same root cause: one domain
  account opens dozens of machines, and the entry holding it has no host
  of its own and never will.

  SSH and RDP are live on every entry now. They had been hidden when the
  entry did not look like a remote host, then greyed out with a reason —
  which explained the situation and still blocked the case the feature
  exists for. The host belongs in the dialog, which has a field for it
  and already refuses to connect without one.

  The batch dialog gained a second tab for typing or pasting a list,
  `[user@]host[:port]` a line, with a chosen account filling in any line
  that names no user. Parsing lives in `ui/bulk_targets.py`, apart from
  the window, because a misread line is not a failed connection — it is a
  session opened to the wrong machine with a domain account. Blank lines
  and `#` comments are skipped so a list can be pasted with notes in it,
  duplicates are dropped, and a bad line is reported by number rather
  than costing the good ones around it.

  Writing those tests found `root@:22` producing a host of `":22"` with
  no complaint, which would have been launched. Any colon not followed by
  a number now refuses the line rather than deferring the failure to ssh,
  where it surfaces as the machine being unreachable and the typo is
  nowhere in sight.

- **Client detection stopped depending on where the installer put
  things.** A dropdown that only lists what it found makes a client
  installed somewhere unexpected indistinguishable from one that is not
  installed — reported as "PuTTY is missing" when winget had put its
  shim on PATH, nowhere near Program Files. PATH is searched now, and
  `ssh_client_path` in settings covers anything still left out. These
  tests run without a display, since detection is static and the windowed
  tests here are the flaky ones.

- **Several SSH sessions at once.** Ten servers meant ten trips through
  the same dialog, re-picking the same client each time. The new dialog
  lists everything the right-click menu would offer SSH for — the same
  `_looks_remote` test, with a test asserting the two agree — and opens
  the ticked ones.

  The hard part was the password, not the launching. One clipboard cannot
  hold ten, and rotating them on a timer would mean the clipboard holding
  whichever secret happened to be current when the user pressed Ctrl+V.
  So the batch stages nothing. A panel stays up with one button per
  server: the user clicks the row for the tab they are in, and that one
  password goes over under the usual auto-clear. One secret at a time,
  and it is the one that was asked for. The panel is destroyed by the
  auto-lock like any other dialog, because it can reach every password in
  the batch.

  Launches are chained through `root.after`, not looped: `Popen` returns
  immediately, so a loop fires them all into one instant, which makes a
  cold-starting MobaXterm drop tabs. A host or username carrying a shell
  character is shown with the reason and left unpickable rather than
  hidden — an entry that offers SSH from its own menu and is missing here
  would read as a bug in the list — and never rewritten, which is the
  rule the single-session flow already follows.

  Two ways in. The main menu has it, and so does the single-session SSH
  dialog — the moment someone notices they want ten of these is the
  moment they are looking at the dialog for one. Following it closes the
  single dialog rather than stacking a second modal on the same job. The
  RDP dialog does not offer it, because the batch opens SSH sessions and
  putting it there would promise something it does not do. The
  right-click menu keeps its two per-entry items unchanged.

  Writing the tests found a real defect: the chain outlived whatever
  started it, so a batch kept opening sessions after the vault
  auto-locked. It surfaced as launches from one test appearing in the
  next one's results. `cancel_ssh_batch` now runs on lock, on quit, and
  before a new batch starts.

- **The test suite stopped borrowing the developer's machine.** It drives
  a real Tk application, so a run put a window and a Toplevel per dialog
  on screen for four minutes, appearing, taking focus and vanishing. It
  was reported as the app opening and closing on its own, which is a fair
  reading of what it looks like — the windows are real, they are just not
  the user's. They are now mapped at +30000+30000 rather than hidden,
  because other tests ask whether a card or a dialog is actually visible
  and hiding them would make those tests pass on nothing. `lift`,
  `tkraise` and `focus_force` are no-ops for the run, and `-topmost` is
  ignored; stealing the keyboard is worse than merely being seen.

  Rewriting the position in `geometry()` was not enough on its own: a
  Toplevel that never asks for a position gets one from the window
  manager, which put these at the top-left of the display. Windows are
  moved at construction too.

- **And it stopped writing to the real log.** `password_vault/__init__.py`
  attaches a rotating handler to `%APPDATA%/PasswordVault/vault.log` when
  the package is imported, so the suite had been appending thousands of
  lines to the log belonging to the installed copy — and rotation then
  discarded the genuine history. That log is the only record of anything
  a user reports, so filling it with test output destroys the evidence
  exactly when it is needed. `conftest` now redirects `APPDATA` at import
  time, which is the only point early enough to beat the handler, and
  fails loudly if anything gets in ahead of it.

  What the app logs gained along the way: a start line with the pid and
  argv, the window transitions at INFO, and `log.exception` around the
  main loop, since a windowed build has no console and a crash otherwise
  left nothing at all behind.

- **The small buttons kept their rounded corners.** Moving the cards to
  plain Tk cost the icon buttons their corner radius, which was the one
  visible thing the speed was paid for. Three ways to get it back were
  measured per button: a CTkButton 6.00 ms, a CTkCanvas driven by
  CustomTkinter's own DrawEngine 4.03 ms, and a `tk.Label` wearing a
  cached pill image 0.48 ms against a 0.42 ms square baseline. The last
  one costs 15% of a plain label rather than 14x it, so that is what
  ships; a 20-entry repaint is unchanged at ~355 ms.

  The pill is a `tk.PhotoImage` drawn once per (size, colour) pair, with
  the corners antialiased in Python. Tk will not antialias a canvas
  polygon and Pillow is not a dependency here — adding one to round six
  24px buttons would be a poor trade and would grow the one-file exe.
  Because a Tk image has no alpha, the colour behind the corners is baked
  in, so the cache is keyed on the card colour too; it stays bounded by
  (pill kinds x card colours) rather than by entry count.

- **Copying a password armed its auto-clear again.** The flash on a copy
  button still read `fg_color`, which is a CTkButton option and does not
  exist on the labels the cards are built from now. It raised after the
  password reached the clipboard and before the auto-clear was
  scheduled, so the secret stayed there until something else overwrote
  it, and the only visible symptom was a missing confirmation. Both
  lists went through that path. `flash_button` handles either kind of
  button, and the click is covered by a test now — nothing had ever
  clicked one.

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

- **A third interface language.** Considered and not wanted: English and
  Arabic cover the users this is built for. The machinery is in place if
  that changes — a catalog in `CATALOG`, a code in `LANGUAGE_CODES`, and
  the coverage test holds any new one to the same completeness as Arabic
  from the moment it is added.

---

## Remaining — smaller, known and deliberate

- **Tk has no bidi algorithm.** Segoe UI handles the joining, but a string
  mixing Arabic with Latin is rendered in logical order rather than
  reordered visually. The fields where that actually showed — URL, host and
  port — are now pinned to left alignment through `ltr_justify()`, so their
  own content reads correctly while their labels still mirror. A note or a
  title that mixes both scripts remains unreordered, and fixing that
  properly means a bidi implementation Tk does not have.
