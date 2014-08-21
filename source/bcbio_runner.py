from dircache import listdir
import hashlib
import os
import shutil
import sys
import base64
from os.path import join, dirname, abspath, expanduser, basename, pardir, isfile, isdir, exists, islink
from source.bcbio_structure import BCBioStructure
from source.calling_process import call
from source.file_utils import verify_dir, verify_file, add_suffix
from source.tools_from_cnf import get_tool_cmdline

from source.file_utils import file_exists, safe_mkdir
from source.logger import info, err, critical
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


class Steps(list):
    def __init__(self):
        super(Steps, self).__init__()

    def add_step(self, step):
        self.append(step)

    def extend(self, iterable):
        for step in iterable:
            self.add_step(step)


# noinspection PyAttributeOutsideInit
class BCBioRunner:
    def __init__(self, cnf, bcbio_structure, bcbio_cnf):
        self.bcbio_structure = bcbio_structure
        self.final_dir = bcbio_structure.final_dirpath
        self.cnf = cnf
        self.bcbio_cnf = bcbio_cnf

        cnf.work_dir = bcbio_structure.work_dir

        hasher = hashlib.sha1(self.final_dir)
        self.run_id = base64.urlsafe_b64encode(hasher.digest()[0:8])[:-1]

        self.threads = str(self.cnf.threads)
        self.qsub_runner = abspath(expanduser(cnf.qsub_runner))

        self.steps = Steps()
        self.vardict_steps = Steps()

        self.set_up_steps(cnf, self.run_id)

        def normalize(name):
            return name.lower().replace('_', '').replace('-', '')

        def contains(x, xs):
            return normalize(x) in [normalize(y) for y in (xs or [])]

        self.steps.extend(
            [s for s in [
                self.varqc,
                self.varannotate,
                self.varfilter_all,
                self.mongo_loader,
                self.varqc_after,
                self.varqc_summary,
                self.targetcov,
                self.seq2c,
                self.ngscat,
                self.qualimap,
                self.targetcov_summary,
                self.ngscat_summary,
                self.qualimap_summary]
             if contains(s.name, cnf.steps)])

        self.vardict_steps.extend(
            [s for s in [
                self.vardict,
                self.testsomatic,
                self.var_to_vcf_somatic,
                self.varqc,
                self.varannotate,
                self.varfilter_all,
                self.varqc_after,
                self.varqc_summary]
             if contains(s.name, cnf.vardict_steps)])

        self._symlink_cnv()


    def set_up_steps(self, cnf, run_id):
        cnfs_line = ' --sys-cnf \'' + self.cnf.sys_cnf + '\' --run-cnf \'' + self.cnf.run_cnf + '\' '
        overwrite_line = {True: '-w', False: '--reuse'}.get(cnf.overwrite, '')
        spec_params = cnfs_line + ' -t ' + str(self.threads) + ' ' + overwrite_line + ' ' \
                      '--log-dir ' + self.bcbio_structure.log_dirpath + ' '

        self.varannotate = Step(cnf, run_id,
            name='VarAnnotate', short_name='va',
            interpreter='python',
            script='varannotate',
            dir_name=BCBioStructure.varannotate_dir,
            paramln=spec_params + ' --vcf \'{vcf}\' {bam_cmdline} {normal_match_cmdline} '
                                  '-o \'{output_dir}\' -s \'{sample}\' -c {caller} '
                                  '--work-dir \'' + join(cnf.work_dir, BCBioStructure.varannotate_name) + '_{sample}\''
        )
        self.varqc = Step(cnf, run_id,
            name='VarQC', short_name='vq',
            interpreter='python',
            script='varqc',
            dir_name=BCBioStructure.varqc_dir,
            paramln=spec_params + ' --vcf \'{vcf}\' -o \'{output_dir}\' -s \'{sample}\' -c {caller} '
                    '--work-dir \'' + join(cnf.work_dir, BCBioStructure.varqc_name) + '_{sample}\''
        )
        self.varqc_after = Step(cnf, run_id,
            name='VarQC_postVarFilter', short_name='vqa',
            interpreter='python',
            script='varqc',
            dir_name=BCBioStructure.varqc_after_dir,
            paramln=spec_params + ' --vcf \'{vcf}\' -o \'{output_dir}\' -s \'{sample}\' -c {caller} '
                    '--work-dir \'' + join(cnf.work_dir, BCBioStructure.varqc_name) + '_{sample}\' ' +
                    '--proc-name ' + BCBioStructure.varqc_after_name
        )
        self.targetcov = Step(cnf, run_id,
            name='TargetCov', short_name='tc',
            interpreter='python',
            script='targetcov',
            dir_name=BCBioStructure.targetseq_dir,
            paramln=spec_params + ' --bam \'{bam}\' --bed \'{bed}\' -o \'{output_dir}\' '
                    '-s \'{sample}\' --work-dir \'' + join(cnf.work_dir, BCBioStructure.targetseq_name) + '_{sample}\''
        )
        self.ngscat = Step(cnf, run_id,
            interpreter='python',
            script='ngscat',
            dir_name=BCBioStructure.ngscat_dir,
            name='ngsCAT', short_name='nc',
            paramln=spec_params + ' --bam \'{bam}\' --bed \'{bed}\' -o \'{output_dir}\' -s \'{sample}\' '
                    '--saturation y --work-dir \'' + join(cnf.work_dir, BCBioStructure.ngscat_name) + '_{sample}\''
        )
        self.qualimap = Step(cnf, run_id,
            script='qualimap',
            dir_name=BCBioStructure.qualimap_dir,
            name='QualiMap', short_name='qm',
            paramln=' bamqc -nt ' + self.threads + ' --java-mem-size=24G -nr 5000 '
                    '-bam \'{bam}\' -outdir \'{output_dir}\' {qualimap_gff} -c -gd HUMAN'
        )
        #############
        # Summaries #
        self.varqc_summary = Step(cnf, run_id,
            name='VarQC_summary', short_name='vqs',
            interpreter='python',
            script='varqc_summary',
            dir_name=BCBioStructure.varqc_summary_dir,
            paramln=cnfs_line + ' ' + self.final_dir
        )
        self.varfilter_all = Step(cnf, run_id,
            name='VarFilter', short_name='vfs',
            interpreter='python',
            script='varfilter_all',
            dir_name=BCBioStructure.varfilter_dir,
            paramln=spec_params + ' ' + self.final_dir
        )
        self.mongo_loader = Step(cnf, run_id,
            name='MongoLoader', short_name='ml',
            interpreter='java',
            script='vcf_loader',
            dir_name='mongo_loader',
            paramln=' -project {project} -sample {sample} -path {path} -variantCaller {variantCaller}'
        )
        self.targetcov_summary = Step(cnf, run_id,
            name='TargetCov_summary', short_name='tcs',
            interpreter='python',
            script='targetcov_summary',
            dir_name=BCBioStructure.targetseq_summary_dir,
            paramln=cnfs_line + ' ' + self.final_dir
        )
        self.seq2c = Step(cnf, run_id,
            name='Seq2C', short_name='seq2c',
            interpreter='python',
            script='seq2c',
            dir_name=BCBioStructure.cnv_summary_dir,
            paramln=cnfs_line + ' ' + self.final_dir
        )
        self.ngscat_summary = Step(cnf, run_id,
            name='ngsCAT_summary', short_name='ncs',
            interpreter='python',
            script='ngscat_summary',
            dir_name=BCBioStructure.ngscat_summary_dir,
            paramln=cnfs_line + ' \'' + self.final_dir + '\''
        )
        self.qualimap_summary = Step(cnf, run_id,
            name='QualiMap_summary', short_name='qms',
            interpreter='python',
            script='qualimap_summary',
            dir_name=BCBioStructure.qualimap_summary_dir,
            paramln=cnfs_line + ' \'' + self.final_dir + '\''
        )

        af_thr = str(cnf.variant_filtering.min_freq)
        self.vardict = Step(cnf, run_id,
            name='VarDict',
            interpreter='perl',
            script='vardict_pl',
            dir_name='VarDict',
            paramln=' -G ' + cnf.genome.seq + ' -f ' + af_thr + ' -N {tumor_name} -b \'{tumor_bam}|{normal_bam}\''
                    ' -z -F -c 1 -S 2 -E 3 -g 4 {bed} > {vars_txt}'
        )
        self.testsomatic = Step(cnf, run_id,
            name='TestSomatic',
            script='testsomatic_r',
            dir_name='VarDict',
            paramln=' < {vars_txt} > {somatic_vars_txt}',
        )
        self.var_to_vcf_somatic = Step(cnf, run_id,
            name='Var2Vcf_Somatic',
            interpreter='perl',
            script='var2vcf_somatic_pl',
            dir_name='VarDict',
            paramln=' -N \'{tumor_name}|{normal_name}\' -f ' +
                    af_thr + ' < {somatic_vars_txt} > {vardict_vcf}',
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


    def submit(self, step, sample_name='', suf=None, create_dir=True,
               out_fpath=None, wait_for_steps=list(), threads=None, **kwargs):

        output_dirpath, log_fpath = self.step_output_dir_and_log_paths(step, sample_name, suf)
        if output_dirpath and not isdir(output_dirpath) and create_dir:
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

        tool_cmdline = get_tool_cmdline(self.cnf, step.interpreter, step.script)
        if not tool_cmdline: sys.exit(1)
        params = dict({'output_dir': output_dirpath}.items() + self.__dict__.items() + kwargs.items())
        cmdline = tool_cmdline + ' ' + step.param_line.format(**params)

        hold_jid_line = '-hold_jid ' + ','.join(wait_for_steps or ['_'])
        job_name = step.job_name(sample_name, suf)
        qsub = get_tool_cmdline(self.cnf, 'qsub')
        threads = str(threads or self.threads)
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

    # def _sumbit_vardict(self, batches):
    #     for batch_name, batch in batches.items():
    #         normal_name, normal_bam_fpath = batch['normal']
    #         bed_fpath = batch['bed']
    #         for tumor_name, tumor_bam_fpath in batch['tumor'].items():
    #             output_dirpath, _ = self.step_output_dir_and_log_paths(self.vardict, tumor_name)
    #             vars_txt = join(output_dirpath, 'vardict.txt')
    #
    #             if not verify_bam(tumor_bam_fpath):
    #                 sys.exit(1)
    #
    #             if not file_exists(tumor_bam_fpath + '.bai'):
    #                 samtools = get_tool_cmdline(self.cnf, 'samtools')
    #                 cmdline = '{samtools} index {bam}'.format(samtools=samtools, bam=tumor_bam_fpath)
    #                 call(self.cnf, cmdline)
    #
    #             if self.vardict in self.vardict_steps:
    #                 self.submit(
    #                     self.vardict, tumor_name, suf='vardict',
    #                     tumor_name=tumor_name,
    #                     normal_name=normal_name,
    #                     tumor_bam=tumor_bam_fpath,
    #                     normal_bam=normal_bam_fpath,
    #                     bed=bed_fpath,
    #                     vars_txt=vars_txt)
    #
    #             somatic_vars_txt = join(output_dirpath, 'somatic_variants.txt')
    #             if self.testsomatic in self.vardict_steps:
    #                 self.submit(
    #                     self.testsomatic, tumor_name, suf='testsomatic',
    #                     vars_txt=vars_txt,
    #                     somatic_vars_txt=somatic_vars_txt,
    #                     wait_for_steps=[self.vardict.job_name(tumor_name, 'vardict')])
    #
    #             vardict_vcf = join(output_dirpath, 'somatic_variants-vardict_standalone.vcf')
    #             if self.var_to_vcf_somatic in self.vardict_steps:
    #                 self.submit(
    #                     self.var_to_vcf_somatic, tumor_name, suf='var2vcf',
    #                     tumor_name=tumor_name,
    #                     normal_name=normal_name,
    #                     somatic_vars_txt=somatic_vars_txt,
    #                     vardict_vcf=vardict_vcf,
    #                     wait_for_steps=[self.testsomatic.job_name(tumor_name, 'testsomatic')])
    #
    #             self._process_vcf(
    #                 tumor_name, tumor_bam_fpath, vardict_vcf, 'vardict_standalone', steps=self.vardict_steps,
    #                 job_names_to_wait=[self.var_to_vcf_somatic.job_name(tumor_name, 'var2vcf')])

    def post_jobs(self):
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
                         self.mongo_loader])
                    or self.vardict_steps):
                continue

            info('Processing "' + sample.name + '"')
            if not self.cnf.verbose:
                info(ending='')

            # BAMS
            if any(step in self.steps for step in [
                   self.targetcov,
                   self.qualimap,
                   self.ngscat]) \
                    or self.vardict in self.vardict_steps:
                if not sample.bam or not verify_bam(sample.bam):
                    sys.exit('Cannot run coverage reports (targetcov, qulimap, ngscat, vardict) without BAM files.')

            # BEDS
            if (self.targetcov in self.steps) and (not sample.bed or not verify_file(sample.bed)):
                critical('Cannot make targetseq reports without BED file.')
            if (self.ngscat in self.steps) and (not sample.bed or not verify_file(sample.bed)):
                critical('Cannot run ngsCAT without BED file.')
            qualimap_gff = ''
            if self.qualimap in self.steps:
                if sample.bed:
                    self.submit(self.qualimap, sample.name, bam=sample.bam,
                                bed=sample.bed, sample=sample,
                                qualimap_gff=' -gff ' + sample.bed + ' ')

            # SUBMITTING
            for step in [self.targetcov, self.ngscat]:
                if step in self.steps:
                    self.submit(step, sample.name, bam=sample.bam,
                                bed=sample.bed, sample=sample)

            for variant_caller in self.bcbio_structure.variant_callers.values():
                vcf_fpath = sample.vcf_by_callername.get(variant_caller.name)
                if not vcf_fpath:
                    err('VCF does not exist: sample ' + sample.name + ', caller ' + variant_caller.name + ' .')
                else:
                    self._process_vcf(sample, sample.bam, vcf_fpath, variant_caller.name)

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
            self.submit(
                self.varqc_summary,
                wait_for_steps=[
                    self.varqc.job_name(s.name, v.name)
                    for v in self.bcbio_structure.variant_callers.values()
                    for s in v.samples
                    if self.varqc in self.steps])

        if self.targetcov_summary in self.steps:
            self.submit(
                self.targetcov_summary,
                wait_for_steps=[
                    self.targetcov.job_name(s.name)
                    for s in self.bcbio_structure.samples
                    if self.targetcov in self.steps])

        if self.seq2c in self.steps:
            self.submit(
                self.seq2c,
                wait_for_steps=[
                    self.targetcov.job_name(s.name)
                    for s in self.bcbio_structure.samples
                    if self.targetcov in self.steps])

        if self.ngscat_summary in self.steps:
            self.submit(
                self.ngscat_summary,
                wait_for_steps=[
                    self.ngscat.job_name(s.name)
                    for s in self.bcbio_structure.samples
                    if self.ngscat in self.steps])

        if self.qualimap_summary in self.steps:
            self.submit(
                self.qualimap_summary,
                wait_for_steps=[
                    self.qualimap.job_name(s.name)
                    for s in self.bcbio_structure.samples
                    if self.qualimap in self.steps])

        if self.varfilter_all in self.steps:
            self.submit(
                self.varfilter_all,
                wait_for_steps=[
                    self.varannotate.job_name(s.name, v.name)
                    for v in self.bcbio_structure.variant_callers.values()
                    for s in v.samples
                    if self.varannotate in self.steps],
                create_dir=False,
                threads=len(self.bcbio_structure.batches))

        if self.mongo_loader in self.steps:
            for sample in self.bcbio_structure.samples:
                for variant_caller in self.bcbio_structure.variant_callers.values():
                    filt_vcf_fpath = sample.filtered_vcf_by_callername.get(variant_caller.name)
                    if filt_vcf_fpath:
                        self.submit(
                            self.mongo_loader, sample.name, suf=variant_caller.name, create_dir=False,
                            wait_for_steps=([self.varfilter_all.job_name()] if self.varfilter_all in self.steps else []),
                            path=filt_vcf_fpath, sample=sample.name, variantCaller=variant_caller.name,
                            project=self.bcbio_structure.project_name)

        if not self.cnf.verbose:
            print ''
        if self.cnf.verbose:
            info('Done.')

    def _process_vcf(self, sample, bam_fpath, vcf_fpath, caller_name,
                     steps=None, job_names_to_wait=list()):
        steps = steps or self.steps
        sample_name = sample.name

        if self.varqc in steps:
            self.submit(
                self.varqc, sample_name, suf=caller_name, vcf=vcf_fpath,
                sample=sample_name, caller=caller_name, wait_for_steps=job_names_to_wait)

        bam_cmdline = '--bam ' + bam_fpath if bam_fpath else ''
        normal_match_cmdline = ''
        if sample.normal_match:
            normal_match_cmdline = ' --match-normal-sample-name ' + sample.normal_match.name + ' '

        if self.varannotate in steps:
            self.submit(
                self.varannotate, sample_name, suf=caller_name, vcf=vcf_fpath,
                bam_cmdline=bam_cmdline, sample=sample_name, caller=caller_name,
                normal_match_cmdline=normal_match_cmdline,
                wait_for_steps=job_names_to_wait)

        anno_dirpath, _ = self.step_output_dir_and_log_paths(self.varannotate, sample_name, caller=caller_name)
        annotated_vcf_fpath = join(anno_dirpath, basename(add_suffix(vcf_fpath, 'anno')))

        filter_dirpath = join(dirname(anno_dirpath), self.varfilter_all.dir_name)
        safe_mkdir(filter_dirpath)
        filtered_clean_vcf_fpath = join(filter_dirpath, basename(add_suffix(annotated_vcf_fpath, 'filt.passed')))

        sample.filtered_clean_vcf_by_callername[caller_name] = filtered_clean_vcf_fpath

        if self.varqc_after in steps:
            self.submit(
                self.varqc_after, sample_name, suf=caller_name,
                wait_for_steps=([self.varfilter_all.job_name()]
                                 if self.varfilter_all in steps else []) + job_names_to_wait,
                vcf=filtered_clean_vcf_fpath, sample=sample_name, caller=caller_name)


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
                            os.symlink(src_fpath, dst_fpath)
                        except OSError:
                            pass

