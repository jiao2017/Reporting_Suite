#!/usr/bin/env python

import sys

if not ((2, 7) <= sys.version_info[:2] < (3, 0)):
    sys.exit('Python 2, versions 2.7 and higher is supported '
             '(you are running %d.%d.%d)' %
             (sys.version_info[0], sys.version_info[1], sys.version_info[2]))

from source.main import read_opts_and_cnfs, check_system_resources, load_genome_resources
from source.runner import run_one
from source.utils import info, get_java_tool_cmdline, intermediate_fname, call, iterate_file


def main(args):
    required_keys = ['vcf']
    optional_keys = []

    cnf = read_opts_and_cnfs(
        extra_opts=[
            (['--var', '--vcf'], 'variants.vcf', {
             'dest': 'vcf',
             'help': 'variants to annotate'}),

            (['--expression'], '', {
             'dest': 'variant_filtering_expression',
             'help': 'filtering line for snpsift'}),
        ],
        required_keys=required_keys,
        optional_keys=optional_keys)

    check_system_resources(cnf, ['snpsift'])
    load_genome_resources(cnf)

    run_one(cnf, required_keys, optional_keys, process_one, finalize_one)


def filter_variants(cnf, vcf_fpath):
    executable = get_java_tool_cmdline(cnf, 'snpsift')
    expression = cnf['variant_filtering_expression'] or ''

    info('')
    info('*' * 70)
    vcf_fpath = iterate_file(cnf, vcf_fpath, lambda l: l.replace('\tPASS\t', '\t\t'))

    cmdline = '{executable} filter -i PASS -f {vcf_fpath} "{expression}"'.format(**locals())
    filtered_fpath = intermediate_fname(cnf, vcf_fpath, 'filtered')
    call(cnf, cmdline, filtered_fpath, overwrite=True)
    return filtered_fpath


def process_one(cnf, *inputs):
    anno_vcf_fpath = filter_variants(cnf, *inputs)
    return [anno_vcf_fpath]


def finalize_one(cnf, filtered_vcf_fpath):
    if filtered_vcf_fpath:
        info('Saved filtered VCF to ' + filtered_vcf_fpath)


if __name__ == '__main__':
    main(sys.argv[1:])