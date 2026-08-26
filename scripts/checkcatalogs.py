#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-

# script for checking of the correctness of the catalog files (cd, ct)
# before running the script the submodules must be updated

import re, os, glob, sys, pytz, shutil, subprocess
from datetime import datetime


################################################################################

class Module(object):
    def __init__(self, name, required_version, version_contract_valid=True):
        self.name = name
        self.required_version = required_version
        self.version_contract_valid = version_contract_valid
        self.language_dict = {} # dictionary with language : available version
        self.present_languages = set()
        self.invalid_languages = set()
        self.unchecked_languages = set()
        self.flexcat_checked_languages = set()
        self.language_warnings = {}

    def get_name(self):
        return self.name
    
    def get_name_as_field(self, len):
        return self.get_name().ljust(len)

    def get_required_version(self):
        return self.required_version
    
    def get_required_version_as_field(self, len):
        if not self.version_contract_valid:
            return ("**invalid**").ljust(len)
        if self.required_version >= 0:
            return str(self.required_version).ljust(len)
        return ("**n/c**").ljust(len)

    def get_version(self, language):
        if language in self.language_dict:
            return self.language_dict[language]
        return -1

    def get_status(self, language):
        if language not in self.present_languages:
            return "MISSING"
        if language in self.invalid_languages or not self.version_contract_valid:
            return "INVALID"
        version = self.get_version(language)
        if version < 0:
            return "INVALID"
        if self.required_version < 0:
            return "NO_VERSION_CONTRACT"
        if version < self.required_version:
            return "STALE"
        if version > self.required_version:
            return "INVALID"
        if language in self.unchecked_languages:
            return "UNCHECKED"
        return "CURRENT"

    def get_version_as_field(self, language, len):
        status = self.get_status(language)
        version = self.get_version(language)
        if status == "MISSING":
            return ("**n/a**").ljust(len)
        if status == "NO_VERSION_CONTRACT":
            return (str(version) + " n/c").ljust(len)
        if status == "CURRENT":
            return str(version).ljust(len)
        if status == "STALE":
            return ("**" + str(version) + "**").ljust(len)
        if status == "UNCHECKED":
            return (str(version) + " ?").ljust(len)
        return ("**invalid**").ljust(len)

    def normalize_language(self, language):
        if language.endswith(".ct"):
            language = language[0:-3]
        return language[0].upper() + language[1:]

    def add_present(self, language):
        self.present_languages.add(self.normalize_language(language))

    def add_version(self, language, version):
        self.language_dict[self.normalize_language(language)] = version

    def add_invalid(self, language):
        self.invalid_languages.add(self.normalize_language(language))

    def add_unchecked(self, language):
        self.unchecked_languages.add(self.normalize_language(language))

    def add_flexcat_checked(self, language):
        self.flexcat_checked_languages.add(self.normalize_language(language))

    def add_warning(self, language, message):
        language = self.normalize_language(language)
        self.language_warnings.setdefault(language, []).append(message)

    def get_warnings(self, language):
        return self.language_warnings.get(language, [])

    def get_languages(self, languages):
        for language in self.present_languages:
            if not language in languages:
                languages.append(language)
                
        
################################################################################
        
