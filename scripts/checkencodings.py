#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Inventory encoding metadata and byte characteristics of catalog files.
# This script reports facts only: it does not infer, validate, or normalize
# the encoding of a catalog file.

import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone


################################################################################

RE_MODULE_PATH = re.compile(r"^\s*?path = (.*)$", re.MULTILINE)
RE_CODESET = re.compile(br"^##[ \t]+codeset[ \t]+([0-9]+)[ \t]*\r?$", re.MULTILINE)


class CatalogFile(object):
    def __init__(self, name, kind, size, codesets, git_encoding, bom,
                 ascii_only, high_bytes, valid_utf8):
        self.name = name
        self.kind = kind
        self.size = size
        self.codesets = codesets
        self.git_encoding = git_encoding
        self.bom = bom
        self.ascii_only = ascii_only
        self.high_bytes = high_bytes
        self.valid_utf8 = valid_utf8

    def declared_codeset(self):
        if not self.codesets:
            return "not present"
        return ", ".join(self.codesets)


class Module(object):
    def __init__(self, name):
        self.name = name
        self.files = []

    def add_file(self, catalog_file):
        self.files.append(catalog_file)

    def count_kind(self, kind):
        return sum(1 for item in self.files if item.kind == kind)

    def declared_codesets(self):
        values = set()
        for item in self.files:
            values.update(item.codesets)
        return sorted(values, key=lambda value: int(value))

    def git_encodings(self):
        return sorted(set(item.git_encoding for item in self.files))

    def ascii_only_count(self):
        return sum(1 for item in self.files if item.ascii_only)

    def high_byte_file_count(self):
        return sum(1 for item in self.files if item.high_bytes > 0)

    def valid_utf8_count(self):
        return sum(1 for item in self.files if item.valid_utf8)


