# RBRi18n Local Translation Toolkit

A set of Python scripts for maintaining and filling translation files offline using [argostranslate](https://github.com/argosopentech/argostranslate).

`Translation.zh.json` is the canonical reference. All other language files follow its structure.

---

## Setup

All scripts must be run from the `Utils/translate/` directory, or with the full path prefix:

```bash
# Option A: cd into the directory first (recommended)
cd d:/RBR/Utils/translate
pip install -r requirements.txt
python setup_translate.py

# Option B: run from the repo root
pip install -r Utils/translate/requirements.txt
python Utils/translate/setup_translate.py
```

`setup_translate.py` downloads the required language model packages (needs internet, run once).

```bash
# Check what is installed / missing without downloading
python setup_translate.py --list

# Re-download packages that are already installed
python setup_translate.py --force
```

---

## sync_keys.py — Sync structure after zh.json is updated

When `Translation.zh.json` gains new keys or removes old ones, run this to bring all other language files up to date:

- Adds missing keys with `""` (empty, ready for translation)
- Removes stale keys no longer present in zh.json
- Re-orders keys in every file to exactly match zh.json order

```bash
# Sync all languages
python sync_keys.py

# Preview changes without writing any files
python sync_keys.py --dry-run

# Sync a single language
python sync_keys.py --lang jp

# Only add new keys — never remove stale ones
python sync_keys.py --no-remove
```

---

## translate_gaps.py — Fill empty keys using local MT

Translates keys that have an empty `""` value in a language file using argostranslate (fully offline after setup).

```bash
# Show gap counts for all languages without translating
python translate_gaps.py --list-langs

# Translate all incomplete languages
python translate_gaps.py

# Translate a single language
python translate_gaps.py --lang jp

# Preview what would be translated without writing
python translate_gaps.py --lang jp --dry-run

# Skip proper-noun-heavy categories (recommended — MT quality is poor for stage names)
python translate_gaps.py --skip-categories stages,dailystages

# Only translate specific categories
python translate_gaps.py --only-categories misc,cars

# Re-translate keys that already have a value
python translate_gaps.py --force

# Change the save interval (default: save every 50 keys)
python translate_gaps.py --batch-size 100
```

Progress is saved incrementally every `--batch-size` keys, so the script can be safely interrupted and restarted.

---

## Typical workflow

```bash
# 1. zh.json was updated — sync structure to all languages first
python sync_keys.py

# 2. Fill in the new empty keys using MT (skip stage names)
python translate_gaps.py --skip-categories stages,dailystages

# 3. Review and manually correct the output in the JSON files
```

---

## Language codes

| File code | argostranslate code | Notes |
|-----------|--------------------|-|
| `zh`      | `zh` | Reference file, never modified by these scripts |
| `zh-Hant` | `zt` | Falls back to `en→zh→zt` chain if `en→zt` unavailable |
| `fi`      | `fi` | |
| `hu`      | `hu` | Flat format (no categories) |
| `jp`      | `ja` | |
| `pt`      | `pt` | |
| `ru`      | `ru` | |