class Report(object):
    def __init__(self):
        self.modules = [] # list of Module objects
        self.issues = []

    def add_module(self, module):
        self.modules.append(module)

    def add_issue(self, path, message):
        self.issues.append((path, message))
    
    def write_subtable_rst(self, fh, languages, start, end):
        # create reST table separator
        tablesep = "=" * 59 + " " + "================ "
        for language in range(start, end):
            tablesep += "=" * 14 + " "
        tablesep += "\n"
        
        # print table header
        fh.write(tablesep)
        fh.write("Module" + " " * 54 + "Required Version ")

        for language_index in range(start, end):
            fh.write(f"{languages[language_index]:15}")
        fh.write("\n")
        fh.write(tablesep)

        for module in self.modules:
            fh.write(module.get_name_as_field(60))
            fh.write(module.get_required_version_as_field(17))
            for language_index in range(start, end):
                fh.write(module.get_version_as_field(languages[language_index], 15))
            fh.write("\n")
        
        fh.write(tablesep)
        fh.write("\n\n")

    def get_languages(self):
        languages = []
        for module in self.modules:
            module.get_languages(languages)
        languages.sort()
        return languages

    def get_module_page_name(self, module):
        return os.path.join("checkresult", module.get_name() + ".rst")

    def get_language_status_text(self, module, language):
        status = module.get_status(language)
        if status == "MISSING":
            return "No Translation!"

        version = module.get_version(language)
        text = "version {}".format(version) if version >= 0 else "version unknown"
        warnings = module.get_warnings(language)

        if status == "NO_VERSION_CONTRACT":
            text += ", no version contract"
        elif status == "UNCHECKED" and not warnings:
            text += ", metadata contract unknown"

        if warnings:
            text += ", {} warning{}: {}".format(
                len(warnings), "" if len(warnings) == 1 else "s", "; ".join(warnings))
        return text

    def write_module_summary_rst(self, fh, languages):
        fh.write("Module Summary\n")
        fh.write("==============\n\n")
        fh.write("Translated counts catalog files present; validity and version status are ")
        fh.write("shown on each linked module page.\n\n")
        fh.write(".. list-table::\n")
        fh.write("   :header-rows: 1\n\n")
        fh.write("   * - Module Name\n")
        fh.write("     - Status\n")
        for module in self.modules:
            present = sum(1 for language in languages
                          if module.get_status(language) != "MISSING")
            target = self.get_module_page_name(module).replace(os.sep, "/")
            fh.write("   * - `{} <{}>`_\n".format(module.get_name(), target))
            fh.write("     - {} / {} translated\n".format(present, len(languages)))
        fh.write("\n")

    def write_module_pages(self, output_dir, languages):
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)

        for module in self.modules:
            page_name = os.path.join(output_dir, module.get_name() + ".rst")
            os.makedirs(os.path.dirname(page_name), exist_ok=True)
            with open(page_name, "w") as page:
                title = module.get_name()
                page.write(title + "\n")
                page.write("=" * len(title) + "\n\n")

                if not module.version_contract_valid:
                    page.write("Required version: invalid version contract.\n\n")
                elif module.required_version < 0:
                    page.write("Required version: no version contract.\n\n")
                else:
                    page.write("Required version: {}.\n\n".format(module.required_version))

                page.write(".. list-table::\n")
                page.write("   :header-rows: 1\n\n")
                page.write("   * - Language\n")
                page.write("     - Status\n")
                for language in languages:
                    page.write("   * - {}\n".format(language))
                    page.write("     - {}\n".format(
                        self.get_language_status_text(module, language)))

    def write_summary_rst(self, fh, languages):
        tablesep = "=============== ======= ======= ======= ======= ======= =========== ======= ========= =======\n"
        fh.write(tablesep)
        fh.write("Language        Modules Present Current Stale   Missing No contract Invalid Unchecked FlexCat\n")
        fh.write(tablesep)

        for language in languages:
            counts = {status: 0 for status in
                      ("CURRENT", "STALE", "MISSING", "NO_VERSION_CONTRACT", "INVALID", "UNCHECKED")}
            present = flexcat = 0
            for module in self.modules:
                status = module.get_status(language)
                counts[status] += 1
                if status != "MISSING":
                    present += 1
                if language in module.flexcat_checked_languages:
                    flexcat += 1

            fh.write(f"{language:15}{len(self.modules):8}{present:8}{counts['CURRENT']:8}"
                     f"{counts['STALE']:8}{counts['MISSING']:8}{counts['NO_VERSION_CONTRACT']:12}"
                     f"{counts['INVALID']:8}{counts['UNCHECKED']:10}{flexcat:8}\n")
        fh.write(tablesep)
        fh.write("\n")

    def write_rst(self, fh):
        languages = self.get_languages()

        self.write_module_summary_rst(fh, languages)

        fh.write("Detailed Matrix\n")
        fh.write("===============\n\n")

        # keep generated tables narrow enough to remain readable
        for start in range(0, len(languages), 6):
            self.write_subtable_rst(fh, languages, start, min(start + 6, len(languages)))

        self.write_summary_rst(fh, languages)

        if self.issues:
            fh.write("Issues\n")
            fh.write("======\n\n")
            for path, message in self.issues:
                fh.write(f"* ``{path}``: {message}\n")
            fh.write("\n")
            

