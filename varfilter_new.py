#!/usr/bin/env python
import sys

if not ((2, 7) <= sys.version_info[:2] < (3, 0)):
    sys.exit('Python 2, versions 2.7 and higher is supported '
             '(you are running %d.%d.%d)' %
             (sys.version_info[0], sys.version_info[1], sys.version_info[2]))

import shutil
import os
from os.path import basename, join, isfile

from source.main import read_opts_and_cnfs, check_system_resources
from source.config import Defaults
from source.logger import info
from source.utils_from_bcbio import add_suffix
from source.runner import run_one
from source.variants.filtering import run_filtering
from varfilter import remove_previous_filter_rejects


def main():
    defaults = Defaults.variant_filtering

    cnf = read_opts_and_cnfs(
        description=
        'The program filters an annotated VCF file by SnpEff using dbSNP and COSMIC, '
        'setting the value of the FILTER column.\n'
        '\n'
        'A novel variant (non-dbSNP, non-COSMIC) is considered false positive '
        'if all three conditions (-r -f -n) are met. False positive variants are '
        'annotated PASS in column FILTER if the conditions are satisfied, or with '
        'other value otherwise, where the value is ;-separated list of failed criteria.',

        extra_opts=[
            (['--vcf', '--var'], dict(
                dest='vcf',
                help='Annotated variants to filter'
            )),

            (['--vardict'], dict(
                dest='vardict_mode',
                action='store_true',
                default=False,
                help='Vardict mode: assumes Vardict annotations.'
            )),

            (['-i', '--impact'], dict(
                dest='impact',
                help='Effect impact. Default: ' + defaults['impact']
            )),

            (['-b', '--bias'], dict(
                dest='bias',
                action='store_true',
                help='Novel or dbSNP variants with strand bias "2;1" or "2;0" '
                     'and AF < 0.3 will be considered as false positive.'
            )),

            (['-M', '--mean-mq'], dict(
                dest='mean_mq',
                type='float',
                help='The filtering mean mapping quality score for variants. '
                     'The raw variant will be filtered if the mean mapping quality '
                     'score is less then specified. Default %d' % defaults['mean_mq'],
            )),

            (['-D', '--filt-depth'], dict(
                dest='filt_depth',
                type='int',
                help='The filtering total depth. The raw variant will be filtered '
                     'on first place if the total depth is less then [filt_depth]. '
                     'Default %d' % defaults['filt_depth'],
            )),

            (['-V', '--mean-vd'], dict(
                dest='mean_vd',
                type='int',
                help='The filtering variant depth. Variants with depth < [mean_vd] will '
                     'be considered false positive. Default is %d (meaning at least %d reads '
                     'are needed for a variant)' % (defaults['mean_vd'], defaults['mean_vd'])
            )),

            (['-m', '--maf'], dict(
                dest='maf',
                type='float',
                help='If there is MAF with frequency, it will be considered dbSNP '
                     'regardless of COSMIC. Default MAF is %f' % defaults['maf'],
            )),

            (['-r', '--fraction'], dict(
                dest='fraction',
                type='float',
                help='When a novel variant is present in more than [fraction] '
                     'of samples and mean allele frequency is less than [freq], '
                     'it\'s considered as likely false positive. Default %f. '
                     'Used with -f and -n' % defaults['fraction'],
            )),

            (['-f', '--freq'], dict(
                dest='freq',
                type='float',
                help='When the average allele frequency is also below the [freq], '
                     'the variant is considered likely false positive. '
                     'Default %f. Used with -r and -n' % defaults['freq'],
            )),

            (['-n'], dict(
                dest='sample_cnt',
                type='int',
                help='When the variant is detected in greater or equal [sample_cnt] '
                     'samples, the variant is considered likely false positive. '
                     'Default %d. Used with -r and -f' % defaults['sample_cnt'],
            )),

            (['-R', '--max-ratio'], dict(
                dest='max_ratio',
                type='float',
                help='When a variant is present in more than [fraction] of samples, '
                     'and AF < 0.3, it\'s considered as likely false positive, '
                     'even if it\'s in COSMIC. Default %f.' % defaults['max_ratio'],
            )),

            (['-F', '--min-freq'], dict(
                dest='min_freq',
                type='float',
                help='When individual allele frequency < feq for variants, '
                     'it was considered likely false poitives. '
                     'Default %f' % defaults['min_freq'],
            )),

            (['-p'], dict(
                dest='min_p_mean',
                type='int',
                help='The minimum mean position in reads for variants.'
                     'Default %d bp' % defaults['min_p_mean'],
            )),

            (['-q'], dict(
                dest='min_q_mean',
                type='float',
                help='The minimum mean base quality phred score for variant.'
                     'Default %d' % defaults['min_q_mean'],
            )),

            (['-P'], dict(
                dest='filt_p_mean',
                type='int',
                help='The filtering mean position in reads for variants. '
                     'The raw variant will be filtered on first place if the mean '
                     'posititon is less then [filt_p_mean]. '
                     'Default %d bp' % defaults['filt_p_mean'],
            )),

            (['-Q'], dict(
                dest='filt_q_mean',
                type='float',
                help='The filtering mean base quality phred score for variants. '
                     'The raw variant will be filtered on first place  '
                     'if the mean quality is less then [filt_q_mean]. '
                     'Default %f' % defaults['filt_q_mean'],
            )),

            (['--sn'], dict(
                dest='signal_noise',
                type='int',
                help='Signal/noise value. Default %d' % defaults['signal_noise']
            )),

            (['-u'], dict(
                dest='count_undetermined',
                action='store_false',
                help='Undeteremined won\'t be counted for the sample count.'
            )),

            (['-c', '--control'], dict(
                dest='control',
                help='The control sample name. Any novel or COSMIC variants passing all '
                     'above filters but also detected in Control sample will be deemed '
                     'considered false positive. Use only when there\'s control sample.'
            )),
        ],
        required_keys=['vcf'],
        file_keys=['vcf'],
        key_for_sample_name='vcf')

    check_system_resources(cnf, required=['java'], optional=[])

    for opt_key in cnf.keys():
        if opt_key in cnf['variant_filtering'].keys():
            cnf['variant_filtering'][opt_key] = cnf[opt_key]
            del cnf[opt_key]

    run_one(cnf, process_one, finalize_one)

    if not cnf['keep_intermediate']:
        shutil.rmtree(cnf['work_dir'])


def finalize_one(cnf, filtered_vcf_fpath):
    if filtered_vcf_fpath:
        info('Saved filtered VCF to ' + filtered_vcf_fpath)


def process_one(cnf):
    vcf_fpath = cnf['vcf']
    filt_cnf = cnf['variant_filtering']

    vcf_fpath = remove_previous_filter_rejects(cnf, vcf_fpath)

    vcf_fpath = run_filtering(cnf, filt_cnf, vcf_fpath)

    final_vcf_fname = add_suffix(basename(cnf['vcf']), 'filt')
    final_vcf_fpath = join(cnf['output_dir'], final_vcf_fname)
    if isfile(final_vcf_fpath):
        os.remove(final_vcf_fpath)
    shutil.copyfile(vcf_fpath, final_vcf_fpath)

    return [final_vcf_fpath]


if __name__ == '__main__':
    main()



