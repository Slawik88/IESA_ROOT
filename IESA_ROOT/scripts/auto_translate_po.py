import argparse
from typing import Iterable

import polib
from deep_translator import GoogleTranslator


def iter_entries(po: polib.POFile) -> Iterable[polib.POEntry]:
    for entry in po:
        if entry.obsolete:
            continue
        yield entry


def should_translate(entry: polib.POEntry) -> bool:
    if entry.msgid == "":
        return False
    if entry.msgstr.strip() == "":
        return True
    if entry.msgstr.strip() == entry.msgid.strip():
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-translate .po files with GoogleTranslator")
    parser.add_argument("po_path", help="Path to django.po")
    parser.add_argument("--lang", required=True, help="Target language code (de, fr, uk)")
    parser.add_argument("--source", default="en", help="Source language code")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of entries to translate")
    args = parser.parse_args()

    po = polib.pofile(args.po_path)
    translator = GoogleTranslator(source=args.source, target=args.lang)

    translated = 0
    for entry in iter_entries(po):
        if not should_translate(entry):
            continue
        if entry.msgid.strip().startswith("%(") or entry.msgid.strip().startswith("{"):
            # Keep placeholder-only strings as-is.
            continue
        entry.msgstr = translator.translate(entry.msgid)
        if "fuzzy" in entry.flags:
            entry.flags.remove("fuzzy")
        translated += 1
        if args.limit and translated >= args.limit:
            break

    if translated:
        po.save()
    print(f"Translated {translated} entries for {args.lang} in {args.po_path}")


if __name__ == "__main__":
    main()
