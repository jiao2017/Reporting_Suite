#!/usr/bin/env python

from __future__ import print_function
import sys
from source.file_utils import verify_dir

if not ((2, 7) <= sys.version_info[:2] < (3, 0)):
    sys.exit('Python 2, versions 2.7 and higher is supported '
             '(you are running %d.%d.%d)' %
             (sys.version_info[0], sys.version_info[1], sys.version_info[2]))

from os.path import abspath, dirname, realpath, join
from site import addsitedir
source_dir = abspath(dirname(realpath(__file__)))
addsitedir(join(source_dir, 'ext_modules'))

from source.ngscat.summarize_ngscat import summary_reports
from source.bcbio_structure import BCBioStructure
from source.summary import summary_script_proc_params


def main():
    cnf, bcbio_structure = summary_script_proc_params(BCBioStructure.ngscat_name)
    cnf.output_dir = join(bcbio_structure.date_dirpath, BCBioStructure.ngscat_summary_dir)
    summary_reports(cnf, bcbio_structure)


if __name__ == '__main__':
    main()