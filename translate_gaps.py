"""
translate_gaps.py — Fill missing translation keys using local argostranslate.

Reads Translation.zh.json as the canonical key reference, compares against each
target language file, and translates any missing keys using offline MT models.

Usage:
    python translate_gaps.py                                    # all incomplete languages
    python translate_gaps.py --lang jp                          # single language
    python translate_gaps.py --lang jp --dry-run                # preview without writing
    python translate_gaps.py --list-langs                       # show gap counts for all langs
    python translate_gaps.py --skip-categories stages,dailystages
    python translate_gaps.py --only-categories misc,cars
    python translate_gaps.py --batch-size 100                   # save interval (default: 50)
    python translate_gaps.py --force                            # re-translate existing keys too

Requirements:
    Run setup_translate.py first to install language packages.
"""

import argparse
import json
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RBRI18N_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "RBRi18n"))
ZH_REF_PATH = os.path.join(RBRI18N_DIR, "Translation.zh.json")

# Maps project filename code -> argostranslate language code
TARGETS = {
    "hu": {"argo_code": "hu", "skip": False},
    "jp": {"argo_code": "ja", "skip": False},
    "pt": {"argo_code": "pt", "skip": False},
    "ru": {"argo_code": "ru", "skip": False},
    "zh-Hant": {"argo_code": "zt", "skip": True},  # already complete
}

PROPER_NOUN_CATEGORIES = {"stages", "dailystages"}

# Regex to find printf-style format specifiers: %s %d %f %i %02d etc.
FORMAT_SPEC_RE = re.compile(r"%[\d.]*[sdifouxX]")


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def load_json(path):
    """Return (data, fmt) where fmt is 'categorized' or 'flat'."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data and isinstance(next(iter(data.values())), dict):
        return data, "categorized"
    return data, "flat"


def write_json(path, data):
    """Atomic write: write to .tmp then rename."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def should_skip_key(key, zh_value):
    """Return True for keys that should not be sent to MT."""
    if key.startswith(";"):
        return True
    if not zh_value or not zh_value.strip():
        return True
    return False


def find_missing_keys(zh_data, target_data, target_fmt, skip_categories=None,
                      only_categories=None, force=False):
    """
    Return list of (category, key) tuples.

    With force=False: only keys absent or empty in target.
    With force=True: all keys (re-translate everything).
    """
    skip_categories = skip_categories or set()
    missing = []

    for category, entries in zh_data.items():
        if category in skip_categories:
            continue
        if only_categories and category not in only_categories:
            continue
        if target_fmt == "categorized":
            target_entries = target_data.get(category, {})
        else:
            target_entries = target_data

        for key, zh_value in entries.items():
            if should_skip_key(key, zh_value):
                continue
            if not force:
                existing = target_entries.get(key, "")
                if existing and existing.strip():
                    continue
            missing.append((category, key))

    return missing


def count_gaps(zh_data, target_data, target_fmt):
    """Return count of missing keys (no category/force filtering)."""
    return len(find_missing_keys(zh_data, target_data, target_fmt))


# ---------------------------------------------------------------------------
# argostranslate helpers
# ---------------------------------------------------------------------------

def get_translator(from_code, to_code):
    from argostranslate import translate
    installed = translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == from_code), None)
    if from_lang is None:
        raise RuntimeError(
            f"Language '{from_code}' not installed. Run setup_translate.py first."
        )
    to_lang = next((l for l in installed if l.code == to_code), None)
    if to_lang is None:
        raise RuntimeError(
            f"Language '{to_code}' not installed. Run setup_translate.py first."
        )
    translation = from_lang.get_translation(to_lang)
    if translation is None:
        raise RuntimeError(
            f"No translation package '{from_code}' -> '{to_code}'. "
            "Run setup_translate.py first."
        )
    return translation


