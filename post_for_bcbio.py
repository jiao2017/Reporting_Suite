#!/usr/bin/env python
import sys
from optparse import OptionParser
from os.path import join, abspath, dirname

from source.config import Defaults, Config
from source.file_utils import tmpdir
from source.logger import info
from source.main import check_system_resources, check_inputs, check_keys
from source.bcbio_runner import run_on_bcbio_final_dir


if not ((2, 7) <= sys.version_info[:2] < (3, 0)):
    sys.exit('Python 2, versions 2.7 and higher is supported '
             '(you are running %d.%d.%d)' %
             (sys.version_info[0], sys.version_info[1], sys.version_info[2]))


def main():
    description = 'This script runs reporting suite on the bcbio final directory.'

    parser = OptionParser(description=description)
    parser.add_option('-d', '-o', dest='bcbio_final_dir', help='Path to bcbio-nextgen final directory (default is pwd)')
    parser.add_option('-s', '--samples', dest='samples', help='List of samples (default is samples.txt in bcbio final directory)')
    parser.add_option('-b', '--bed', dest='bed', help='BED file')
    parser.add_option('--vcf-suffix', dest='vcf_suffix', help='Suffix to choose VCF file s(mutect, ensembl, freebayes, etc)')
    parser.add_option('--qualimap', dest='qualimap', action='store_true', default=Defaults.qualimap, help='Run QualiMap in the end')

    parser.add_option('-v', dest='verbose', action='store_true', help='Verbose')
    parser.add_option('-t', dest='threads', type='int', help='Number of threads for each process')
    parser.add_option('-w', dest='overwrite', action='store_true', help='Overwrite existing results')

    parser.add_option('--runner', dest='qsub_runner', help='Bash script that takes command line as the 1st argument. This script will be submitted to GRID. Default: ' + Defaults.qsub_runner)
    parser.add_option('--sys-cnf', dest='sys_cnf', default=Defaults.sys_cnf, help='system configuration yaml with paths to external tools and genome resources (see default one %s)' % Defaults.sys_cnf)
    parser.add_option('--run-cnf', dest='run_cnf', default=Defaults.run_cnf, help='run configuration yaml (see default one %s)' % Defaults.run_cnf)

    (opts, args) = parser.parse_args()
    cnf = Config(opts.__dict__, opts.sys_cnf, opts.run_cnf)

    if not cnf.samples:
        cnf.samples = join(cnf.bcbio_final_dir, 'samples.txt')

    info('BCBio "final" dir: ' + cnf.bcbio_final_dir + ' (set with -d)')
    info('Samples: ' + cnf.samples + ' (set with -s)')

    if not check_keys(cnf, ['bcbio_final_dir', 'samples', 'bed', 'vcf_suffix']):
        parser.print_help()
        sys.exit(1)

    if not check_inputs(cnf, file_keys=['samples', 'bed', 'qsub_runner'], dir_keys=['bcbio_final_dir']):
        sys.exit(1)

    info('Capture/amplicons BED file: ' + cnf.bed + ' (set with -b)')
    info('Suffix to choose VCF files: ' + cnf.vcf_suffix + ' (set with --vcf-suffix)')
    info()
    info('*' * 70)

    if opts.qualimap and 'QualiMap' not in cnf.steps:
        cnf.steps.append('QualiMap')

    check_system_resources(cnf, required=['qsub'])

    with tmpdir(cnf):
        run_on_bcbio_final_dir(cnf, cnf.bcbio_final_dir, cnf.samples, cnf.bed, cnf.vcf_suffix)


if __name__ == '__main__':
    main()









