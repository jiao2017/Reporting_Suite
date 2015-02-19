from itertools import dropwhile
from os.path import isfile, join, abspath
import sys
from source.calling_process import call
from source.file_utils import intermediate_fname, iterate_file
from source.logger import info, critical, warn
from source.tools_from_cnf import get_system_path


def index_bam(cnf, bam_fpath):
    indexed_bam = bam_fpath + '.bai'
    if not isfile(bam_fpath + '.bai'):
        info('Indexing to ' + indexed_bam + '...')
        samtools = get_system_path(cnf, 'samtools')
        if not samtools:
            sys.exit(1)
        cmdline = '{samtools} index {bam_fpath}'.format(**locals())
        call(cnf, cmdline)
    info('Index: ' + indexed_bam)


def count_bed_cols(bed_fpath):
    with open(bed_fpath) as f:
        for l in f:
            if l and l.strip() and not l.startswith('#'):
                return len(l.split('\t'))
    # return len(next(dropwhile(lambda x: x.strip().startswith('#'), open(bed_fpath))).split('\t'))
    critical('Empty bed file: ' + bed_fpath)


def prepare_beds(cnf, exons_bed, amplicons_bed, seq2c_bed=None):
    if abspath(exons_bed) == abspath(amplicons_bed):
        warn('Same file used for exons and amplicons: ' + exons_bed)

    # Exons
    info()
    info('Sorting exons by (chrom, gene name, start); and merging regions within genes...')
    exons_bed = group_and_merge_regions_by_gene(cnf, exons_bed, keep_genes=True)

    info()
    info('bedtools-sotring amplicons...')
    amplicons_bed = sort_bed(cnf, amplicons_bed)

    if cnf.reannotate or (seq2c_bed and count_bed_cols(seq2c_bed)) < 4:
        info()
        info('Annotating amplicons with gene names from Ensembl...')
        amplicons_bed = annotate_amplicons(cnf, amplicons_bed, exons_bed)

    if seq2c_bed:
        seq2c_bed = _prep_bed_for_seq2c(cnf, seq2c_bed, amplicons_bed)

    info()
    info('Merging amplicons...')
    amplicons_bed = group_and_merge_regions_by_gene(cnf, amplicons_bed, keep_genes=False)

    return exons_bed, amplicons_bed, seq2c_bed


def annotate_amplicons(cnf, amplicons_bed, exons_bed):
    output_fpath = intermediate_fname(cnf, amplicons_bed, 'ann')

    annotate_bed_py = get_system_path(cnf, 'python', join('tools', 'annotate_bed.py'))
    bedtools = get_system_path(cnf, 'bedtools')

    cmdline = '{annotate_bed_py} {amplicons_bed} {cnf.work_dir} {exons_bed} {bedtools}'.format(**locals())
    call(cnf, cmdline, output_fpath)

    return output_fpath


def group_and_merge_regions_by_gene(cnf, bed_fpath, keep_genes=False):
    output_fpath = intermediate_fname(cnf, bed_fpath, 'merge')

    merge_bed_py = get_system_path(cnf, 'python', join('tools', 'group_and_merge_by_gene.py'))

    cmdline = '{merge_bed_py} {bed_fpath}'.format(**locals())
    if not keep_genes:
        cmdline += ' | grep -vw Gene'

    call(cnf, cmdline, output_fpath)

    return output_fpath


def _prep_bed_for_seq2c(cnf, seq2c_bed, amplicons_bed):
    info()
    info('Preparing BED file for seq2c...')

    if count_bed_cols(seq2c_bed) < 4:
        seq2c_bed = amplicons_bed

    elif count_bed_cols(seq2c_bed) > 4:
        cmdline = 'cut -f1,2,3,4 ' + seq2c_bed
        seq2c_bed = intermediate_fname(cnf, seq2c_bed, 'cut')
        call(cnf, cmdline, seq2c_bed)

    # removing regions with no gene annotation
    def f(l, i):
        if l.split('\t')[3].strip() == '.':
            return None
        else:
            return l
    seq2c_bed = iterate_file(cnf, seq2c_bed, f, 'filt')

    info('Done: ' + seq2c_bed)
    return seq2c_bed


def filter_bed_with_gene_set(cnf, bed_fpath, gene_names_set):
    def fn(l, i):
        if l:
            fs = l.split('\t')
            new_gns = []
            for g in fs[3].split(','):
                if g in gene_names_set:
                    new_gns.append(g)
            if new_gns:
                return l.replace(fs[3], ','.join(new_gns))

    return iterate_file(cnf, bed_fpath, fn, suffix='key')


def sort_bed(cnf, bed_fpath):
    bedtools = get_system_path(cnf, 'bedtools')
    cmdline = '{bedtools} sort -i {bed_fpath}'.format(**locals())
    output_fpath = intermediate_fname(cnf, bed_fpath, 'sorted')
    call(cnf, cmdline, output_fpath)
    return output_fpath

