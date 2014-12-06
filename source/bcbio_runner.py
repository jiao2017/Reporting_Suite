from dircache import listdir
import hashlib
import os
import shutil
import sys
import base64
from os.path import join, dirname, abspath, expanduser, basename, pardir, isfile, isdir, exists, islink, relpath
from source.bcbio_structure import BCBioStructure
from source.calling_process import call
from source.file_utils import verify_dir, verify_file, add_suffix, symlink_plus, remove_quotes
from source.tools_from_cnf import get_system_path

from source.file_utils import file_exists, safe_mkdir
from source.logger import info, err, critical, send_email
from source.ngscat.bed_file import verify_bam


class Step:
    def __init__(self, cnf, run_id, name, script, dir_name=None,
                 interpreter=None, short_name=None, paramln=''):
        self.name = name
        self.dir_name = dir_name
        self.cnf = cnf
        assert run_id
        self.run_id_ = run_id
        self.short_name = short_name or name
        self.param_line = paramln
        self.run_id = None
        self.script = script
        self.interpreter = interpreter

    def job_name(self, sample=None, caller=None):
        return self.short_name.upper() + '_' + self.run_id_ + \
               ('_' + sample if sample else '') + \
               ('_' + caller if caller else '')

    def __repr__(self):
        return self.name


class Steps(list):
    def __init__(self):
        super(Steps, self).__init__()

    def add_step(self, step):
        self.append(step)

    def extend(self, iterable):
        for step in iterable:
            self.add_step(step)


class JobRunning:
    def __init__(self, name, log_fpath, qsub_cmdline):
        self.name = name
        self.log_fpath = log_fpath
        self.qsub_cmdline = qsub_cmdline


