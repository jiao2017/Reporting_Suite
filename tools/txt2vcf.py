#!/usr/bin/env python
# noinspection PyUnresolvedReferences

import os
import re
import sys
from collections import OrderedDict
from optparse import OptionParser
from os.path import join, basename

import bcbio_postproc
from source.bcbio.bcbio_structure import BCBioStructure, process_post_bcbio_args
from source.clinical_reporting.clinical_parser import get_record_from_vcf, parse_mutations, \
    get_mutations_fpath_from_bs
from source.clinical_reporting.combine_reports import get_rejected_mutations_fpaths
from source.file_utils import safe_mkdir, adjust_path, add_suffix, file_transaction, verify_file, open_gzipsafe
from source.logger import info, warn
from source.prepare_args_and_cnf import add_cnf_t_reuse_prjname_donemarker_workdir_genome_debug
from source.variants import vcf_parser as vcf
from source.variants.vcf_processing import bgzip_and_tabix

filter_descriptions_dict = {
    'not canonical transcript': 'Transcript',
    'PASS=False': 'REJECT',
    'PROTEIN_PROTEIN_CONTACT': 'PROT_PROT',
    'MSI fail': 'MSI',
    'snp in snpeffect_export_polymorphic': 'PolymorphicSNP',
    'common SNP': 'SNP',
    'not act': 'Not_act',
    'not_known': 'Not_known',
    'unknown': 'Unknown',
    'act germline': 'Act_germ',
    'act somatic': 'Act_som',
    'SYNONYMOUS': 'Synonymous',
    'not ClnSNP_known': 'Not_ClnSNP_known',
    'in filter_common_snp': 'filterSNP',
    'in filter_artifacts': 'Artifact',
    'AF < 0.35': 'f0.35',
    'clnsig dbSNP': 'clnsig',
    'in snpeff_snp': 'SnpEff_snp',
    'dbSNP': 'dbSNP',
    'in INTRON': 'Intron',
    'no aa_ch\g': 'no_aa_chg',
    'SPLICE': 'Splice',
    'UPSTREAM': 'Upstrean',
    'DOWNSTREAM': 'Downstream',
    'INTERGENIC': 'Intergenic',
    'INTRAGENIC': 'Intragenic',
    'not UTR /CODON': 'not_UTR_/Codon',
    'NON_CODING': 'Non_coding',
    'fclass=NON_CODING': 'Non_coding',
    'variants occurs after last known critical amino acid': 'CritAA',
    'blacklist gene': 'Blacklist',
}

filter_patterns_dict = {
    re.compile('depth < (\d+)'): 'd',
    re.compile('VD < (\d+)'): 'v',
    re.compile('AF < ([0-9.]+)'): 'f',
    re.compile('all GMAF > ([0-9.]+)'): 'GMAF',
}


filt_vcf_ending = '.filt.vcf'


def main():
    info(' '.join(sys.argv))
    info()
    description = 'This script converts Vardict TXT file to VCF.'

    parser = OptionParser(description=description, usage='Usage: ' + basename(__file__) + ' [-o Output_directory -c Var_caller_name] Project_directory')
    add_cnf_t_reuse_prjname_donemarker_workdir_genome_debug(parser)
    parser.add_option('--log-dir', dest='log_dir', default='-')
    parser.add_option('-c', '--caller', dest='caller_name', default='vardict')
    parser.add_option('-o', dest='output_dir', help='Output directory.')

    cnf, bcbio_project_dirpaths, bcbio_cnfs, final_dirpaths, tags, is_wgs_in_bcbio, is_rnaseq \
        = process_post_bcbio_args(parser)

    if not bcbio_project_dirpaths:
        parser.print_help(file=sys.stderr)
        sys.exit(1)

    bcbio_structures = []
    for bcbio_project_dirpath, bcbio_cnf, final_dirpath in zip(
            bcbio_project_dirpaths, bcbio_cnfs, final_dirpaths):
        bs = BCBioStructure(cnf, bcbio_project_dirpath, bcbio_cnf, final_dirpath)
        bcbio_structures.append(bs)

    cnf.work_dir = cnf.work_dir or adjust_path(join(cnf.output_dir, 'work'))
    safe_mkdir(cnf.work_dir)

    info('')
    info('*' * 70)
    for bs in bcbio_structures:
        for sample in bs.samples:
            process_one_sample(cnf, bs, sample)