################################################################################

# regex for parsing .gitmodules
re_path = re.compile(r"^\s*?path = (.*)$", re.MULTILINE)

# regex for parsing ## version in a CT file
# Some imported catalogs still use D.M.YY dates.
re_ct_ver = re.compile(r"""
^\#\#\s+version\s+\$VER:\s+\S+?\.catalog\s+
(\d+)\.\d+\s+\((\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})\).*?$
""", re.MULTILINE | re.VERBOSE)

# regex for parsing ## language in a CT file
re_ct_lang = re.compile(r"^##\s+language\s+(\w+)$", re.MULTILINE)

# regex for parsing ## codeset in a CT file
re_ct_code = re.compile(r"^##\s+codeset\s+(\d+)$", re.MULTILINE)

# regex for parsing #defin CATALOG_VERSION in catalog_version.h
re_ct_reqver = re.compile(r"^#define\s+CATALOG_VERSION\s+(\d+)$", re.MULTILINE)


languages = {
    "albanian.ct":      (0, "ISO-8859-1", "unknown"),
    "basque.ct":        (0, "ISO-8859-1", "euskara"),
    "catalan.ct":       (0, "ISO-8859-1", "català"),
    "danish.ct":        (0, "ISO-8859-1", "dansk"),
    "dutch.ct":         (0, "ISO-8859-1", "nederlands"),
    "faroese.ct":       (0, "ISO-8859-1", "unknown"),
    "finnish.ct":       (0, "ISO-8859-1", "suomi"),
    "french.ct":        (0, "ISO-8859-1", "français"),
    "german.ct":        (0, "ISO-8859-1", "deutsch"),
    "irish.ct":         (0, "ISO-8859-1", "unknown"),
    "icelandic.ct":     (0, "ISO-8859-1", "unknown"),
    "italian.ct":       (0, "ISO-8859-1", "italiano"),
    "norwegian.ct":     (0, "ISO-8859-1", "norsk"),
    "portuguese.ct":    (0, "ISO-8859-1", "português"),
    "spanish.ct":       (0, "ISO-8859-1", "español"),
    "swedish.ct":       (0, "ISO-8859-1", "svenska"),
    "bosnian.ct":       (5, "ISO-8859-2", "unknown"),
    "croatian.ct":      (5, "Windows-1252", "hrvatski"), # Windows-1252 or ISO-8859-2 ?
    "czech.ct":         (5, "ISO-8859-2", "czech"),
    "hungarian.ct":     (5, "ISO-8859-2", "magyar"),
    "rumanian.ct":      (5, "ISO-8859-2", "unknown"),
    "slovak.ct":        (5, "ISO-8859-2", "unknown"),
    "slovene.ct":       (5, "ISO-8859-2", "unknown"),
    "polish.ct":        (5, "ISO-8859-2", "polski"), # AmigaPL or ISO-8859-2 ?
    "maltese.ct":       (6, "ISO-8859-3", "unknown"),
    "estonian.ct":      (7, "ISO-8859-4", "unknown"),
    "latvian.ct":       (7, "ISO-8859-4", "unknown"),
    "lithuanian.ct":    (7, "ISO-8859-4", "unknown"),
    "bulgarian.ct":     (8, "ISO-8859-5", "unknown"),
    "macedonian.ct":    (8, "ISO-8859-5", "unknown"),
    "serbian.ct":       (8, "CP852", "srpski"), # Latin script, CP852 (Amiga) byte mapping
    "ukrainian.ct":     (8, "ISO-8859-5", "unknown"),
    "turkish.ct":       (12, "ISO-8859-9", "türkçe"),
    "russian.ct":       (2104, "windows-1251", "russian")
}

