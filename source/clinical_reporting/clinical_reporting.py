from collections import OrderedDict
from json import load, dump, JSONEncoder, dumps
import os
from os.path import join, islink, dirname, abspath, relpath

import source
from source import verify_file, info
from source.file_utils import add_suffix, verify_module
from source.file_utils import adjust_path
from source.reporting import MetricStorage, Metric, PerRegionSampleReport, ReportSection, SampleReport, \
    calc_cell_contents, make_cell_td, write_static_html_report, make_cell_th
from source.targetcov.flag_regions import get_depth_cutoff
from source.targetcov.summarize_targetcov import get_float_val, get_val
from source.utils import is_local


def make_key_gene_cov_report(cnf, sample, key_gene_names, ave_depth):
    info('Preparing coverage stats key gene tables')

    depth_cutoff = get_depth_cutoff(ave_depth, cnf.coverage_reports.depth_thresholds)

    stats_by_genename = dict()
    with open(sample.targetcov_detailed_tsv) as f_inp:
        for l in f_inp:
            if not l.startswith('#') and ('Whole-Gene' in l or 'Gene-Exon' in l):
                fs = l.split('\t')
                chrom = get_val(fs[0])
                gene_name = get_val(fs[4])
                gene_ave_depth = get_float_val(fs[9])
                if gene_name in key_gene_names:
                    for t, field in zip(cnf.coverage_reports.depth_thresholds, fs[12:]):
                        if int(t) == depth_cutoff:
                            stats_by_genename[gene_name] = chrom, gene_ave_depth, get_float_val(field)
                            continue

    clinical_cov_metrics = [
        Metric('Gene'),
        Metric('Chr', with_heatmap=False, style="text-align: right"),
        Metric('Ave depth', med=ave_depth),
        Metric('% cov at {}x'.format(depth_cutoff), unit='%', med=1, low_inner_fence=0.5, low_outer_fence=0.1)]
    seq2c_tsv = cnf.seq2c_tsv_fpath
    seq2c_data_by_genename = dict()
    if verify_file(seq2c_tsv, silent=True):
        with open(seq2c_tsv) as f_inp:
            for i, l in enumerate(f_inp):
                if i == 0:
                    continue
                fs = l.strip().split('\t')
                gene_name = fs[1]
                if fs[0] == sample.name and gene_name in key_gene_names and fs[9] in ['Del', 'Amp']:
                    seq2c_data_by_genename[gene_name] = fs[9] + ', ' + fs[8]
        if seq2c_data_by_genename:
            clinical_cov_metrics.append(Metric('SNV'))

    clinical_cov_metric_storage = MetricStorage(
        sections=[ReportSection(metrics=clinical_cov_metrics)])
    key_genes_report = PerRegionSampleReport(sample=sample, metric_storage=clinical_cov_metric_storage)
    for gene_name in sorted(key_gene_names):
        chrom, gene_ave_depth, depth_in_thresh = stats_by_genename.get(gene_name, (None, None, None))
        reg = key_genes_report.add_region()
        reg.add_record('Gene', gene_name)
        reg.add_record('Chr', chrom.replace('chr', '') if chrom else None)
        reg.add_record('Ave depth', gene_ave_depth)
        m = clinical_cov_metric_storage.find_metric('% cov at {}x'.format(depth_cutoff))
        reg.add_record(m.name, depth_in_thresh)
        if seq2c_data_by_genename:
            reg.add_record('SNV', seq2c_data_by_genename[gene_name] if gene_name in seq2c_data_by_genename else '')

    key_genes_report.save_tsv(sample.clinical_targqc_tsv, human_readable=True)
    info('Saved coverage report to ' + key_genes_report.tsv_fpath)
    info('-' * 70)
    info()
    return key_genes_report, seq2c_data_by_genename


def get_target_fraction(sample, targqc_json_fpath):
    with open(targqc_json_fpath) as f:
        data = load(f, object_pairs_hook=OrderedDict)
    sr = SampleReport.load(data, sample, None)
    r = sr.find_record(sr.records, 'Percentage of target covered by at least 1 read')
    if not r:
        r = sr.find_record(sr.records, 'Percentage of genome covered by at least 1 read')
    return r.value if r else None


