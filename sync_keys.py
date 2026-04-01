"""
sync_keys.py — Sync all language files to match Translation.zh.json structure.

When Translation.zh.json gains new keys or categories, this script:
  - Adds missing keys to every other language file (value = "")
  - Removes keys that no longer exist in zh.json (stale keys)
  - Re-orders keys in every file to match zh.json key order exactly
  - Preserves existing translated values

Run this every time zh.json is updated.

Usage:
    python sync_keys.py                  # sync all languages, show summary
    python sync_keys.py --dry-run        # preview changes without writing
    python sync_keys.py --lang jp        # single language only
    python sync_keys.py --no-remove      # only add new keys, never remove stale ones
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RBRI18N_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "RBRi18n"))
ZH_REF_PATH = os.path.join(RBRI18N_DIR, "Translation.zh.json")

# All language files to sync (excluding zh itself)
# fmt: "categorized" or "flat"
TARGETS = {
    "zh-Hant": "categorized",
    "fi":      "categorized",
    "hu":      "flat",
    "jp":      "categorized",
    "pt":      "categorized",
    "ru":      "categorized",
}


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    """Atomic write: write to .tmp then rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def sync_categorized(zh_data, target_data, remove_stale):
    """
    Sync a categorized target file against zh_data.

    Returns (new_data, stats) where stats = {added, removed, reordered}.
    new_data has the exact same category and key order as zh_data.
    """
    added = 0
    removed = 0
    new_data = {}

    for category, zh_entries in zh_data.items():
        existing = target_data.get(category, {})
        new_cat = {}

        # Walk zh key order — add missing with "", keep existing values
        for key in zh_entries:
            if key in existing:
                new_cat[key] = existing[key]
            else:
                new_cat[key] = ""
                added += 1

        # Detect stale keys (in target but not in zh)
        stale = set(existing.keys()) - set(zh_entries.keys())
        if stale and not remove_stale:
            # Keep stale keys at the end
            for key in existing:
                if key in stale:
                    new_cat[key] = existing[key]
        elif stale and remove_stale:
            removed += len(stale)

        new_data[category] = new_cat

    # Detect stale categories
    stale_cats = set(target_data.keys()) - set(zh_data.keys())
    if stale_cats and not remove_stale:
        for cat in stale_cats:
            new_data[cat] = target_data[cat]
    elif stale_cats and remove_stale:
        removed += sum(len(v) for v in (target_data[c] for c in stale_cats))

    stats = {"added": added, "removed": removed}
    return new_data, stats


def sync_flat(zh_data, target_data, remove_stale):
    """
    Sync a flat target file against zh_data (which is categorized).

    The flat file uses the same keys as zh but without categories.
    Key order follows zh category order then key order within each category.
    """
    added = 0
    removed = 0
    new_data = {}

    for category, zh_entries in zh_data.items():
        for key in zh_entries:
            if key in target_data:
                new_data[key] = target_data[key]
            else:
                new_data[key] = ""
                added += 1

    if remove_stale:
        all_zh_keys = {k for entries in zh_data.values() for k in entries}
        stale = set(target_data.keys()) - all_zh_keys
        removed = len(stale)
        # stale keys are simply not copied into new_data
    else:
        # Append stale keys at the end
        all_zh_keys = {k for entries in zh_data.values() for k in entries}
        for key in target_data:
            if key not in all_zh_keys:
                new_data[key] = target_data[key]

    stats = {"added": added, "removed": removed}
    return new_data, stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_language(lang_code, fmt, zh_data, dry_run, remove_stale):
    file_path = os.path.join(RBRI18N_DIR, f"Translation.{lang_code}.json")

    if not os.path.exists(file_path):
        print(f"[{lang_code}] File not found — will create from scratch.")
        target_data = {} if fmt == "flat" else {}
    else:
        target_data = load_json(file_path)

    if fmt == "categorized":
        new_data, stats = sync_categorized(zh_data, target_data, remove_stale)
    else:
        new_data, stats = sync_flat(zh_data, target_data, remove_stale)

    added = stats["added"]
    removed = stats["removed"]

    if added == 0 and removed == 0:
        print(f"[{lang_code}] Already in sync. No changes.")
        return

    action = "Would update" if dry_run else "Updated"
    parts = []
    if added:
        parts.append(f"+{added} new keys")
    if removed:
        parts.append(f"-{removed} stale keys")
    print(f"[{lang_code}] {action}: {', '.join(parts)}")

    if dry_run:
        # Show a sample of new keys
        sample_new = []
        for category, zh_entries in zh_data.items():
            existing = target_data.get(category, {}) if fmt == "categorized" else target_data
            for key in zh_entries:
                if key not in existing:
                    sample_new.append((category, key))
                if len(sample_new) >= 5:
                    break
            if len(sample_new) >= 5:
                break
        for cat, key in sample_new:
            print(f"    + [{cat}] {key!r}")
        if added > len(sample_new):
            print(f"    ... and {added - len(sample_new)} more.")
        return

    write_json(file_path, new_data)


def main():
    parser = argparse.ArgumentParser(
        description="Sync all RBRi18n language files to match Translation.zh.json structure."
    )
    parser.add_argument("--lang", help="Sync a single language only (e.g. jp).")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    parser.add_argument(
        "--no-remove", action="store_true",
        help="Only add new keys; keep stale keys that no longer exist in zh.json."
    )
    args = parser.parse_args()

    remove_stale = not args.no_remove

    if not os.path.exists(ZH_REF_PATH):
        print(f"Error: reference not found: {ZH_REF_PATH}", file=sys.stderr)
        sys.exit(1)

    zh_data = load_json(ZH_REF_PATH)
    total_zh = sum(len(v) for v in zh_data.values())
    print(f"Reference: Translation.zh.json — {total_zh} keys across {len(zh_data)} categories\n")

    if args.lang:
        if args.lang not in TARGETS:
            print(f"Error: unknown language '{args.lang}'. Valid: {', '.join(TARGETS)}", file=sys.stderr)
            sys.exit(1)
        targets = {args.lang: TARGETS[args.lang]}
    else:
        targets = TARGETS

    for lang_code, fmt in targets.items():
        process_language(lang_code, fmt, zh_data, dry_run=args.dry_run, remove_stale=remove_stale)

    if args.dry_run:
        print("\n[dry-run] No files were modified.")
    else:
        print("\nSync complete.")


if __name__ == "__main__":
    main()
