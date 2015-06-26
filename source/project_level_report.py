import os
from os.path import join, relpath, dirname
from collections import OrderedDict
import getpass
from traceback import print_exc
import source

from source.bcbio_structure import BCBioStructure
from source.logger import info, step_greetings, send_email, warn, err
from source.file_utils import verify_file, file_transaction, adjust_path, safe_mkdir, add_suffix
from source.reporting import Metric, Record, MetricStorage, ReportSection, SampleReport, FullReport
from source.html_reporting.html_saver import write_static_html_report
from source.tools_from_cnf import get_system_path
from utils import is_local, is_uk


def make_project_level_report(cnf, bcbio_structure):
    step_greetings('Project-level report')

    general_section = ReportSection('general_section', '', [])
    general_records = []
    general_records = _add_summary_reports(bcbio_structure, general_section, general_records)
    general_records = _add_variants(bcbio_structure, general_section, general_records)

    individual_reports_section = ReportSection('individual_reports', '', [])
    sample_reports_records = _add_per_sample_reports(bcbio_structure, general_records, individual_reports_section)

    metric_storage = MetricStorage(general_section=general_section, sections=[individual_reports_section])
    sample_reports = []
    for sample in bcbio_structure.samples:
        sample_reports.append(SampleReport(
            sample,
            records=sample_reports_records[sample.name],
            html_fpath=None,
            metric_storage=metric_storage))

    full_report = FullReport(cnf.name, sample_reports, metric_storage=metric_storage)
    # final_summary_report_fpath = full_report.save_html(
    #     bcbio_structure.date_dirpath, bcbio_structure.project_name,
    #     'Project-level report for ' + bcbio_structure.project_name)
    final_summary_report_fpath = _save_static_html(full_report, bcbio_structure.date_dirpath,
        report_base_name=bcbio_structure.project_name,
        project_name=bcbio_structure.project_name)

    html_report_url = ''
    if not is_local() and '/ngs/oncology/' in bcbio_structure.final_dirpath:
        info()
        csv_fpath = '/ngs/oncology/NGS.Project.csv'
        location = 'US'
        fn = _symlink_report_us
        if is_uk():
            csv_fpath = '/ngs/oncology/reports/NGS.Project.csv'
            location = 'UK'
            fn = _symlink_report_uk
        html_report_url = fn(cnf, cnf.work_dir, bcbio_structure, final_summary_report_fpath)
        if verify_file(csv_fpath, 'Project list'):
            write_to_csv_file(cnf.work_dir, cnf.jira, csv_fpath, location, bcbio_structure.project_name, len(bcbio_structure.samples),
                              dirname(bcbio_structure.final_dirpath), html_report_url)

    info()
    info('*' * 70)
    info('Project-level report saved in: ')
    info('  ' + final_summary_report_fpath)
    if html_report_url:
        info('  Web link: ' + html_report_url)
    # send_email('Report for ' + bcbio_structure.project_name + ':\n  ' + (html_report_url or final_summary_report_fpath))

    info()
    info('Done report for ' + bcbio_structure.project_name + ':\n  ' + (html_report_url or final_summary_report_fpath))

    # if cnf.done_marker:
    #     safe_mkdir(dirname(cnf.done_marker))
    #     with open(cnf.done_marker, 'w') as f:
    #         f.write(html_report_url or final_summary_report_fpath)

    return html_report_url or final_summary_report_fpath


