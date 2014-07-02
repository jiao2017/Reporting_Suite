#!/usr/bin/env python
import sys

from os.path import basename, join, expanduser
from collections import OrderedDict

from ext_modules import vcf
from ext_modules.vcf.model import _Record

from source.calling_process import call_subprocess
from source.change_checking import check_file_changed
from source.config import join_parent_conf
from source.file_utils import iterate_file, verify_file
from source.tools_from_cnf import get_java_tool_cmdline
from source.utils_from_bcbio import open_gzipsafe, splitext_plus
from source.logger import step_greetings, info, critical


class Record(_Record):
    # noinspection PyMissingConstructor
    def __init__(self, _record, line_num):
        self.__dict__.update(_record.__dict__)
        self.line_num = line_num

    def cls(self):
        cls = 'Novel'
        if 'COSM' in self.ID:
            cls = 'COSMIC'
        elif self.ID.startswith('rs'):
            if self.check_clnsig:
                cls = 'ClnSNP'
            else:
                cls = 'dbSNP'
        return cls

    def is_rejected(self):
        if self.FILTER:
            assert '.' not in self.FILTER
        return self.FILTER and 'PASS' not in self.FILTER

    def check_clnsig(self):
        if not self.INFO.get('CLNSIG'):
            return 0

        for c in self.INFO.get('CLNSIG'):
            if 3 < c < 7 or c == 255:
                return 1

        return -1

    def sample(self):
        return self.INFO.get('SAMPLE')

    def var_id(self):
        return ':'.join(map(str, [self.CHROM, self.POS, self.REF, self.ALT]))


def proc_vcf(inp_f, out_f, proc_line_fun):
    reader = vcf.Reader(inp_f)
    writer = vcf.Writer(out_f, reader)

    for i, rec in enumerate(reader):
        rec = proc_line_fun(Record(rec, i))
        if rec:
            writer.write_record(rec)


def filter_rejected(cnf, input_fpath):
    step_greetings('Extracting dataset by filename, filtering '
                   'lines that are not . nor PASS in filter.')

    def __iter_file(l, i):
        if l.startswith('#'):
            return l

        filt = l.split('\t')[6]
        if filt in ['PASS', '.']:
            return l
        else:
            return None

    output_fpath = iterate_file(cnf, input_fpath, __iter_file)
    info('Saved to ' + output_fpath)
    return output_fpath


def read_samples_info_and_split(common_cnf, options, inputs):
    #TODO: _set_up_dirs(cnf) for each sample

    info('')
    info('Processing input details...')

    details = None
    for key in inputs:
        if options.get(key):
            common_cnf[key] = expanduser(options[key])
            info('Using ' + common_cnf[key])
            details = [common_cnf]
    if not details:
        details = common_cnf.get('details')
    if not details:
        critical('Please, provide input ' + ', '.join(inputs) +
                 ' in command line or in run info yaml config.')

    all_samples = OrderedDict()

    for one_item_cnf in details:
        if 'vcf' not in one_item_cnf:
            critical('ERROR: A section in details does not contain field "var".')
        one_item_cnf['vcf'] = expanduser(one_item_cnf['vcf'])
        if not verify_file(one_item_cnf['vcf'], 'Input file'):
            sys.exit(1)

        join_parent_conf(one_item_cnf, common_cnf)

        work_vcf = join(one_item_cnf['work_dir'], basename(one_item_cnf['vcf']))
        check_file_changed(one_item_cnf, one_item_cnf['vcf'], work_vcf)
        if not one_item_cnf.get('reuse_intermediate'):
            with open_gzipsafe(one_item_cnf['vcf']) as inp, open(work_vcf, 'w') as out:
                out.write(inp.read())
        one_item_cnf['vcf'] = work_vcf

        vcf_header_samples = read_sample_names_from_vcf(one_item_cnf['vcf'])

        # MULTIPLE SAMPELS
        if ('samples' in one_item_cnf or one_item_cnf.get('split_samples')) and len(vcf_header_samples) == 0:
            sample_cnfs = _verify_sample_info(one_item_cnf, vcf_header_samples)

            for header_sample_name in vcf_header_samples:
                if header_sample_name not in sample_cnfs:
                    sample_cnfs[header_sample_name] = one_item_cnf.copy()

                if header_sample_name in all_samples:
                    critical('ERROR: duplicated sample name: ' + header_sample_name)

                cnf = all_samples[header_sample_name] = sample_cnfs[header_sample_name]
                cnf['name'] = header_sample_name
                if cnf.get('keep_intermediate'):
                    cnf['log'] = join(cnf['work_dir'], cnf['name'] + '.log')

                cnf['vcf'] = extract_sample(cnf, one_item_cnf['vcf'], cnf['name'], cnf['work_dir'])
                info()

        # SINGLE SAMPLE
        else:
            cnf = one_item_cnf

            if 'bam' in cnf:
                cnf['bam'] = expanduser(cnf['bam'])
                if not verify_file(cnf['bam']):
                    sys.exit(1)

            cnf['name'] = splitext_plus(basename(cnf['vcf']))[0]

            if cnf.get('keep_intermediate'):
                cnf['log'] = join(cnf['work_dir'], cnf['name'] + '.log')

            cnf['vcf'] = work_vcf
            all_samples[cnf['name']] = cnf

    if not all_samples:
        info('No samples.')
    else:
        info('Using samples: ' + ', '.join(all_samples) + '.')

    return all_samples


