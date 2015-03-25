#!/usr/bin/env python

from os.path import abspath, dirname, realpath, join, exists, basename
from site import addsitedir
project_dir = abspath(dirname(dirname(realpath(__file__))))
addsitedir(join(project_dir))
addsitedir(join(project_dir, 'ext_modules'))
import sub_scripts.__check_python_version  # do not remove it: checking for python version and adding site dirs inside

import sys
import os
import annotate_bed
import subprocess
from source.file_utils import add_suffix, _remove_files
from source.utils import human_sorted
from optparse import OptionParser


""" Input: Any BED file
    Output:
        BED file with regions from input and with exactly 4 columns (or exactly 8 columns for BEDs with primers info).
        The forth column ("gene symbol") is generated with annotate_bed.py script. If no annotation is found
        gene symbol is set to "not_a_gene_%d". If more than one annotation is found for region only one is remained
        (priory from highest to lowest: key gene, approved gene, first gene).
        Output BED is sorted using by chromosome name -> start -> end. Run standardize_bed.py --help for details about
        options.

    Usage: python standardize_bed.py [options] Input_BED_file work_dir > Standardized_BED_file
"""


def _read_args(args_list):
    options = [
        (['-k', '--key-genes'], dict(
            dest='key_genes_fpath',
            help='list of key genes (they are at top priority when choosing one of multiple annotations)',
            default='/ngs/reference_data/genomes/Hsapiens/common/az_key_genes.txt')
         ),
        (['-a', '--approved-genes'], dict(
            dest='approved_genes_fpath',
            help='list of HGNC approved genes (they are preferable when choosing one of multiple annotations)',
            default='/ngs/reference_data/genomes/Hsapiens/common/HGNC_gene_synonyms.txt')
         ),
        (['-e', '--ensembl-bed'], dict(
            dest='ensembl_bed_fpath',
            help='reference BED file for annotation (Ensembl)',
            default='/ngs/reference_data/genomes/Hsapiens/hg19/bed/Exons/Exons.with_genes.bed')
         ),
        (['-r', '--refseq-bed'], dict(
            dest='refseq_bed_fpath',
            help='reference BED file for annotation (RefSeq)',
            default='/ngs/reference_data/genomes/Hsapiens/hg19/bed/Exons/RefSeq.bed')
         ),
        (['-b', '--bedtools'], dict(
            dest='bedtools',
            help='path to bedtools',
            default='bedtools')
         ),
        (['--debug'], dict(
            dest='debug',
            help='run in a debug more (verbose output, keeping of temporary files)',
            default=False,
            action='store_true')
         ),
        (['--output-hg'], dict(
            dest='output_hg',
            help='output chromosome names in hg-style (chr1, .., chr22, chrX, chrY, chrM)',
            default=False,
            action='store_true')
         ),
        (['--output-grch'], dict(
            dest='output_grch',
            help='output chromosome names in GRCh-style (1, .., 22, X, Y, MT)',
            default=False,
            action='store_true')
         )
    ]

    parser = OptionParser(usage='usage: %prog [options] Input_BED_file work_dir > Standardized_BED_file',
                          description='Scripts outputs a standardized version of input BED file. '
                                      'Standardized BED: 1) has 4 or 8 fields (for BEDs with primer info);'
                                      ' 2) has HGNC approved symbol in forth column if annotation is '
                                      'possible and not_a_gene_X otherwise;'
                                      ' 3) is sorted based on chromosome name -> start -> end;'
                                      ' 4) has no duplicated regions (regions with the same chromosome, start and end), '
                                      'the only exception is _CONTROL_ regions.')
    for args, kwargs in options:
        parser.add_option(*args, **kwargs)
    (opts, args) = parser.parse_args(args_list)

    if len(args) != 2:
        parser.print_help(file=sys.stderr)
        sys.exit(1)

    input_bed_fpath = abspath(args[0])
    log('Input: ' + input_bed_fpath)

    work_dirpath = abspath(args[1])
    log('Working directory: ' + work_dirpath)
    if not exists(work_dirpath):
        os.makedirs(work_dirpath)

    # process configuration
    for k, v in opts.__dict__.iteritems():
        if k.endswith('fpath'):
            opts.__dict__[k] = abspath(v)
    if opts.output_grch and opts.output_hg:
        err('you cannot specify --output-hg and --output-grch simultaneously!')

    if opts.debug:
        log('Configuration: ')
        for k, v in opts.__dict__.iteritems():
            log('\t' + k + ': ' + str(v))
    log()

    return input_bed_fpath, work_dirpath, opts


