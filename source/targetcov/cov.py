# coding=utf-8

from collections import OrderedDict
from itertools import izip
from os.path import join, isfile, abspath, realpath, dirname, relpath, basename
import shutil
import traceback
import math

import source
from source.qualimap.report_parser import parse_qualimap_sample_report
import source.targetcov
from source.calling_process import call
from source.file_utils import intermediate_fname, verify_file, safe_mkdir, splitext_plus
from source.logger import critical, info, err, warn, debug
from source.reporting.reporting import Metric, SampleReport, MetricStorage, ReportSection, PerRegionSampleReport, Row, \
    BaseReport, write_txt_rows, write_tsv_rows, get_col_widths
from source.targetcov.Region import calc_bases_within_threshs, \
    calc_rate_within_normal, build_gene_objects_list, Region, GeneInfo
from source.targetcov.bam_and_bed_utils import index_bam, total_merge_bed, sort_bed, fix_bed_for_qualimap, \
    remove_dups, get_padded_bed_file, number_mapped_reads_on_target, flag_stat, calc_region_number, \
    intersect_bed, calc_sum_of_regions, bam_to_bed, number_of_mapped_reads, call_sambamba, count_bed_cols, \
    sambamba_depth
from source.tools_from_cnf import get_system_path
from source.utils import get_chr_len_fpath


def get_header_metric_storage(depth_thresholds, is_wgs=False, padding=None):
    sections = [
        ReportSection('reads', 'Reads', [
            Metric('Reads', short_name='reads'),
            Metric('Mapped reads', short_name='mapped', description='samtools view -c -F 4', ok_threshold='Percentage of mapped reads', bottom=0),
            Metric('Percentage of mapped reads', short_name='%', unit='%', ok_threshold=0.98, bottom=0),
            Metric('Properly paired mapped reads percent', short_name='mapped paired', unit='%', description='Pecent of properly paired mapped reads.', ok_threshold=0.9, bottom=0),
            Metric('Properly paired reads percent', short_name='paired', unit='%', description='Pecent of properly paired reads (-f 2).', ok_threshold=0.9, bottom=0),
            Metric('Duplication rate', short_name='dup rate', description='Percent of mapped reads (-F 4), marked as duplicates (-f 1024)', quality='Less is better', unit='%'),
            Metric('Read min length', short_name='min len', description='Read minimum length'),
            Metric('Read max length', short_name='max len', description='Read maximum length'),
            Metric('Read mean length', short_name='avg len', description='Read average length'),
            Metric('Sex', short_name='sex', is_hidden=True),
        ]),
    ]
    if not is_wgs:
        sections.extend([
            ReportSection('target_metrics', 'Target coverage', [
                Metric('Covered bases in target', short_name='trg covered', unit='bp'),
                Metric('Percentage of target covered by at least 1 read', short_name='%', unit='%'),
                Metric('Percentage of reads mapped on target', short_name='reads on trg', unit='%',
                       description='Percentage of unique mapped reads overlapping target at least by 1 base'),
                Metric('Percentage of reads mapped off target', short_name='reads off trg', unit='%',
                       quality='Less is better',
                       description='Percentage of unique mapped reads that don\'t overlap target even by 1 base'),
                Metric('Percentage of reads mapped on padded target',
                       short_name='reads on trg' + (' %dbp pad' % padding if padding is not None else ' w/ padding'),
                       unit='%',
                       description='Percentage of reads that overlap target at least by 1 base. Should be 1-2% higher.'),
                Metric('Percentage of usable reads', short_name='usable reads', unit='%',
                       description='Share of unique reads mapped on target in the total number of original reads '
                                   '(reported in the very first column Reads'),
                Metric('Read bases mapped on target', short_name='read bp on trg', unit='bp'),
            ]),
        ])
    else:
        sections.extend([
            ReportSection('target_metrics_wgs', 'Genome coverage', [
                Metric('Covered bases in genome', short_name='genome covered', unit='bp'),
                Metric('Percentage of genome covered by at least 1 read', short_name='%', unit='%'),
                Metric('Covered bases in exome', short_name='CDS covered', description='Covered CDS bases. CDS coordinates are taken from RefSeq', unit='bp'),
                Metric('Percentage of exome covered by at least 1 read', short_name='%', description='Percentage of CDS covered by at least 1 read. CDS coordinates are taken from RefSeq', unit='%'),
                Metric('Percentage of reads mapped on exome', short_name='reads on CDS', unit='%',
                       description='Percentage of reads mapped on CDS. CDS coordinates are taken from RefSeq'),
                Metric('Percentage of reads mapped off exome', short_name='off CDS', unit='%', quality='Less is better',
                       description='Percentage of reads mapped outside of CDS. CDS coordinates are taken from RefSeq'),
                Metric('Percentage of usable reads', short_name='usable reads', unit='%',
                       description='Share of mapped unique reads in all reads (reported in the very first column Reads)'),
            ]),
        ])

    trg_name = 'target' if not is_wgs else 'genome'
    depth_section = ReportSection('depth_metrics', ('Target' if not is_wgs else 'Genome') + ' coverage depth', [
        Metric('Median ' + trg_name + ' coverage depth', short_name='median'),
        Metric('Average ' + trg_name + ' coverage depth', short_name='avg'),
        Metric('Estimated ' + trg_name + ' full coverage', short_name='est full cov',
               description='Estimated average coverage of full dataset. Calculated as (the total number of raw reads * '
                           'downsampled mapped reads fraction / total downsampled mapped reads) * downsampled average coverage'),
        Metric('Std. dev. of ' + trg_name + ' coverage depth', short_name='std dev', quality='Less is better'),
        # Metric('Minimal ' + trg_name + ' coverage depth', short_name='Min', is_hidden=True),
        # Metric('Maximum ' + trg_name + ' coverage depth', short_name='Max', is_hidden=True),
        Metric('Percentage of ' + trg_name + ' within 20% of mean depth', short_name='&#177;20% avg', unit='%')
    ])
    for depth in depth_thresholds:
        name = 'Part of ' + trg_name + ' covered at least by ' + str(depth) + 'x'
        depth_section.add_metric(Metric(name, short_name=str(depth) + 'x', description=name, unit='%'))
    sections.append(depth_section)

    sections.append(
        ReportSection('qualimap', 'Qualimap stats' + ('' if is_wgs else ' within the target'), [
            Metric('Mean Mapping Quality',  'mean MQ',            'Mean mapping quality, inside of regions'),
            Metric('Mismatches',            'mismatches',         'Mismatches, inside of regions', quality='Less is better'),  # added in Qualimap v.2.0
            Metric('Insertions',            'insertions',         'Insertions, inside of regions', quality='Less is better'),
            Metric('Deletions',             'deletions',          'Deletions, inside of regions', quality='Less is better'),
            Metric('Homopolymer indels',    'homopolymer indels', 'Percentage of homopolymer indels, inside of regions', quality='Less is better'),
            Metric('Qualimap',              'Qualimap report',           'Qualimap report'),
            Metric('ngsCAT',                'ngsCAT report',             'ngsCAT report')
        ])
    )

    ms = MetricStorage(
        general_section=ReportSection('general_section', '', [
            Metric('Target', short_name='Target', common=True),
            Metric('Reference size', short_name='Reference bp', unit='bp', common=True),
            # Metric('Target ready', short_name='Target ready', common=True),
            Metric('Regions in target', short_name='Regions in target', common=True),
            Metric('Bases in target', short_name='Target bp', unit='bp', common=True),
            Metric('Percentage of reference', short_name='Percentage of reference', unit='%', common=True),
            # Metric('Genes', short_name='Genes', common=True),
            Metric('Genes in target', short_name='Genes in target', common=True),
        ]),
        sections=sections
    )
    return ms