def write_to_csv_file(work_dir, jira_case, project_list_fpath, location, project_name, samples_num=None,
                      analysis_dirpath=None, html_report_url=None):
    info('Reading project list ' + project_list_fpath)
    with open(project_list_fpath) as f:
        lines = f.readlines()
    uncom_lines = [l.strip() for l in lines if not l.strip().startswith('#')]

    header = uncom_lines[0].strip()
    info('header: ' + header)
    header_keys = header.split(',')  # 'Updated By,PID,Name,JIRA URL,HTML report path,Why_IfNoReport,Data Hub,Analyses directory UK,Analyses directory US,Type,Division,Department,Sample Number,Reporter,Assignee,Description,IGV,Notes'
    index_of_pid = header_keys.index('PID')
    if index_of_pid == -1: index_of_pid = 1

    values_by_keys_by_pid = OrderedDict()
    for l in uncom_lines[1:]:
        if l:
            values = l.split(',')
            pid = values[index_of_pid]
            values_by_keys_by_pid[pid] = OrderedDict(zip(header_keys, values))

    pid = project_name
    with file_transaction(work_dir, project_list_fpath) as tx_fpath:
        if pid not in values_by_keys_by_pid:
            info('Adding new record for ' + pid)
            values_by_keys_by_pid[pid] = OrderedDict(zip(header_keys, [''] * len(header_keys)))
        else:
            info('Updating existing record for ' + pid)
        d = values_by_keys_by_pid[pid]
        if 'Updated By' not in d:
            d['Updated By'] = getpass.getuser()

        d['PID'] = pid
        d['Name'] = project_name
        if jira_case:
            d['JIRA URL'] = jira_case.url
        if html_report_url:
            d['HTML report path'] = html_report_url
        if analysis_dirpath:
            d['Analyses directory ' + location] = analysis_dirpath
        if samples_num:
            d['Sample Number'] = str(samples_num)

        new_line = ','.join(d.values())
        info('Adding the new line: ' + new_line)

        with open(tx_fpath, 'w') as f:
            os.umask(0002)
            os.chmod(tx_fpath, 0666)
            for l in lines:
                if not l:
                    pass
                if l.startswith('#'):
                    f.write(l)
                else:
                    if ',' + project_name + ',' in l:
                        info('Old csv line: ' + l)
                        # f.write('#' + l)
                    else:
                        f.write(l)
            f.write(new_line + '\n')


def _symlink_report_uk(cnf, work_dir, bcbio_structure, html_report_fpath):
    html_report_url = 'http://ukapdlnx115.ukapd.astrazeneca.net/ngs/reports/' + bcbio_structure.project_name + '/' + \
        relpath(html_report_fpath, bcbio_structure.final_dirpath)

    server_path = '/ngs/oncology/reports'
    info('UK, symlinking to ' + server_path)
    link_fpath = join(server_path, bcbio_structure.project_name)
    cmd = 'rm ' + link_fpath + '; ln -s ' + bcbio_structure.final_dirpath + ' ' + link_fpath
    info(cmd)
    try:
        os.system(cmd)
    except Exception, e:
        warn('Cannot create symlink')
        warn('  ' + str(e))
        html_report_url = None
    return html_report_url


def _symlink_report_us(cnf, work_dir, bcbio_structure, html_report_fpath):
    html_report_url = 'http://ngs.usbod.astrazeneca.net/reports/' + bcbio_structure.project_name + '/' + \
        relpath(html_report_fpath, bcbio_structure.final_dirpath)

    server_url = '172.18.47.33'  # ngs
    server_path = '/opt/lampp/htdocs/reports'
    username = 'klpf990'
    password = '123werasd'
    rsa_key_path = get_system_path(cnf, join('source', 'id_rsa'), is_critical=False)
    if rsa_key_path:
        try:
            from ext_modules.paramiko import SSHClient, RSAKey, AutoAddPolicy
        except ImportError as e:
            print_exc()
            err('Cannot improt SSHClient - skipping trasnferring symlinking to the ngs-website')
        else:
            ssh = SSHClient()
            ssh.load_system_host_keys()
            # ki = RSAKey.from_private_key_file(filename=rsa_key_path)
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            try:
                key = RSAKey(filename=rsa_key_path, password='%1!6vLaD')
            except Exception, e:
                warn('Cannot read RSAKey from ' + rsa_key_path)
                warn('  ' + str(e))
            else:
                info('Succesfully read RSAKey from ' + rsa_key_path)
                try:
                    ssh.connect(server_url, username=username, password=password, pkey=key)
                except Exception, e:
                    warn('Cannot connect to ' + server_url + ':')
                    warn('  ' + str(e))
                    html_report_url = None
                else:
                    info('Succesfully connected to ' + server_url)
                    final_dirpath_in_ngs = bcbio_structure.final_dirpath.split('/gpfs')[1]
                    link_path = join(server_path, bcbio_structure.project_name)
                    cmd = 'rm ' + link_path + '; ln -s ' + final_dirpath_in_ngs + ' ' + link_path
                    ssh.exec_command(cmd)
                    info('  ' + cmd)
                    ssh.close()
    info()
    return html_report_url