def get_gender(sample, targqc_json_fpath):
    with open(targqc_json_fpath) as f:
        data = load(f, object_pairs_hook=OrderedDict)
    sr = SampleReport.load(data, sample, None)
    r = sr.find_record(sr.records, 'Gender')
    return r.value if r else None


def get_ave_coverage(sample, targqc_json_fpath):
    with open(targqc_json_fpath) as f:
        data = load(f, object_pairs_hook=OrderedDict)
    sr = SampleReport.load(data, sample, None)
    r = sr.find_record(sr.records, 'Average target coverage depth')
    if not r:
        r = sr.find_record(sr.records, 'Average genome coverage depth')
    return r.value if r else None


def get_min_coverage(sample, targqc_json_fpath):
    with open(targqc_json_fpath) as f:
        data = load(f, object_pairs_hook=OrderedDict)
    sr = SampleReport.load(data, sample, None)
    r = sr.find_record(sr.records, 'Minimum target coverage depth')
    if not r:
        r = sr.find_record(sr.records, 'Minimum genome coverage depth')
    return r.value if r else None


def get_total_variants_number(sample, varqc_json_fpath):
    with open(varqc_json_fpath) as f:
        data = load(f, object_pairs_hook=OrderedDict)
    sr = SampleReport.load(data, sample, None)
    r = sr.find_record(sr.records, 'Total with rejected')
    return r.value if r else None


def is_sample_presents_in_file(sample_name, mutations_fpath):
    with open(mutations_fpath) as f:
        for i, l in enumerate(f):
            if i == 0:
                continue
            fs = l.strip().split('\t')
            if fs[0] == sample_name:
                return True
    return False