class TargetInfo:
    def __init__(self, fpath=None, bed=None, original_target_bed=None, regions_num=None,
                 bases_num=None, fraction=None, genes_fpath=None, genes_num=None):
        self.fpath = realpath(fpath) if fpath else None  # raw source file - to demonstrate where we took one
        self.bed = bed                                   # processed (sorted, merged...), to do real calculations
        self.original_target_bed = original_target_bed
        self.regions_num = regions_num
        self.bases_num = bases_num
        self.fraction = fraction
        self.genes_fpath = realpath(genes_fpath) if genes_fpath else None
        self.genes_num = genes_num
        self.type = None  # 'Regional', 'WGS'


def _run_qualimap(cnf, sample, bam_fpath, bed_fpath=None, pcr=False):
    safe_mkdir(dirname(sample.qualimap_dirpath))

    bed = ''
    if bed_fpath:
        qualimap_bed_fpath = join(cnf.work_dir, 'tmp_qualimap.bed')
        fix_bed_for_qualimap(bed_fpath, qualimap_bed_fpath)
        bed = '--bed ' + qualimap_bed_fpath

    qm = get_system_path(cnf, 'python', join('scripts', 'post', 'qualimap.py'))
    cmdl = '{qm} --project-name {cnf.project_name} --sys-cnf {cnf.sys_cnf} --run-cnf {cnf.run_cnf} ' \
           '--bam {bam_fpath} {bed} -o {sample.qualimap_dirpath} -t {cnf.threads}'.format(**locals())
    if pcr:
        info('PCR: BAM files are not deduplicated')
        cmdl += ' --pcr'
    call(cnf, cmdl, sample.qualimap_html_fpath, stdout_to_outputfile=False)
    return sample.qualimap_dirpath


def _dedup_and_flag_stat(cnf, bam_fpath):
    bam_stats = flag_stat(cnf, bam_fpath)
    info('Total reads: ' + Metric.format_value(bam_stats['total']))
    info('Total mapped reads: ' + Metric.format_value(bam_stats['mapped']))
    info('Total dup reads: ' + Metric.format_value(bam_stats['duplicates']))
    info('Total properly paired reads: ' + Metric.format_value(bam_stats['properly paired']))

    # dedup_bam_dirpath = join(cnf.work_dir, source.dedup_bam)
    # safe_mkdir(dedup_bam_dirpath)
    # dedup_bam_fpath = join(dedup_bam_dirpath, add_suffix(basename(bam_fpath), source.dedup_bam))
    # remove_dups(cnf, bam_fpath, output_fpath=dedup_bam_fpath, use_grid=False)
    # dedup_bam_stats = samtools_flag_stat(cnf, dedup_bam_fpath)
    # info('Total reads after dedup (samtools view -F 1024): ' + Metric.format_value(dedup_bam_stats['total']))
    # info('Total mapped reads after dedup (samtools view -F 1024): ' + Metric.format_value(dedup_bam_stats['mapped']))
    return bam_stats  # dedup_bam_fpath, bam_stats, dedup_bam_stats


def _parse_qualimap_results(qualimap_html_fpath, qualimap_cov_hist_fpath, depth_thresholds):
    if not verify_file(qualimap_html_fpath):
        critical('Qualimap report was not found')

    depth_stats = dict()

    if not verify_file(qualimap_cov_hist_fpath):
        err('Qualimap hist fpath is not found, cannot build histogram')
    else:
        bases_by_depth = OrderedDict()
        with open(qualimap_cov_hist_fpath) as f:
            for l in f:
                if l.startswith('#'):
                    pass
                else:
                    cov, bases = map(int, map(float, l.strip().split()))
                    bases_by_depth[cov] = bases
        depth_stats['bases_by_depth'] = bases_by_depth

        # calculating median coverage
        num_counts = sum(bases_by_depth.values())
        cum_counts = 0
        median_coverage = None
        for thiscov, thiscount in bases_by_depth.items():
            cum_counts += thiscount
            if cum_counts >= num_counts/2:
                median_coverage = thiscov
                break
        depth_stats['median_depth'] = median_coverage

    qualimap_records = parse_qualimap_sample_report(qualimap_html_fpath)

    def find_rec(name):
        return next((r.value for r in qualimap_records if r.metric.name.startswith(name)), None)

    depth_stats['ave_depth'] = find_rec('Coverage Mean')
    # depth_stats['min_depth'] = find_rec('Coverage Min')
    # depth_stats['max_depth'] = find_rec('Coverage Max')
    depth_stats['stddev_depth'] = find_rec('Coverage Standard Deviation')

    target_stats = dict(
        reference_size  = find_rec('Reference size'),
        target_size     = find_rec('Regions size/percentage of reference (on target)'),
        target_fraction = find_rec('Regions size/percentage of reference (on target) %'),
    )

    reads_stats = dict(
        total                    = find_rec('Number of reads'),
        mapped                   = find_rec('Mapped reads'),
        mapped_rate              = find_rec('Mapped reads %'),
        unmapped                 = find_rec('Unmapped reads'),
        unmapped_rate            = find_rec('Unmapped reads %'),
        # mapped_on_target         = find_rec('Mapped reads (on target)'),
        # mapped_rate_on_target    = find_rec('Mapped reads % (on target)'),
        mapped_paired            = find_rec('Mapped paired reads'),
        mapped_paired_rate       = find_rec('Mapped paired reads %'),
        paired                   = find_rec('Paired reads'),
        paired_rate              = find_rec('Paired reads %'),
        dup                      = find_rec('Duplicated reads (flagged)'),
        dup_rate                 = find_rec('Duplicated reads (flagged) %'),
        min_len                  = find_rec('Read min length'),
        max_len                  = find_rec('Read max length'),
        ave_len                  = find_rec('Read mean length'),
    )
    if reads_stats.get('dup_rate') is None:
        reads_stats['dup']       = find_rec('Duplicated reads (flagged) (on target)')
        reads_stats['dup_rate']  = find_rec('Duplicated reads (flagged) (on target) %')

    mm_indels_stats = dict(
        mean_mq     = find_rec('Mean Mapping Quality'),
        mismatches  = find_rec('Mismatches'),
        insertions  = find_rec('Insertions'),
        deletions   = find_rec('Deletions'),
        homo_indels = find_rec('Homopolymer indels'),
    )

    return depth_stats, reads_stats, mm_indels_stats, target_stats