def read_sample_names_from_vcf(vcf_fpath):
    basic_fields = next((l.strip()[1:].split() for l in open_gzipsafe(vcf_fpath)
                        if l.strip().startswith('#CHROM')), None)
    if not basic_fields:
        critical('Error: no VCF header in ' + vcf_fpath)
    if len(basic_fields) < 9:
        return []
    return basic_fields[9:]


def extract_sample(cnf, input_fpath, samplename, work_dir=None):
    if work_dir is None:
        work_dir = cnf['work_dir']

    vcf_header_samples = read_sample_names_from_vcf(input_fpath)

    if len(vcf_header_samples) == 0:
        return input_fpath

    if len(vcf_header_samples) > 0 and samplename not in vcf_header_samples:
            critical('Error: not sample ' + samplename + ' in the ' + input_fpath +
                     ' header: available only ' + ', '.join(vcf_header_samples))

    if len(vcf_header_samples) == 1:
        return input_fpath

    info('-' * 70)
    info('Extracting sample ' + samplename)
    info('-' * 70)

    executable = get_java_tool_cmdline(cnf, 'gatk')
    ref_fpath = cnf['genome']['seq']

    corr_samplename = ''.join([c if c.isalnum() else '_' for c in samplename])

    output_fname = splitext_plus(input_fpath)[0] + '.' + corr_samplename + '.vcf'
    output_fpath = join(work_dir, output_fname)

    cmd = '{executable} -nt 30 -R {ref_fpath} -T SelectVariants ' \
          '--variant {input_fpath} -sn {samplename} ' \
          '-o {output_fpath}'.format(**locals())
    call_subprocess(cnf, cmd, None, output_fpath, stdout_to_outputfile=False,
         to_remove=[input_fpath + '.idx'])

    return output_fpath


def _verify_sample_info(vcf_conf, vcf_header_samples):
    if 'samples' in vcf_conf:
        for header_sample_name, sample_conf in vcf_conf['samples'].items():
            join_parent_conf(sample_conf, vcf_conf)

            bam = sample_conf.get('bam')
            if bam and not verify_file(expanduser(bam), 'Bam file'):
                exit()
            sample_conf['bam'] = expanduser(bam)

    sample_cnfs = vcf_conf.get('samples') or OrderedDict()

    # compare input sample names to vcf header
    if sample_cnfs:
        for input_sample_name, sample_conf in sample_cnfs.items():
            if input_sample_name not in vcf_header_samples:
                critical('ERROR: sample ' + input_sample_name +
                         ' is not in VCF header ' + vcf_header_samples + '\n'
                         'Available samples: ' + ', '.join(vcf_header_samples))
    return sample_cnfs