#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Inventory catalog entry coverage and source-reference drift.
# This script reports facts only: it does not judge translation correctness.

import os
import re
import shutil
import sys
from pathlib import Path
from collections import Counter, OrderedDict
from datetime import datetime, timezone


RE_MODULE_PATH = re.compile(r"^\s*?path = (.*)$", re.MULTILINE)
RE_VERSION_CATALOG = re.compile(
    br"^##[ \t]+version[ \t]+\$VER:[ \t]+([^ \t\r\n]+)\.catalog\b",
    re.MULTILINE | re.IGNORECASE)
RE_CD_LANGUAGE = re.compile(
    br"^#[ \t]*language[ \t]+([^ \t\r\n]+)[ \t]*$",
    re.MULTILINE | re.IGNORECASE)
RE_CT_LANGUAGE = re.compile(
    br"^##[ \t]+language[ \t]+([^\r\n]+?)[ \t]*$",
    re.MULTILINE | re.IGNORECASE)
RE_ID = re.compile(br"^[A-Za-z_][A-Za-z0-9_]*$")
RE_CD_ID = re.compile(
    br"^([A-Za-z_][A-Za-z0-9_]*)[ \t]*\([^)]*\)[ \t]*$")

HELPER_CT_FILES = {
    "empty.ct",
    "ahi.ct",
    "ahiprefs.ct",
}


def split_blocks(data):
    block = []
    for raw_line in data.splitlines():
        line = raw_line.rstrip(b"\r")
        if line.strip() == b";":
            if block:
                yield block
            block = []
        else:
            block.append(line)
    if block:
        yield block


def trim_blank_lines(lines):
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def fold_continuations(lines):
    logical = []
    current = b""

    for line in trim_blank_lines(lines):
        if current:
            current += line
        else:
            current = line

        if line.endswith(b"\\"):
            current = current[:-1]
            continue

        logical.append(current)
        current = b""

    if current:
        logical.append(current)

    return b"\n".join(logical)


def strip_source_comment(line):
    if not line.startswith(b";"):
        return None

    value = line[1:]
    if value.startswith(b" "):
        value = value[1:]
    return value


def display_payload(data):
    if data is None:
        return "-"
    text = data.decode("latin-1")
    return text.encode("unicode_escape").decode("ascii").replace("``", r"\`\`")


class Entry(object):
    def __init__(self, entry_id, payload, source_reference=None):
        self.entry_id = entry_id
        self.payload = payload
        self.source_reference = source_reference


class Descriptor(object):
    def __init__(self, path, language, entries, duplicates):
        self.path = path
        self.language = language
        self.entries = entries
        self.duplicates = duplicates
        self.mapped_ct = []

    @property
    def name(self):
        return self.path.name

    @property
    def stem(self):
        return self.path.stem

    def entry_ids(self):
        return list(self.entries.keys())


class Translation(object):
    def __init__(self, path, catalog_base, language):
        self.path = path
        self.catalog_base = catalog_base
        self.language = language
        self.entries = OrderedDict()
        self.duplicates = []
        self.ct_only_observed = []
        self.descriptor = None
        self.mapping = None

    @property
    def name(self):
        return self.path.name

    @property
    def label(self):
        return self.path.stem


class Module(object):
    def __init__(self, name):
        self.name = name
        self.descriptors = []
        self.translations = []

    def mapped_translations(self):
        return [ct for ct in self.translations if ct.descriptor is not None]

    def unresolved_translations(self):
        return [ct for ct in self.translations if ct.descriptor is None]