chry_key_regions_by_genome = {
    'hg19': join(dirname(abspath(__file__)), 'chrY.hg19.bed'),
    'hg19-noalt': join(dirname(abspath(__file__)), 'chrY.hg19.bed'),
    'hg19-chr21': join(dirname(abspath(__file__)), 'chrY.hg19.bed'),
    'hg38': join(dirname(abspath(__file__)), 'chrY.hg38.bed'),
    'hg38-noalt': join(dirname(abspath(__file__)), 'chrY.hg38.bed'),
}
MALE_TARGET_REGIONS_FACTOR = 0.7
AVE_DEPTH_THRESHOLD_TO_DETERMINE_SEX = 5
FEMALE_Y_COVERAGE_FACTOR = 10.0

def _determine_sex(cnf, sample, bam_fpath, ave_depth, target_bed=None):
    info()
    info('Determining sex')

    male_genes_bed = chry_key_regions_by_genome.get(cnf.genome.name)
    if not male_genes_bed:
        warn('Warning: no male key regions for ' + cnf.genome.name + ', cannot identify sex')
        return None

    male_area_size = calc_sum_of_regions(male_genes_bed)
    info('Male region total size: ' + str(male_area_size))

    if target_bed:
        male_genes_bed = intersect_bed(cnf, target_bed, male_genes_bed)
        target_male_area_size = calc_sum_of_regions(male_genes_bed)
        if target_male_area_size < male_area_size * MALE_TARGET_REGIONS_FACTOR:
            info('Target male region total size is ' + str(target_male_area_size) + ', which is less than the ' +
                 'checked male regions size * ' + str(MALE_TARGET_REGIONS_FACTOR) +
                 ' (' + str(male_area_size * MALE_TARGET_REGIONS_FACTOR) + ') - cannot determine sex')
            return None
        else:
            info('Target male region total size is ' + str(target_male_area_size) + ', which is higher than the ' +
                 'checked male regions size * ' + str(MALE_TARGET_REGIONS_FACTOR) +
                 ' (' + str(male_area_size * MALE_TARGET_REGIONS_FACTOR) + '). ' +
                 'Determining sex based on coverage in those regions.')
    else:
        info('WGS, determining sex based on chrY key regions coverage.')

    info('Detecting sex by comparing the Y chromosome key regions coverage and average coverage depth.')
    if not bam_fpath:
        critical(sample.name + ': BAM file is required.')
    index_bam(cnf, bam_fpath)

    chry_cov_output_fpath = sambamba_depth(cnf, male_genes_bed, bam_fpath)
    chry_mean_coverage = get_mean_cov(chry_cov_output_fpath)
    info('Y key regions average depth: ' + str(chry_mean_coverage))
    ave_depth = float(ave_depth)
    info('Sample average depth: ' + str(ave_depth))
    if ave_depth < AVE_DEPTH_THRESHOLD_TO_DETERMINE_SEX:
        info('Sample average depth is too low (less then ' + str(AVE_DEPTH_THRESHOLD_TO_DETERMINE_SEX) +
             ') - cannot determine sex')
        return None

    if chry_mean_coverage == 0:
        info('Y depth is 0 - it\s female')
        sex = 'F'
    else:
        factor = ave_depth / chry_mean_coverage
        info('Sample depth / Y depth = ' + str(factor))
        if factor > FEMALE_Y_COVERAGE_FACTOR:  # if mean target coverage much higher than chrY coverage
            info('Sample depth is more than ' + str(FEMALE_Y_COVERAGE_FACTOR) + ' times higher than Y depth - it\s female')
            sex = 'F'
        else:
            info('Sample depth is not more than ' + str(FEMALE_Y_COVERAGE_FACTOR) + ' times higher than Y depth - it\s male')
            sex = 'M'
    info('Sex is ' + sex)
    info()
    return sex


def get_mean_cov(bedcov_output_fpath):
    mean_cov = []
    mean_cov_col = None
    total_len = 0
    with open(bedcov_output_fpath) as bedcov_file:
        for line in bedcov_file:
            if line.startswith('#'):
                mean_cov_col = line.split('\t').index('meanCoverage')
                continue
            line_tokens = line.replace('\n', '').split()
            start, end = map(int, line_tokens[1:3])
            size = end - start
            mean_cov.append(float(line_tokens[mean_cov_col]) * size)
            total_len += size
    mean_cov = sum(mean_cov) / total_len if total_len > 0 else 0
    return mean_cov