def make_mutations_report(cnf, sample, key_gene_names, mutations_fpath):
    info('Preparing mutations stats for key gene tables')

    clinical_mut_metric_storage = MetricStorage(
        sections=[ReportSection(metrics=[
            Metric('Gene'),  # Gene & Transcript
            Metric('Transcript'),  # Gene & Transcript
            Metric('Codon chg', style='max-width: 80px; min-width: 80px;', class_='long_line'),            # c.244G>A
            Metric('AA chg', style='max-width: 80px; min-width: 80px;', class_='long_line'),            # p.Glu82Lys
            # Metric('Allele'),             # Het.
            Metric('Chr', with_heatmap=False, style="text-align: right"),       # chr11
            Metric('Position'),       # g.47364249
            Metric('Change', style='max-width: 80px; min-width: 80px;', class_='long_line'),       # G>A
            Metric('Depth'),              # 658
            Metric('Frequency', unit='%', with_heatmap=False),          # .19
            Metric('AA length', with_heatmap=False),          # 128
            Metric('dbSNP', class_='long_line', style="max-width: 80px; min-width: 80px;"),                 # rs352343, COSM2123
            Metric('COSMIC', class_='long_line', style="max-width: 80px; min-width: 80px;"),                 # rs352343, COSM2123
            Metric('Type', style='max-width: 100px; min-width: 100px;', class_='long_line'),               # Frameshift
            Metric('Classification'),     # Likely Pathogenic
        ])])
    report = PerRegionSampleReport(sample=sample, metric_storage=clinical_mut_metric_storage)
    if not verify_file(mutations_fpath, silent=True):
        single_mutations_fpath = add_suffix(mutations_fpath, source.mut_single_suffix)
        paired_mutations_fpath = add_suffix(mutations_fpath, source.mut_paired_suffix)
        if verify_file(single_mutations_fpath, silent=True) and is_sample_presents_in_file(sample.name, single_mutations_fpath):
            mutations_fpath = single_mutations_fpath
        elif verify_file(paired_mutations_fpath, silent=True):
            mutations_fpath = paired_mutations_fpath

    info('Reading mutations from ' + mutations_fpath)
    met_alts = set()
    with open(mutations_fpath) as f:
        for i, l in enumerate(f):
            if i == 0:
                continue
            fs = l.strip().split('\t')
            if len(fs) > 60:
                sample_name, chrom, start, id, ref, alt, type_, effect, func, codon_change, aa_change, cdna_change, \
                    aa_len, gene, transcr_biotype, coding, transcript, exon, cosmic_cds_change, cosmic_aa_change, \
                    cosmic_cnt, end, depth, af, bias, pmean, pstd, qual, qstd, sbf, gmaf, vd, clnsif, oddratio, hiaf, \
                    mq, sn, adjaf, nm, shift3, msi, dbsnpbuildid, vtype, status1, paired_pval, paired_oddratiom, \
                    m_depth, m_af, m_vd, m_bias, m_pmean, m_pstd, m_qual, m_qstd, m_hiaf, m_mq, m_sn, m_adjaf, m_nm, \
                    n_sample, n_var, pcnt_sample, ave_af, filter_, var_type, var_class, status = fs[:67]  # 67 of them
            else:
                sample_name, chrom, start, id, ref, alt, type_, effect, func, codon_change, aa_change, cdna_change, \
                    aa_len, gene, transcr_biotype, coding, transcript, exon, cosmic_cds_change, cosmic_aa_change, \
                    cosmic_cnt, end, depth, af, bias, pmean, pstd, qual, qstd, sbf, gmaf, vd, clnsif, oddratio, hiaf, \
                    mq, sn, adjaf, nm, shift3, msi, dbsnpbuildid, \
                    n_sample, n_var, pcnt_sample, ave_af, filter_, var_type, var_class, status = fs[:50]  # 50 of them

            if sample_name == sample.name and gene in key_gene_names:
                if (chrom, start, ref, alt) in met_alts:
                    continue
                met_alts.add((chrom, start, ref, alt))

                reg = report.add_region()
                reg.add_record('Gene', gene)
                reg.add_record('Transcript', transcript)
                reg.add_record('Codon chg', codon_change)
                reg.add_record('AA chg', 'p.' + aa_change if aa_change else '')
                # reg.add_record('Allele', allele_record)
                reg.add_record('Chr', chrom.replace('chr', '') if chrom else '')
                reg.add_record('Position', 'g.' + (Metric.format_value(int(start), human_readable=True) if start else ''))
                reg.add_record('Change', ref + '>' + alt)
                reg.add_record('Depth', depth)
                reg.add_record('Frequency', af)
                reg.add_record('AA length', aa_len)
                reg.add_record('dbSNP', ' '.join(i for i in id.split(';') if i.startswith('rs')) if id != '.' else '')
                reg.add_record('COSMIC', ' '.join(i for i in id.split(';') if i.startswith('COS')) if id != '.' else '')
                reg.add_record('Type', type_[0] + type_[1:].lower().replace('_', ' ') if type_ else type_)
                if status == 'likely':
                    status += ' pathogenic'
                reg.add_record('Classification', status[0].upper() + status[1:] if status else status)

    report.save_tsv(sample.clinical_mutation_tsv, human_readable=True)
    info('Saved mutations report to ' + report.tsv_fpath)
    info('-' * 70)
    info()
    return report


ACTIONABLE_GENES_FPATH = join(__file__, '..', 'db', 'broad_db.tsv')
def proc_actionable_genes(cnf, sample, key_gene_names, mutations_report, seq2c_data_by_genename):
    act_fpath = verify_file(ACTIONABLE_GENES_FPATH, is_critical=False, description='Actionable genes')
    if act_fpath:
        with open(act_fpath) as f:
            actionable_gene_table = [l.split('\t') for l in f.readlines()]
            actionable_gene_dict = dict((l[0], l[1:]) for l in actionable_gene_table)

        return make_actionable_genes_report(cnf, sample, key_gene_names,
            actionable_gene_dict, mutations_report, seq2c_data_by_genename)
    return None


