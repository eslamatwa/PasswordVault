"""Translation lookup and layout direction.

The English string is its own key. That was the deciding choice for
retrofitting this onto a UI that was written entirely in hardcoded English:
call sites stay readable (``t("Settings")`` rather than
``t("settings.title")``), a key that has no translation falls back to the
English it already was, and the extraction pass could not silently change
what a screen says.

Placeholders are named and formatted here, so a translation is free to
reorder them::

    t("Found {n} entries", n=len(entries))

Direction helpers sit alongside the catalog because they answer the same
question. Tk has no notion of writing direction: ``anchor``, ``justify``,
``side`` and every padding tuple are absolute. In an RTL layout each one
has to be mirrored, so the code asks for "start"/"end" and gets "w"/"e" or
"e"/"w" depending on the active language.

Changing language rebuilds the window. Tk cannot re-flow an existing widget
tree — anchors and pack sides are fixed at creation — so a live swap would
leave half the UI mirrored.
"""

from __future__ import annotations

import logging

log = logging.getLogger("PasswordVault")

# (settings value, name shown in its own language)
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("English", "English"),
    ("Arabic", "العربية"),
)

LANGUAGE_VALUES = tuple(value for value, _ in LANGUAGES)
LANGUAGE_LABELS = tuple(label for _, label in LANGUAGES)

RTL_LANGUAGES = frozenset({"Arabic"})

_current = "English"


def set_language(language: str) -> None:
    """Set the active language. Unknown values fall back to English."""
    global _current
    if language not in LANGUAGE_VALUES:
        log.warning("Unknown language %r; using English.", language)
        language = "English"
    _current = language


def get_language() -> str:
    return _current


def is_rtl() -> bool:
    return _current in RTL_LANGUAGES


def label_for(value: str) -> str:
    """The name of a language, written in that language."""
    for val, label in LANGUAGES:
        if val == value:
            return label
    return value


def value_for(label: str) -> str:
    """Inverse of :func:`label_for`, for reading a dropdown selection."""
    for val, lbl in LANGUAGES:
        if lbl == label:
            return val
    return label


def t(text: str, **kwargs) -> str:
    """Translate *text* into the active language and fill placeholders.

    An untranslated string is returned as written, so a missing entry
    degrades to English rather than to a key.
    """
    table = CATALOG.get(_current)
    out = table.get(text, text) if table else text
    if kwargs:
        try:
            out = out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # A translation with a broken placeholder must not take a
            # dialog down; fall back to the English formatting.
            log.warning("Bad placeholders in translation of %r.", text)
            try:
                out = text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                out = text
    return out


# ─── Direction Helpers ───────────────────────────────────────
def anchor_start() -> str:
    """``anchor`` for text that begins at the reading edge."""
    return "e" if is_rtl() else "w"


def anchor_end() -> str:
    return "w" if is_rtl() else "e"


def side_start() -> str:
    """``pack(side=…)`` for the reading edge."""
    return "right" if is_rtl() else "left"


def side_end() -> str:
    return "left" if is_rtl() else "right"


def justify_start() -> str:
    return "right" if is_rtl() else "left"


def justify_end() -> str:
    return "left" if is_rtl() else "right"


def ltr_justify() -> str:
    """``justify`` for a field whose content is always Latin.

    Tk has no bidi algorithm, so a URL, hostname or port rendered into a
    right-aligned Arabic form reads from the wrong edge — the scheme ends
    up on the right and the path on the left. These fields are pinned to
    left alignment in both languages: the surrounding labels still mirror,
    but the value itself reads the way its own script does.

    Only for fields that cannot contain the UI language. A username or a
    note can be Arabic and must keep following the layout.
    """
    return "left"


def pad(start, end):
    """Mirror a ``(left, right)`` padding pair for the active direction.

    Written as ``pad(start, end)``: the first value is always the padding
    at the reading edge, whichever physical side that is.
    """
    return (end, start) if is_rtl() else (start, end)


