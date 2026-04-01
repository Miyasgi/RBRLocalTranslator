"""
setup_translate.py — One-time argostranslate package installer for RBRi18n.

Run this script once (requires internet) to download the language model packages.
After that, translate_gaps.py works fully offline.

Usage:
    python setup_translate.py            # install missing packages only
    python setup_translate.py --force    # re-download even if already installed
    python setup_translate.py --list     # show what is installed / missing
"""

import argparse
from argostranslate import package

REQUIRED_PAIRS = [
    ("en", "ja"),  # Japanese
    ("en", "hu"),  # Hungarian
    ("en", "pt"),  # Portuguese
    ("en", "ru"),  # Russian
    ("en", "zh"),  # Simplified Chinese (also used as en->zh->Traditional chain via opencc)
]


def get_installed_pairs():
    return {(p.from_code, p.to_code) for p in package.get_installed_packages()}


def list_status(available_pairs, installed_pairs):
    print(f"{'Pair':<12} {'Available':>10} {'Installed':>10}")
    print("-" * 36)
    for from_code, to_code in REQUIRED_PAIRS:
        pair_str = f"{from_code} -> {to_code}"
        avail = "yes" if (from_code, to_code) in available_pairs else "no"
        inst = "yes" if (from_code, to_code) in installed_pairs else "no"
        print(f"{pair_str:<12}   {avail:>8}   {inst:>8}")


def main():
    parser = argparse.ArgumentParser(description="Install argostranslate packages for RBRi18n.")
    parser.add_argument("--force", action="store_true", help="Re-download even if already installed.")
    parser.add_argument("--list", action="store_true", help="Show install status and exit.")
    args = parser.parse_args()

    print("Fetching argostranslate package index...")
    package.update_package_index()

    available = package.get_available_packages()
    available_pairs = {(p.from_code, p.to_code): p for p in available}
    installed_pairs = get_installed_pairs()

    print(f"Found {len(available)} packages in index. {len(installed_pairs)} currently installed.\n")

    if args.list:
        list_status(available_pairs, installed_pairs)
        return

    installed_count = 0
    skipped_count = 0
    missing_from_index = []

    for from_code, to_code in REQUIRED_PAIRS:
        pair_str = f"{from_code} -> {to_code}"

        if (from_code, to_code) not in available_pairs:
            missing_from_index.append(pair_str)
            print(f"  NOT IN INDEX: {pair_str}")
            continue

        if (from_code, to_code) in installed_pairs and not args.force:
            print(f"  Already installed: {pair_str} (use --force to re-download)")
            skipped_count += 1
            continue

        pkg = available_pairs[(from_code, to_code)]
        print(f"Downloading {pair_str} ...")
        download_path = pkg.download()
        package.install_from_path(download_path)
        print(f"  Installed: {pair_str}")
        installed_count += 1

    print(
        f"\nDone. Installed {installed_count}, skipped {skipped_count} "
        f"(already present), {len(missing_from_index)} not in index."
    )

    if missing_from_index:
        print("\nPackages not found in argostranslate index:")
        for m in missing_from_index:
            print(f"  - {m}")

    if "en -> zt" in missing_from_index:
        print(
            "\nNote: 'en -> zt' (Traditional Chinese) is unavailable.\n"
            "translate_gaps.py will fall back to chaining en->zh then zh->zt.\n"
            "Make sure 'en -> zh' is also installed."
        )
        # Auto-install en->zh as fallback if needed
        installed_pairs = get_installed_pairs()
        if ("en", "zh") not in installed_pairs:
            if ("en", "zh") in available_pairs:
                print("Installing en -> zh as fallback...")
                package.install_from_path(available_pairs[("en", "zh")].download())
                print("  Installed: en -> zh")
            else:
                print("  Warning: en -> zh also not available in index.")


if __name__ == "__main__":
    main()