# for colored output
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

################################################################################

def get_required_version(catalog_path, report):
    retval = -1
    required_version_filename = os.path.join(catalog_path, "catalog_version.h")
    if os.path.exists(required_version_filename):
        required_version_file = open(required_version_filename, "r")
        required_version_content = required_version_file.read()
        required_version_file.close()

        match = re_ct_reqver.search(required_version_content)
        if not match:
            report.add_issue(required_version_filename,
                             "CATALOG_VERSION definition is missing or invalid")
            print(bcolors.FAIL, "Invalid catalog version contract in",
                  required_version_filename, bcolors.ENDC)
            return -1, False
        retval = match.group(1)
    else:
        print(bcolors.WARNING, "Warning! catalog_version.h doesn't exist. No version check!", bcolors.ENDC)

    return int(retval), True


def valid_catalog_date(day, month, year):
    year = int(year)
    if year < 100:
        year += 1900 if year >= 80 else 2000
    if year < 1980 or year > 2050:
        return False
    try:
        datetime(year, int(month), int(day))
    except ValueError:
        return False
    return True

################################################################################

check_with_flexcat = True # needs tool flexcat in search path
flexcat = shutil.which("flexcat") if check_with_flexcat else None

# read all paths from .gitmodules
module_file_name = "../.gitmodules"
if not os.path.exists(module_file_name):
    print(bcolors.FAIL, "Error! ../.gitmodules doesn't exist.", bcolors.ENDC)
    sys.exit(2)

module_file = open(module_file_name, "r")
module_file_content = module_file.read()
module_paths = [match.group(1) for match in re_path.finditer(module_file_content)]
module_file.close()
if not module_paths:
    print(bcolors.FAIL, "Error! No catalog paths found in ../.gitmodules.", bcolors.ENDC)
    sys.exit(2)

# An incomplete checkout cannot produce a meaningful missing-catalog census.
missing_module_paths = [path for path in module_paths
                        if not os.path.isdir(os.path.join("..", path))]
if missing_module_paths:
    for path in missing_module_paths:
        print(bcolors.FAIL, "Error! catalog submodule isn't available:", path, bcolors.ENDC)
    sys.exit(2)

if check_with_flexcat and not flexcat:
    print(bcolors.WARNING,
          "Warning! flexcat isn't available. FlexCat validation will be skipped.",
          bcolors.ENDC)

report = Report()