def get_zt_translator():
    """
    Return a callable for en -> Traditional Chinese (zt).

    Translates English to Simplified Chinese first (via argostranslate),
    then converts Simplified -> Traditional using opencc (character mapping,
    no MT quality loss).
    """
    try:
        import opencc
    except ImportError:
        raise RuntimeError(
            "opencc-python-reimplemented is not installed.\n"
            "Run: pip install opencc-python-reimplemented"
        )
    t_en_zh = get_translator("en", "zh")
    converter = opencc.OpenCC("s2t")  # Simplified -> Traditional
    return lambda text: converter.convert(t_en_zh.translate(text))


# ---------------------------------------------------------------------------
# Format specifier check
# ---------------------------------------------------------------------------

def check_format_specifiers(key, translated):
    """Warn if format specifiers present in key are missing from translation."""
    original_specs = FORMAT_SPEC_RE.findall(key)
    if not original_specs:
        return
    translated_specs = FORMAT_SPEC_RE.findall(translated)
    if sorted(original_specs) != sorted(translated_specs):
        print(
            f"  Warning: format specifier mismatch for {key!r}\n"
            f"    original:   {original_specs}\n"
            f"    translated: {translated_specs}"
        )


# ---------------------------------------------------------------------------
# Merge and incremental write
# ---------------------------------------------------------------------------

def apply_entry(data, fmt, category, key, value):
    """Apply a single translated entry into data in-place."""
    if fmt == "categorized":
        if category not in data:
            data[category] = {}
        data[category][key] = value
    else:
        data[key] = value


# ---------------------------------------------------------------------------
# Per-language processing
# ---------------------------------------------------------------------------

def process_language(lang_code, argo_code, zh_data, skip_categories, only_categories,
                     batch_size, dry_run, force):
    file_path = os.path.join(RBRI18N_DIR, f"Translation.{lang_code}.json")

    if not os.path.exists(file_path):
        print(f"[{lang_code}] File not found, will create from scratch.")
        target_data = {cat: {} for cat in zh_data}
        target_fmt = "categorized"
    else:
        target_data, target_fmt = load_json(file_path)

    missing = find_missing_keys(
        zh_data, target_data, target_fmt,
        skip_categories=skip_categories,
        only_categories=only_categories,
        force=force,
    )

    if not missing:
        print(f"[{lang_code}] No missing keys. Nothing to do.")
        return 0

    print(f"[{lang_code}] Found {len(missing)} missing keys.")

    if any(cat in PROPER_NOUN_CATEGORIES for cat, _ in missing):
        included_pn = {cat for cat, _ in missing if cat in PROPER_NOUN_CATEGORIES}
        print(
            f"  Warning: categories {included_pn} contain proper stage/car names. "
            "MT results may be poor. Use --skip-categories stages,dailystages to exclude them."
        )

    if dry_run:
        print(f"  [dry-run] Would translate {len(missing)} keys for '{lang_code}'.")
        for category, key in missing[:10]:
            print(f"    [{category}] {key!r}")
        if len(missing) > 10:
            print(f"    ... and {len(missing) - 10} more.")
        return len(missing)

    # Get translator
    if argo_code == "zt":
        translate_fn = get_zt_translator()
    else:
        translator = get_translator("en", argo_code)
        translate_fn = translator.translate

    total = len(missing)
    translated_count = 0
    error_count = 0
    start_time = time.monotonic()

    for i, (category, key) in enumerate(missing):
        # Progress + time estimate every batch_size items
        if i > 0 and i % batch_size == 0:
            elapsed = time.monotonic() - start_time
            rate = i / elapsed  # keys/sec
            remaining = (total - i) / rate if rate > 0 else 0
            print(
                f"  [{i}/{total}] {lang_code} — "
                f"{rate:.1f} keys/s — "
                f"~{int(remaining // 60)}m{int(remaining % 60):02d}s remaining"
            )
            # Incremental save every batch_size keys
            write_json(file_path, target_data)

        try:
            value = translate_fn(key)
            check_format_specifiers(key, value)
            apply_entry(target_data, target_fmt, category, key, value)
            translated_count += 1
        except Exception as exc:
            print(f"  Error translating {key!r}: {exc}")
            error_count += 1

    # Final save
    write_json(file_path, target_data)

    elapsed = time.monotonic() - start_time
    print(
        f"[{lang_code}] Done. "
        f"Translated {translated_count}/{total} keys "
        f"({error_count} errors) "
        f"in {int(elapsed // 60)}m{int(elapsed % 60):02d}s"
    )
    return translated_count