def make_targqc_reports(cnf, output_dir, sample, bam_fpath, features_bed, features_no_genes_bed, target_bed, gene_keys_list):
    info('Starting targeqSeq for ' + sample.name + ', saving into ' + output_dir)
    gene_by_name_and_chrom = build_gene_objects_list(cnf, sample.name, features_bed, gene_keys_list)

    # ref_fapth = cnf.genome.seq
    original_target_bed = cnf.original_target_bed or target_bed
    target_info = TargetInfo(
        fpath=target_bed, bed=target_bed, original_target_bed=original_target_bed,
        genes_num=len(gene_by_name_and_chrom) if gene_by_name_and_chrom else None)
    if target_bed:
        target_info.regions_num = calc_region_number(target_bed)

    # if not cnf.no_dedup:
    #     sample.dedup_bam = intermediate_fname(cnf, bam_fpath, source.dedup_bam)
    #     remove_dups(cnf, bam_fpath, sample.dedup_bam)
    #     index_bam(cnf, sample.dedup_bam)

    _run_qualimap(cnf, sample, bam_fpath, target_bed)

    depth_stats, reads_stats, mm_indels_stats, target_stats = _parse_qualimap_results(
        sample.qualimap_html_fpath, sample.qualimap_cov_hist_fpath, cnf.coverage_reports.depth_thresholds)

    reads_stats['gender'] = _determine_sex(cnf, sample, cnf.bam, depth_stats['ave_depth'], target_bed)
    info()

    if 'bases_by_depth' in depth_stats:
        depth_stats['bases_within_threshs'], depth_stats['rates_within_threshs'] = calc_bases_within_threshs(
            depth_stats['bases_by_depth'],
            target_stats['target_size'] if target_bed else target_stats['reference_size'],
            cnf.coverage_reports.depth_thresholds)

        depth_stats['wn_20_percent'] = calc_rate_within_normal(
            depth_stats['bases_by_depth'],
            depth_stats['ave_depth'],
            target_stats['target_size'] if target_bed else target_stats['reference_size'])

    if target_stats['target_size']:
        target_info.bases_num = target_stats['target_size']
        target_info.fraction  = target_stats['target_fraction']
    else:
        target_info.bases_num = target_stats['reference_size']

    # if sample.dedup_bam:
    #     bam_fpath = sample.dedup_bam
    reads_stats['mapped_dedup'] = number_of_mapped_reads(cnf, bam_fpath, dedup=True)

    if target_info.bed:
        reads_stats['mapped_dedup_on_target'] = number_mapped_reads_on_target(cnf, target_bed, bam_fpath, dedup=True) or 0

    if target_info.bed:
        padded_bed = get_padded_bed_file(cnf, target_info.bed, get_chr_len_fpath(cnf), cnf.coverage_reports.padding)
        reads_stats['mapped_dedup_on_padded_target'] = number_mapped_reads_on_target(cnf, padded_bed, bam_fpath, dedup=True) or 0
    elif cnf.genome.cds:
        info('Using the CDS reference BED ' + cnf.genome.cds + ' to calc "reads on CDS"')
        reads_stats['mapped_dedup_on_exome'] = number_mapped_reads_on_target(cnf, cnf.genome.cds, bam_fpath, dedup=True) or 0
    # elif features_no_genes_bed:
    #     info('Using ensemble ' + features_no_genes_bed + ' to calc reads on exome')
    #     reads_stats['mapped_dedup_on_exome'] = number_mapped_reads_on_target(cnf, features_no_genes_bed, bam_fpath) or 0

    summary_report = make_summary_report(cnf, depth_stats, reads_stats, mm_indels_stats, sample, output_dir, target_info)

    info()
    avg_depth = depth_stats['ave_depth']
    per_gene_report = make_per_gene_report(cnf, sample, bam_fpath, target_bed, features_bed,
               features_no_genes_bed, output_dir, gene_by_name_and_chrom, avg_depth=avg_depth)

    # key_genes_report = make_key_genes_reports(cnf, sample, gene_by_name, depth_stats['ave_depth'])

    info()
    info('-' * 70)
    return avg_depth, gene_by_name_and_chrom, [summary_report, per_gene_report]


def get_records_by_metrics(records, metrics):
    _records = []
    for rec in records:
        if rec.metric.name in metrics:
            rec.metric = metrics[rec.metric.name]
            _records.append(rec)
    return _records


