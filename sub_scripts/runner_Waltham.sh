#!/bin/bash
#set -x
date >&2
hostname >&2
source /etc/profile.d/modules.sh >&2
module unload python >&2 2>&2
module unload gcc gcc/4.7 >&2 2>&2
module load gcc/4.9.2 sge java perl bcbio bedtools/2.24.0 bedops >&2 2>&2
echo >&2
echo "$2" >&2
echo >&2
echo >&2
eval $2
echo >&2
date >&2
touch $1 >&2
#set +x