def get_mutation_dicts(cnf, bs, sample):
    pass_mut_dict = dict()
    reject_mut_dict = dict()
    filter_values = set()

    pass_mutations_fpath, _ = get_mutations_fpath_from_bs(bs)
    pass_mutations = parse_mutations(cnf, sample, dict(), pass_mutations_fpath, '')
    for mut in pass_mutations:
        pass_mut_dict[(mut.chrom, mut.pos, mut.transcript)] = mut
    for reject_mutations_fpath in get_rejected_mutations_fpaths(pass_mutations_fpath):
        if verify_file(reject_mutations_fpath, silent=True):
            reject_mutations = parse_mutations(cnf, sample, dict(), reject_mutations_fpath, '')
            for mut in reject_mutations:
                reject_mut_dict[(mut.chrom, mut.pos, mut.transcript)] = mut
                filt_values = mut.reason.split(' and ')
                for val in filt_values:
                    filter_values.add(val)
    for filt_val in filter_values:
        for pattern, description in filter_patterns_dict.iteritems():
            val = pattern.findall(filt_val)
            if val:
                filter_descriptions_dict[filt_val] = description + val[0]
    return pass_mut_dict, reject_mut_dict, list(filter_values)


def combine_mutations(pass_mut_dict, reject_mut_dict):
    combined_dict = pass_mut_dict.copy()
    combined_dict.update(reject_mut_dict)
    sorted_combined_dict = OrderedDict(sorted(combined_dict.items(), key=lambda x: ([x[0][j] for j in range(len(x[0]))])))
    return sorted_combined_dict


def process_one_sample(cnf, bs, sample):
    info('')
    info('Preparing data for ' + sample.name)
    anno_filt_vcf_fpath = sample.find_filt_vcf_by_callername(cnf.caller_name)
    output_dir = cnf.output_dir or os.path.dirname(anno_filt_vcf_fpath)
    output_vcf_fpath = join(output_dir, cnf.caller_name + filt_vcf_ending)
    pass_output_vcf_fpath = add_suffix(output_vcf_fpath, 'pass')

    info('Parsing PASS and REJECT mutations...')
    pass_mut_dict, reject_mut_dict, filter_values = get_mutation_dicts(cnf, bs, sample)
    sorted_mut_dict = combine_mutations(pass_mut_dict, reject_mut_dict)

    info('')
    info('Writing VCFs')
    vcf_reader = vcf.Reader(open_gzipsafe(anno_filt_vcf_fpath, 'r'))
    with file_transaction(cnf.work_dir, output_vcf_fpath) as filt_tx, \
        file_transaction(cnf.work_dir, pass_output_vcf_fpath) as pass_tx:
        vcf_writer = vcf.Writer(open(filt_tx, 'w'), template=vcf_reader)
        vcf_pass_writer = vcf.Writer(open(pass_tx, 'w'), template=vcf_reader)
        for filt_val in filter_values:
            filter_id = filter_descriptions_dict[filt_val] if filt_val in filter_descriptions_dict else ''
            filt = vcf._Filter(filter_id, filt_val)
            vcf_reader.filters[filter_id] = filt
        for key, mut in sorted_mut_dict.items():
            record = get_record_from_vcf(vcf_reader, mut)
            if record:
                if key in pass_mut_dict:
                    record.FILTER = ['PASS']
                    if mut.reason:
                        record.INFO['Reason'] = mut.reason
                elif key in reject_mut_dict:
                    reject_reason_ids = []
                    if mut.reason:
                        reject_reason_ids = [filter_descriptions_dict[reason] if reason in filter_descriptions_dict else reason
                                             for reason in mut.reason.split(' and ')]
                    record.FILTER = [';'.join(reject_reason_ids)]
                if mut.signif:
                    record.INFO['Signif'] = mut.signif
                if mut.status:
                    record.INFO['Status'] = mut.status
                vcf_writer.write_record(record)
                if key in pass_mut_dict:
                    vcf_pass_writer.write_record(record)
            else:
                warn('No record was found in ' + anno_filt_vcf_fpath + ' for mutation ' + str(mut))

    output_gzipped_vcf_fpath = bgzip_and_tabix(cnf, output_vcf_fpath)
    output_gzipped_pass_vcf_fpath = bgzip_and_tabix(cnf, pass_output_vcf_fpath)
    info('VCF file for vardict.txt is saved to ' + output_gzipped_vcf_fpath)
    info('VCF file for vardict.PASS.txt is saved to ' + output_gzipped_pass_vcf_fpath)


if __name__ == '__main__':
    main()