class Report(object):
    def __init__(self):
        self.modules = []
        self.technical_errors = []

    def add_module(self, module):
        self.modules.append(module)

    def add_technical_error(self, path, message):
        self.technical_errors.append((path, message))

    def all_files(self):
        for module in self.modules:
            for item in module.files:
                yield item

    def get_module_page_name(self, module):
        return os.path.join("encodingresult", module.name + ".rst")

    def write_module_summary(self, fh):
        fh.write("Module Summary\n")
        fh.write("==============\n\n")
        fh.write("Each module links to the raw per-file encoding facts collected for it.\n\n")
        fh.write(".. list-table::\n")
        fh.write("   :header-rows: 1\n\n")
        fh.write("   * - Module Name\n")
        fh.write("     - Files\n")
        fh.write("     - CT\n")
        fh.write("     - CD\n")
        fh.write("     - Declared codesets\n")
        fh.write("     - Git encodings\n")
        fh.write("     - ASCII-only\n")
        fh.write("     - Files with bytes >= 0x80\n")
        fh.write("     - UTF-8 byte-valid\n")

        for module in self.modules:
            target = self.get_module_page_name(module).replace(os.sep, "/")
            codesets = ", ".join(module.declared_codesets()) or "none"
            encodings = ", ".join(module.git_encodings()) or "none"
            fh.write("   * - `{} <{}>`_\n".format(module.name, target))
            fh.write("     - {}\n".format(len(module.files)))
            fh.write("     - {}\n".format(module.count_kind("CT")))
            fh.write("     - {}\n".format(module.count_kind("CD")))
            fh.write("     - {}\n".format(codesets))
            fh.write("     - {}\n".format(encodings))
            fh.write("     - {}\n".format(module.ascii_only_count()))
            fh.write("     - {}\n".format(module.high_byte_file_count()))
            fh.write("     - {}\n".format(module.valid_utf8_count()))
        fh.write("\n")

    def write_corpus_summary(self, fh):
        files = list(self.all_files())
        codesets = Counter()
        encodings = Counter()
        bom_values = Counter()

        for item in files:
            if item.kind == "CT":
                if item.codesets:
                    for value in item.codesets:
                        codesets[value] += 1
                else:
                    codesets["not present"] += 1
            encodings[item.git_encoding] += 1
            bom_values[item.bom] += 1

        fh.write("Corpus Summary\n")
        fh.write("==============\n\n")
        fh.write("* Modules: {}\n".format(len(self.modules)))
        fh.write("* Catalog files: {}\n".format(len(files)))
        fh.write("* CT files: {}\n".format(sum(1 for item in files if item.kind == "CT")))
        fh.write("* CD files: {}\n".format(sum(1 for item in files if item.kind == "CD")))
        fh.write("* ASCII-only files: {}\n".format(sum(1 for item in files if item.ascii_only)))
        fh.write("* Files containing bytes >= 0x80: {}\n".format(
            sum(1 for item in files if item.high_bytes > 0)))
        fh.write("* Files whose complete byte stream is valid UTF-8: {}\n\n".format(
            sum(1 for item in files if item.valid_utf8)))

        self.write_counter_table(fh, "Declared codeset values", "Codeset", codesets)
        self.write_counter_table(fh, "Effective Git encoding attributes", "Encoding", encodings)
        self.write_counter_table(fh, "Byte order marks", "BOM", bom_values)

    def write_counter_table(self, fh, title, field_name, values):
        fh.write(title + "\n")
        fh.write("-" * len(title) + "\n\n")
        fh.write(".. list-table::\n")
        fh.write("   :header-rows: 1\n\n")
        fh.write("   * - {}\n".format(field_name))
        fh.write("     - Files\n")
        for value in sorted(values, key=str):
            fh.write("   * - {}\n".format(value))
            fh.write("     - {}\n".format(values[value]))
        fh.write("\n")

    def write_module_pages(self, output_dir):
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)

        for module in self.modules:
            page_name = os.path.join(output_dir, module.name + ".rst")
            os.makedirs(os.path.dirname(page_name), exist_ok=True)
            with open(page_name, "w", encoding="utf-8") as page:
                title = module.name
                page.write(title + "\n")
                page.write("=" * len(title) + "\n\n")
                page.write("The table contains observed metadata and byte characteristics only.\n\n")
                page.write(".. list-table::\n")
                page.write("   :header-rows: 1\n\n")
                page.write("   * - File\n")
                page.write("     - Type\n")
                page.write("     - Declared codeset\n")
                page.write("     - Git encoding\n")
                page.write("     - BOM\n")
                page.write("     - Bytes\n")
                page.write("     - Bytes >= 0x80\n")
                page.write("     - ASCII-only\n")
                page.write("     - UTF-8 byte-valid\n")

                for item in module.files:
                    page.write("   * - {}\n".format(item.name))
                    page.write("     - {}\n".format(item.kind))
                    page.write("     - {}\n".format(item.declared_codeset()))
                    page.write("     - {}\n".format(item.git_encoding))
                    page.write("     - {}\n".format(item.bom))
                    page.write("     - {}\n".format(item.size))
                    page.write("     - {}\n".format(item.high_bytes))
                    page.write("     - {}\n".format("yes" if item.ascii_only else "no"))
                    page.write("     - {}\n".format("yes" if item.valid_utf8 else "no"))

    def write_rst(self, fh):
        self.write_module_summary(fh)
        self.write_corpus_summary(fh)

        if self.technical_errors:
            fh.write("Technical Errors\n")
            fh.write("================\n\n")
            for path, message in self.technical_errors:
                fh.write("* ``{}``: {}\n".format(path, message))
            fh.write("\n")


################################################################################

def detect_bom(data):
    if data.startswith(b"\x00\x00\xfe\xff"):
        return "UTF-32BE"
    if data.startswith(b"\xff\xfe\x00\x00"):
        return "UTF-32LE"
    if data.startswith(b"\xef\xbb\xbf"):
        return "UTF-8"
    if data.startswith(b"\xfe\xff"):
        return "UTF-16BE"
    if data.startswith(b"\xff\xfe"):
        return "UTF-16LE"
    return "none"


