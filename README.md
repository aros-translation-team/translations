Please Note:
============

Creating/Editing Catalog Files
------------------------------

For information on naming descriptors, and the encoding to use - please see the [![Wiki](https://github.com/aros-translation-team/translations/wiki)](https://github.com/aros-translation-team/translations/wiki)

Adding the Catalog Submodules
-----------------------------

The proccess for adding a new catalog-translation submodule to the main AROS respository, aswell as the translations repository is the same.

If the original catalogs where located at e.g 'workbench/tools/"my_tool"/catalogs', you should firstly create a repository called "my_tool" in the translation team organization. Use this to store the actual catalog descriptors, and mmakefile.src to create the catalogs.

Once the "my tool" repository is set up, add it to the main repositories as follows -:
  
* cd "repository path"
* cd "path to location the submodule should be attached under"
  
In our example case this would be 'cd workbench/tools/"my_tool"'.
  
* git submodule add https://github.com/aros-translation-team/"my_tool".git catalogs

Finaly commit and push the changes.

Updating the Submodules
-----------------------

to synchronise the repository with the individual catalog submodules, use ...

* git submodule update --remote --merge

Updating the AROS Developer mirror
----------------------------------

to push changes from the translation teams repository, to the official developer team mirror, please do the following...

Initial Setup:

* git clone --mirror https://github.com/aros-translation-team/translations.git
* cd translations.git
* git remote set-url --push origin https://github.com/aros-development-team/translations.git

Push changes in the Mirror:

* git fetch -p origin
* git push --mirror