def make_summary_report(cnf, depth_stats, reads_stats, mm_indels_stats, sample, output_dir, target_info):
    report = SampleReport(sample, metric_storage=get_header_metric_storage(
        cnf.coverage_reports.depth_thresholds, is_wgs=target_info.bed is None, padding=cnf.coverage_reports.padding))
    report.add_record('Qualimap', value='Qualimap', url=relpath(sample.qualimap_html_fpath, output_dir), silent=True)
    if reads_stats.get('gender') is not None:
        report.add_record('Sex', reads_stats['gender'], silent=True)

    info('* General coverage statistics *')
    report.add_record('Reads', reads_stats['total'])
    report.add_record('Mapped reads', reads_stats['mapped'])
    # report.add_record('Unmapped reads', reads_stats['totaAvgl'] - reads_stats['mapped'])
    percent_mapped = 1.0 * (reads_stats['mapped'] or 0) / reads_stats['total'] if reads_stats['total'] else None
    assert percent_mapped <= 1.0 or percent_mapped is None, str(percent_mapped)
    report.add_record('Percentage of mapped reads', percent_mapped)
    # percent_unmapped = 1.0 * (reads_stats['total'] - reads_stats['mapped']) / reads_stats['total'] if reads_stats['total'] else None
    # assert percent_unmapped <= 1.0 or percent_unmapped is None, str(percent_unmapped)
    # report.add_record('Percentage of unmapped reads', percent_unmapped)
    if reads_stats.get('mapped_paired') is not None:
        total_paired_reads_pecent = 1.0 * (reads_stats['mapped_paired'] or 0) / reads_stats['total'] if reads_stats['total'] else None
        assert total_paired_reads_pecent <= 1.0 or total_paired_reads_pecent is None, str(total_paired_reads_pecent)
        report.add_record('Properly paired mapped reads percent', total_paired_reads_pecent)
    if reads_stats.get('paired') is not None:
        total_paired_reads_pecent = 1.0 * (reads_stats['paired'] or 0) / reads_stats['total'] if reads_stats['total'] else None
        assert total_paired_reads_pecent <= 1.0 or total_paired_reads_pecent is None, str(total_paired_reads_pecent)
        report.add_record('Properly paired reads percent', total_paired_reads_pecent)
    # if dedup_bam_stats:
    # dup_rate = 1 - (1.0 * dedup_bam_stats['mapped'] / bam_stats['mapped']) if bam_stats['mapped'] else None
    report.add_record('Duplication rate', reads_stats['dup_rate'])
    # report.add_record('Dedupped mapped reads', reads_stats['mapped'] - reads_stats[''])

    info('')

    if target_info.bed:
        info('* Target coverage statistics *')
        if target_info.original_target_bed:
            report.add_record('Target', target_info.original_target_bed)
            if count_bed_cols(target_info.original_target_bed) == 3:
                report.add_record('Ready target (sorted and annotated)', target_info.fpath)
        else:
            report.add_record('Target', target_info.fpath)
        report.add_record('Bases in target', target_info.bases_num)
        report.add_record('Percentage of reference', target_info.fraction)
        report.add_record('Regions in target', target_info.regions_num)
    else:
        info('* Genome coverage statistics *')
        report.add_record('Target', 'whole genome')
        report.add_record('Reference size', target_info.bases_num)

    report.add_record('Genes in target', target_info.genes_num)

    trg_type = 'target' if target_info.bed else 'genome'

    if 'bases_within_threshs' in depth_stats:
        bases_within_threshs = depth_stats['bases_within_threshs']
        v_covered_bases_in_targ = bases_within_threshs.items()[0][1]
        v_percent_covered_bases_in_targ = 1.0 * (v_covered_bases_in_targ or 0) / target_info.bases_num if target_info.bases_num else None
        assert v_percent_covered_bases_in_targ <= 1.0 or v_percent_covered_bases_in_targ is None, str(v_percent_covered_bases_in_targ)

        report.add_record('Covered bases in ' + trg_type, v_covered_bases_in_targ)
        report.add_record('Percentage of ' + trg_type + ' covered by at least 1 read', v_percent_covered_bases_in_targ)

    if target_info.bed:
        info('Getting number of mapped reads on target...')
        # mapped_reads_on_target = number_mapped_reads_on_target(cnf, target_info.bed, bam_fpath)
        if 'mapped_dedup_on_target' in reads_stats:
            # report.add_record('Reads mapped on target', reads_stats['mapped_on_target'])
            info('Unique mapped on target: ' + str(reads_stats['mapped_dedup_on_target']))
            percent_mapped_dedup_on_target = 1.0 * reads_stats['mapped_dedup_on_target'] / reads_stats['mapped_dedup'] if reads_stats['mapped_dedup'] != 0 else None
            report.add_record('Percentage of reads mapped on target', percent_mapped_dedup_on_target)
            assert percent_mapped_dedup_on_target <= 1.0 or percent_mapped_dedup_on_target is None, str(percent_mapped_dedup_on_target)

            percent_mapped_dedup_off_target = 1.0 * (reads_stats['mapped_dedup'] - reads_stats['mapped_dedup_on_target']) / reads_stats['mapped_dedup'] if reads_stats['mapped_dedup'] != 0 else None
            report.add_record('Percentage of reads mapped off target', percent_mapped_dedup_off_target)
            assert percent_mapped_dedup_off_target <= 1.0 or percent_mapped_dedup_off_target is None, str(percent_mapped_dedup_off_target)

            percent_usable = 1.0 * reads_stats['mapped_dedup_on_target'] / reads_stats['total'] if reads_stats['total'] != 0 else None
            report.add_record('Percentage of usable reads', percent_usable)
            assert percent_usable <= 1.0 or percent_usable is None, str(percent_usable)

        read_bases_on_targ = int(target_info.bases_num * depth_stats['ave_depth'])  # sum of all coverages
        report.add_record('Read bases mapped on target', read_bases_on_targ)

        if 'mapped_dedup_on_padded_target' in reads_stats:
            # report.add_record('Reads mapped on padded target', reads_stats['mapped_reads_on_padded_target'])
            percent_mapped_on_padded_target = 1.0 * reads_stats['mapped_dedup_on_padded_target'] / reads_stats['mapped_dedup'] if reads_stats['mapped_dedup'] else None
            report.add_record('Percentage of reads mapped on padded target', percent_mapped_on_padded_target)
            assert percent_mapped_on_padded_target <= 1.0 or percent_mapped_on_padded_target is None, str(percent_mapped_on_padded_target)

    elif 'mapped_dedup_on_exome' in reads_stats:
        # report.add_record('Reads mapped on target', reads_stats['mapped_on_target'])
        percent_mapped_on_exome = 1.0 * reads_stats['mapped_dedup_on_exome'] / reads_stats['mapped_dedup'] if reads_stats['mapped_dedup'] != 0 else None
        if percent_mapped_on_exome:
            report.add_record('Percentage of reads mapped on exome', percent_mapped_on_exome)
            assert percent_mapped_on_exome <= 1.0 or percent_mapped_on_exome is None, str(percent_mapped_on_exome)
            percent_mapped_off_exome = 1.0 - percent_mapped_on_exome
            report.add_record('Percentage of reads mapped off exome ', percent_mapped_off_exome)

        percent_usable = 1.0 * reads_stats['mapped_dedup'] / reads_stats['total'] if reads_stats['total'] != 0 else None
        report.add_record('Percentage of usable reads', percent_usable)
        assert percent_usable <= 1.0 or percent_usable is None, str(percent_usable)

    info('')
    report.add_record('Average ' + trg_type + ' coverage depth', depth_stats['ave_depth'])
    if cnf.downsampled and cnf.fastqc_dirpath:
        full_reads_number = get_total_reads_number_from_fastqc(sample.name, cnf.fastqc_dirpath)
        if full_reads_number:
            est_full_cov = (full_reads_number * percent_mapped / reads_stats['total']) * depth_stats['ave_depth']
            report.add_record('Estimated ' + trg_type + ' full coverage', est_full_cov)
    report.add_record('Median ' + trg_type + ' coverage depth', depth_stats['median_depth'])
    report.add_record('Std. dev. of ' + trg_type + ' coverage depth', depth_stats['stddev_depth'])
    # report.add_record('Minimal ' + trg_type + ' coverage depth', depth_stats['min_depth'])
    # report.add_record('Maximum ' + trg_type + ' coverage depth', depth_stats['max_depth'])
    if 'wn_20_percent' in depth_stats:
        report.add_record('Percentage of ' + trg_type + ' within 20% of mean depth', depth_stats['wn_20_percent'])
        assert depth_stats['wn_20_percent'] <= 1.0 or depth_stats['wn_20_percent'] is None, str( depth_stats['wn_20_percent'])

    if 'bases_within_threshs' in depth_stats:
        for depth, bases in depth_stats['bases_within_threshs'].items():
            fraction_val = 1.0 * (bases or 0) / target_info.bases_num if target_info.bases_num else 0
            if fraction_val > 0:
                report.add_record('Part of ' + trg_type + ' covered at least by ' + str(depth) + 'x', fraction_val)
            assert fraction_val <= 1.0 or fraction_val is None, str(fraction_val)
    info()

    report.add_record('Read mean length', reads_stats['ave_len'])
    report.add_record('Read min length', reads_stats['min_len'])
    report.add_record('Read max length', reads_stats['max_len'])
    report.add_record('Mean Mapping Quality', mm_indels_stats['mean_mq'])
    report.add_record('Mismatches', mm_indels_stats['mismatches'])
    report.add_record('Insertions', mm_indels_stats['insertions'])
    report.add_record('Deletions', mm_indels_stats['deletions'])
    report.add_record('Homopolymer indels', mm_indels_stats['homo_indels'])

    report.save_json(join(output_dir, sample.name + '.' + source.targetseq_name + '.json'))
    report.save_txt(join(output_dir, sample.name + '.' + source.targetseq_name + '.txt'))
    report.save_html(cnf, join(output_dir, sample.name + '.' + source.targetseq_name + '.html'), caption='Target coverage statistics for ' + sample.name)
    info()
    info('Saved to ')
    info('  ' + report.txt_fpath)
    return report