# ---------------------------------------------------------------------------
# --list-langs: show gap summary
# ---------------------------------------------------------------------------

def list_langs(zh_data):
    print(f"{'Lang':<10} {'File':<12} {'Total keys':>10} {'Missing':>8}")
    print("-" * 44)
    total_ref = sum(len(v) for v in zh_data.values())
    for lang_code, cfg in TARGETS.items():
        file_path = os.path.join(RBRI18N_DIR, f"Translation.{lang_code}.json")
        if not os.path.exists(file_path):
            print(f"{lang_code:<10} {'(missing)':<12} {total_ref:>10} {total_ref:>8}")
            continue
        target_data, target_fmt = load_json(file_path)
        gaps = count_gaps(zh_data, target_data, target_fmt)
        present = total_ref - gaps
        status = " (skip)" if cfg["skip"] else ""
        print(f"{lang_code:<10} {'exists':<12} {present:>10} {gaps:>8}{status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fill missing RBRi18n translations using argostranslate."
    )
    parser.add_argument("--lang", help="Target language code (e.g. jp, ru). Omit for all.")
    parser.add_argument("--dry-run", action="store_true", help="Preview gaps without writing.")
    parser.add_argument("--list-langs", action="store_true", help="Show gap counts and exit.")
    parser.add_argument("--force", action="store_true", help="Re-translate already-translated keys.")
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Keys per progress report + incremental save interval (default: 50)."
    )
    parser.add_argument(
        "--skip-categories", default="",
        help="Comma-separated categories to skip (e.g. stages,dailystages)."
    )
    parser.add_argument(
        "--only-categories", default="",
        help="Comma-separated categories to limit translation to (e.g. misc,cars)."
    )
    args = parser.parse_args()

    skip_categories = set(c.strip() for c in args.skip_categories.split(",") if c.strip())
    only_categories = set(c.strip() for c in args.only_categories.split(",") if c.strip()) or None

    # GPU check
    try:
        import torch
        if torch.cuda.is_available():
            print(f"GPU: {torch.cuda.get_device_name(0)}")
        else:
            print("GPU: None (CPU mode — translation will be slow for large files)")
    except ImportError:
        pass

    # Load reference
    if not os.path.exists(ZH_REF_PATH):
        print(f"Error: Reference file not found: {ZH_REF_PATH}", file=sys.stderr)
        sys.exit(1)

    zh_data, zh_fmt = load_json(ZH_REF_PATH)
    if zh_fmt != "categorized":
        print("Error: zh reference file is not in categorized format.", file=sys.stderr)
        sys.exit(1)

    print(f"Reference: {ZH_REF_PATH} ({sum(len(v) for v in zh_data.values())} keys)\n")

    if args.list_langs:
        list_langs(zh_data)
        return

    # Determine which languages to process
    if args.lang:
        if args.lang not in TARGETS:
            print(
                f"Error: Unknown language '{args.lang}'. "
                f"Valid options: {', '.join(TARGETS)}",
                file=sys.stderr,
            )
            sys.exit(1)
        targets_to_run = {args.lang: TARGETS[args.lang]}
    else:
        targets_to_run = {k: v for k, v in TARGETS.items() if not v["skip"]}

    total_translated = 0
    for lang_code, cfg in targets_to_run.items():
        print()
        count = process_language(
            lang_code=lang_code,
            argo_code=cfg["argo_code"],
            zh_data=zh_data,
            skip_categories=skip_categories,
            only_categories=only_categories,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            force=args.force,
        )
        total_translated += count

    print(f"\nTotal keys translated: {total_translated}")


if __name__ == "__main__":
    main()