def parse_descriptor(path):
    data = path.read_bytes()
    language_match = RE_CD_LANGUAGE.search(data)
    language = (
        language_match.group(1).decode("ascii", errors="replace")
        if language_match else "not declared"
    )

    parsed = []

    for block in split_blocks(data):
        positions = []

        for index, line in enumerate(block):
            match = RE_CD_ID.match(line.strip())
            if match:
                positions.append((index, match.group(1).decode("ascii")))

        for pos_index, (line_index, entry_id) in enumerate(positions):
            end = (
                positions[pos_index + 1][0]
                if pos_index + 1 < len(positions)
                else len(block)
            )

            payload_lines = []
            for line in block[line_index + 1:end]:
                # Descriptor comment lines are documentation, not payload.
                if line.startswith(b";"):
                    continue
                payload_lines.append(line)

            parsed.append(
                Entry(entry_id, fold_continuations(payload_lines)))

    counts = Counter(entry.entry_id for entry in parsed)
    duplicates = sorted(
        entry_id for entry_id, count in counts.items() if count > 1)

    entries = OrderedDict()
    for entry in parsed:
        entries.setdefault(entry.entry_id, entry)

    return Descriptor(path, language, entries, duplicates)


def parse_translation_header(path):
    data = path.read_bytes()

    catalog_match = RE_VERSION_CATALOG.search(data)
    catalog_base = (
        catalog_match.group(1).decode("ascii", errors="replace")
        if catalog_match else None
    )

    language_match = RE_CT_LANGUAGE.search(data)
    language = (
        language_match.group(1).decode("latin-1")
        if language_match else "not declared"
    )

    return Translation(path, catalog_base, language)


def map_translation(module, translation):
    if len(module.descriptors) == 1:
        translation.descriptor = module.descriptors[0]
        translation.mapping = "single descriptor"
        module.descriptors[0].mapped_ct.append(translation)
        return

    if translation.catalog_base:
        matches = [
            descriptor for descriptor in module.descriptors
            if descriptor.stem.casefold() == translation.catalog_base.casefold()
        ]

        if len(matches) == 1:
            translation.descriptor = matches[0]
            translation.mapping = "catalog basename"
            matches[0].mapped_ct.append(translation)
            return

        if len(matches) > 1:
            translation.mapping = "ambiguous catalog basename"
            return

    if not module.descriptors:
        translation.mapping = "no descriptor"
    elif translation.catalog_base is None:
        translation.mapping = "catalog name not declared"
    else:
        translation.mapping = "no descriptor basename match"


def first_content_line(block):
    for line in block:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(b";") or stripped.startswith(b"#"):
            continue
        return stripped
    return None


def parse_translation_entries(translation):
    descriptor = translation.descriptor
    if descriptor is None:
        return

    data = translation.path.read_bytes()
    master_lookup = {
        entry_id.encode("ascii"): entry_id
        for entry_id in descriptor.entries
    }

    parsed = []
    ct_only_observed = []

    for block in split_blocks(data):
        first = first_content_line(block)
        if (
            first is not None
            and RE_ID.fullmatch(first)
            and first not in master_lookup
        ):
            ct_only_observed.append(first.decode("ascii"))

        positions = []
        for index, line in enumerate(block):
            stripped = line.strip()
            entry_id = master_lookup.get(stripped)
            if entry_id is not None:
                positions.append((index, entry_id))

        for pos_index, (line_index, entry_id) in enumerate(positions):
            end = (
                positions[pos_index + 1][0]
                if pos_index + 1 < len(positions)
                else len(block)
            )

            translation_lines = []
            source_lines = []
            source_started = False

            for line in block[line_index + 1:end]:
                source_line = strip_source_comment(line)

                if source_line is not None:
                    source_started = True
                    source_lines.append(source_line)
                    continue

                if not source_started:
                    translation_lines.append(line)

            payload = fold_continuations(translation_lines)
            source_reference = (
                fold_continuations(source_lines)
                if source_started else None
            )

            parsed.append(Entry(entry_id, payload, source_reference))

    counts = Counter(entry.entry_id for entry in parsed)
    translation.duplicates = sorted(
        entry_id for entry_id, count in counts.items() if count > 1)

    entries = OrderedDict()
    for entry in parsed:
        entries.setdefault(entry.entry_id, entry)

    translation.entries = entries
    translation.ct_only_observed = sorted(set(ct_only_observed))


