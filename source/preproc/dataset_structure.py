import re
import os
from os.path import join, isfile, isdir

from source import TargQCStandaloneSample
from source.logger import critical
from source.file_utils import verify_dir, verify_file


class DatasetStructure:
    pre_fastqc_repr =        'Preproc FastQC'
    downsample_targqc_repr = 'TargQC downsampled'

    def __init__(self, dirpath, project_name=None):
        self.dirpath = dirpath
        self.unaligned_dirpath = join(self.dirpath, 'Unalign')
        verify_dir(self.unaligned_dirpath, description='Unalign dir', is_critical=True)

        self.basecalls_dirpath = join(self.dirpath, 'Data/Intensities/BaseCalls')
        verify_dir(self.basecalls_dirpath, is_critical=True)

        self.bcl2fastq_dirpath = self.__get_bcl2fastq_dirpath()
        self.project_name = project_name or self.bcl2fastq_dirpath.split('Project_')[1]

        self.sample_sheet_csv_fpath = join(self.basecalls_dirpath, 'SampleSheet.csv')
        if not isfile(self.sample_sheet_csv_fpath):
            self.sample_sheet_csv_fpath = join(self.dirpath, 'SampleSheet.csv')
        verify_file(self.sample_sheet_csv_fpath, is_critical=True)

        self.fastq_dirpath = join(self.unaligned_dirpath, 'fastq')
        self.fastqc_dirpath = join(self.fastq_dirpath, 'FastQC')
        self.comb_fastqc_fpath = join(self.fastqc_dirpath, 'FastQC.html')
        self.downsample_metamapping_dirpath = join(self.dirpath, 'Downsample_MetaMapping')
        self.downsample_targqc_dirpath = join(self.dirpath, 'Downsample_TargQC')
        self.downsample_targqc_report_fpath = join(self.downsample_targqc_dirpath, 'targQC.html')
        self.project_report_html_fpath = join(self.dirpath, self.project_name + '.html')

        self.samples = []
        for sample_dirname in os.listdir(self.bcl2fastq_dirpath):
            sample_dirpath = join(self.bcl2fastq_dirpath, sample_dirname)
            if isdir(sample_dirpath) and sample_dirname.startswith('Sample_'):
                sample_name = sample_dirname.split('_', 1)[1]
                s = DatasetSample(self, sample_name, bcl2fastq_sample_dirpath=sample_dirpath)
                self.samples.append(s)

    def __get_bcl2fastq_dirpath(self):
        # Reading project name
        bcl2fastq_dirpath = None
        try:
            bcl2fastq_dirpath = join(self.unaligned_dirpath, next(fn for fn in os.listdir(self.unaligned_dirpath) if fn.startswith('Project_')))
        except StopIteration:
            critical('Could not find directory starting with Project_ in ' + self.unaligned_dirpath)
        return bcl2fastq_dirpath


class DatasetSample:
    def __init__(self, ds, name, bcl2fastq_sample_dirpath=None):
        self.ds = ds
        self.name = name
        self.bcl2fastq_sample_dirpath = bcl2fastq_sample_dirpath
        self.l_fpath = join(ds.fastq_dirpath, name + '_R1.fastq.gz')
        self.r_fpath = join(ds.fastq_dirpath, name + '_R2.fastq.gz')

        self.sample_fastqc_dirpath = join(ds.fastqc_dirpath, self.name + '.fq_fastqc')
        self.fastqc_html_fpath = join(ds.fastqc_dirpath, self.name + '.fq_fastqc.html')
        if not isfile(self.fastqc_html_fpath):
            self.fastqc_html_fpath = join(self.sample_fastqc_dirpath, 'fastqc_report.html')

        self.targqc_sample = TargQCStandaloneSample(self.name, ds.downsample_targqc_dirpath)
        self.targetcov_html_fpath = self.targqc_sample.targetcov_html_fpath
        self.ngscat_html_fpath    = self.targqc_sample.ngscat_html_fpath
        self.qualimap_html_fpath  = self.targqc_sample.qualimap_html_fpath

    def find_raw_fastq(self, suf='R1'):
        fastq_fpaths = [
            join(self.bcl2fastq_sample_dirpath, fname)
                for fname in os.listdir(self.bcl2fastq_sample_dirpath)
                if re.match(self.name + '.*_' + suf + '.*\.fastq\.gz', fname)]
        if not fastq_fpaths:
            critical('No fastq files for the sample ' + self.name + ' were found inside ' + self.bcl2fastq_sample_dirpath)
        return fastq_fpaths