# ─── Catalog ─────────────────────────────────────────────────
# Keys are the English source strings. Anything absent falls through to
# English, so a partial catalog is a valid catalog.
ARABIC: dict[str, str] = {
    # ── App & login ──
    "Password Vault": "خزنة كلمات المرور",
    "Create a master password": "أنشئ كلمة مرور رئيسية",
    "Enter your master password": "أدخل كلمة المرور الرئيسية",
    "Master Password": "كلمة المرور الرئيسية",
    "Confirm Password": "تأكيد كلمة المرور",
    "Unlock  🔓": "فتح  🔓",
    "Create Vault  🔐": "إنشاء الخزنة  🔐",
    "⏳  Unlocking…": "⏳  جارٍ الفتح…",
    "🛟  Restore from backup": "🛟  استعادة من نسخة احتياطية",
    "Enter your master password to unlock the vault":
        "أدخل كلمة المرور الرئيسية لفتح الخزنة",
    "Show / hide password": "إظهار / إخفاء كلمة المرور",
    "Shows how strong your password is": "يوضح قوة كلمة المرور",
    "Re-enter your password to confirm": "أعد إدخال كلمة المرور للتأكيد",
    "Decrypt and open your vault": "فك تشفير الخزنة وفتحها",
    "Create a new encrypted vault": "إنشاء خزنة مشفّرة جديدة",
    "Restore vault contents from an encrypted backup file":
        "استعادة محتويات الخزنة من ملف نسخة احتياطية مشفّر",

    # ── Login errors ──
    "⚠️ Enter a password": "⚠️ أدخل كلمة مرور",
    "⚠️ Passwords don't match": "⚠️ كلمتا المرور غير متطابقتين",
    "⚠️ Too many attempts. Wait {seconds}s":
        "⚠️ محاولات كثيرة. انتظر {seconds} ثانية",
    "⚠️ Locked for {seconds}s": "⚠️ مقفلة لمدة {seconds} ثانية",
    "⚠️ Wrong password ({remaining} attempts left)":
        "⚠️ كلمة مرور خاطئة (باقي {remaining} محاولات)",
    "⚠️ Vault file could not be read": "⚠️ تعذّرت قراءة ملف الخزنة",
    "⚠️ Too short (min 12 chars for master password)":
        "⚠️ قصيرة جداً (12 حرفاً على الأقل لكلمة المرور الرئيسية)",
    "⚠️ Need at least one uppercase letter":
        "⚠️ مطلوب حرف كبير واحد على الأقل",
    "⚠️ Need at least one lowercase letter":
        "⚠️ مطلوب حرف صغير واحد على الأقل",
    "⚠️ Need at least one digit": "⚠️ مطلوب رقم واحد على الأقل",
    "⚠️ Master password is not strong enough":
        "⚠️ كلمة المرور الرئيسية ليست قوية بما يكفي",

    # ── Strength labels ──
    "Very Weak": "ضعيفة جداً",
    "Weak": "ضعيفة",
    "Fair": "متوسطة",
    "Strong": "قوية",
    "Very Strong": "قوية جداً",

    # ── Main window ──
    "＋  Add New": "＋  إضافة",
    "Add a new password entry  (Ctrl+N)": "إضافة كلمة مرور جديدة  (Ctrl+N)",
    "Settings — Preferences, export/import, security dashboard":
        "الإعدادات — التفضيلات، التصدير/الاستيراد، لوحة الأمان",
    "Search passwords...": "ابحث في كلمات المرور...",
    "Filter by category": "تصفية حسب الفئة",
    "🗂️  All": "🗂️  الكل",
    "Categories": "الفئات",
    "＋  Category": "＋  فئة",
    "Create a new category to organize passwords":
        "إنشاء فئة جديدة لتنظيم كلمات المرور",
    "All": "الكل",
    "Show all entries": "عرض كل العناصر",
    "Show entries in {category}": "عرض عناصر {category}",
    "Delete '{category}' category": "حذف فئة '{category}'",
    "No passwords yet": "لا توجد كلمات مرور بعد",
    "Click '＋ Add New' to get started": "اضغط '＋ إضافة' للبدء",
    "⬇  Show more  ({hidden} hidden)": "⬇  عرض المزيد  ({hidden} مخفية)",
    "Render the next {count} entries": "عرض الـ {count} عنصراً التالية",

    # ── Entry card ──
    "Pin to top": "تثبيت في الأعلى",
    "Unpin from top": "إلغاء التثبيت",
    "Move to Recycle Bin": "نقل إلى سلة المحذوفات",
    "Edit this entry": "تعديل هذا العنصر",
    "Copy username": "نسخ اسم المستخدم",
    "Copy password": "نسخ كلمة المرور",
    "🔑 Copy": "🔑 نسخ",
    "Open {url}": "فتح {url}",
    "Today": "اليوم",
    "Future?": "مستقبلي؟",

    # ── Context menu ──
    "📋  Copy Username": "📋  نسخ اسم المستخدم",
    "🔑  Copy Password": "🔑  نسخ كلمة المرور",
    "🌐  Open URL in Browser": "🌐  فتح الرابط في المتصفح",
    "🌐  Open URL + Copy Username": "🌐  فتح الرابط + نسخ اسم المستخدم",
    "🖥️  SSH Session …": "🖥️  جلسة SSH …",
    "🖥️  RDP Session …": "🖥️  جلسة RDP …",
    "✏️  Edit Entry": "✏️  تعديل العنصر",
    "📌  Pin / Unpin": "📌  تثبيت / إلغاء التثبيت",
    "🗑️  Delete": "🗑️  حذف",
    "✂️  Cut": "✂️  قص",
    "📋  Copy": "📋  نسخ",
    "📄  Paste": "📄  لصق",
    "🔤  Select All": "🔤  تحديد الكل",

    # ── Settings menu ──
    "⚙️  Settings": "⚙️  الإعدادات",
    "🔑  Change Master Password": "🔑  تغيير كلمة المرور الرئيسية",
    "🛡️  Security Dashboard": "🛡️  لوحة الأمان",
    "📤  Export Data  (Ctrl+E)": "📤  تصدير البيانات  (Ctrl+E)",
    "📥  Import Data  (Ctrl+I)": "📥  استيراد البيانات  (Ctrl+I)",
    "🛟  Encrypted Backup …": "🛟  نسخة احتياطية مشفّرة …",
    "♻️  Restore From Backup …": "♻️  استعادة من نسخة احتياطية …",
    "🗑️  Recycle Bin ({count})": "🗑️  سلة المحذوفات ({count})",
    "🔒  Lock Vault  (Ctrl+L)": "🔒  قفل الخزنة  (Ctrl+L)",
    "ℹ️  About": "ℹ️  حول",
    "✕  Exit": "✕  خروج",

    # ── Settings dialog ──
    "Settings": "الإعدادات",
    "Security": "الأمان",
    "Auto-Lock": "القفل التلقائي",
    "Max Login Attempts": "أقصى عدد محاولات",
    "Lockout Duration": "مدة القفل",
    "Clear Clipboard": "مسح الحافظة",
    "Password Generator Defaults": "إعدادات مولّد كلمات المرور",
    "Default Length": "الطول الافتراضي",
    "Uppercase (ABC)": "حروف كبيرة (ABC)",
    "Lowercase (abc)": "حروف صغيرة (abc)",
    "Digits (0-9)": "أرقام (0-9)",
    "Symbols (#$%&)": "رموز (#$%&)",
    "Appearance": "المظهر",
    "Theme": "السمة",
    "Language": "اللغة",
    "Default Card Color": "لون البطاقة الافتراضي",
    "Behavior": "السلوك",
    "Start Minimized": "البدء مصغّراً",
    "💾  Save Settings": "💾  حفظ الإعدادات",
    "Save all settings and close": "حفظ كل الإعدادات والإغلاق",
    "Never": "أبداً",
    "Off": "معطّل",
    "{n} min": "{n} دقيقة",
    "{n} sec": "{n} ثانية",
    "System": "النظام",
    "Light": "فاتح",
    "Dark": "داكن",
    "Lock the vault after this period of inactivity. 'Never' disables "
    "auto-lock.":
        "قفل الخزنة بعد هذه المدة من عدم النشاط. 'أبداً' يعطّل القفل "
        "التلقائي.",
    "Maximum wrong password attempts before lockout.":
        "أقصى عدد محاولات خاطئة قبل القفل.",
    "How long the vault stays locked after too many failed attempts.":
        "المدة التي تبقى فيها الخزنة مقفلة بعد محاولات فاشلة كثيرة.",
    "Automatically clear copied passwords from clipboard after this time.":
        "مسح كلمات المرور المنسوخة من الحافظة تلقائياً بعد هذه المدة.",
    "Default password length when opening the generator.":
        "الطول الافتراضي عند فتح المولّد.",
    "Include uppercase letters (A-Z).": "تضمين الحروف الكبيرة (A-Z).",
    "Include lowercase letters (a-z).": "تضمين الحروف الصغيرة (a-z).",
    "Include digits (0-9).": "تضمين الأرقام (0-9).",
    "Include special symbols (!@#$%&).": "تضمين الرموز الخاصة (!@#$%&).",
    "Light, dark, or follow the Windows setting. Applies immediately.":
        "فاتح أو داكن أو حسب إعداد ويندوز. يُطبَّق فوراً.",
    "The window is rebuilt when the language changes.":
        "تُعاد بناء النافذة عند تغيير اللغة.",
    "Default color for new password entries.":
        "اللون الافتراضي للعناصر الجديدة.",
    "Start the app minimized to the floating widget.":
        "بدء التطبيق مصغّراً إلى الأيقونة العائمة.",
    "{label} — set as default card color":
        "{label} — تعيين كلون افتراضي للبطاقات",

    # ── Entry dialog ──
    "New Password": "كلمة مرور جديدة",
    "Edit Password": "تعديل كلمة المرور",
    "Identity": "الهوية",
    "Title": "العنوان",
    "Category": "الفئة",
    "URL": "الرابط",
    "Credentials": "بيانات الدخول",
    "Username": "اسم المستخدم",
    "Password": "كلمة المرور",
    "Color": "اللون",
    "Notes": "ملاحظات",
    "💾  Save": "💾  حفظ",
    "💾  Save Changes": "💾  حفظ التغييرات",
    "Save this password entry": "حفظ هذا العنصر",
    "Open password generator": "فتح مولّد كلمات المرور",
    "Password strength indicator": "مؤشر قوة كلمة المرور",
    "⚠️ Title is required": "⚠️ العنوان مطلوب",
    "⚠️ Password is required": "⚠️ كلمة المرور مطلوبة",
    "⚠️ Same password used in '{title}'":
        "⚠️ نفس كلمة المرور مستخدمة في '{title}'",
    "{label} card color": "لون البطاقة {label}",

    # ── Confirmations ──
    "Cancel": "إلغاء",
    "Delete": "حذف",
    "Exit": "خروج",
    "OK": "موافق",
    "Delete Category?": "حذف الفئة؟",
    "Delete Category": "حذف الفئة",
    'Delete "{name}"?': 'حذف "{name}"؟',
    '{count} entries → "General".': '{count} عنصراً → "General".',
    "Move to Recycle Bin?": "نقل إلى سلة المحذوفات؟",
    'Delete "{title}"?\nYou can restore it from the Recycle Bin.':
        'حذف "{title}"؟\nيمكنك استعادته من سلة المحذوفات.',
    "Exit Password Vault?": "الخروج من خزنة كلمات المرور؟",
    "Exit Password Vault": "الخروج من خزنة كلمات المرور",
    "The vault will be locked and closed.": "سيتم قفل الخزنة وإغلاقها.",
    "Delete Forever?": "حذف نهائي؟",
    "Delete Forever": "حذف نهائي",
    '"{title}"\nThis cannot be undone.':
        '"{title}"\nلا يمكن التراجع عن هذا.',
    "Empty Recycle Bin?": "إفراغ سلة المحذوفات؟",
    "Empty Trash": "إفراغ السلة",
    "Permanently delete all {count} items?\nThis action cannot be undone.":
        "حذف كل الـ {count} عنصراً نهائياً؟\nلا يمكن التراجع عن هذا.",
    "Delete All": "حذف الكل",

    # ── Category dialog ──
    "New Category": "فئة جديدة",
    "Name": "الاسم",
    "Category name": "اسم الفئة",
    "＋  Add": "＋  إضافة",
    "⚠️ Enter a name": "⚠️ أدخل اسماً",
    "⚠️ Already exists": "⚠️ موجودة بالفعل",

    # ── Alerts ──
    "Could not save": "تعذّر الحفظ",
    "The vault file could not be written, so this change is only in memory "
    "for now.\n\n{error}":
        "تعذّرت كتابة ملف الخزنة، لذا هذا التغيير في الذاكرة فقط "
        "حالياً.\n\n{error}",
    "Link blocked": "رابط محظور",
    "This entry's link is not an http or https address, so it was not "
    "opened.":
        "رابط هذا العنصر ليس عنوان http أو https، لذلك لم يُفتح.",
    "Could not open browser": "تعذّر فتح المتصفح",
    "Clipboard unavailable": "الحافظة غير متاحة",
    "This system has no working clipboard, so nothing was copied.":
        "لا توجد حافظة عاملة على هذا النظام، لذلك لم يُنسخ شيء.",
    "✅ Done!": "✅ تم!",

    # ── Generator ──
    "Password Generator": "مولّد كلمات المرور",
    "🎲  Password Generator": "🎲  مولّد كلمات المرور",
    "Length:": "الطول:",
    "🔄  Regenerate": "🔄  توليد جديد",
    "✅  Use This": "✅  استخدام هذه",
    "Generate a new random password": "توليد كلمة مرور عشوائية جديدة",
    "Apply this password to the entry": "تطبيق كلمة المرور على العنصر",
    "Drag to change password length": "اسحب لتغيير الطول",
    "Generated password — click Use This to apply it":
        "كلمة المرور المولّدة — اضغط 'استخدام هذه' لتطبيقها",
    "Include uppercase letters": "تضمين الحروف الكبيرة",
    "Include lowercase letters": "تضمين الحروف الصغيرة",
    "Include digits": "تضمين الأرقام",
    "Include special characters": "تضمين الرموز الخاصة",

    # ── Change master password ──
    "Change Master Password": "تغيير كلمة المرور الرئيسية",
    "Current": "الحالية",
    "Confirm": "التأكيد",
    "Change Password": "تغيير كلمة المرور",
    "⏳  Re-encrypting…": "⏳  إعادة التشفير…",
    "⏳  Encrypting…": "⏳  جارٍ التشفير…",
    "⏳  Decrypting…": "⏳  جارٍ فك التشفير…",
    "Save the new master password": "حفظ كلمة المرور الرئيسية الجديدة",
    "Deriving key and re-encrypting the vault…":
        "اشتقاق المفتاح وإعادة تشفير الخزنة…",
    "⚠️ Fill all fields": "⚠️ املأ كل الحقول",
    "⚠️ New passwords don't match": "⚠️ كلمتا المرور الجديدتان غير متطابقتين",
    "⚠️ Current password is wrong": "⚠️ كلمة المرور الحالية خاطئة",
    "⚠️ Could not save — try again": "⚠️ تعذّر الحفظ — حاول مرة أخرى",
    "⚠️ The vault is locked": "⚠️ الخزنة مقفلة",

    # ── Export / import ──
    "Export Data": "تصدير البيانات",
    "Import Data": "استيراد البيانات",
    "⚠️  The exported file will contain all your\npasswords in PLAIN TEXT. "
    "Keep it secure!":
        "⚠️  الملف المصدَّر سيحتوي على كل كلمات المرور\nكنص صريح. احتفظ به "
        "في مكان آمن!",
    "📊  {count} entries will be exported": "📊  سيتم تصدير {count} عنصراً",
    "📄  Export CSV": "📄  تصدير CSV",
    "📊  Export Excel": "📊  تصدير Excel",
    "Export to Excel (.xlsx)": "التصدير إلى Excel (.xlsx)",
    " (install openpyxl)": " (ثبّت openpyxl)",
    "Excel export needs the openpyxl package":
        "تصدير Excel يحتاج حزمة openpyxl",
    "Could not write the file: {error}": "تعذّرت كتابة الملف: {error}",
    "Select a CSV, Excel or JSON file to import.\nExports from Chrome, "
    "Bitwarden, LastPass, 1Password,\nKeePass and Firefox are recognised "
    "too.":
        "اختر ملف CSV أو Excel أو JSON للاستيراد.\nملفات Chrome و "
        "Bitwarden و LastPass و 1Password\nو KeePass و Firefox مدعومة "
        "أيضاً.",
    "Format": "الصيغة",
    "Auto-detect": "كشف تلقائي",
    "Which application this file came from. Auto-detect reads the header "
    "row; pick a format to override it.":
        "التطبيق الذي جاء منه الملف. الكشف التلقائي يقرأ صف العناوين؛ اختر "
        "صيغة لتجاوزه.",
    "Detected: {description}": "تم الكشف: {description}",
    "Reading as {label}": "تُقرأ كـ {label}",
    "📂  Browse File...": "📂  اختيار ملف...",
    "⏳  Reading…": "⏳  جارٍ القراءة…",
    "⏳  Reading file…": "⏳  جارٍ قراءة الملف…",
    "📊  Found {total} entries  |  New: {new}  |  Duplicates: {dup}":
        "📊  وُجد {total} عنصراً  |  جديد: {new}  |  مكرر: {dup}",
    "Import (Skip Dups)": "استيراد (تخطي المكرر)",
    "Import All": "استيراد الكل",
    "File is too large to import": "الملف أكبر من أن يُستورد",
    "⚠️ No entries to import": "⚠️ لا توجد عناصر للاستيراد",
    "⚠️ Could not save the import — nothing was changed":
        "⚠️ تعذّر حفظ الاستيراد — لم يتغيّر شيء",
    "Only the first {count} rows were read":
        "قُرئ أول {count} صف فقط",
    "Columns not imported: {columns}": "أعمدة لم تُستورد: {columns}",
    "No rows matched this format — try another one":
        "لا صفوف تطابق هذه الصيغة — جرّب صيغة أخرى",

    # ── Encrypted backup ──
    "Encrypted Backup": "نسخة احتياطية مشفّرة",
    "Restore From Backup": "استعادة من نسخة احتياطية",
    "Use this if you ever forget your master password.\nThe backup is "
    "encrypted with a SEPARATE password\nyou choose below. Keep it "
    "somewhere safe.":
        "استخدم هذا إن نسيت كلمة المرور الرئيسية.\nالنسخة مشفّرة بكلمة مرور "
        "منفصلة تختارها\nبالأسفل. احتفظ بها في مكان آمن.",
    "Backup Password": "كلمة مرور النسخة",
    "🛟  Create Backup": "🛟  إنشاء نسخة احتياطية",
    "Encrypt the vault and save it to a backup file":
        "تشفير الخزنة وحفظها في ملف نسخة احتياطية",
    "⚠️ Enter a backup password": "⚠️ أدخل كلمة مرور للنسخة",
    "⚠️ Use at least 8 characters": "⚠️ استخدم 8 أحرف على الأقل",
    "Backup created!": "تم إنشاء النسخة!",
    "Saved to:\n{path}": "حُفظت في:\n{path}",
    "⚠️  Keep this file AND its password safe.\nWithout both, the backup "
    "cannot be opened.":
        "⚠️  احتفظ بالملف وبكلمة مروره معاً.\nبدونهما لا يمكن فتح النسخة.",
    "Close": "إغلاق",
    "Restoring will create a new vault from this backup.\nYou'll set a new "
    "master password below.":
        "الاستعادة ستنشئ خزنة جديدة من هذه النسخة.\nستحدد كلمة مرور رئيسية "
        "جديدة بالأسفل.",
    "⚠️  This will REPLACE all entries currently in\nyour vault with the "
    "contents of the backup.":
        "⚠️  هذا سيستبدل كل العناصر الموجودة حالياً\nفي خزنتك بمحتويات "
        "النسخة الاحتياطية.",
    "No file selected": "لم يُختر ملف",
    "📂  Browse Backup File...": "📂  اختيار ملف النسخة...",
    "New Master Password": "كلمة مرور رئيسية جديدة",
    "🛟  Restore": "🛟  استعادة",
    "Decrypt the backup and load it into the vault":
        "فك تشفير النسخة وتحميلها في الخزنة",
    "⚠️ Pick a backup file first": "⚠️ اختر ملف نسخة أولاً",
    "⚠️ File not found": "⚠️ الملف غير موجود",
    "⚠️ Enter the backup password": "⚠️ أدخل كلمة مرور النسخة",
    "⚠️ Set a new master password": "⚠️ حدّد كلمة مرور رئيسية جديدة",
    "⚠️ Master passwords don't match":
        "⚠️ كلمتا المرور الرئيسيتان غير متطابقتين",
    "⚠️ Restore failed: {error}": "⚠️ فشلت الاستعادة: {error}",

    # ── Recycle bin ──
    "Recycle Bin": "سلة المحذوفات",
    "Recycle Bin  ({count} items)": "سلة المحذوفات  ({count} عنصر)",
    "🗑️  Recycle Bin  ({count} items)": "🗑️  سلة المحذوفات  ({count} عنصر)",
    "Items are automatically deleted after {days} days":
        "تُحذف العناصر تلقائياً بعد {days} يوماً",
    "🗑️  Empty": "🗑️  فارغة",
    "♻️ Restore": "♻️ استعادة",
    "🗑️ Delete Forever": "🗑️ حذف نهائي",
    "🗑️  Empty Trash": "🗑️  إفراغ السلة",
    "Restore this entry back to the vault": "إعادة هذا العنصر إلى الخزنة",
    "Permanently delete this entry": "حذف هذا العنصر نهائياً",
    "Permanently delete all items in trash":
        "حذف كل عناصر السلة نهائياً",
    "🗑️ Deleted {age}": "🗑️ حُذف {age}",

    # ── Security dashboard ──
    "Security Dashboard": "لوحة الأمان",
    "Overview": "نظرة عامة",
    "Total Entries": "إجمالي العناصر",
    "Strong Passwords": "كلمات مرور قوية",
    "Fair Passwords": "كلمات مرور متوسطة",
    "Weak Passwords": "كلمات مرور ضعيفة",
    "Duplicate Passwords": "كلمات مرور مكررة",
    "Old (>{days}d)": "قديمة (>{days} يوم)",
    "Recommendations": "التوصيات",
    "Breach Check": "فحص التسريبات",
    "Your security score: {score}/100": "درجة الأمان: {score}/100",
    "⚠️  {count} weak password(s) — update them for better security":
        "⚠️  {count} كلمة مرور ضعيفة — حدّثها لأمان أفضل",
    "🔁  {count} reused password(s) — use unique passwords per account":
        "🔁  {count} كلمة مرور مكررة — استخدم كلمة فريدة لكل حساب",
    "⏰  {count} password(s) older than {days} days — consider updating":
        "⏰  {count} كلمة مرور أقدم من {days} يوماً — يُنصح بتحديثها",
    "✅  Great job! Your vault is secure!": "✅  ممتاز! خزنتك آمنة!",
    "Check if your passwords appear in known\ndata breaches (via Have I "
    "Been Pwned).":
        "تحقّق مما إذا كانت كلمات مرورك ظهرت في\nتسريبات معروفة (عبر Have I "
        "Been Pwned).",
    "🔍  Check Breaches": "🔍  فحص التسريبات",
    "⏳ Checking...": "⏳ جارٍ الفحص...",
    "No entries to check.": "لا عناصر للفحص.",
    "Checking passwords against HIBP database...":
        "جارٍ فحص كلمات المرور مقابل قاعدة HIBP...",
    "Checking passwords… {done}/{total}":
        "جارٍ فحص كلمات المرور… {done}/{total}",
    "🚨 {count} password(s) found in breaches!":
        "🚨 {count} كلمة مرور وُجدت في تسريبات!",
    "  … and {count} more": "  … و {count} أخرى",
    "✅ No passwords found in breaches!":
        "✅ لم توجد كلمات مرور في التسريبات!",
    "⚠️ {count} could not be checked (network error)":
        "⚠️ تعذّر فحص {count} (خطأ في الشبكة)",
    "Check all passwords against the HIBP breach database (uses "
    "k-anonymity — your passwords are NOT sent)":
        "فحص كل كلمات المرور مقابل قاعدة تسريبات HIBP (يستخدم k-anonymity — "
        "كلمات مرورك لا تُرسَل)",

    # ── SSH / RDP ──
    "SSH Session": "جلسة SSH",
    "RDP Session": "جلسة RDP",
    "🖥️  SSH Session": "🖥️  جلسة SSH",
    "🖥️  Remote Desktop (RDP)": "🖥️  سطح المكتب البعيد (RDP)",
    "Entry: {title}": "العنصر: {title}",
    "Host / IP": "المضيف / IP",
    "e.g. 192.168.1.10 or server.example.com":
        "مثال: 192.168.1.10 أو server.example.com",
    "username": "اسم المستخدم",
    "Port": "المنفذ",
    "SSH Client": "عميل SSH",
    "No SSH client found": "لم يُعثر على عميل SSH",
    "💡 Password will be copied to clipboard":
        "💡 سيتم نسخ كلمة المرور إلى الحافظة",
    "🖥️  Connect": "🖥️  اتصال",
    "Start {kind} session (password copied to clipboard)":
        "بدء جلسة {kind} (كلمة المرور تُنسخ إلى الحافظة)",
    "⚠️ Host / IP is required": "⚠️ المضيف / IP مطلوب",
    "⚠️ Invalid port number": "⚠️ رقم منفذ غير صالح",
    "⚠️ No SSH client found on system": "⚠️ لا يوجد عميل SSH على النظام",
    "⚠️ SSH client not found": "⚠️ لم يُعثر على عميل SSH",
    "⚠️ {field} contains characters that cannot be passed to a terminal: "
    "{chars}":
        "⚠️ {field} يحتوي على رموز لا يمكن تمريرها إلى الطرفية: {chars}",
    "⚠️ {field} cannot start with '-'": "⚠️ {field} لا يمكن أن يبدأ بـ '-'",
    "Could not start the session": "تعذّر بدء الجلسة",

    # ── Mini vault & floating widget ──
    "Mini Vault": "الخزنة المصغّرة",
    "🔐  Mini Vault": "🔐  الخزنة المصغّرة",
    "Close Mini Vault": "إغلاق الخزنة المصغّرة",
    "Open full vault window": "فتح نافذة الخزنة الكاملة",
    "No results": "لا نتائج",
    "⬇  Show more  ({hidden})": "⬇  عرض المزيد  ({hidden})",
    "📋 User": "📋 المستخدم",
    "🔑 Pass": "🔑 المرور",
    "Copy username to clipboard": "نسخ اسم المستخدم إلى الحافظة",
    "Copy password to clipboard": "نسخ كلمة المرور إلى الحافظة",
    "⬜  Open Full Vault": "⬜  فتح الخزنة الكاملة",
    "📋  Mini Vault": "📋  الخزنة المصغّرة",

    # ── About ──
    "About Password Vault": "حول خزنة كلمات المرور",
    "Information": "معلومات",
    "Version": "الإصدار",
    "Developer": "المطوّر",
    "Encryption": "التشفير",
    "Key Derivation": "اشتقاق المفتاح",
    "Data Location": "مكان البيانات",
    "Features": "المزايا",
}

CATALOG: dict[str, dict[str, str]] = {"Arabic": ARABIC}