def make_actionable_genes_report(cnf, sample, key_gene_names, actionable_genes, mutations_report, seq2c_data_by_genename):
    info('Preparing mutations stats for key gene tables')

    clinical_action_metric_storage = MetricStorage(
        sections=[ReportSection(metrics=[
            Metric('Gene'),  # Gene & Transcript
            Metric('Variant', style='min-width: 80px; max-width: 80px; white-space: pre !important;', class_='long_line_ellipsis'),            # p.Glu82Lys
            Metric('Type', style='min-width: 120px; white-space: pre; !important', class_='long_line_ellipsis'),               # Frameshift
            Metric('Types of recurrent alterations', short_name='Types of recurrent\nalterations', style='min-width: 100px; white-space: pre;'),  # Mutation
            Metric('Rationale', style='max-width: 300px !important; white-space: normal;'),          # Translocations predict sensitivity
            Metric('Therapeutic Agents'),  # Sorafenib
        ])])
    report = PerRegionSampleReport(sample=sample, metric_storage=clinical_action_metric_storage)
    actionable_gene_names = actionable_genes.keys()
    for gene in actionable_gene_names:
        if gene not in key_gene_names:
            continue
        possible_mutations = actionable_genes[gene][1].split('; ')
        skipped_mutations = ['Rearrangement', 'Fusion']
        possible_mutations = [mutation for mutation in possible_mutations if mutation not in skipped_mutations]
        if not possible_mutations:
            continue
        variants = []
        types = []
        amp_del = None
        for region in mutations_report.regions:
            if mutations_report.find_record(region.records, 'Gene').value == gene:
                variant = mutations_report.find_record(region.records, 'AA chg').value
                variants.append(variant if variant else '.')
                types.append(mutations_report.find_record(region.records, 'Type').value)
        if gene in seq2c_data_by_genename:
            amp_del = seq2c_data_by_genename[gene]

        if 'Amplification' in possible_mutations and (not amp_del or 'Amp' not in amp_del):
            possible_mutations.remove('Amplification')
        if 'Deletion' in possible_mutations and (not amp_del or 'Del' not in amp_del):
            possible_mutations.remove('Deletion')
        if not possible_mutations or (not variants and 'Amplification' not in possible_mutations and 'Deletion' not in possible_mutations):
            continue

        reg = report.add_region()
        reg.add_record('Gene', gene)
        reg.add_record('Variant', '\n'.join(variants))
        reg.add_record('Type', '\n'.join(types))
        reg.add_record('Types of recurrent alterations', actionable_genes[gene][1].replace('; ', '\n'))
        reg.add_record('Rationale', actionable_genes[gene][0])
        reg.add_record('Therapeutic Agents', actionable_genes[gene][2])

    report.save_tsv(sample.clinical_target_tsv, human_readable=True)
    info('Saved report for actionable genes to ' + report.tsv_fpath)
    info('-' * 70)
    info()
    return report


