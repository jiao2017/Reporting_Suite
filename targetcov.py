#!/usr/bin/env python

from __future__ import print_function
import sys
import os

if not ((2, 7) <= sys.version_info[:2] < (3, 0)):
    sys.exit('Python 2, versions 2.7 and higher is supported '
             '(you are running %d.%d.%d)' %
             (sys.version_info[0], sys.version_info[1], sys.version_info[2]))

from os.path import join, expanduser, splitext, basename, isdir
from source.targetcov.cov import log, run_cov_report, \
    intersect_bed, get_target_depth_analytics, run_header_report

#downlad hg19.genome
#https://github.com/arq5x/bedtools/tree/master/genomes

#TODO
# check on the input file format
# format result and calculation to the 2 decimal places on the header report    .00
# multi - sample report                                                         header only
#       sample1 sample2
#number 2       3
#bases  10      20

# check if samtools and bedtools exist
# log file
# yaml
# take folder name as a sample name (first column on the report)
# give user an option to select type of the report to run ????
from shutil import rmtree
from source.main import common_main, check_system_resources, load_genome_resources
from source.utils import verify_file, critical, step_greetings
from source.targetcov import cov


REPORT_TYPES = 'summary,amplicons,exons,genes'


def main(args):
    cnf, options = common_main(
        'targetcov',
        opts=[
            (['--bam'], 'align.bam', {
                'dest': 'bam',
                'help': 'used to generate some annotations by GATK'}),

            (['--capture', '--bed'], 'capture.bed', {
                'dest': 'capture',
                'help': ''}),

            (['--genes', '--genes'], 'genes.bed', {
                'dest': 'genes',
                'help': ''}),

            (['--exons', '--exons'], 'exons.bed', {
                'dest': 'exons',
                'help': ''}),

            (['--padding'], '250', {
                'dest': 'padding',
                'help': '',
                'default': 250}),

            (['--reports'], '', {
                'dest': 'reports',
                'help': '--reports ' + REPORT_TYPES,
                'default': REPORT_TYPES}),
        ])

    check_system_resources(cnf, ['samtools', 'bedtools'])
    load_genome_resources(cnf, ['chr_lengths', 'genes', 'exons'])

    genes_bed = options.get('genes') or cnf.get('genes') or cnf['genome'].get('genes')
    exons_bed = options.get('exons') or cnf.get('exons') or expanduser(cnf['genome'].get('exons'))
    chr_len_fpath = cnf.get('chr_lengths') or cnf['genome'].get('chr_lengths')
    capture_bed = options.get('capture') or cnf.get('capture')
    bam = options.get('bam') or cnf.get('bam')

    if not genes_bed:
        critical('Specify sorted genes bed file in system info or in run info.')
    if not exons_bed:
        critical('Specify sorted exons bed file in system info or in run info.')
    if not chr_len_fpath:
        critical('Specify chromosome lengths for the genome'
                 ' in system info or in run info.')
    if not bam:
        critical('Specify bam file by --bam option or in run_config.')
    if not capture_bed:
        critical('Specify capture file by --capture option or in run_config.')

    print('using genes ' + genes_bed)
    print('using exons ' + exons_bed)
    print('using chr lengths ' + chr_len_fpath)
    print('using bam ' + bam)
    print('using capture panel ' + capture_bed)

    genes_bed = expanduser(genes_bed)
    exons_bed = expanduser(exons_bed)
    chr_len_fpath = expanduser(chr_len_fpath)
    bam = expanduser(bam)
    capture_bed = expanduser(capture_bed)

    if not verify_file(genes_bed): exit(1)
    if not verify_file(exons_bed): exit(1)
    if not verify_file(chr_len_fpath): exit(1)
    if not verify_file(bam): exit(1)
    if not verify_file(capture_bed): exit(1)

    depth_threshs = cnf['depth_thresholds']
    padding = options.get('padding', cnf.get('padding', 250))
    output_dir = options.get('output_dir') or cnf.get('output_dir') or os.getcwd()
    print('writing to output dir ' + output_dir)
    output_dir = expanduser(output_dir)

    work_dir = join(output_dir, 'work')
    if isdir(work_dir):
        rmtree(work_dir)
    os.makedirs(work_dir)

    print('')

    #########################################
    sample_name, _ = splitext(basename(bam))

    summary_report_fpath = None
    amplicons_report_fpath = None
    exons_report_fpath = None

    if 'summary' or 'amplicons' in options['reports']:
        log('Calculation of coverage statistics for the regions in the input BED file...')
        bases_per_depth_per_amplicon, max_depth, total_bed_size = \
            get_target_depth_analytics(capture_bed, bam, depth_threshs)

        if 'summary' in options['reports']:
            step_greetings('Target coverage summary report')
            summary_report_fpath = join(output_dir, sample_name + '.summary.report')
            run_header_report(
                summary_report_fpath, output_dir, work_dir,
                capture_bed, bam, chr_len_fpath,
                depth_threshs, padding,
                bases_per_depth_per_amplicon[-1], max_depth, total_bed_size)

        if 'amplicons' in options['reports']:
            step_greetings('Coverage report for the input BED file regions')
            amplicons_report_fpath = join(output_dir, sample_name + '.amplicons.report')
            run_cov_report(amplicons_report_fpath, sample_name, depth_threshs, bases_per_depth_per_amplicon)

        if 'exons' in options['reports']:
            if not genes_bed or not exons_bed:
                if options['reports'] == 'exons':
                    exit('Error: no genes and exons specified for the genome in system config, '
                         'cannot run per-exon report.')
                if not genes_bed or not exons_bed:
                    print('Warning: no genes and exons specified for the genome in system config, '
                          'cannot run per-exon report.', file=sys.stderr)
            else:
                log('Getting the gene regions that intersect with our capture panel.')
                bed = intersect_bed(genes_bed, capture_bed, work_dir)
                log('Getting the exons of the genes.')
                bed = intersect_bed(exons_bed, bed, work_dir)

                log('Calculation of coverage statistics for exons of the genes ovelapping with the input regions...')
                bases_per_depth_per_amplicon, _, _ = get_target_depth_analytics(bed, bam, depth_threshs)

                exons_report_fpath = join(output_dir, sample_name + '.exons.report')
                run_cov_report(exons_report_fpath, sample_name, depth_threshs, bases_per_depth_per_amplicon)

    print('')
    print('*' * 70)
    if summary_report_fpath:
        log('Summary report: ' + summary_report_fpath)
    if amplicons_report_fpath:
        log('Region coverage report: ' + amplicons_report_fpath)
    if exons_report_fpath:
        log('Exons coverage report: ' + exons_report_fpath)


if __name__ == '__main__':
    main(sys.argv)