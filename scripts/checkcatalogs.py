#!/usr/bin/env python3

# script for checking of the correctness of the catalog files (cd, ct)
# before running the script the submodules must be updated

import re, os, glob, sys

# regex for parsing .gitmodules
re_path = re.compile("^\s*?path = (.*)$", re.MULTILINE)

# regex for parsing ## version in a CT file
re_ct_ver = re.compile(r"""
^\#\#\s+version\s+\$VER:\s+\w+?\.catalog\s+
(\d+)\.\d+\s+\((\d\d)\.(\d\d)\.(\d\d\d\d)\).*?$
""", re.MULTILINE | re.VERBOSE)

# regex for parsing ## language in a CT file
re_ct_lang = re.compile(r"^##\s+language\s+(\w+)$", re.MULTILINE)

# regex for parsing ## codeset in a CT file
re_ct_code = re.compile(r"^##\s+codeset\s+(\d+)$", re.MULTILINE)

# regex for parsing #defin CATALOG_VERSION in catalog_version.h
re_ct_reqver = re.compile(r"^#define\s+CATALOG_VERSION\s+(\d+)$", re.MULTILINE)


languages = {
    "albanian.ct":      (0, "ISO-8859-1", "unknown"),
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
    "croatian.ct":      (5, "ISO-8859-2", "hrvatski"),
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
    "serbian.ct":       (8, "ISO-8859-5", "srpski"),
    "ukrainian.ct":     (8, "ISO-8859-5", "unknown"),
    "turkish.ct":       (12, "ISO-8859-9", "türkçe"),
    "russian.ct":       (2104, "WINDOWS-1251", "russian")
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



def get_required_version(catalog_path):
    retval = -1
    
    required_version_filename = os.path.join(catalog_path, "catalog_version.h")
    if os.path.exists(required_version_filename):
        required_version_file =  open(required_version_filename, "r")
        required_version_content = required_version_file.read()
        required_version_file.close()

        match = re_ct_reqver.search(required_version_content)
        retval = match.group(1)

    else:
        print(bcolors.WARNING, "Warning! catalog_version.h doesn't exist. No version check!", bcolors.ENDC)

    return int(retval)


# read all paths from .gitmodules
module_file = open("../.gitmodules", "r")
module_file_content = module_file.read()
module_path_iter = re_path.finditer(module_file_content)
module_file.close()

# loop through all submodules
for module_path in module_path_iter:
    catalog_path = os.path.join("..", module_path.group(1))
    print("checking directory", catalog_path)

    required_version = get_required_version(catalog_path)
    
    ct_file_names = glob.glob(catalog_path + "/*.ct")
    
    # loop through all CT files in a directory
    for ct_file_name in ct_file_names:
        # print("checking CT file", ct_file_name)
        # get base of file (which is the language name including .ct)
        ct_file_lang = os.path.basename(ct_file_name)
        
        # blacklist
        if ct_file_lang in ("ahiprefs.ct", "ahi.ct"):
            continue
        
        iana_num, charset, native_language = languages[ct_file_lang]
        
        # check for ## codeset
        # later versions of locale.library might use that to open the right font
        # we must specify the encoding because Python 3 defaults to UTF-8
        ct_file = open(ct_file_name, "r", encoding="ISO-8859-1")
        ct_file_content = ct_file.read()
        ct_file.close()
        match = re_ct_code.search(ct_file_content)
        if int(match.group(1)) != iana_num:
            print("Codeset error in file", ct_file_name)
            print("IANA num doesn't match! Is: ", match.group(1), "Required:", iana_num)
            sys.exit(1)
        
        # check ## version
        match = re_ct_ver.search(ct_file_content)
        vversion = int(match.group(1))
        if vversion == 0:
            print("Version error in file", ct_file_name)
            print("Version number must be > 0! Is: ", match.group(1))
            sys.exit(1)
            
        vday = int(match.group(2))
        vmonth = int(match.group(3))
        vyear = int(match.group(4))
        if vday < 1 or vday > 31 or vmonth < 1 or vmonth > 12 \
            or vyear < 1980 or vyear > 2050:
            print("Version error in file", ct_file_name)
            print("Invalid values for date! Is: ",
                match.group(2), match.group(3), match.group(4))
            sys.exit(1)

        # check ## language
        match = re_ct_lang.search(ct_file_content)
        if match.group(1) != native_language:
            print("Language error in file", ct_file_name)
            print("Language doesn't match! Is: ", match.group(1), "Required:", native_language)
            sys.exit(1)

        # check required version
        if required_version !=-1:
            if required_version != vversion:
                print(bcolors.WARNING, "Requird version mismatch in file", ct_file_name)
                print("Is:", vversion, "Required:", required_version, bcolors.ENDC)