def log(msg=''):
    sys.stderr.write(msg + '\n')


def err(msg=''):
    log('Error: ' + msg + '\n')
    sys.exit(1)


class BedParams:
    GRCh_to_hg = {'MT': 'chrM', 'X': 'chrX', 'Y': 'chrY'}
    for i in range(1, 23):
        GRCh_to_hg[str(i)] = 'chr' + str(i)
    hg_to_GRCh = {v: k for k, v in GRCh_to_hg.items()}

    def __init__(self, header=list(), controls=list(), GRCh_names=None, n_cols_needed=None):
        self.header = header
        self.controls = controls
        self.GRCh_names = GRCh_names
        self.n_cols_needed = n_cols_needed

    @staticmethod
    def calc_n_cols_needed(line):
        columns = line.strip().split('\t')
        if len(columns) < 8:
            return 4
        elif columns[6].isdigit() and columns[7].isdigit():  # primers info
            return 8
        else:
            return 4


class Region:
    GRCh_names = False
    n_cols_needed = 4
    approved_genes = []
    key_genes = []

    def __init__(self, bed_line):
        entries = bed_line.strip().split('\t')
        self.chrom = entries[0]
        self.start = int(entries[1])
        self.end = int(entries[2])
        self.symbol = None
        self.type = None
        self.set_symbol(entries[3] if len(entries) > 3 else '{0}:{1}-{2}'.format(self.chrom, self.start, self.end))
        self.rest = entries[4:]

    def set_symbol(self, symbol):
        self.symbol = symbol
        if self.symbol in self.key_genes:
            self.type = 'key'
        elif self.symbol in self.approved_genes:
            self.type = 'approved'
        else:
            self.type = 'not_approved'

    def __str__(self):
        fs = [BedParams.hg_to_GRCh[self.chrom] if self.GRCh_names else self.chrom,
              str(self.start), str(self.end), self.symbol] + (self.rest if self.n_cols_needed > 4 else [])
        return '\t'.join(fs) + '\n'

    def get_key(self):
        return '\t'.join([self.chrom, str(self.start), str(self.end)])

    def is_control(self):
        if self.symbol.startswith('_CONTROL'):
            return True
        return False

    def __lt__(self, other):
        # special case: chrM goes to the end
        if self.chrom != other.chrom and (self.chrom == 'chrM' or other.chrom == 'chrM'):
            return True if other.chrom == 'chrM' else False
        sorted_pair = human_sorted([self.get_key(), other.get_key()])
        if sorted_pair[0] == self.get_key() and sorted_pair[1] != self.get_key():
            return True
        if self.get_key() == other.get_key() and self.is_control():
            return True
        return False

    def __eq__(self, other):
        return self.get_key() == other.get_key()

    def __hash__(self):
        return hash(self.get_key())