def make_per_gene_report(cnf, sample, bam_fpath, target_bed, features_bed, features_no_genes_bed, output_dir, gene_by_name_and_chrom,
                         avg_depth=None):
    info('-' * 70)
    info('Detailed exon-level report')

    if cnf.reuse_intermediate and verify_file(sample.targetcov_detailed_tsv, silent=True):
        info(sample.targetcov_detailed_tsv + ' exists, reusing')
        rep = PerRegionSampleReport()
        rep.txt_fpath = sample.targetcov_detailed_txt
        rep.tsv_fpath = sample.targetcov_detailed_tsv
        with open(sample.targetcov_detailed_tsv) as f:
            for l in f:
                rep.rows.append(1)
                fs = l.strip().split('\t')

                if len(fs) < 13 or l.startswith('#'):
                    continue
                chrom, start, end, size, gene_name, strand, feature, biotype, transcript_id, min_depth, avg_depth, std_dev, wn20ofmean = fs[:13]

                if gene_name != '.':
                    region = Region(gene_name=gene_name, transcript_id=transcript_id, exon_num=None,
                         strand=strand, biotype=biotype, feature=feature, extra_fields=list(), chrom=chrom,
                         start=int(start) if start != '.' else None,
                         end=int(end) if end != '.' else None,
                         size=int(size) if size != '.' else None,
                         min_depth=float(min_depth) if min_depth != '.' else None,
                         avg_depth=float(avg_depth) if avg_depth != '.' else None,
                         std_dev=float(std_dev) if std_dev != '.' else None,
                         rate_within_normal=float(wn20ofmean) if wn20ofmean and wn20ofmean != '.' else None,)
                    if (gene_name, chrom) not in gene_by_name_and_chrom:
                        continue
                    region.sample_name = gene_by_name_and_chrom[(gene_name, chrom)].sample_name
                    depth_thresholds = cnf.coverage_reports.depth_thresholds
                    rates_within_threshs = OrderedDict((depth, None) for depth in depth_thresholds)
                    rates = fs[-(len(depth_thresholds)):]
                    for i, t in enumerate(rates_within_threshs):
                        rates_within_threshs[t] = float(rates[i]) if rates[i] != '.' else None
                    region.rates_within_threshs = rates_within_threshs
                    if 'Capture' in feature:
                        gene_by_name_and_chrom[(gene_name, chrom)].add_amplicon(region)
                    elif 'CDS' in feature or feature == 'Exon':
                        gene_by_name_and_chrom[(gene_name, chrom)].add_exon(region)
                    else:
                        gene_by_name_and_chrom[(gene_name, chrom)].chrom = region.chrom
                        gene_by_name_and_chrom[(gene_name, chrom)].strand = region.strand
                        gene_by_name_and_chrom[(gene_name, chrom)].avg_depth = region.avg_depth
                        gene_by_name_and_chrom[(gene_name, chrom)].min_depth = region.min_depth
                        gene_by_name_and_chrom[(gene_name, chrom)].rates_within_threshs = region.rates_within_threshs
        return rep

    else:
        per_gene_report = None
        if features_bed or target_bed:
            per_gene_report = _generate_report_from_bam(cnf, sample, bam_fpath, target_bed, features_no_genes_bed,
                                                        gene_by_name_and_chrom, avg_depth)
            #per_gene_report = _generate_report_from_regions(
            #        cnf, sample, output_dir, gene_by_name_and_chrom.values(), un_annotated_amplicons)

        return per_gene_report


def _generate_report_from_regions(cnf, sample, output_dir, genes, un_annotated_amplicons):
    final_regions = []

    info('Combining all regions for final report...')
    i = 0
    for gene in genes:
        if gene.gene_name != '.':
            if i and i % 100000 == 0:
                info('Processed {0:,} genes, current gene {1}'.format(i, gene.gene_name))
            i += 1

            final_regions.extend(gene.get_amplicons())
            final_regions.extend(gene.get_exons())
            final_regions.append(gene)

    un_annotated_summary_region = next((g for g in genes if g.gene_name == '.'), None)
    if un_annotated_summary_region and un_annotated_amplicons:
        un_annotated_summary_region.feature = 'NotAnnotatedSummary'
        for ampl in un_annotated_amplicons:
            ampl.gene_name = un_annotated_summary_region.gene_name
            un_annotated_summary_region.add_amplicon(ampl)
            final_regions.append(ampl)
        final_regions.append(un_annotated_summary_region)
    info('Processed {0:,} genes.'.format(i))

    info()
    info('Summing up region stats...')
    i = 0
    for region in final_regions:
        i += 1
        if i % 10000 == 0:
            info('Processed {0:,} regions.'.format(i))
        region.sum_up(cnf.coverage_reports.depth_thresholds)

    info('Saving report...')
    report = make_flat_region_report(sample, final_regions, cnf.coverage_reports.depth_thresholds)
    report.save_txt(sample.targetcov_detailed_txt)
    report.save_tsv(sample.targetcov_detailed_tsv)
    info('')
    info('Regions (total ' + str(len(final_regions)) + ') saved into:')
    info('  ' + report.txt_fpath)

    return report


def get_detailed_metric_storage(depth_threshs):
    return MetricStorage(
        general_section=ReportSection(metrics=[
            Metric('Sample'),
        ]),
        sections=[ReportSection(metrics=[
            Metric('Chr'),
            Metric('Start'),
            Metric('End'),
            Metric('Size'),
            Metric('Gene'),
            Metric('Strand'),
            Metric('Feature'),
            Metric('Biotype'),
            Metric('Transcript'),
            Metric('Min depth'),
            Metric('Ave depth'),
            Metric('Std dev', description='Coverage depth standard deviation'),
            Metric('W/n 20% of ave depth', description='Percentage of the region that lies within 20% of an avarage depth.', unit='%'),
            # Metric('Norm depth', description='Ave region depth devided by median depth of sample'),
        ] + [
            Metric('{}x'.format(thresh), description='Bases covered by at least {} reads'.format(thresh), unit='%')
            for thresh in depth_threshs
        ])]
    )


def make_flat_region_report(sample, regions, depth_threshs):
    report = PerRegionSampleReport(sample=sample, metric_storage=get_detailed_metric_storage(depth_threshs))
    report.add_record('Sample', sample.name)

    i = 0
    for region in regions:
        i += 1
        if i % 10000 == 0:
            info('Processed {0:,} regions.'.format(i))
        add_region_to_report(report, region, depth_threshs)

    info('Processed {0:,} regions.'.format(i))
    return report


def _unique_longest_exons(cnf, exons_bed_fpath):
    unique_exons_dict = OrderedDict()

    with open(exons_bed_fpath) as f:
        for line in f:
            if not line.strip() or line.startswith('#'):
                continue

            ts = line.split()

            if len(ts) < 4:
                pass

            elif len(ts) < 5:
                chrom, start, end, gene = ts
                unique_exons_dict[(gene, '')] = ts

            else:
                chrom, start, end, gene, exon_num = ts[:5]
                prev_ts = unique_exons_dict.get((gene, exon_num))
                if not prev_ts:
                    unique_exons_dict[(gene, exon_num)] = ts
                else:
                    size = int(ts[2]) - int(ts[1])
                    prev_size = int(prev_ts[2]) - int(prev_ts[1])
                    if size > prev_size:
                        unique_exons_dict[(gene, exon_num)] = ts

    unique_bed_fpath = intermediate_fname(cnf, exons_bed_fpath, 'uniq')
    with open(unique_bed_fpath, 'w') as f:
        for ts in unique_exons_dict.values():
            f.write('\t'.join(ts) + '\n')

    info('Saved to ' + unique_bed_fpath)
    return unique_bed_fpath