def make_clinical_html_report(cnf, sample, coverage_report, mutations_report,
          target_type, ave_depth, target_fraction, gender, total_variants,
          key_gene_names, actionable_genes_report, seq2c_plot_fpath=None):
    # def __process_record(rec, short=False):
    #     d = rec.__dict__.copy()
    #
    #     if isinstance(rec.html_fpath, basestring):
    #         d['contents'] = '<a href="' + rec.html_fpath + '">' + rec.value + '</a>'
    #
    #     elif isinstance(rec.html_fpath, dict):
    #         d['contents'] = ', '.join('<a href="{v}">{k}</a>'.format(k=k, v=v) for k, v in rec.html_fpath.items()) if rec.html_fpath else '-'
    #         if not short:
    #             d['contents'] = rec.metric.name + ': ' + d['contents']
    #
    #     else:
    #         d['contents'] = '-'
    #
    #     d['metric'] = rec.metric.__dict__
    #     return d
    #
    # def _get_summary_report_name(rec):
    #     return rec.value.lower().replace(' ', '_')

    # common records (summary reports)
    sample_dict = dict()
    sample_dict['sample'] = sample.name.replace('_', ' ')
    sample_dict['project_name'] = cnf.project_name.replace('_', ' ')
    sample_dict['sex'] = gender
    sample_dict['genome_build'] = cnf.genome.name

    approach_dict = dict()
    approach_dict['target_type'] = cnf.target_type
    approach_dict['target_fraction'] = Metric.format_value(target_fraction, is_html=True, unit='%')
    # approach_dict['min_depth'] = Metric.format_value(min_depth, is_html=True)
    approach_dict['ave_depth'] = Metric.format_value(ave_depth, is_html=True)
    approach_dict['total_variants'] = Metric.format_value(total_variants, is_html=True)
    approach_dict['total_key_genes'] = Metric.format_value(len(key_gene_names), is_html=True)

    mutations_dict = dict()
    if mutations_report.regions:
        # mutations_dict['first_col_header'] = mutations_report.metric_storage.get_metrics()[0].name
        if is_local():
            mutations_report.regions = mutations_report.regions[:4]
        calc_cell_contents(mutations_report, mutations_report.regions, mutations_report.metric_storage.sections[0])
        mutations_dict['metric_names'] = [make_cell_th(m) for m in mutations_report.metric_storage.get_metrics()]
        mutations_dict['rows'] = [
            dict(records=[make_cell_td(r, td_classes='') for r in region.records])
                for region in mutations_report.regions]

    coverage_dict = dict(columns=[])
    GENE_COL_NUM = 3
    genes_in_col = len(coverage_report.regions) / GENE_COL_NUM
    calc_cell_contents(coverage_report, coverage_report.regions, coverage_report.metric_storage.sections[0])
    for i in range(GENE_COL_NUM):
        column_dict = dict()
        # column_dict['first_col_header'] = coverage_report.metric_storage.get_metrics()[0].name
        column_dict['metric_names'] = [make_cell_th(m) for m in coverage_report.metric_storage.get_metrics()]
        column_dict['rows'] = [
            dict(records=[make_cell_td(r, td_classes='') for r in region.records])
                for region in coverage_report.regions[i * genes_in_col:(i+1) * genes_in_col]]
        coverage_dict['columns'].append(column_dict)

    seq2c_plot_dict = dict()
    if seq2c_plot_fpath:
        # seq2c_plot_dict['plot_src'] = relpath(seq2c_plot_fpath, cnf.output_dir)
        import base64
        with open(seq2c_plot_fpath, 'rb') as f:
            encoded_string = base64.b64encode(f.read())
        seq2c_plot_dict['plot_src'] = 'data:image/png;base64,' + encoded_string

    actionable_genes_dict = dict()
    if actionable_genes_report:
        calc_cell_contents(actionable_genes_report, actionable_genes_report.regions, actionable_genes_report.metric_storage.sections[0])
        actionable_genes_dict['metric_names'] = [make_cell_th(m) for m in actionable_genes_report.metric_storage.get_metrics()]
        actionable_genes_dict['rows'] = [
            dict(records=[make_cell_td(r, td_classes='short_line') for r in region.records])
                for region in actionable_genes_report.regions]

    sample.clinical_html = write_static_html_report(cnf.work_dir, {
        'sample': sample_dict,
        'approach': approach_dict,
        'variants': mutations_dict,
        'coverage': coverage_dict,
        'seq2c_plot': seq2c_plot_dict,
        'actionable_genes': actionable_genes_dict,
    }, sample.clinical_html,
       tmpl_fpath=join(dirname(abspath(__file__)), 'template.html'),
       extra_js_fpaths=[join(dirname(abspath(__file__)), 'static', 'clinical_report.js')],
       extra_css_fpaths=[join(dirname(abspath(__file__)), 'static', 'clinical_report.css'),
                         join(dirname(abspath(__file__)), 'static', 'header_picture.css')])

    clin_rep_symlink = adjust_path(join(sample.dirpath, '..', sample.name + '.clinical_report.html'))
    if islink(clin_rep_symlink):
        os.unlink(clin_rep_symlink)
    os.symlink(sample.clinical_html, clin_rep_symlink)

    info('Saved clinical report to ' + clin_rep_symlink)
    info('-' * 70)
    info()
    return clin_rep_symlink


def tooltip_long(string, max_len=30):
    if len(string) < max_len:
        return string
    else:
        return '<a class="tooltip-link" rel="tooltip" title="' + string + '">' + string[:max_len - 2] + '...</a>'