def analyze_translation(translation):
    descriptor = translation.descriptor
    if descriptor is None:
        return None

    master_ids = set(descriptor.entries)
    ct_ids = set(translation.entries)

    missing = sorted(master_ids - ct_ids)
    empty = []
    source_same = []
    source_differs = []
    no_source_reference = []

    for entry_id in sorted(master_ids & ct_ids):
        ct_entry = translation.entries[entry_id]
        master_entry = descriptor.entries[entry_id]

        if ct_entry.payload == b"":
            empty.append(entry_id)

        if ct_entry.source_reference is None:
            no_source_reference.append(entry_id)
        elif ct_entry.source_reference == master_entry.payload:
            source_same.append(entry_id)
        else:
            source_differs.append(entry_id)

    return {
        "missing": missing,
        "empty": empty,
        "duplicates": list(translation.duplicates),
        "source_same": source_same,
        "source_differs": source_differs,
        "no_source_reference": no_source_reference,
        "ct_only_observed": list(translation.ct_only_observed),
    }


def entry_cell(translation, entry_id):
    descriptor = translation.descriptor
    if descriptor is None:
        return "UNMAPPED"

    if entry_id not in translation.entries:
        return "MISSING"

    flags = ["PRESENT"]

    if entry_id in translation.duplicates:
        flags.append("DUPLICATE")

    entry = translation.entries[entry_id]

    if entry.payload == b"":
        flags.append("EMPTY")

    if entry.source_reference is None:
        flags.append("NO_SOURCE_REFERENCE")
    elif entry.source_reference == descriptor.entries[entry_id].payload:
        flags.append("SOURCE_SAME")
    else:
        flags.append("SOURCE_DIFFERS")

    return " / ".join(flags)


def write_counter_table(fh, title, field_name, counter):
    fh.write(title + "\n")
    fh.write("-" * len(title) + "\n\n")
    fh.write(".. list-table::\n")
    fh.write("   :header-rows: 1\n\n")
    fh.write("   * - {}\n".format(field_name))
    fh.write("     - Count\n")

    if not counter:
        fh.write("   * - none\n")
        fh.write("     - 0\n")
    else:
        for key in sorted(counter, key=str):
            fh.write("   * - {}\n".format(key))
            fh.write("     - {}\n".format(counter[key]))

    fh.write("\n")


def module_totals(module):
    totals = Counter()

    totals["descriptors"] = len(module.descriptors)
    totals["translations"] = len(module.translations)
    totals["mapped"] = len(module.mapped_translations())
    totals["unmapped"] = len(module.unresolved_translations())

    for descriptor in module.descriptors:
        totals["master_entries"] += len(descriptor.entries)
        totals["descriptor_duplicates"] += len(descriptor.duplicates)

    for translation in module.mapped_translations():
        analysis = analyze_translation(translation)

        totals["missing"] += len(analysis["missing"])
        totals["empty"] += len(analysis["empty"])
        totals["translation_duplicates"] += len(analysis["duplicates"])
        totals["source_same"] += len(analysis["source_same"])
        totals["source_differs"] += len(analysis["source_differs"])
        totals["no_source_reference"] += len(
            analysis["no_source_reference"])
        totals["ct_only_observed"] += len(
            analysis["ct_only_observed"])

        if not analysis["missing"]:
            totals["complete_master_set"] += 1

    return totals


def write_missing_entries(fh, module):
    fh.write("Missing Master Entries\n")
    fh.write("----------------------\n\n")

    any_missing = False
    for translation in module.mapped_translations():
        missing = analyze_translation(translation)["missing"]
        if not missing:
            continue
        any_missing = True
        fh.write(
            "* ``{}``: {}\n".format(
                translation.name,
                ", ".join("``{}``".format(entry_id) for entry_id in missing)))

    if not any_missing:
        fh.write("None observed.\n")
    fh.write("\n")


