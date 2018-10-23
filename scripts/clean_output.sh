#!/usr/bin/env bash

# Removes all output files and plots

# Abort on error
set -e

# https://stackoverflow.com/questions/59895/
this_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

rm -f ${this_dir}/../output/scan/*.out
rm -f ${this_dir}/../output/distance/*.out
rm -f ${this_dir}/../output/cluster/*.out


