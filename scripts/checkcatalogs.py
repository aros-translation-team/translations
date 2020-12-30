#!/usr/bin/env python3

# script for checking of the correctness of the catalog files (cd, ct)
# before running the script the submodules must be updated

import re, os, glob, sys

re_path = re.compile("^\s*?path = (.*)$", re.MULTILINE)

re_ct_ver = re.compile(r"""
^\#\#\s+version\s+\$VER:\s+\w+?\.catalog\s+
(\d+)\.\d+\s+\(\d\d\.\d\d\.\d\d\d\d\).*?$
""", re.MULTILINE | re.VERBOSE)

re_ct_lang = re.compile(r"^##\s+language\s+(\w*)$", re.MULTILINE)
re_ct_code = re.compile(r"^##\s+codeset\s+(\d+)$", re.MULTILINE)

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


# read all paths from .gitmodules
module_file = open("../.gitmodules")
module_file_content = module_file.read()
module_path_iter = re_path.finditer(module_file_content)
module_file.close()

for module_path in module_path_iter:
    catalog_path = os.path.join("..", module_path.group(1))
    print("checking directory", catalog_path)
    
    ct_file_names = glob.glob(catalog_path + "/*.ct")
    
    for ct_file_name in ct_file_names:
        print("checking CT file", ct_file_name)
        # get prefix of file (which is the language name)
        ct_file_lang = os.path.basename(ct_file_name)
        
        # blacklist
        if ct_file_lang in ("ahiprefs.ct", "ahi.ct"):
            continue
        
        iana_num, charset, native_language = languages[ct_file_lang]
        
        # check for ## codeset
        # later versions of locale.library might use that to open the right font
        ct_file = open(ct_file_name, encoding="ISO-8859-1")
        ct_file_content = ct_file.read()
        ct_file.close()
        match = (re_ct_code.search(ct_file_content))
        if int(match.group(1)) != iana_num:
            print("Codeset error")
            print("IANA num doesn't match! Is: ",match.group(1), "Required:", iana_num)
            sys.exit(1)
        
        # check ## version
        match = (re_ct_ver.search(ct_file_content))
        if int(match.group(1)) == 0:
            print("Version error")
            print("Version number must be > 0! Is: ",match.group(1))
            sys.exit(1)
   
        # check ## language
        match = (re_ct_lang.search(ct_file_content))
        if match.group(1) != native_language:
            print("Language error")
            print("Language doesn't match! Is: ",match.group(1), "Required:", native_language)
            sys.exit(1)