def write_module_page(module, output_dir):
    page_name = os.path.join(output_dir, module.name + ".rst")
    os.makedirs(os.path.dirname(page_name), exist_ok=True)

    with open(page_name, "w", encoding="utf-8") as fh:
        title = module.name
        fh.write(title + "\n")
        fh.write("=" * len(title) + "\n\n")

        fh.write(
            "This page compares catalog translation entries with their mapped "
            "catalog descriptor master entries. Reported states are "
            "observations, not translation-quality judgments.\n\n")
        fh.write(
            "``CT-only observed`` contains only identifier-like lines that are "
            "structurally observable at the start of a CT block and are not "
            "present in the mapped master. It is deliberately conservative and "
            "is not a complete obsolete-entry census.\n\n")

        fh.write("Descriptors\n")
        fh.write("-----------\n\n")
        fh.write(".. list-table::\n")
        fh.write("   :header-rows: 1\n\n")
        fh.write("   * - Descriptor\n")
        fh.write("     - Declared language\n")
        fh.write("     - Entries\n")
        fh.write("     - Duplicate IDs\n")
        fh.write("     - Mapped CT files\n")

        if not module.descriptors:
            fh.write("   * - none\n")
            fh.write("     - -\n")
            fh.write("     - 0\n")
            fh.write("     - 0\n")
            fh.write("     - 0\n")
        else:
            for descriptor in module.descriptors:
                fh.write("   * - {}\n".format(descriptor.name))
                fh.write("     - {}\n".format(descriptor.language))
                fh.write("     - {}\n".format(len(descriptor.entries)))
                fh.write("     - {}\n".format(len(descriptor.duplicates)))
                fh.write("     - {}\n".format(len(descriptor.mapped_ct)))

        fh.write("\n")

        fh.write("Translation Summary\n")
        fh.write("-------------------\n\n")
        fh.write(".. list-table::\n")
        fh.write("   :header-rows: 1\n\n")
        fh.write("   * - Language file\n")
        fh.write("     - Master\n")
        fh.write("     - Present\n")
        fh.write("     - Missing\n")
        fh.write("     - Empty\n")
        fh.write("     - Duplicate\n")
        fh.write("     - Source same\n")
        fh.write("     - Source differs\n")
        fh.write("     - No source reference\n")
        fh.write("     - CT-only observed\n")

        for translation in module.translations:
            analysis = analyze_translation(translation)

            fh.write("   * - {}\n".format(translation.name))

            if analysis is None:
                fh.write(
                    "     - unmapped ({})\n".format(
                        translation.mapping or "not mapped"))
                for _ in range(8):
                    fh.write("     - -\n")
                continue

            descriptor = translation.descriptor
            present = len(translation.entries)

            fh.write("     - {}\n".format(descriptor.name))
            fh.write(
                "     - {} / {}\n".format(
                    present, len(descriptor.entries)))
            fh.write("     - {}\n".format(len(analysis["missing"])))
            fh.write("     - {}\n".format(len(analysis["empty"])))
            fh.write("     - {}\n".format(len(analysis["duplicates"])))
            fh.write("     - {}\n".format(len(analysis["source_same"])))
            fh.write("     - {}\n".format(len(analysis["source_differs"])))
            fh.write(
                "     - {}\n".format(
                    len(analysis["no_source_reference"])))
            fh.write(
                "     - {}\n".format(
                    len(analysis["ct_only_observed"])))

        fh.write("\n")

        for descriptor in module.descriptors:
            translations = descriptor.mapped_ct

            section = "Entry Matrix — {}".format(descriptor.name)
            fh.write(section + "\n")
            fh.write("-" * len(section) + "\n\n")

            if not translations:
                fh.write("No CT files map to this descriptor.\n\n")
                continue

            for start in range(0, len(translations), 6):
                group = translations[start:start + 6]

                fh.write(".. list-table::\n")
                fh.write("   :header-rows: 1\n\n")
                fh.write("   * - Entry\n")

                for translation in group:
                    fh.write("     - {}\n".format(translation.label))

                for entry_id in descriptor.entry_ids():
                    fh.write("   * - {}\n".format(entry_id))
                    for translation in group:
                        fh.write(
                            "     - {}\n".format(
                                entry_cell(translation, entry_id)))

                fh.write("\n")

        write_missing_entries(fh, module)

        source_diffs = []

        for translation in module.mapped_translations():
            descriptor = translation.descriptor
            analysis = analyze_translation(translation)

            for entry_id in analysis["source_differs"]:
                source_diffs.append(
                    (
                        translation.name,
                        descriptor.name,
                        entry_id,
                        descriptor.entries[entry_id].payload,
                        translation.entries[entry_id].source_reference,
                    )
                )

        fh.write("Source Reference Differences\n")
        fh.write("----------------------------\n\n")

        if not source_diffs:
            fh.write("None observed.\n\n")
        else:
            for ct_name, descriptor_name, entry_id, master, old in source_diffs:
                fh.write(
                    "* ``{}`` / ``{}`` / ``{}``\n".format(
                        ct_name, descriptor_name, entry_id))
                fh.write(
                    "  * master: ``{}``\n".format(
                        display_payload(master)))
                fh.write(
                    "  * CT source reference: ``{}``\n".format(
                        display_payload(old)))
            fh.write("\n")

        fh.write("CT-only IDs Observed\n")
        fh.write("--------------------\n\n")

        ct_only_any = False
        for translation in module.mapped_translations():
            observed = analyze_translation(translation)["ct_only_observed"]
            if not observed:
                continue
            ct_only_any = True
            fh.write(
                "* ``{}``: {}\n".format(
                    translation.name,
                    ", ".join(
                        "``{}``".format(entry_id)
                        for entry_id in observed)))

        if not ct_only_any:
            fh.write("None observed.\n")
        fh.write("\n")

        fh.write("Unmapped Translation Files\n")
        fh.write("--------------------------\n\n")

        unresolved = module.unresolved_translations()

        if not unresolved:
            fh.write("None.\n")
        else:
            for translation in unresolved:
                fh.write(
                    "* ``{}``: {}; catalog base: ``{}``\n".format(
                        translation.name,
                        translation.mapping or "not mapped",
                        translation.catalog_base or "not declared"))
        fh.write("\n")