def _generate_report_from_bam(cnf, sample, bam, target_bed, features_no_genes_bed, gene_by_name_and_chrom, avg_depth):
    depth_thresholds = cnf.coverage_reports.depth_thresholds
    if avg_depth:
        key_gene_cov_threshold = max(1, int(avg_depth / 2))
        depth_thresholds.append(key_gene_cov_threshold)
        depth_thresholds.sort()
    sample_name = sample.name

    report = PerRegionSampleReport(sample=sample, metric_storage=get_detailed_metric_storage(depth_thresholds))
    report.add_record('Sample', sample.name)
    report.txt_fpath = sample.targetcov_detailed_txt
    report.tsv_fpath = sample.targetcov_detailed_tsv

    ready_to_report_genes = []
    ready_to_report_set = set()

    first_txt_rows = report.flatten(None, human_readable=True)
    col_widths = get_col_widths(first_txt_rows)
    col_widths[6] = len('Gene-Exon')

    #####################################
    #####################################
    for (bed, feature) in zip([target_bed, features_no_genes_bed], ['amplicons', 'exons']):  # features are canonical
        if not bed:
            continue
        info()
        info('Calculating coverage statistics for ' + ('CDS and miRNA exons...' if feature == 'exons' else 'the regions in the target BED file...'))

        sambamba_depth_output_fpath = sambamba_depth(cnf, bed, bam, depth_thresholds=depth_thresholds)
        if not sambamba_depth_output_fpath:
            continue
        regions = parse_sambamba_depth_output(sample_name, sambamba_depth_output_fpath, depth_thresholds, feature)
        info('Total genes: ' + str(len(ready_to_report_genes)) + ', total regions: ' + str(len(regions)))

        # #####################################
        # #####################################
        # info('Second round of sambamba depth - calculating depth within 20% bounds of average depth')
        # sambamba_depth_output_fpath = sambamba_depth(cnf, bed, bam, depth_thresholds=[int()])
        # if not sambamba_depth_output_fpath:
        #     continue
        #
        # info('Adding rates within normal...')
        # with open(sambamba_depth_output_fpath) as sambabma_depth_file:
        #     total_regions_count = 0
        #     for region, line in zip(regions, (l for l in sambabma_depth_file if not l.startswith('#'))):
        #         line_tokens = line.replace('\n', '').split()
        #         rate_within_low_bound = line_tokens[std_dev_col + 1]
        #         rate_within_higher_bound = line_tokens[std_dev_col + 2]
        #         regions.rate_within_normal = rate_within_low_bound - rate_within_higher_bound
        #
        #         total_regions_count += 1
        #         if total_regions_count > 0 and total_regions_count % 10000 == 0:
        #              info('  Processed {0:,} regions'.format(total_regions_count))
        #     info('Processed {0:,} regions'.format(total_regions_count))

        #####################################
        #####################################
        info('Preparing report rows...')
        total_regions_count = 0
        cur_unannotated_gene = None
        for region in regions:
            if region.feature == 'Capture':
                if region.gene_name != '.':
                    cur_unannotated_gene = None
                    gene = gene_by_name_and_chrom[(region.gene_name, region.chrom)]
                    if (gene.gene_name, gene.chrom) not in ready_to_report_set:
                        ready_to_report_genes.append(gene)
                        ready_to_report_set.add((gene.gene_name, gene.chrom))
                    gene.add_amplicon(region)
                else:
                    if cur_unannotated_gene is None:
                        cur_unannotated_gene = GeneInfo(sample_name=region.sample_name,
                            gene_name=region.gene_name, chrom=region.chrom, feature='NotAnnotatedSummary')
                        ready_to_report_genes.append(cur_unannotated_gene)
                    cur_unannotated_gene.add_amplicon(region)

            else:
                gene = gene_by_name_and_chrom[(region.gene_name, region.chrom)]
                gene.add_exon(region)
                if not target_bed:  # in case if only reporting based on features_bed
                    if (gene.gene_name, gene.chrom) not in ready_to_report_set:
                        ready_to_report_genes.append(gene)
                        ready_to_report_set.add((gene.gene_name, gene.chrom))

            row = [region.chrom, region.start, region.end, region.get_size(), region.gene_name, region.strand,
                   region.feature, region.biotype, region.transcript_id, region.min_depth, region.avg_depth, region.std_dev,
                   region.rate_within_normal]
            row = [Metric.format_value(val, human_readable=True) for val in row]
            rates = [Metric.format_value(val, unit='%', human_readable=True) for val in region.rates_within_threshs.values()]
            row.extend(rates)
            col_widths = [max(len(v), w) for v, w in izip(row, col_widths)]

            total_regions_count += 1
            if total_regions_count > 0 and total_regions_count % 10000 == 0:
                 info('  Processed {0:,} regions'.format(total_regions_count))
        info('Processed {0:,} regions'.format(total_regions_count))

    #####################################
    #####################################
    safe_mkdir(dirname(report.tsv_fpath))
    write_tsv_rows(report.flatten(None, human_readable=False), report.tsv_fpath)
    write_txt_rows(first_txt_rows, report.txt_fpath, col_widths=col_widths)
    fpaths_to_write = [report.tsv_fpath, report.txt_fpath]

    for g in ready_to_report_genes:
        debug(g.gene_name, ending=', ', print_date=False)
        for a in g.get_amplicons():
            add_region_to_report(report, a, depth_thresholds, fpaths_to_write, col_widths=col_widths)
        for e in g.get_exons():
            add_region_to_report(report, e, depth_thresholds, fpaths_to_write, col_widths=col_widths)
        if g.get_exons():
            process_gene(g, depth_thresholds)
            add_region_to_report(report, g, depth_thresholds, fpaths_to_write, col_widths=col_widths)

    info(print_date=True)

    # un_annotated_summary_region = next((g for g in gene_by_name_and_chrom.values() if g.gene_name == '.'), None)
    # if un_annotated_summary_region and un_annotated_amplicons:
    #     un_annotated_summary_region.feature = 'NotAnnotatedSummary'
    #     for ampl in un_annotated_amplicons:
    #         ampl.gene_name = un_annotated_summary_region.gene_name
    #         un_annotated_summary_region.add_amplicon(ampl)
    #         add_region_to_report(report, ampl, depth_thresholds)
    #     add_region_to_report(report, un_annotated_summary_region, depth_thresholds)

    #report.save_txt(sample.targetcov_detailed_txt)
    #report.save_tsv(sample.targetcov_detailed_tsv)
    info('')
    info('Regions (total ' + str(len(report.rows)) + ') saved into:')
    info('  ' + report.txt_fpath)
    return report


