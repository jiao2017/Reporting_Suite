from os.path import join
from collections import OrderedDict
from source.file_utils import verify_file
from source.logger import info
from source import targetcov

detail_gene_report_baseending = '.details.gene'

varfilter_name           = 'varFilter'
varannotate_name         = 'varAnnotate'
targetseq_name           = 'targetSeq'
cnv_dir                  = 'cnv'

varqc_name               = 'varQC'
varqc_after_name         = 'varQC_postVarFilter'
ngscat_name              = 'ngscat'
qualimap_name            = 'qualimap'
picard_name              = 'picard'
targqc_name              = 'targQC'
fastqc_name              = 'fastqc'

varqc_repr               = 'Var QC'
varqc_after_repr         = 'Var QC after filtering'
ngscat_repr              = 'Ngscat'
qualimap_repr            = 'Qualimap'
targqc_repr              = 'Target QC'
fastqc_repr              = 'FastQC'

seq2c_name               = 'Seq2C'
seq2c_seq2cov_ending     = 'seq2c_seq2cov.txt'

mut_fname_template = '{caller_name}.txt'
mut_single_suffix = 'single'
mut_paired_suffix = 'paired'
mut_pass_suffix = 'PASS'


class BaseSample:
    def __init__(self, name, dirpath=None, path_base=None, bam=None, bed=None, vcf=None, genome=None):
        self.name = name
        self.bam = bam
        self.bed = bed
        self.qualimap_bed = None
        self.vcf_by_callername = OrderedDict()  # string -> vcf_fpath
        self.vcf = vcf
        self.dirpath = dirpath
        self.phenotype = None
        self.genome = None
        self.var_dirpath = None
        self.normal_match = None
        self.min_af = None

        self.targetcov_html_fpath          = self.make_fpath(path_base + '{sample}.{name}.html', name=targetseq_name)
        self.targetcov_json_fpath          = self.make_fpath(path_base + '{sample}.{name}.json', name=targetseq_name)
        self.targetcov_detailed_txt        = self.make_fpath(path_base + '{sample}.{name}' + detail_gene_report_baseending + '.txt', name=targetseq_name)
        self.targetcov_detailed_tsv        = self.make_fpath(path_base + '{sample}.{name}' + detail_gene_report_baseending + '.tsv', name=targetseq_name)
        self.targetcov_norm_depth_vcf_txt  = None
        self.targetcov_norm_depth_vcf_tsv  = None
        self.picard_ins_size_hist_fpath    = self.make_fpath(path_base + 'picard_ins_size_hist.txt', name=targetseq_name)
        self.ngscat_html_fpath             = self.make_fpath(path_base + 'captureQC.html', name=ngscat_name)
        self.qualimap_html_fpath           = self.make_fpath(path_base + 'qualimapReport.html', name=qualimap_name)
        self.qualimap_genome_results_fpath = self.make_fpath(path_base + 'genome_results.txt', name=qualimap_name)
        self.qualimap_ins_size_hist_fpath  = self.make_fpath(path_base + 'raw_data_qualimapReport/insert_size_histogram.txt', name=qualimap_name)
        self.fastqc_html_fpath             = self.make_fpath(path_base + 'fastqc_report.html', name=fastqc_name)
        self.seq2cov_output_fpath          = self.make_fpath(path_base + '{sample}.{name}_' + seq2c_seq2cov_ending, name=targetseq_name)
        self.seq2cov_output_dup_fpath      = self.make_fpath(path_base + '{sample}.{name}_dup_' + seq2c_seq2cov_ending, name=targetseq_name)

    def make_fpath(self, path_template, **kwargs):
        keys = dict(dict(dirpath=self.dirpath, sample=self.name).items() + kwargs.items())
        return join(*path_template.split('/')).format(**keys)

    def targetcov_done(self):
        if verify_file(self.targetcov_json_fpath) \
           and verify_file(self.targetcov_html_fpath) \
           and verify_file(self.targetcov_detailed_tsv):
            # info(self.targetcov_json_fpath + ', ' +
            #      self.targetcov_html_fpath + ', and ' +
            #      self.targetcov_detailed_tsv + ' exist.')
            return True
        return False

    def ngscat_done(self):
        if verify_file(self.ngscat_html_fpath):
            # info(self.ngscat_html_fpath + ' exists.')
            return True
        return False

    def qualimap_done(self):
        if verify_file(self.qualimap_html_fpath):
            # info(self.qualimap_html_fpath + ' exists.')
            return True
        return False

    # def picard_dup_done(self):
    #     if verify_file(self.picard_dup_metrics_fpath):
    #         info(self.picard_dup_metrics_fpath + ' exists.')
    #         return True
    #     return False
    #
    # def picard_ins_size_done(self):
    #     if verify_file(self.picard_ins_size_pdf_fpath):
    #         info(self.picard_ins_size_pdf_fpath + ' exists.')
    #         return True
    #     return False

    def __cmp__(self, other):
        return cmp(self.key_to_sort(), other.key_to_sort())

    def key_to_sort(self):
        parts = []

        cur_part = []
        prev_was_num = False

        for c in self.name:
            if prev_was_num == c.isdigit() and c not in ['-', '.']:  # same type of symbol, but not - or .
                cur_part.append(c)
            else:
                if cur_part:
                    part = ''.join(cur_part)
                    if prev_was_num:
                        part = int(part)
                    parts.append(part)
                    cur_part = []

                if c in ['-', '.']:
                    pass
                else:
                    if c.isdigit():
                        prev_was_num = True
                    else:
                        prev_was_num = False
                    cur_part.append(c)

        return tuple(parts)

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name


class SingleSample(BaseSample):
    def __init__(self, name, output_dir, **kwargs):
        BaseSample.__init__(self, name, output_dir, path_base=output_dir, **kwargs)