def concentration_rows(modules, key):
    rows = []
    for module in modules:
        totals = module_totals(module)
        value = totals[key]
        if value:
            rows.append((value, module.name, totals))
    rows.sort(key=lambda item: (-item[0], item[1].casefold()))
    return rows


def write_concentration_section(fh, modules, title, key):
    rows = concentration_rows(modules, key)
    fh.write(title + "\n")
    fh.write("-" * len(title) + "\n\n")
    fh.write(".. list-table::\n")
    fh.write("   :header-rows: 1\n\n")
    fh.write("   * - Module\n")
    fh.write("     - Count\n")
    fh.write("     - CT\n")
    fh.write("     - Complete master set\n")

    if not rows:
        fh.write("   * - none\n")
        fh.write("     - 0\n")
        fh.write("     - 0\n")
        fh.write("     - 0\n")
    else:
        for value, module_name, totals in rows:
            fh.write("   * - {}\n".format(module_name))
            fh.write("     - {}\n".format(value))
            fh.write("     - {}\n".format(totals["translations"]))
            fh.write("     - {}\n".format(totals["complete_master_set"]))

    fh.write("\n")


def print_concentration(modules, title, key):
    rows = concentration_rows(modules, key)
    print()
    print("=== {} ===".format(title.upper()))
    print("modules={}".format(len(rows)))
    if not rows:
        print("NONE")
        return
    for value, module_name, totals in rows:
        print(
            "{:6d} | ct={:3d} | complete={:3d} | {}".format(
                value,
                totals["translations"],
                totals["complete_master_set"],
                module_name))


module_file_name = "../.gitmodules"

if not os.path.exists(module_file_name):
    print("Error! ../.gitmodules doesn't exist.")
    sys.exit(2)

with open(module_file_name, "r", encoding="utf-8") as module_file:
    module_file_content = module_file.read()