def _add_variants(bcbio_structure, general_section, general_records):
    val = OrderedDict()
    single_val = OrderedDict()
    paired_val = OrderedDict()

    for caller in bcbio_structure.variant_callers.values():
        mut_fname = add_suffix(source.mut_fname_template.format(caller_name=caller.name), source.mut_pass_suffix)
        mut_fpath = join(bcbio_structure.date_dirpath, mut_fname)

        if verify_file(mut_fpath, silent=True):
            val[caller.name] = mut_fpath
        else:
            single_mut_fpath = add_suffix(mut_fpath, source.mut_single_suffix)
            paired_mut_fpath = add_suffix(mut_fpath, source.mut_paired_suffix)
            if verify_file(single_mut_fpath):
                single_val[caller.name] = single_mut_fpath
                # _add_rec(single_mut_fpath, caller.name + ' mutations for separate samples')
            if verify_file(paired_mut_fpath):
                paired_val[caller.name] = paired_mut_fpath
                # _add_rec(paired_mut_fpath, caller.name + ' mutations for paired samples')

    for val, metric_name in (
         (val, 'Mutations'),
         (single_val, 'Mutations for separate samples'),
         (paired_val, 'Mutations for paired samples')):
        if val:
            metric = Metric(metric_name, common=True)
            rec = Record(
                metric=metric,
                value=metric.name,
                html_fpath=_convert_to_relpath(val, bcbio_structure.date_dirpath))
            general_section.add_metric(metric)
            general_records.append(rec)

    return general_records


def _add_summary_reports(bcbio_structure, general_section, general_records):
    for (name, repr_name, summary_dir) in [
            (BCBioStructure.fastqc_name,      BCBioStructure.fastqc_repr,      BCBioStructure.fastqc_summary_dir),
            (BCBioStructure.targqc_name,      BCBioStructure.targqc_repr,      BCBioStructure.targqc_summary_dir),
            (BCBioStructure.varqc_name,       BCBioStructure.varqc_repr,       BCBioStructure.varqc_summary_dir),
            (BCBioStructure.varqc_after_name, BCBioStructure.varqc_after_repr, BCBioStructure.varqc_after_summary_dir)]:

        summary_report_fpath = join(bcbio_structure.date_dirpath, summary_dir, name + '.html')
        if verify_file(summary_report_fpath):
            cur_metric = Metric(repr_name + ' summary', common=True)
            general_section.add_metric(cur_metric)
            general_records.append(
                Record(metric=cur_metric,
                       value=cur_metric.name,
                       html_fpath=_convert_to_relpath(
                           summary_report_fpath,
                           bcbio_structure.date_dirpath)))

    return general_records


def _add_per_sample_reports(bcbio_structure, general_records, individual_reports_section):
    varqc_htmls_by_sample       = _add_varqc_reports(bcbio_structure, BCBioStructure.varqc_name, BCBioStructure.varqc_dir)
    varqc_after_htmls_by_sample = _add_varqc_reports(bcbio_structure, BCBioStructure.varqc_after_name, BCBioStructure.varqc_after_dir)
    targqc_htmls_by_sample      = _add_targqc_reports(bcbio_structure)
    fastqc_htmls_by_sample      = dict([(s.name, verify_file(s.fastqc_html_fpath)) for s in bcbio_structure.samples])

    sample_reports_records = dict()
    for sample in bcbio_structure.samples:
        sample_reports_records[sample.name] = list(general_records)

    for (repr_name, links_by_sample) in [
            (bcbio_structure.fastqc_repr,      fastqc_htmls_by_sample),
            # ('BAM',                            bams_by_samples),
            (bcbio_structure.targqc_repr,      targqc_htmls_by_sample),
            (bcbio_structure.varqc_repr,       varqc_htmls_by_sample),
            (bcbio_structure.varqc_after_repr, varqc_after_htmls_by_sample)]:
        cur_metric = Metric(repr_name)
        individual_reports_section.add_metric(cur_metric)
        for sample in bcbio_structure.samples:
            if links_by_sample and links_by_sample.get(sample.name):
                sample_reports_records[sample.name].append(
                    Record(
                        metric=cur_metric,
                        value=cur_metric.name,
                        html_fpath=_convert_to_relpath(
                            links_by_sample[sample.name],
                            bcbio_structure.date_dirpath)))
            else:
                sample_reports_records[sample.name].append(
                    Record(metric=cur_metric, value=None, html_fpath=None))
    return sample_reports_records