def _preprocess(bed_fpath, work_dirpath):
    bed_params = BedParams()
    output_fpath = __intermediate_fname(work_dirpath, bed_fpath, 'prep')
    log('preprocessing: ' + bed_fpath + ' --> ' + output_fpath)
    with open(bed_fpath, 'r') as in_f:
        with open(output_fpath, 'w') as out_f:
            for line in in_f:
                if line.startswith('#') or line.startswith('track') or line.startswith('browser'):  # header
                    bed_params.header.append(line if line.startswith('#') else '#' + line)
                else:
                    cur_ncn = BedParams.calc_n_cols_needed(line)
                    if bed_params.n_cols_needed is not None and cur_ncn != bed_params.n_cols_needed:
                        err('number and type of columns should be the same on all lines!')
                    bed_params.n_cols_needed = cur_ncn
                    if Region(line).is_control():
                        bed_params.controls.append(Region(line))
                        continue
                    if line.startswith('chr'):
                        if bed_params.GRCh_names is not None and bed_params.GRCh_names:
                            err('mixing of GRCh and hg chromosome names!')
                        bed_params.GRCh_names = False
                        out_f.write(line)
                    elif line.split('\t')[0] in BedParams.GRCh_to_hg:  # GRCh chr names
                        if bed_params.GRCh_names is not None and not bed_params.GRCh_names:
                            err('mixing of GRCh and hg chromosome names!')
                        bed_params.GRCh_names = True
                        out_f.write('\t'.join([BedParams.GRCh_to_hg[line.split('\t')[0]]] + line.split('\t')[1:]))
                    else:
                        err('incorrect chromosome name!')
    return output_fpath, bed_params


def _annotate(bed_fpath, work_dirpath, cnf):
    annotated_files = []
    input_fpath = bed_fpath
    references = [('RefSeq', cnf.refseq_bed_fpath), ('Ensembl', cnf.ensembl_bed_fpath)]

    for id, (db_name, db_bed_fpath) in enumerate(references):
        output_fpath = __intermediate_fname(work_dirpath, bed_fpath, 'ann_' + db_name.lower())
        log('annotating based on {db_name}: {bed_fpath} --> {output_fpath}'.format(**locals()))
        annotate_bed_py = sys.executable + ' ' + annotate_bed.__file__
        cmdline = '{annotate_bed_py} {input_fpath} {work_dirpath} {db_bed_fpath} {cnf.bedtools}'.format(**locals())
        __call(cnf, cmdline, output_fpath)
        if id < len(references) - 1:
            if cnf.debug:
                log("filtering annotated and not annotated regions into separate files:")
            only_annotated_bed = __intermediate_fname(work_dirpath, bed_fpath, 'only_ann_' + db_name.lower())
            not_annotated_bed = __intermediate_fname(work_dirpath, bed_fpath, 'not_ann_' + db_name.lower())
            with open(only_annotated_bed, 'w') as out:
                cmdline = 'grep -v ".\t.\t.\t.\t." {output_fpath}'.format(**locals())
                if cnf.debug:
                    log(cmdline + ' > ' + only_annotated_bed)
                subprocess.call(cmdline, shell=True, stdout=out)
            with open(not_annotated_bed, 'w') as out:
                cmdline = 'grep ".\t.\t.\t.\t." {output_fpath}'.format(**locals())
                if cnf.debug:
                    log(cmdline + ' > ' + not_annotated_bed)
                subprocess.call(cmdline, shell=True, stdout=out)
            if not cnf.debug:
                _remove_files(output_fpath)
            output_fpath = only_annotated_bed
            input_fpath = not_annotated_bed
        annotated_files.append(output_fpath)
        if id != 0 and not cnf.debug:
            _remove_files(input_fpath)

    return annotated_files