module_paths = [
    match.group(1)
    for match in RE_MODULE_PATH.finditer(module_file_content)
]

if not module_paths:
    print("Error! No catalog paths found in ../.gitmodules.")
    sys.exit(2)

missing_module_paths = [
    path for path in module_paths
    if not os.path.isdir(os.path.join("..", path))
]

if missing_module_paths:
    for path in missing_module_paths:
        print("Error! catalog submodule isn't available:", path)
    sys.exit(2)

modules = []
technical_errors = []

for module_name in module_paths:
    module_path = os.path.join("..", module_name)
    print("checking directory", module_path)

    module = Module(module_name)
    modules.append(module)

    for descriptor_path in sorted(
            (os.path.join(module_path, name)
             for name in os.listdir(module_path)
             if name.lower().endswith(".cd")),
            key=str.lower):
        try:
            module.descriptors.append(
                parse_descriptor(Path(os.path.abspath(descriptor_path))))
        except OSError as error:
            technical_errors.append((descriptor_path, str(error)))

    for translation_path in sorted(
            (os.path.join(module_path, name)
             for name in os.listdir(module_path)
             if name.lower().endswith(".ct")
             and name not in HELPER_CT_FILES),
            key=str.lower):
        try:
            module.translations.append(
                parse_translation_header(
                    Path(os.path.abspath(translation_path))))
        except OSError as error:
            technical_errors.append((translation_path, str(error)))

    for translation in module.translations:
        map_translation(module, translation)
        if translation.descriptor is None:
            continue
        try:
            parse_translation_entries(translation)
        except OSError as error:
            technical_errors.append((str(translation.path), str(error)))

output_dir = "entryresult"

if os.path.isdir(output_dir):
    shutil.rmtree(output_dir)

for module in modules:
    write_module_page(module, output_dir)

corpus = Counter()

for module in modules:
    totals = module_totals(module)
    for key, value in totals.items():
        corpus[key] += value