def _add_varqc_reports(bcbio_structure, name, dir_name):
    callers = bcbio_structure.variant_callers.values()
    if len(callers) == 0:
        varqc_htmls_by_sample = None
    elif len(callers) == 1:
        varqc_htmls_by_sample = callers[0].find_fpaths_by_sample(
            dir_name, name, 'html')
    else:
        varqc_htmls_by_sample = OrderedDict()
        for sample in bcbio_structure.samples:
            varqc_htmls_by_sample[sample.name] = OrderedDict()
        for caller in callers:
            for sample, fpath in caller.find_fpaths_by_sample(
                    dir_name, name, 'html').items():
                varqc_htmls_by_sample[sample][caller.name] = fpath

    return varqc_htmls_by_sample


def _add_targqc_reports(bcbio_structure):
    targqc_htmls_by_sample = OrderedDict()

    for sample in bcbio_structure.samples:
        targqc_htmls_by_sample[sample.name] = OrderedDict()
        for report_name, report_html_fpath in [
            ('targetcov', sample.targetcov_html_fpath),
            ('ngscat', sample.ngscat_html_fpath),
            ('qualimap', sample.qualimap_html_fpath)]:
            if verify_file(report_html_fpath):
                targqc_htmls_by_sample[sample.name][report_name] = verify_file(report_html_fpath)

    return targqc_htmls_by_sample


def _convert_to_relpath(value, base_dirpath):
    if not value:
        return None
    if isinstance(value, str):
        return relpath(value, base_dirpath)
    elif isinstance(value, dict):
        for k in value.keys():
            if not value[k]:
                value[k] = None
            else:
                value[k] = relpath(value[k], base_dirpath)
        return value
    else:
        return value


def _save_static_html(full_report, output_dirpath, report_base_name, project_name):
    # metric name in FullReport --> metric name in Static HTML
    metric_names = OrderedDict([
        (BCBioStructure.fastqc_repr, 'FastQC'),
        # ('BAM', 'BAM'),
        (BCBioStructure.targqc_repr, 'SeqQC'),
        # ('Mutations', 'Mutations'),
        # ('Mutations for separate samples', 'Mutations for separate samples'),
        # ('Mutations for paired samples', 'Mutations for paired samples'),
        (BCBioStructure.varqc_repr, 'VarQC'),
        (BCBioStructure.varqc_after_repr, 'VarQC after filtering')])

    def _process_record(record):
        new_html_fpath = []
        if isinstance(record["html_fpath"], basestring):
            new_html_fpath = [{"html_fpath_name": record["value"], "html_fpath_value": record["html_fpath"]}]
        elif isinstance(record["html_fpath"], dict):
            for k, v in record["html_fpath"].items():
                new_html_fpath.append({"html_fpath_name": k, "html_fpath_value": v})
        record["html_fpath"] = new_html_fpath
        return record

    def _get_summary_report_name(record):
        return record.value.lower().replace(' ', '_')

    # common records (summary reports)
    common_dict = dict()
    common_dict["project_name"] = project_name
    sample_report = full_report.sample_reports[0]
    for record in sample_report.records:
        if record.metric.common:
            common_dict[_get_summary_report_name(record)] = record.__dict__
            if 'Mutations' in record.metric.name:
                common_dict[_get_summary_report_name(record)]['contents'] = (
                    record.metric.name + ': ' + ', '.join('<a href={v}>{k}</a>'.format(k=k, v=v) for k, v in record.html_fpath.items()))

    # individual records
    main_dict = dict()
    main_dict["sample_reports"] = []
    main_dict["metric_names"] = [v for k, v in metric_names.items()
                                 if k in [m.name for m in full_report.metric_storage.get_metrics(skip_general_section=True)]]
    for sample_report in full_report.sample_reports:
        new_records = [_process_record(record.__dict__) for record in sample_report.records
                       if record.metric.name in metric_names.keys()]
        sample_report_dict = dict()
        sample_report_dict["records"] = new_records
        sample_report_dict["sample_name"] = sample_report.display_name
        main_dict["sample_reports"].append(sample_report_dict)

    return write_static_html_report({"common": common_dict, "main": main_dict},
                                    output_dirpath, report_base_name)