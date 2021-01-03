#!/bin/bash

# enable command echo
set -x

git checkout master
git pull

# ensure that the new submodules exist in .gitmodules
git submodule init

# update the submodules
git submodule update --remote --merge

# checkout master so that we can work on them
git submodule foreach git checkout master