with open("entryresult.rst", "w", encoding="utf-8") as fh:
    fh.write("============\n")
    fh.write("Entry Census\n")
    fh.write("============\n\n")
    fh.write(
        "This report compares catalog translation entries with their mapped "
        "catalog descriptor master entries. It reports entry presence, "
        "source-reference state and structural facts only; it does not judge "
        "translation correctness.\n\n")
    fh.write(
        "``SOURCE_DIFFERS`` means that the English source reference stored "
        "in a CT entry differs byte-for-byte from the current descriptor "
        "text after physical continuation lines are folded. It does not "
        "mean that the translation itself is wrong.\n\n")
    fh.write(
        "``CT-only observed`` is deliberately conservative: only identifier-"
        "like lines structurally visible at the beginning of a CT block are "
        "reported when they are absent from the mapped master.\n\n")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    fh.write("Created on UTC " + now + ".\n\n")

    fh.write("Module Summary\n")
    fh.write("==============\n\n")
    fh.write(".. list-table::\n")
    fh.write("   :header-rows: 1\n\n")
    fh.write("   * - Module Name\n")
    fh.write("     - Masters\n")
    fh.write("     - Master entries\n")
    fh.write("     - CT\n")
    fh.write("     - Mapped CT\n")
    fh.write("     - Complete master set\n")
    fh.write("     - Missing IDs\n")
    fh.write("     - CT-only observed\n")
    fh.write("     - Empty\n")
    fh.write("     - Source differs\n")
    fh.write("     - No source reference\n")

    for module in modules:
        totals = module_totals(module)
        target = os.path.join(
            "entryresult", module.name + ".rst").replace(os.sep, "/")
        fh.write("   * - `{} <{}>`_\n".format(module.name, target))
        fh.write("     - {}\n".format(totals["descriptors"]))
        fh.write("     - {}\n".format(totals["master_entries"]))
        fh.write("     - {}\n".format(totals["translations"]))
        fh.write("     - {}\n".format(totals["mapped"]))
        fh.write("     - {}\n".format(totals["complete_master_set"]))
        fh.write("     - {}\n".format(totals["missing"]))
        fh.write("     - {}\n".format(totals["ct_only_observed"]))
        fh.write("     - {}\n".format(totals["empty"]))
        fh.write("     - {}\n".format(totals["source_differs"]))
        fh.write("     - {}\n".format(totals["no_source_reference"]))

    fh.write("\n")

    fh.write("Finding Concentration\n")
    fh.write("=====================\n\n")
    write_concentration_section(
        fh, modules, "Missing master IDs by module", "missing")
    write_concentration_section(
        fh, modules, "Empty translation payloads by module", "empty")
    write_concentration_section(
        fh, modules, "Source reference drift by module", "source_differs")
    write_concentration_section(
        fh, modules, "No source reference by module", "no_source_reference")
    write_concentration_section(
        fh, modules, "CT-only IDs observed by module", "ct_only_observed")

    fh.write("Corpus Summary\n")
    fh.write("==============\n\n")
    fh.write("* Modules: {}\n".format(len(modules)))
    fh.write("* Descriptor files: {}\n".format(corpus["descriptors"]))
    fh.write("* Translation CT files: {}\n".format(corpus["translations"]))
    fh.write("* Mapped CT files: {}\n".format(corpus["mapped"]))
    fh.write("* Unmapped CT files: {}\n".format(corpus["unmapped"]))
    fh.write("* Master entries: {}\n".format(corpus["master_entries"]))
    fh.write(
        "* CT files containing the complete master ID set: {}\n".format(
            corpus["complete_master_set"]))
    fh.write("* Missing-ID occurrences: {}\n".format(corpus["missing"]))
    fh.write(
        "* Structurally observed CT-only IDs: {}\n".format(
            corpus["ct_only_observed"]))
    fh.write("* Empty translation payloads: {}\n".format(corpus["empty"]))
    fh.write(
        "* Source references matching current master: {}\n".format(
            corpus["source_same"]))
    fh.write(
        "* Source references differing from current master: {}\n".format(
            corpus["source_differs"]))
    fh.write(
        "* Entries without source reference: {}\n".format(
            corpus["no_source_reference"]))
    fh.write(
        "* Duplicate CT master IDs: {}\n".format(
            corpus["translation_duplicates"]))
    fh.write(
        "* Duplicate descriptor IDs: {}\n\n".format(
            corpus["descriptor_duplicates"]))

    mapping_counter = Counter()
    for module in modules:
        for translation in module.translations:
            mapping_counter[translation.mapping or "not mapped"] += 1

    write_counter_table(
        fh,
        "CT-to-master mapping",
        "Mapping",
        mapping_counter)

    if technical_errors:
        fh.write("Technical Errors\n")
        fh.write("================\n\n")
        for path, message in technical_errors:
            fh.write("* ``{}``: {}\n".format(path, message))
        fh.write("\n")

print("-" * 80)
print("modules:", len(modules))
print("descriptor files:", corpus["descriptors"])
print("translation CT files:", corpus["translations"])
print("mapped CT files:", corpus["mapped"])
print("unmapped CT files:", corpus["unmapped"])
print("master entries:", corpus["master_entries"])
print(
    "CT files containing complete master ID set:",
    corpus["complete_master_set"])
print("missing-ID occurrences:", corpus["missing"])
print("structurally observed CT-only IDs:", corpus["ct_only_observed"])
print("empty translation payloads:", corpus["empty"])
print("source references matching current master:", corpus["source_same"])
print("source references differing from current master:", corpus["source_differs"])
print("entries without source reference:", corpus["no_source_reference"])
print("result: entryresult.rst")

print_concentration(modules, "Missing master IDs by module", "missing")
print_concentration(modules, "Empty translation payloads by module", "empty")
print_concentration(modules, "Source reference drift by module", "source_differs")
print_concentration(modules, "No source reference by module", "no_source_reference")
print_concentration(modules, "CT-only IDs observed by module", "ct_only_observed")

sys.exit(2 if technical_errors else 0)