# noinspection PyAttributeOutsideInit
class BCBioRunner:
    def __init__(self, cnf, bcbio_structure, bcbio_cnf):
        self.bcbio_structure = bcbio_structure
        self.final_dir = bcbio_structure.final_dirpath
        self.bcbio_cnf = bcbio_cnf

        self.cnf = cnf
        cnf.work_dir = bcbio_structure.work_dir

        self.run_id = self.__generate_run_id(bcbio_structure)

        self.qsub_runner = abspath(expanduser(cnf.qsub_runner))

        self.max_threads = self.cnf.threads or 40
        total_samples = len(self.bcbio_structure.samples) * len(self.bcbio_structure.variant_callers)
        self.threads_per_sample = max(self.max_threads / total_samples, 1)

        self.steps = Steps()
        self._set_up_steps(cnf, self.run_id)

        self.jobs = []

        normalize = lambda name: name.lower().replace('_', '').replace('-', '')
        contains = lambda x, xs: normalize(x) in [normalize(y) for y in (xs or [])]

        self.steps.extend([
            self.varqc_summary,
            self.varqc_after_summary,
            self.fastqc_summary,
            self.targqc_summary,
            self.combined_report,
        ])

        self.steps.extend(
            [s for s in [
                self.varqc,
                self.varannotate,
                self.varfilter_all,
                self.mongo_loader,
                self.varqc_after,
                self.targetcov,
                self.abnormal_regions,
                self.seq2c,
                self.ngscat,
                self.qualimap,
            ] if contains(s.name, cnf.steps)])

        # self.vardict_steps.extend(
        #     [s for s in [
        #         self.vardict,
        #         self.testsomatic,
        #         self.var_to_vcf_somatic,
        #         self.varqc,
        #         self.varannotate,
        #         self.varfilter_all,
        #         self.varqc_after,
        #         self.varqc_summary,
        #         self.varqc_after_summary
        # ] if contains(s.name, cnf.vardict_steps)])

        self._symlink_cnv()

    def __generate_run_id(self, bcbio_structure):
        hasher = hashlib.sha1(self.final_dir)
        path_hash = base64.urlsafe_b64encode(hasher.digest()[0:4])[:-1]
        return path_hash + '_' + bcbio_structure.project_name

    def _set_up_steps(self, cnf, run_id):
        params_for_everyone = \
            ' --sys-cnf ' + self.cnf.sys_cnf + \
            ' --run-cnf ' + self.cnf.run_cnf + \
            ' -t ' + str(self.threads_per_sample) + \
           (' --reuse ' if self.cnf.reuse_intermediate else '') + \
            ' --log-dir ' + self.bcbio_structure.log_dirpath
        if cnf.email:
            params_for_everyone += ' --email ' + remove_quotes(self.cnf.email) + ' '

        summaries_cmdline_params = ''
        if cnf.bed:
            summaries_cmdline_params += ' --bed ' + cnf.bed

        # Params for those who doesn't call bcbio_structure
        spec_params = \
            params_for_everyone + \
            ' --genome {genome}' + \
            ' --project-name ' + self.bcbio_structure.project_name + ' '

        anno_paramline = spec_params + ('' +
             ' --vcf \'{vcf}\' {bam_cmdline} {normal_match_cmdline} ' +
             '-o \'{output_dir}\' -s \'{sample}\' -c {caller} ' +
             '--work-dir \'' + join(cnf.work_dir, BCBioStructure.varannotate_name) + '_{sample}_{caller}\' ')

        self.varannotate = Step(cnf, run_id,
            name='VarAnnotate', short_name='va',
            interpreter='python',
            script=join('sub_scripts', 'varannotate.py'),
            dir_name=BCBioStructure.varannotate_dir,
            paramln=anno_paramline,
        )
        self.varqc = Step(cnf, run_id,
            name='VarQC', short_name='vq',
            interpreter='python',
            script=join('sub_scripts', 'varqc.py'),
            dir_name=BCBioStructure.varqc_dir,
            paramln=spec_params + ' --vcf \'{vcf}\' -o \'{output_dir}\' -s \'{sample}\' -c {caller} '
                    '--work-dir \'' + join(cnf.work_dir, BCBioStructure.varqc_name) + '_{sample}_{caller}\''
        )
        self.varqc_after = Step(cnf, run_id,
            name='VarQC_postVarFilter', short_name='vqa',
            interpreter='python',
            script=join('sub_scripts', 'varqc.py'),
            dir_name=BCBioStructure.varqc_after_dir,
            paramln=spec_params + ' --vcf \'{vcf}\' -o \'{output_dir}\' -s \'{sample}\' -c {caller} '
                    '--work-dir \'' + join(cnf.work_dir, BCBioStructure.varqc_after_name) + '_{sample}_{caller}\' ' +
                    '--proc-name ' + BCBioStructure.varqc_after_name
        )
        self.targetcov = Step(cnf, run_id,
            name='TargetCov', short_name='tc',
            interpreter='python',
            script=join('sub_scripts', 'targetcov.py'),
            dir_name=BCBioStructure.targetseq_dir,
            paramln=spec_params + ' --bam \'{bam}\' --bed \'{bed}\' -o \'{output_dir}\' '
                    '-s \'{sample}\' --work-dir \'' + join(cnf.work_dir, BCBioStructure.targetseq_name) + '_{sample}\' '
        )
        self.abnormal_regions = Step(cnf, run_id,
            name='AbnormalCovReport', short_name='acr',
            interpreter='python',
            script=join('sub_scripts', 'abnormal_regions.py'),
            dir_name=BCBioStructure.targetseq_dir,
            paramln=spec_params + ' -o \'{output_dir}\' {caller_names} {vcfs} '
                    '-s \'{sample}\' --work-dir \'' + join(cnf.work_dir, BCBioStructure.targetseq_name) + '_{sample}\' '
        )
        self.ngscat = Step(cnf, run_id,
            name='ngsCAT', short_name='nc',
            interpreter='python',
            script=join('sub_scripts', 'ngscat.py'),
            dir_name=BCBioStructure.ngscat_dir,
            paramln=spec_params + ' --bam \'{bam}\' --bed \'{bed}\' -o \'{output_dir}\' -s \'{sample}\' '
                    '--saturation y --work-dir \'' + join(cnf.work_dir, BCBioStructure.ngscat_name) + '_{sample}\''
        )
        self.qualimap = Step(cnf, run_id,
            name='QualiMap', short_name='qm',
            script='qualimap',
            dir_name=BCBioStructure.qualimap_dir,
            paramln=' bamqc -nt ' + str(self.threads_per_sample) + ' --java-mem-size=24G -nr 5000 '
                    '-bam \'{bam}\' -outdir \'{output_dir}\' {qualimap_gff} -c -gd HUMAN'
        )
        #############
        # Summaries #
        self.varqc_summary = Step(cnf, run_id,
            name='VarQC_summary', short_name='vqs',
            interpreter='python',
            script=join('sub_scripts', 'varqc_summary.py'),
            dir_name=BCBioStructure.varqc_summary_dir,
            paramln=params_for_everyone + ' ' + self.final_dir + ' ' + summaries_cmdline_params
        )
        self.varqc_after_summary = Step(cnf, run_id,
            name='VarQC_postVarFilter_summary', short_name='vqas',
            interpreter='python',
            script=join('sub_scripts', 'varqc_summary.py'),
            dir_name=BCBioStructure.varqc_after_summary_dir,
            paramln=params_for_everyone + ' ' + self.final_dir +
                    ' --name ' + BCBioStructure.varqc_after_name +
                    ' --dir ' + BCBioStructure.varqc_after_dir +
                    ' ' + summaries_cmdline_params
        )
        varfilter_paramline = params_for_everyone + ' ' + self.final_dir + ' ' + summaries_cmdline_params
        if cnf.datahub_path:
            varfilter_paramline += ' --datahub-path ' + cnf.datahub_path

        self.varfilter_all = Step(cnf, run_id,
            name='VarFilter', short_name='vfs',
            interpreter='python',
            script=join('sub_scripts', 'varfilter.py'),
            dir_name=BCBioStructure.varfilter_dir,
            paramln=varfilter_paramline
        )

        self.mongo_loader = Step(cnf, run_id,
            name='MongoLoader', short_name='ml',
            interpreter='java',
            script='vcf_loader',
            dir_name='mongo_loader',
            paramln='-module loader -project {project} -sample {sample} -path {path} -variantCaller {variantCaller}'
        )
        self.seq2c = Step(cnf, run_id,
            name=BCBioStructure.seq2c_name, short_name='seq2c',
            interpreter='python',
            script=join('sub_scripts', 'seq2c.py'),
            dir_name=BCBioStructure.cnv_summary_dir,
            paramln=params_for_everyone + ' ' + self.final_dir + ' ' + summaries_cmdline_params
        )
        self.targqc_summary = Step(
            cnf, run_id,
            name='TargQC_summary', short_name='targqc',
            interpreter='python',
            script=join('sub_scripts', 'targqc_summary.py'),
            dir_name=BCBioStructure.targqc_summary_dir,
            paramln=params_for_everyone + ' ' + self.final_dir + ' ' + summaries_cmdline_params

        )
        self.fastqc_summary = Step(
            cnf, run_id,
            name='FastQC_summary', short_name='fastqc',
            interpreter='python',
            script=join('sub_scripts', 'fastqc_summary.py'),
            dir_name=BCBioStructure.fastqc_summary_dir,
            paramln=params_for_everyone + ' ' + self.final_dir + ' ' + summaries_cmdline_params
        )
        self.combined_report = Step(cnf, run_id,
            name='Combined_report', short_name='cr',
            interpreter='python',
            script=join('sub_scripts', 'combined_report.py'),
            dir_name=self.bcbio_structure.date_dirpath,
            paramln=params_for_everyone + ' ' + self.final_dir + ' ' + summaries_cmdline_params
        )

    def step_output_dir_and_log_paths(self, step, sample_name, caller=None):
        if sample_name:
            base_output_dirpath = abspath(join(self.final_dir, sample_name))
        else:
            base_output_dirpath = abspath(self.bcbio_structure.date_dirpath)

        output_dirpath = join(base_output_dirpath, step.dir_name) if step.dir_name else ''

        log_fpath = join(self.bcbio_structure.log_dirpath,
             (step.name + ('_' + sample_name if sample_name else '') +
                          ('_' + caller if caller else '')) + '.log')

        return output_dirpath, log_fpath


    def _submit_job(self, step, sample_name='', suf=None, create_dir=True,
                    out_fpath=None, wait_for_steps=None, threads=1, **kwargs):

        output_dirpath, log_fpath = self.step_output_dir_and_log_paths(step, sample_name, suf)
        if output_dirpath and not isdir(output_dirpath) and create_dir:
            safe_mkdir(join(output_dirpath, pardir))
            safe_mkdir(output_dirpath)

        out_fpath = out_fpath or log_fpath

        if isfile(out_fpath):
            try:
                os.remove(out_fpath)
            except OSError:
                err('Warning: cannot remove log file ' + out_fpath + ', probably permission denied.')

        if log_fpath and isfile(log_fpath):
            try:
                os.remove(log_fpath)
            except OSError:
                err('Warning: cannot remove log file ' + out_fpath + ', probably permission denied.')

        safe_mkdir(dirname(log_fpath))
        safe_mkdir(dirname(out_fpath))

        tool_cmdline = get_system_path(self.cnf, step.interpreter, step.script)
        if not tool_cmdline: sys.exit(1)
        params = dict({'output_dir': output_dirpath}.items() + self.__dict__.items() + kwargs.items())
        cmdline = tool_cmdline + ' ' + step.param_line.format(**params)

        hold_jid_line = '-hold_jid ' + ','.join(wait_for_steps or ['_'])
        job_name = step.job_name(sample_name, suf)
        qsub = get_system_path(self.cnf, 'qsub')
        threads = str(threads)
        queue = self.cnf.queue
        runner_script = self.qsub_runner
        qsub_cmdline = (
            '{qsub} -pe smp {threads} -S /bin/bash -q {queue} '
            '-j n -o {out_fpath} -e {log_fpath} {hold_jid_line} '
            '-N {job_name} {runner_script} "{cmdline}"'.format(**locals()))

        if self.cnf.verbose:
            info(step.name)
            info(qsub_cmdline)
        else:
            print step.name,

        call(self.cnf, qsub_cmdline, silent=True)

        self.jobs.append(JobRunning(name=step.name, log_fpath=log_fpath, qsub_cmdline=qsub_cmdline))

        if self.cnf.verbose: info()
        return output_dirpath

    def _qualimap_bed(self, bed_fpath):
        if self.qualimap in self.steps and bed_fpath:
            qualimap_bed_fpath = join(self.cnf.work_dir, 'tmp_qualimap.bed')

            with open(qualimap_bed_fpath, 'w') as out, open(bed_fpath) as inn:
                for l in inn:
                    fields = l.strip().split('\t')

                    if len(fields) < 3:
                        continue
                    try:
                        int(fields[1]), int(fields[2])
                    except ValueError:
                        continue

                    if len(fields) < 4:
                        fields.append('-')

                    if len(fields) < 5:
                        fields.append('0')

                    if len(fields) < 6:
                        fields.append('+')

                    out.write('\t'.join(fields) + '\n')

            return qualimap_bed_fpath
        else:
            return bed_fpath

    def post_jobs(self):
        callers = self.bcbio_structure.variant_callers.values()

        if self.qualimap in self.steps:
            bed_by_sample = dict((s, s.bed) for s in self.bcbio_structure.samples if s.bed)
            beds = set(bed_by_sample.values())
            samples_by_bed = dict((b, (s for s in self.bcbio_structure.samples if s.bed and s.bed == b)) for b in beds)
            for bed, samples in samples_by_bed.items():
                bed = self._qualimap_bed(bed)
                for s in samples:
                    s.bed = bed

        for sample in self.bcbio_structure.samples:
            if not (any(step in self.steps for step in
                        [self.targetcov,
                         self.seq2c,
                         self.qualimap,
                         self.ngscat,
                         self.varqc,
                         self.varqc_after,
                         self.varannotate,
                         self.mongo_loader,
                         self.abnormal_regions])):
                continue

            info('Processing "' + sample.name + '"')
            if not self.cnf.verbose:
                info(ending='')

            # BAMS
            if any(step in self.steps for step in [
                   self.targetcov,
                   self.qualimap,
                   self.ngscat]):
                if not sample.bam or not verify_bam(sample.bam):
                    err('Cannot run coverage reports (targetcov, qualimap, ngscat) without BAM files.')

                # TargetCov reports
                if self.targetcov in self.steps:
                    info('Target coverage for "' + sample.name + '"')
                    self._submit_job(
                        self.targetcov, sample.name,
                        bam=sample.bam, bed=sample.bed, sample=sample.name, genome=sample.genome,
                        caller_names='', vcfs='', threads=self.threads_per_sample)

                # ngsCAT reports
                if (self.ngscat in self.steps) and (not sample.bed or not verify_file(sample.bed)):
                    err('Warning: no BED file, assuming WGS, thus skipping ngsCAT reports.')
                else:
                    if self.ngscat in self.steps:
                        self._submit_job(self.ngscat, sample.name, bam=sample.bam, bed=sample.bed,
                                         sample=sample.name, genome=sample.genome, threads=self.threads_per_sample)

                # Qualimap
                if self.qualimap in self.steps:
                    qualimap_gff = ''
                    if sample.bed:
                        qualimap_gff = ' -gff ' + sample.bed + ' '
                    self._submit_job(self.qualimap, sample.name, bam=sample.bam,
                                     sample=sample.name, genome=sample.genome,
                                     qualimap_gff=qualimap_gff, threads=self.threads_per_sample)

            # Processing VCFs: QC, annotation
            for caller in self.bcbio_structure.variant_callers.values():
                vcf_fpath = sample.vcf_by_callername.get(caller.name)
                if not vcf_fpath:
                    if sample.phenotype != 'normal':
                        err('VCF does not exist: sample ' + sample.name + ', caller ' + caller.name + '.')
                else:
                    self._process_vcf(sample, sample.bam, vcf_fpath, caller.name, threads=self.threads_per_sample)

            if self.cnf.verbose:
                info('-' * 70)
            else:
                print ''
                info()

        if not self.cnf.verbose:
            info('', ending='')

        # if self.vardict_steps:
        #     self._sumbit_vardict(self.bcbio_structure.batches)

        if self.varqc_summary in self.steps:
            self._submit_job(
                self.varqc_summary,
                wait_for_steps=[
                    self.varqc.job_name(s.name, v.name)
                    for v in self.bcbio_structure.variant_callers.values()
                    for s in v.samples
                    if self.varqc in self.steps])

        if self.varfilter_all in self.steps:
            self._submit_job(
                self.varfilter_all,
                wait_for_steps=[
                    self.varannotate.job_name(s.name, v.name)
                    for v in self.bcbio_structure.variant_callers.values()
                    for s in v.samples
                    if self.varannotate in self.steps],
                create_dir=False)

        # TargetSeq reports
        if self.abnormal_regions in self.steps:
            for sample in self.bcbio_structure.samples:
                if not self.cnf.verbose:
                    info(ending='')

                if not sample.bed or not verify_file(sample.bed):
                    err('Warning: no BED file, assuming WGS, thus running targetSeq reports '
                        'only to generate Seq2C reports.')
                    continue

                callers_and_filtered_vcfs = [(c, f) for c, f in ((c.name, c.get_filt_vcf_by_sample().get(sample.name)) for c in callers) if f]
                if callers_and_filtered_vcfs:
                    caller_names, filtered_vcfs = zip(*callers_and_filtered_vcfs)
                else:
                    caller_names, filtered_vcfs = [], []

                wait_for_steps = []
                if self.varfilter_all in self.steps:
                    wait_for_steps.extend([self.varfilter_all.job_name()])
                if self.targetcov in self.steps:
                    wait_for_steps.extend([self.targetcov.job_name(sample.name)])

                self._submit_job(
                    self.abnormal_regions, sample.name,
                    wait_for_steps=wait_for_steps,
                    sample=sample, threads=self.threads_per_sample,
                    caller_names='--caller-names ' + ','.join(caller_names) if caller_names else '',
                    vcfs='--vcfs ' + ','.join(filtered_vcfs) if filtered_vcfs else '')

        if self.varqc_after in self.steps:
            info('VarQC_postVarFilter:')
            for caller in self.bcbio_structure.variant_callers.values():
                info('  ' + caller.name)
                for sample in caller.samples:
                    info('    ' + sample.name)
                    clean_vcf_fpath = sample.get_pass_filt_vcf_fpath_by_callername(caller.name)
                    if not file_exists(clean_vcf_fpath) and not self.varfilter_all:
                        err('VCF does not exist: sample ' + sample.name + ', caller "' +
                            caller.name + '". You need to run VarFilter first.')
                    else:
                        self._submit_job(
                            self.varqc_after, sample.name, suf=caller.name, threads=self.threads_per_sample,
                            wait_for_steps=([self.varfilter_all.job_name()] if self.varfilter_all in self.steps else []),
                            vcf=sample.get_pass_filt_vcf_fpath_by_callername(caller.name),
                            sample=sample.name, caller=caller.name, genome=sample.genome)

        if self.varqc_after_summary in self.steps:
            self._submit_job(
                self.varqc_after_summary,
                wait_for_steps=[
                    self.varqc_after.job_name(s.name, v.name)
                    for v in self.bcbio_structure.variant_callers.values()
                    for s in v.samples
                    if self.varqc_after in self.steps])

        if self.seq2c in self.steps:
            self._submit_job(
                self.seq2c,
                wait_for_steps=[
                    self.targetcov.job_name(s.name)
                    for s in self.bcbio_structure.samples
                    if self.targetcov in self.steps])

        if self.targqc_summary in self.steps:
            wait_for_steps = []
            wait_for_steps += [self.targetcov.job_name(s.name) for s in self.bcbio_structure.samples if self.targetcov in self.steps]
            wait_for_steps += [self.ngscat.job_name(s.name) for s in self.bcbio_structure.samples if self.ngscat in self.steps]
            wait_for_steps += [self.qualimap.job_name(s.name) for s in self.bcbio_structure.samples if self.qualimap in self.steps]
            self._submit_job(
                self.targqc_summary,
                wait_for_steps=wait_for_steps
            )

        if self.fastqc_summary in self.steps:
            self._submit_job(self.fastqc_summary)

        if self.combined_report in self.steps:
            wait_for_steps = []
            # summaries
            wait_for_steps += [self.varqc_summary.job_name()] if self.varqc_summary in self.steps else []
            wait_for_steps += [self.targqc_summary.job_name()] if self.targqc_summary in self.steps else []
            wait_for_steps += [self.fastqc_summary.job_name()] if self.fastqc_summary in self.steps else []
            # and individual reports too
            wait_for_steps += [self.varqc.job_name(s.name) for s in self.bcbio_structure.samples if self.varqc in self.steps]
            wait_for_steps += [self.targetcov.job_name(s.name) for s in self.bcbio_structure.samples if self.targetcov in self.steps]
            wait_for_steps += [self.ngscat.job_name(s.name) for s in self.bcbio_structure.samples if self.ngscat in self.steps]
            wait_for_steps += [self.qualimap.job_name(s.name) for s in self.bcbio_structure.samples if self.qualimap in self.steps]
            self._submit_job(
                self.combined_report,
                wait_for_steps=wait_for_steps
            )

        if self.mongo_loader in self.steps:
            for sample in self.bcbio_structure.samples:
                for caller in self.bcbio_structure.variant_callers.values():

                    filt_vcf_fpath = sample.get_filt_vcf_fpath_by_callername(caller.name)
                    anno_vcf = sample.get_anno_vcf_fpath_by_callername(caller.name)
                    vcf = sample.get_vcf_fpath_by_callername(caller.name)

                    if file_exists(filt_vcf_fpath) or file_exists(vcf) or file_exists(anno_vcf):
                        self._submit_job(
                            self.mongo_loader, sample.name, suf=caller.name, create_dir=False,
                            wait_for_steps=([self.varfilter_all.job_name()] if self.varfilter_all in self.steps else []),
                            path=filt_vcf_fpath, sample=sample.name, variantCaller=caller.name,
                            project=self.bcbio_structure.project_name)

        if not self.cnf.verbose:
            print ''
        if self.cnf.verbose:
            info('Done.')

        if not self.jobs:
            info()
            info('No jobs submitted.')
        else:
            msg = ['Submitted jobs for the project ' + self.bcbio_structure.project_name +
                   '. Log files for each jobs to track:']
            lengths = []
            for job in self.jobs:
                lengths.append(len(job.name))
            max_length = max(lengths)

            for job in self.jobs:
                msg.append('  ' + job.name + ': ' + ' ' * (max_length - len(job.name)) + job.log_fpath)
            send_email('\n'.join(msg))

    def _process_vcf(self, sample, bam_fpath, vcf_fpath, caller_name, threads,
                     steps=None, job_names_to_wait=None):
        steps = steps or self.steps

        if self.varqc in steps:
            self._submit_job(
                self.varqc, sample.name, suf=caller_name, vcf=vcf_fpath, threads=threads,
                sample=sample.name, caller=caller_name, genome=sample.genome,
                wait_for_steps=job_names_to_wait)

        bam_cmdline = '--bam ' + bam_fpath if bam_fpath else ''
        normal_match_cmdline = ''
        if sample.normal_match:
            normal_match_cmdline = ' --match-normal-sample-name ' + sample.normal_match.name + ' '

        if self.varannotate in steps:
            self._submit_job(
                self.varannotate, sample.name, suf=caller_name, vcf=vcf_fpath, threads=threads,
                bam_cmdline=bam_cmdline, sample=sample.name, caller=caller_name,
                genome=sample.genome, normal_match_cmdline=normal_match_cmdline,
                wait_for_steps=job_names_to_wait)

        # anno_dirpath, _ = self.step_output_dir_and_log_paths(self.varannotate, sample_name, caller=caller_name)
        # annotated_vcf_fpath = join(anno_dirpath, basename(add_suffix(vcf_fpath, 'anno')))
        #
        # filter_dirpath = join(dirname(anno_dirpath), self.varfilter_all.dir_name)
        # safe_mkdir(filter_dirpath)

    def _symlink_cnv(self):
        cnv_summary_dirpath = join(self.bcbio_structure.date_dirpath, BCBioStructure.cnv_summary_dir)
        try:
            safe_mkdir(cnv_summary_dirpath)
        except OSError:
            pass

        for sample in self.bcbio_structure.samples:
            sample_dirpath = join(self.bcbio_structure.final_dirpath, sample.name)
            cnv_dirpath = join(sample_dirpath, BCBioStructure.cnv_dir)

            for fname in listdir(sample_dirpath):
                if any(fname.endswith(s) for s in ['-cn_mops.bed', '-ensemble.bed']):
                    if not isdir(cnv_dirpath): safe_mkdir(cnv_dirpath)
                    try:
                        os.rename(join(sample_dirpath, fname), join(cnv_dirpath, fname))
                    except OSError:
                        pass

            if isdir(cnv_dirpath):
                for fname in listdir(cnv_dirpath):
                    if not fname.startswith('.'):
                        src_fpath = join(cnv_dirpath, fname)

                        dst_fname = fname
                        if sample.name not in fname:
                            dst_fname = sample.name + '.' + dst_fname

                        dst_fpath = join(cnv_summary_dirpath, dst_fname)
                        try:
                            if islink(dst_fpath):
                                os.unlink(dst_fpath)
                            symlink_plus(src_fpath, dst_fpath)
                        except OSError:
                            pass