#!/usr/bin/env python
'''Convert BAM files to BigWig file format in a specified region.
Usage:
    bam_to_wiggle.py <BAM file> [<YAML config>]
    [--outfile=<output file name>
     --chrom=<chrom>
     --start=<start>
     --end=<end>
     --normalize]
chrom start and end are optional, in which case they default to everything.
The normalize flag adjusts counts to reads per million.
The config file is in YAML format and specifies the location of the wigToBigWig
program from UCSC:
program:
  ucsc_bigwig: wigToBigWig
If not specified, these will be assumed to be present in the system path.
The script requires:
    pysam (http://code.google.com/p/pysam/)
    wigToBigWig from UCSC (http://hgdownload.cse.ucsc.edu/admin/exe/)
If a configuration file is used, then PyYAML is also required (http://pyyaml.org/)
'''
import os
import sys
from genericpath import isfile
from os.path import splitext, join
from contextlib import contextmanager, closing
import pysam

import bcbio_postproc  # do not remove it: checking for python version and adding site dirs inside
from source.logger import critical
from source.main import read_opts_and_cnfs
from source.prepare_args_and_cnf import check_genome_resources
from source.tools_from_cnf import get_system_path
from source.calling_process import call
from tools.add_jbrowse_tracks import create_jbrowse_symlink


def proc_args(argv):
    cnf = read_opts_and_cnfs(
        extra_opts=[
            (['--bam'], dict(
                dest='bam',
            )),
        ],
        required_keys=['bam'],
        file_keys=['bam'],
    )

    check_genome_resources(cnf)

    if not cnf.bam:
        critical('No bam file provided to input')
    if not cnf.genome:
        critical('Please, specify the --genome option (e.g. --genome hg19)')

    return cnf

def process_bam(cnf, bam_file, chrom='all', start=0, end=None,
         outfile=None, normalize=False, use_tempfile=False):
    if outfile is None:
        outfile = '%s.bigwig' % splitext(bam_file)[0]
    if start > 0:
        start = int(start) - 1
    if end is not None:
        end = int(end)
    regions = [(chrom, start, end)]
    bigwig_fpath = outfile
    if not (os.path.exists(outfile) and os.path.getsize(outfile) > 0):
        wig_file = '%s.wig' % splitext(outfile)[0]
        out_handle = open(wig_file, 'w')
        with closing(out_handle):
            chr_sizes, wig_valid = write_bam_track(bam_file, regions, out_handle,
                                                   normalize)
        try:
            if wig_valid:
                bigwig_fpath = convert_to_bigwig(wig_file, chr_sizes, cnf, outfile)
        finally:
            os.remove(wig_file)
    return bigwig_fpath

@contextmanager
def indexed_bam(bam_fpath):
    sam_reader = pysam.Samfile(bam_fpath, 'rb')
    yield sam_reader
    sam_reader.close()

def write_bam_track(bam_fpath, regions, out_handle, normalize):
    out_handle.write('track %s\n' % ' '.join(['type=wiggle_0',
        'name=%s' % os.path.splitext(os.path.split(bam_fpath)[-1])[0],
        'visibility=full']))
    normal_scale = 1e6
    is_valid = False
    with indexed_bam(bam_fpath) as work_bam:
        total = sum(1 for r in work_bam.fetch() if not r.is_unmapped) if normalize else None
        sizes = zip(work_bam.references, work_bam.lengths)
        if len(regions) == 1 and regions[0][0] == 'all':
            regions = [(name, 0, length) for name, length in sizes]
        for chrom, start, end in regions:
            if end is None and chrom in work_bam.references:
                end = work_bam.lengths[work_bam.references.index(chrom)]
            assert end is not None
            out_handle.write('variableStep chrom=%s\n' % chrom)
            for col in work_bam.pileup(chrom, start, end):
                if normalize:
                    n = float(col.n) / total * normal_scale
                else:
                    n = col.n
                out_handle.write('%s %.1f\n' % (col.pos+1, n))
                is_valid = True
    return sizes, is_valid

def convert_to_bigwig(wig_fpath, chr_sizes, cnf, bw_fpath=None):
    if not bw_fpath:
        bw_fpath = '%s.bigwig' % (os.path.splitext(wig_fpath)[0])
    chr_sizes_fpath = '%s-sizes.txt' % (os.path.splitext(wig_fpath)[0])
    with open(chr_sizes_fpath, 'w') as out_handle:
        for chrom, size in chr_sizes:
            out_handle.write('%s\t%s\n' % (chrom, size))
    try:
        cmdl = get_system_path(cnf, join('tools', 'wigToBigWig'), is_critical=True)
        cmdl += ' ' + wig_fpath + ' ' + chr_sizes_fpath + ' ' + bw_fpath
        call(cnf, cmdl, exit_on_error=False)
    finally:
        os.remove(chr_sizes_fpath)
    return bw_fpath

def main():
    cnf = proc_args(sys.argv)
    bigwig_fpath = process_bam(cnf, cnf.bam)
    if isfile(bigwig_fpath) and cnf.project_name and cnf.sample:
        create_jbrowse_symlink(cnf.genome.name, cnf.project_name, cnf.sample, bigwig_fpath)


if __name__ == '__main__':
    main()