def _postprocess(input_fpath, annotated_fpaths, bed_params, cnf):
    '''
    1. Sorts.
    1. Chooses appropriate number of columns (4 or 8 for BEDs with primers).
    2. Removes duplicates.
    '''
    log('postprocessing (sorting, cutting, removing duplicates)')

    key_genes = []
    with open(cnf.key_genes_fpath, 'r') as f:
        for line in f:
            key_genes.append(line.strip())
    approved_genes = []
    with open(cnf.approved_genes_fpath, 'r') as f:
        f.readline()  # header
        for line in f:
            approved_genes.append(line.split('\t')[0])

    Region.GRCh_names = bed_params.GRCh_names
    if cnf.output_grch:
        Region.GRCh_names = True
        if cnf.debug and not bed_params.GRCh_names:
            log('Changing chromosome names from hg-style to GRCh-style.')
    if cnf.output_hg:
        Region.GRCh_names = False
        if cnf.debug and bed_params.GRCh_names:
            log('Changing chromosome names from GRCh-style to hg-style.')
    Region.n_cols_needed = bed_params.n_cols_needed
    Region.key_genes = key_genes
    Region.approved_genes = approved_genes

    input_regions = set()  # we want only unique regions
    with open(input_fpath) as f:
        for line in f:
            input_regions.add(Region(line))
    annotated_regions = []
    for annotated_fpath in annotated_fpaths:
        with open(annotated_fpath) as f:
            for line in f:
                annotated_regions.append(Region(line))

    # starting to output result
    for line in bed_params.header:
        sys.stdout.write(line)

    annotated_regions.sort()
    i = 0
    prev_symbol, prev_chr, not_a_gene_count = "", "", 0
    for in_region in sorted(list(input_regions) + bed_params.controls):
        ready_region = in_region
        if not ready_region.is_control():
            assert annotated_regions[i] == in_region, str(in_region) + ' != ' + str(annotated_regions[i]) + '(i=%d)' % i
            if annotated_regions[i].symbol != '.':
                ready_region.set_symbol(annotated_regions[i].symbol)
            else:
                if prev_chr != ready_region.chrom or not prev_symbol.startswith("not_a_gene"):
                    not_a_gene_count += 1
                ready_region.set_symbol("not_a_gene_%d" % not_a_gene_count)
            i += 1
            while i < len(annotated_regions) and annotated_regions[i] == in_region:  # processing duplicates
                if annotated_regions[i].symbol != '.' and annotated_regions[i].symbol != ready_region.symbol:
                    if annotated_regions[i].type == 'approved' and ready_region.type == 'not_approved':
                        ready_region.set_symbol(annotated_regions[i].symbol)
                    elif annotated_regions[i].type == 'key' and ready_region.type != 'key':
                        ready_region.set_symbol(annotated_regions[i].symbol)
                        if cnf.debug:
                            log('key gene priority over approved gene was used')
                    elif annotated_regions[i].type == ready_region.type:
                        if annotated_regions[i].symbol == prev_symbol:
                            ready_region.set_symbol(annotated_regions[i].symbol)
                            if cnf.debug:
                                log('previous gene name was preferred among several ambiguous names')
                i += 1
        sys.stdout.write(str(ready_region))  # automatically output correct number of columns and GRCh/hg names
        prev_chr = ready_region.chrom
        prev_symbol = ready_region.symbol


def __intermediate_fname(work_dir, fname, suf):
    output_fname = add_suffix(fname, suf)
    return join(work_dir, basename(output_fname))


def __call(cnf, cmdline, output_fpath=None):
    stdout = open(output_fpath, 'w') if output_fpath else None
    stderr = None if cnf.debug else open('/dev/null', 'w')
    if cnf.debug:
        log(cmdline)
    ret_code = subprocess.call(cmdline, shell=True, stdout=stdout, stderr=stderr, stdin=None)
    return ret_code


# def __sort_bed(fpath, cnf):
#     work_dirpath = dirname(fpath)
#     output_fpath = __intermediate_fname(work_dirpath, fpath, 'sort')
#     cmdline = 'sort -k1,1V -k2,2n -k3,3n ' + fpath  # TODO: -k1,1V not working on Mac
#     __call(cnf, cmdline, output_fpath)
#     return fpath


def main():
    input_bed_fpath, work_dirpath, cnf = _read_args(sys.argv[1:])

    preprocessed_fpath, bed_params = _preprocess(input_bed_fpath, work_dirpath)
    annotated_fpaths = _annotate(preprocessed_fpath, work_dirpath, cnf)
    _postprocess(preprocessed_fpath, annotated_fpaths, bed_params, cnf)
    if not cnf.debug:
        _remove_files([preprocessed_fpath] + annotated_fpaths)

if __name__ == '__main__':
    main()