def parse_sambamba_depth_output(sample_name, sambamba_depth_output_fpath, depth_thresholds=None, feature=None):
    regions = []

    read_count_col = None
    mean_cov_col = None
    min_depth_col = None
    std_dev_col = None

    #####################################
    #####################################
    cur_unannotated_gene = None
    info('Reading coverage statistics...')
    with open(sambamba_depth_output_fpath) as sambabma_depth_file:
        total_regions_count = 0
        for line in sambabma_depth_file:
            if line.startswith('#'):
                read_count_col = line.split('\t').index('readCount')
                mean_cov_col = line.split('\t').index('meanCoverage')
                min_depth_col = line.split('\t').index('minDepth')
                std_dev_col = line.split('\t').index('stdDev')
                continue
            line_tokens = line.replace('\n', '').split()
            chrom = line_tokens[0]
            start, end = map(int, line_tokens[1:3])
            region_size = end - start
            gene_name = line_tokens[3] if read_count_col != 3 else None
            ave_depth = float(line_tokens[mean_cov_col])
            min_depth = int(line_tokens[min_depth_col]) if min_depth_col else None
            std_dev = float(line_tokens[std_dev_col]) if std_dev_col else None
            rates_within_threshs = line_tokens[std_dev_col + 1:-1]

            extra_fields = tuple(line_tokens[4:read_count_col]) if read_count_col > 4 else ()

            region = Region(
                sample_name=sample_name, chrom=chrom,
                start=start, end=end, size=region_size,
                avg_depth=ave_depth,
                gene_name=gene_name, extra_fields=extra_fields)
            regions.append(region)

            if depth_thresholds:
                region.rates_within_threshs = OrderedDict((depth, float(rate) / 100.0) for (depth, rate) in zip(depth_thresholds, rates_within_threshs))
            region.min_depth = min_depth
            region.std_dev = std_dev

            if feature == 'amplicons':
                region.feature = 'Capture'
            else:
                if extra_fields:
                    region.exon_num = extra_fields[0]
                    if len(extra_fields) >= 2:
                        region.strand = extra_fields[1]
                    if len(extra_fields) >= 3:
                        region.feature = extra_fields[2]
                    else:
                        region.feature = 'CDS'
                    if len(extra_fields) >= 4:
                        region.biotype = extra_fields[3]
                    if len(extra_fields) >= 5:
                        region.transcript_id = extra_fields[4]

            total_regions_count += 1
            if total_regions_count > 0 and total_regions_count % 10000 == 0:
                 info('  Processed {0:,} regions'.format(total_regions_count))
    return regions


def process_gene(gene, depth_thresholds):
    gene.rates_within_threshs = OrderedDict((depth, None) for depth in depth_thresholds)
    if gene.size == 0:
        gene.start = None
        gene.end = None
        return
    exons = gene.get_exons()
    if not exons:
        return

    total_depth = sum(e.avg_depth * e.size for e in exons)
    gene.size = sum(e.size for e in exons)
    gene.avg_depth = total_depth / gene.size
    sum_of_sq_var = sum((((e.avg_depth - e.std_dev) - gene.avg_depth) ** 2 + ((e.avg_depth + e.std_dev) - gene.avg_depth) ** 2) * e.size for e in exons)
    gene.std_dev = math.sqrt(sum_of_sq_var / 2 / float(gene.size))
    for t in depth_thresholds:
        total_rate = sum(e.rates_within_threshs[t] * e.size for e in exons)
        rate = total_rate / gene.size
        gene.rates_within_threshs[t] = rate


def add_region_to_report(report, region, depth_threshs, fpaths_to_write=None, col_widths=None):
    if fpaths_to_write:
        report.rows.append(1)
        rep_region = Row(parent_report=report)
    else:
        rep_region = report.add_row()
    rep_region.add_record('Chr', region.chrom)
    rep_region.add_record('Start', region.start)
    rep_region.add_record('End', region.end)
    rep_region.add_record('Size', region.get_size())
    rep_region.add_record('Gene', region.gene_name)
    rep_region.add_record('Strand', region.strand)
    rep_region.add_record('Feature', region.feature)
    rep_region.add_record('Biotype', region.biotype)
    rep_region.add_record('Transcript', region.transcript_id)
    rep_region.add_record('Min depth', region.min_depth)
    rep_region.add_record('Ave depth', region.avg_depth)
    rep_region.add_record('Std dev', region.std_dev)
    rep_region.add_record('W/n 20% of ave depth', region.rate_within_normal)

    if region.rates_within_threshs is None:
        warn('Error: no rates_within_threshs for ' + str(region))
    for thresh in depth_threshs:
        rep_region.add_record('{}x'.format(thresh), region.rates_within_threshs.get(thresh) if region.rates_within_threshs else None)

    if fpaths_to_write:
        for fpath in fpaths_to_write:
            human_readable = fpath.endswith('txt')
            flat_row = []
            for m in report.metric_storage.get_metrics(None, skip_general_section=True):
                rec = BaseReport.find_record(rep_region.records, m.name)
                if rec:
                    flat_row.append(rec.format(human_readable=human_readable))

            with open(fpath, 'a') as out:
                if fpath.endswith('tsv'):
                    out.write('\t'.join([val for val in flat_row]) + '\n')
                else:
                    for val, w in izip(flat_row, col_widths):
                                out.write(val + (' ' * (w - len(val) + 2)))
                    out.write('\n')


def get_total_reads_number_from_fastqc(sample, fastqc_dirpath):
    fastqc_txt_fpaths = find_fastqc_txt(sample, fastqc_dirpath)
    if not fastqc_txt_fpaths:
        return
    num_reads = 0
    for fpath in fastqc_txt_fpaths:
        with open(fpath) as f_in:
            for line in f_in:
                if 'total sequences' in line.lower():
                    num_reads += int(line.strip().split('\t')[-1])
                    break
    return num_reads


def find_fastqc_txt(sample_name, fastqc_dirpath):
    l_fastqc_dirpath = join(fastqc_dirpath, sample_name + '_R1_fastqc')
    r_fastqc_dirpath = join(fastqc_dirpath, sample_name + '_R2_fastqc')
    fastqc_txt_fpaths = [join(l_fastqc_dirpath, 'fastqc_data.txt'), join(r_fastqc_dirpath, 'fastqc_data.txt')]
    if all(isfile(fpath) for fpath in fastqc_txt_fpaths):
        return fastqc_txt_fpaths
    else:
        return None


# def _bases_by_depth(depth_vals, depth_thresholds):
#     bases_by_min_depth = {depth: 0 for depth in depth_thresholds}
#
#     for depth_value in depth_vals:
#         for threshold in depth_thresholds:
#             if depth_value >= threshold:
#                 bases_by_min_depth[threshold] += 1
#
#         return [1.0 * bases_by_min_depth[thres] / len(depth_vals) if depth_vals else 0
#                 for thres in depth_thresholds]