# loop through all submodules
for module_name in module_paths:
    catalog_path = os.path.join("..", module_name)
    print("checking directory", catalog_path)

    required_version, version_contract_valid = get_required_version(catalog_path, report)
    module = Module(module_name, required_version, version_contract_valid)
    report.add_module(module)

    # loop through all CT files in a directory
    for ct_file_name in glob.glob(catalog_path + "/*.ct"):
        ct_file_lang = os.path.basename(ct_file_name)

        # Non-translation helper/template files are not languages.
        if ct_file_lang in ("ahiprefs.ct", "ahi.ct", "empty.ct"):
            continue

        module.add_present(ct_file_lang)
        language_contract = languages.get(ct_file_lang)
        invalid = False
        details = []

        # we must specify the encoding because Python 3 defaults to UTF-8
        ct_file = open(ct_file_name, "r", encoding="ISO-8859-1")
        ct_file_content = ct_file.read()
        ct_file.close()

        # check for ## codeset
        match = re_ct_code.search(ct_file_content)
        if not match:
            invalid = True
            details.append("missing ## codeset")
        elif language_contract and int(match.group(1)) != language_contract[0]:
            invalid = True
            details.append("codeset {} != expected {}".format(match.group(1), language_contract[0]))

        # check ## version
        match = re_ct_ver.search(ct_file_content)
        if not match:
            invalid = True
            vversion = -1
            details.append("missing or unsupported ## version")
        else:
            vversion = int(match.group(1))
            module.add_version(ct_file_lang, vversion)
            if vversion == 0:
                invalid = True
                details.append("catalog version must be > 0")
            if not valid_catalog_date(match.group(2), match.group(3), match.group(4)):
                invalid = True
                details.append("invalid catalog date")

        # check ## language
        match = re_ct_lang.search(ct_file_content)
        if not match:
            invalid = True
            details.append("missing ## language")
        elif language_contract and match.group(1) != language_contract[2]:
            invalid = True
            details.append("language {} != expected {}".format(match.group(1), language_contract[2]))

        if not language_contract:
            module.add_unchecked(ct_file_lang)
            module.add_warning(ct_file_lang, "language metadata contract is unknown")
            report.add_issue(ct_file_name, "language metadata contract is unknown")

        if not version_contract_valid:
            invalid = True
            details.append("module version contract is invalid")

        if not invalid and required_version >= 0 and vversion > required_version:
            invalid = True
            details.append("catalog version {} > required {}".format(vversion, required_version))

        # FlexCat can still validate a catalog without a version contract.
        if not invalid and flexcat and (required_version == vversion or required_version < 0):
            cd_file_names = glob.glob(catalog_path + "/*.cd")
            if len(cd_file_names) == 1:
                module.add_flexcat_checked(ct_file_lang)
                res = subprocess.run(
                    [flexcat, cd_file_names[0], ct_file_name, "catalog", "dummy.catalog"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False).returncode
                if res != 0:
                    invalid = True
                    details.append("flexcat returned {}".format(res))

        if invalid:
            module.add_invalid(ct_file_lang)
            for detail in details:
                module.add_warning(ct_file_lang, detail)
            detail = "; ".join(details)
            report.add_issue(ct_file_name, detail)
            print(bcolors.FAIL, "INVALID", ct_file_name, detail, bcolors.ENDC)
        elif module.get_status(module.normalize_language(ct_file_lang)) == "STALE":
            module.add_warning(ct_file_lang,
                               "stale; required {}".format(required_version))
            print(bcolors.WARNING, "STALE", ct_file_name,
                  "Is:", vversion, "Required:", required_version, bcolors.ENDC)


print("-" * 80)

# create the reST file
with open("checkresult.rst", "w") as fh:
    fh.write("=============\n")
    fh.write("Catalog Check\n")
    fh.write("=============\n\n")
    fh.write("The tables compare the catalog version requested by each module with\n")
    fh.write("the versions present in its \\*.ct translation files.\n\n")
    fh.write("Cell markers:\n\n")
    fh.write("+ n/a: translation catalog isn't available\n")
    fh.write("+ n/c: module has no catalog_version.h version contract\n")
    fh.write("+ ?: language metadata is not known to this checker\n")
    fh.write("+ highlighted value: stale or invalid catalog\n\n")
    fh.write("FlexCat validation: {}.\n".format(
        "available" if flexcat else "unavailable; skipped"))
    fh.write("The FlexCat summary column counts catalogs actually checked with FlexCat; ")
    fh.write("it is independent of version-contract status.\n\n")
    
    now = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
    fh.write("Created on UTC " + now + ".\n\n")

    report.write_rst(fh)

report.write_module_pages("checkresult", report.get_languages())


has_invalid = any(
    module.get_status(language) == "INVALID"
    for module in report.modules for language in module.present_languages)
sys.exit(1 if has_invalid else 0)