def is_valid_utf8(data):
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def get_effective_git_encoding(git, module_path, file_name):
    result = subprocess.run(
        [git, "-C", module_path, "check-attr", "encoding", "--", file_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git check-attr failed")

    output = result.stdout.strip()
    fields = output.split(": ", 2)
    if len(fields) != 3:
        raise RuntimeError("unexpected git check-attr output: {}".format(output))
    return fields[2]


def catalog_file_names(module_path):
    result = []
    for name in os.listdir(module_path):
        full_path = os.path.join(module_path, name)
        if not os.path.isfile(full_path):
            continue
        lower = name.lower()
        if lower.endswith(".ct") or lower.endswith(".cd"):
            result.append(name)
    return sorted(result, key=str.lower)


################################################################################

module_file_name = "../.gitmodules"
if not os.path.exists(module_file_name):
    print("Error! ../.gitmodules doesn't exist.")
    sys.exit(2)

with open(module_file_name, "r", encoding="utf-8") as module_file:
    module_file_content = module_file.read()

module_paths = [match.group(1) for match in RE_MODULE_PATH.finditer(module_file_content)]
if not module_paths:
    print("Error! No catalog paths found in ../.gitmodules.")
    sys.exit(2)

missing_module_paths = [path for path in module_paths
                        if not os.path.isdir(os.path.join("..", path))]
if missing_module_paths:
    for path in missing_module_paths:
        print("Error! catalog submodule isn't available:", path)
    sys.exit(2)

git = shutil.which("git")
if not git:
    print("Error! git isn't available; effective encoding attributes cannot be read.")
    sys.exit(2)

for module_name in module_paths:
    module_path = os.path.join("..", module_name)
    result = subprocess.run(
        [git, "-C", module_path, "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False)
    if result.returncode != 0 or os.path.realpath(result.stdout.strip()) != os.path.realpath(module_path):
        print("Error! catalog submodule is not an initialized Git worktree:", module_name)
        sys.exit(2)

report = Report()

for module_name in module_paths:
    module_path = os.path.join("..", module_name)
    print("checking directory", module_path)
    module = Module(module_name)
    report.add_module(module)

    for file_name in catalog_file_names(module_path):
        file_path = os.path.join(module_path, file_name)
        try:
            with open(file_path, "rb") as catalog_file:
                data = catalog_file.read()
            git_encoding = get_effective_git_encoding(git, module_path, file_name)
        except (OSError, RuntimeError) as error:
            report.add_technical_error(file_path, str(error))
            print("Error! could not measure", file_path, str(error))
            continue

        codesets = [match.decode("ascii") for match in RE_CODESET.findall(data)]
        high_bytes = sum(1 for value in data if value >= 0x80)
        kind = "CT" if file_name.lower().endswith(".ct") else "CD"

        module.add_file(CatalogFile(
            file_name,
            kind,
            len(data),
            codesets,
            git_encoding,
            detect_bom(data),
            high_bytes == 0,
            high_bytes,
            is_valid_utf8(data)))

print("-" * 80)

with open("encodingresult.rst", "w", encoding="utf-8") as fh:
    fh.write("===============\n")
    fh.write("Encoding Census\n")
    fh.write("===============\n\n")
    fh.write("This report inventories catalog encoding metadata and raw byte characteristics.\n")
    fh.write("It does not infer an encoding, validate an encoding, or classify a finding as ")
    fh.write("correct or incorrect.\n\n")
    fh.write("``UTF-8 byte-valid`` means only that the complete byte stream can be decoded ")
    fh.write("as UTF-8; it is not an encoding identification.\n\n")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    fh.write("Created on UTC " + now + ".\n\n")
    report.write_rst(fh)

report.write_module_pages("encodingresult")

print("modules:", len(report.modules))
print("catalog files:", sum(len(module.files) for module in report.modules))
print("result: encodingresult.rst")

sys.exit(2 if report.technical_errors else 0)
