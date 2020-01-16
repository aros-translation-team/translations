Please Note:
============

Creating/Editing Catalog Files
------------------------------

For information on naming descriptors, and the encoding to use - please see the [!(Wiki)(https://github.com/aros-translation-team/translations/wiki)](https://github.com/aros-translation-team/translations/wiki)

Updating the submodules
-----------------------

to synchronise the repository with the individual catalog submodules, use ...

* git submodule update --remote --merge

Updating the AROS developer mirror
----------------------------------

to push changes from the translation teams repository, to the official developer team mirror, please do the following...

Initial Setup:

* git clone --mirror https://github.com/aros-translation-team/translations.git
* cd translations.git
* git remote set-url --push origin https://github.com/aros-development-team/translations.git

Push changes in the Mirror:

* git fetch -p origin
* git push --mirror
