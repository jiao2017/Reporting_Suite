# Annotation script that takes 1-3 inputs, first being the vcf file name,
# second being an indicator if the vcf is from bcbio's ensemble pipeline ('true' if true) and
# third being 'RNA' if the vcf is from the rna-seq mutect pipeline
from genericpath import isfile, getsize
import os
from os.path import join, splitext
import subprocess
import sys
import shutil
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


def which(program):
    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None


def check_executable(program):
    assert which(program), program + ' executable required.'


def check_existence(file):
    assert isfile(file) and getsize(file), file + ' required and does not exist or empty.'


run_config = {}
system_config = {}


def log_print(msg=''):
    print(msg)
    if 'log' in run_config:
        open(run_config['log'], 'w').write(msg)


def _call_and_rename(cmdline, input_fpath, suffix, to_stdout=True):
    basepath, ext = splitext(input_fpath)
    output_fpath = basepath + '.' + suffix + ext

    if run_config.get('reuse') and isfile(output_fpath) and getsize(output_fpath) > 0:
        log_print(output_fpath + ' exists, reusing')
        return output_fpath

    log_print('')
    log_print('*' * 70)
    log_print(cmdline)
    res = subprocess.call(
        cmdline.split(),
        stdout=open(output_fpath, 'w') if to_stdout else open(run_config['log'], 'a'),
        stderr=open(run_config['log'], 'a'))
    log_print('')
    if res != 0:
        log_print('Command returned status ' + str(res) + ('. Log in ' + run_config['log']))
        exit(1)
    else:
        log_print('Saved to ' + output_fpath)
        print('Log in ' + run_config['log'])

    if not run_config.get('save_intermediate'):
        os.remove(input_fpath)
    log_print('Now processing ' + output_fpath)
    return output_fpath


def snpsift_annotate(db_name, input_fpath):
    assert 'snpeff' in system_config['resources']
    snpeff_config = system_config['resources']['snpeff']
    check_executable('java')
    assert dir in snpeff_config, 'Please, provide snpEff directory (dir).'
    snpeff_dir = snpeff_config['dir']
    snpsift_jar = join(snpeff_dir, 'SnpSift.jar')
    check_existence(snpsift_jar)

    db_path = run_config[db_name].get('path')
    annotations = run_config[db_name].get('annotations')

    cmdline = 'java -jar %s annotate -v %s %s' % (snpsift_jar, db_path, input_fpath)
    return _call_and_rename(cmdline, input_fpath, db_path, to_stdout=True)


def snpsift_db_nsfp(input_fpath):
    if 'db_nsfp' not in run_config:
        return input_fpath

    assert 'snpeff' in system_config['resources']
    snpeff_config = system_config['resources']['snpeff']
    check_executable('java')
    assert dir in snpeff_config, 'Please, provide snpEff directory in the system config (dir).'
    snpeff_dir = snpeff_config['dir']
    snpsift_jar = os.path.join(snpeff_dir, 'SnpSift.jar')
    check_existence(snpsift_jar)

    db_path = run_config['db_nsfp'].get('path')
    assert db_path, 'Please, provide a path to db nsfp file in run_config.'
    annotations = run_config['db_nsfp'].get('annotations', [])
    ann_line = '"' + ','.join(annotations) + '"'

    cmdline = 'java -jar %s dbnsfp -f %s -v %s %s' % (snpsift_jar, ann_line, db_path, input_fpath)
    return _call_and_rename(cmdline, input_fpath, 'db_nsfp', to_stdout=True)


def snpeff(input_fpath):
    if 'snpeff' not in run_config:
        return input_fpath

    assert 'snpeff' in system_config['resources']
    snpeff_config = system_config['resources']['snpeff']
    check_executable('java')
    assert dir in snpeff_config, 'Please, provide snpEff directory in the system config (dir).'
    snpeff_dir = snpeff_config['dir']
    snpeff_jar = join(snpeff_dir, 'SnpEff.jar')
    check_existence(snpeff_jar)

    ref_name = run_config['genome_build']
    db_path = run_config['snpeff'].get('path')
    assert db_path, 'Please, provide a path to db nsfp file in run_config.'

    cmdline = 'java -Xmx4g -jar %s eff -dataDir %s -noStats -cancer ' \
              '-noLog -1 -i vcf -o vcf %s %s' % \
              (snpeff_jar, db_path, ref_name, input_fpath)

    return _call_and_rename(cmdline, input_fpath, 'snpEff', to_stdout=True)


def rna_editing_sites(db, input_fpath):
    assert which('vcfannotate'), 'vcfannotate executable required.'

    cmdline = 'vcfannotate -b %s -k RNA_editing_site %s' % (db, input_fpath)
    return _call_and_rename(cmdline, input_fpath, 'edit', to_stdout=True)


def gatk(input_fpath):
    if 'gatk' not in run_config:
        return input_fpath

    assert 'gatk' in system_config['resources']
    gatk_config = system_config['resources']['gatk']
    check_executable('java')
    assert dir in gatk_config, 'Please, provide gatk directory in the system config (dir).'
    gatk_dir = gatk_config['dir']
    gatk_jar = join(gatk_dir, 'GenomeAnalysisTK.jar')
    check_existence(gatk_jar)

    base_name, ext = os.path.splitext(input_fpath)
    output_fpath = base_name + '.gatk' + ext

    ref_fpath = run_config['reference']

    cmdline = 'java -Xmx2g -jar %s -R %s -T VariantAnnotator ' \
              '-o %s --variant %s' % \
              (gatk_jar, ref_fpath, output_fpath, input_fpath)

    if 'annotations' in gatk_config:
        annotations = gatk_config['annotations']
        for ann in annotations:
            cmdline += " -A " + ann

    return _call_and_rename(cmdline, input_fpath, 'gatk', to_stdout=False)


#def annotate_hg19(sample_fpath, snp_eff_dir, snp_eff_scritps, gatk_dir, run_config, log_fpath=None):
#    is_rna = run_config.get('rna', False)
#    is_ensemble = run_config.get('ensemble', False)
#
#    ref_name = 'hg19'
#    ref_path = '/ngs/reference_data/genomes/Hsapiens/hg19/seq/hg19.fa'
#    dbsnp_db = '/ngs/reference_data/genomes/Hsapiens/hg19/variation/dbsnp_137.vcf'
#    cosmic_db = '/ngs/reference_data/genomes/Hsapiens/hg19/variation/cosmic-v67_20131024-hg19.vcf'
#    db_nsfp_db = '/ngs/reference_data/genomes/Hsapiens/hg19/dbNSF/dbNSFP2.3/dbNSFP2.3.txt.gz'
#    snpeff_datadir = '/ngs/reference_data/genomes/Hsapiens/hg19/snpeff'
#    annot_track = '/ngs/reference_data/genomes/Hsapiens/hg19/variation/Human_AG_all_hg19_INFO.bed'
#
#    annotate(sample_fpath,
#             snp_eff_dir, snp_eff_scritps, gatk_dir,
#             ref_name, ref_path,
#             dbsnp_db, cosmic_db, db_nsfp_db,
#             snpeff_datadir, annot_track,
#             log_fpath, True, is_rna, is_ensemble, reuse)


#def annotate_GRCh37(sample_fpath, snp_eff_dir, snp_eff_scripts, gatk_dir, run_config, log_fpath=None):
#    is_rna = run_config.get('rna', False)
#    is_ensemble = run_config.get('ensemble', False)
#
#    ref_name = 'GRCh37'
#    ref_path = '/ngs/reference_data/genomes/Hsapiens/GRCh37/seq/GRCh37.fa'
#    dbsnp_db = '/ngs/reference_data/genomes/Hsapiens/GRCh37/variation/dbsnp_138.vcf'
#    cosmic_db = '/ngs/reference_data/genomes/Hsapiens/GRCh37/variation/cosmic-v67_20131024-GRCh37.vcf'
#    db_nsfp_db = '/ngs/reference_data/genomes/Hsapiens/hg19/dbNSF/dbNSFP2.3/dbNSFP2.3.txt.gz'
#    snpeff_datadir = '/ngs/reference_data/genomes/Hsapiens/GRCh37/snpeff'
#    annot_track = '/ngs/reference_data/genomes/Hsapiens/hg19/variation/Human_AG_all_hg19_INFO.bed'
#
#    annotate(sample_fpath,
#             snp_eff_dir, snp_eff_scripts, gatk_dir,
#             ref_name, ref_path,
#             dbsnp_db, cosmic_db, db_nsfp_db,
#             snpeff_datadir, annot_track,
#             log_fpath, True, is_rna, is_ensemble)


def extract_fields(input_fpath):
    check_executable('perl')
    check_executable('java')

    snpeff_config = system_config['resources'].get('snpeff')
    assert snpeff_config

    assert dir in snpeff_config, 'Please, provide snpEff directory in the system config (dir).'
    snpeff_dir = snpeff_config['dir']
    snpsift_jar = os.path.join(snpeff_dir, 'SnpSift.jar')
    check_existence(snpsift_jar)

    snpeff_scripts = snpeff_config['scripts']
    assert snpeff_scripts
    vcfoneperline = os.path.join(snpeff_scripts, 'vcfEffOnePerLine.pl')
    check_existence(vcfoneperline)

    cmdline = 'perl ' + vcfoneperline + ' | ' \
              'java -jar ' + snpsift_jar + ' extractFields - ' \
              'CHROM POS ID CNT GMAF REF ALT QUAL FILTER TYPE ' \
              '"EFF[*].EFFECT" "EFF[*].IMPACT" "EFF[*].CODON" ' \
              '"EFF[*].AA" "EFF[*].AA_LEN" "EFF[*].GENE" ' \
              '"EFF[*].FUNCLASS" "EFF[*].BIOTYPE" "EFF[*].CODING" ' \
              '"EFF[*].TRID" "EFF[*].RANK" ' \
              'dbNSFP_SIFT_score dbNSFP_Polyphen2_HVAR_score ' \
              'dbNSFP_Polyphen2_HVAR_pred dbNSFP_LRT_score dbNSFP_LRT_pred ' \
              'dbNSFP_MutationTaster_score dbNSFP_MutationTaster_pred ' \
              'dbNSFP_MutationAssessor_score dbNSFP_MutationAssessor_pred ' \
              'dbNSFP_FATHMM_score dbNSFP_Ensembl_geneid dbNSFP_Ensembl_transcriptid ' \
              'dbNSFP_Uniprot_acc dbNSFP_1000Gp1_AC dbNSFP_1000Gp1_AF ' \
              'dbNSFP_ESP6500_AA_AF dbNSFP_ESP6500_EA_AF KGPROD PM PH3 ' \
              'AB AC AF DP FS GC HRun HaplotypeScore ' \
              'G5 CDA GMAF GENEINFO OM DB GENE AA CDS ' \
              'MQ0 QA QD ReadPosRankSum '

    basepath, ext = os.path.splitext(input_fpath)
    output_fpath = basepath + '.extract' + ext

    if run_config.get('reuse') and isfile(output_fpath) and getsize(output_fpath):
        log_print(output_fpath + ' exists, reusing')
    else:
        log_print('')
        log_print('*' * 70)
        log_print(cmdline)
        res = subprocess.call(cmdline,
                              stdin=open(sample_fpath),
                              stdout=open(output_fpath, 'w'),
                              stderr=open(run_config['log'], 'a'),
                              shell=True)
        log_print('')
        if res != 0:
            log_print('Command returned status ' + str(res) + ('. Log in ' + run_config['log']))
            exit(1)
            # return input_fpath
        else:
            log_print('Saved to ' + output_fpath)
            print('Log in ' + run_config['log'])

        if not run_config.get('save_intermediate'):
            os.remove(sample_fpath)

    os.rename(sample_fpath, splitext(sample_fpath)[0] + '.tsv')


def process_rna(sample_fpath):
    sample_fname = os.path.basename(sample_fpath)
    sample_basename, ext = os.path.splitext(sample_fname)
    check_executable('vcf-subset')
    cmdline = 'vcf-subset -c %s -e %s' % (sample_basename.replace('-ensemble', ''), sample_fpath)

    return _call_and_rename(cmdline, sample_fpath, '.ensm', to_stdout=True)


def process_ensemble(sample_fpath):
    sample_basepath, ext = os.path.splitext(sample_fpath)
    pass_sample_fpath = sample_basepath + '.pass' + ext
    with open(sample_fpath) as sample, open(pass_sample_fpath, 'w') as pass_sample:
        for line in sample.readlines():
            if 'REJECT' not in line:
                pass_sample.write(line)
    if run_config.get('save_intermediate'):
        return pass_sample_fpath
    else:
        os.remove(sample_fpath)
        os.rename(pass_sample_fpath, sample_fpath)
        return sample_fpath


def annotate(sample_fpath):
    assert 'resources' in system_config

    if run_config.get('rna'):
        sample_fpath = process_rna(sample_fpath)

    if run_config.get('ensemble'):
        sample_fpath = process_ensemble(sample_fpath)

    assert 'genome_build' in run_config, 'Please, provide genome build (genome_build).'
    assert 'reference' in run_config, 'Please, provide path to the reference file (reference).'
    check_existence(run_config['reference'])

    if 'vcfs' in run_config:
        for vcf in run_config['vcfs']:
            sample_fpath = snpsift_annotate(vcf, sample_fpath)

    sample_fpath = snpsift_db_nsfp(sample_fpath)

    #if run_config.get('rna'):
    #    sample_fpath = rna_editing_sites(annot_track, sample_fpath, save_intermediate)

    sample_fpath = gatk(sample_fpath)
    sample_fpath = snpeff(sample_fpath)
    extract_fields(sample_fpath)


def remove_quotes(str):
    if str and str[0] == '"':
        str = str[1:]
    if str and str[-1] == '"':
        str = str[:-1]
    return str


def split_genotypes(sample_fpath, result_fpath):
    with open(sample_fpath) as vcf, open(result_fpath, 'w') as out:
        for i, line in enumerate(vcf):
            clean_line = line.strip()
            if not clean_line or clean_line[0] == '#':
                out.write(line)
            else:
                tokens = line.split()
                alt_field = remove_quotes(tokens[4])
                alts = alt_field.split(',')
                if len(alts) > 1:
                    for alt in alts:
                        line = '\t'.join(tokens[:2] + ['.'] + [tokens[3]] + [alt] + tokens[5:]) + '\n'
                        out.write(line)
                else:
                    line = '\t'.join(tokens[:2] + ['.'] + tokens[3:]) + '\n'
                    out.write(line)

    if run_config.get('save_intermediate'):
        return result_fpath
    else:
        os.remove(sample_fpath)
        os.rename(result_fpath, sample_fpath)
        return sample_fpath


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        sys.stderr.write('Usage: python ' + __file__ + ' system_info.yaml run_info.yaml')
        exit(1)

    assert os.path.isfile(args[0]), args[0] + ' does not exist of is a directory.'
    assert os.path.isfile(args[1]), args[1] + ' does not exist of is a directory.'
    system_config = load(args[0], Loader=Loader)
    run_config = load(args[1], Loader=Loader)

    sample_fpath = os.path.realpath(run_config.get('file', None))
    assert os.path.isfile(sample_fpath), sample_fpath + ' does not exists or is not a file.'

    result_dir = os.path.realpath(run_config.get('output_dir', os.getcwd()))
    assert os.path.isdir(result_dir), result_dir + ' does not exists or is not a directory'

    sample_fname = os.path.basename(sample_fpath)
    sample_basename, ext = os.path.splitext(sample_fname)

    if result_dir != os.path.realpath(os.path.dirname(sample_fpath)):
        new_sample_fpath = os.path.join(result_dir, sample_fname)
        if os.path.exists(new_sample_fpath):
            os.remove(new_sample_fpath)
        shutil.copyfile(sample_fpath, new_sample_fpath)
        sample_fpath = new_sample_fpath

    if 'log' not in run_config:
        run_config['log'] = os.path.join(os.path.dirname(sample_fpath), sample_basename + '.log')
    if os.path.isfile(run_config['log']):
        os.remove(run_config['log'])

    log_print('Writing into ' + result_dir)
    log_print('Logging to ' + run_config['log'])

    print('Note: please, load modules before start:')
    print('   source /etc/profile.d/modules.sh')
    print('   module load java')
    print('   module load perl')
    # print ''
    # print 'In Waltham, run this as well:'
    # print '   export PATH=$PATH:/group/ngs/src/snpEff/snpEff3.5/scripts'
    # print '   export PERL5LIB=$PERL5LIB:/opt/az/local/bcbio-nextgen/stable/0.7.6/tooldir/lib/perl5/site_perl'

    if run_config.get('split_genotypes'):
        sample_basepath, ext = os.path.splitext(sample_fpath)
        result_fpath = sample_basepath + '.split' + ext
        log_print('')
        log_print('*' * 70)
        log_print('Splitting genotypes.')
        sample_fpath = split_genotypes(sample_fpath, result_fpath)
        log_print('Saved to ' + result_fpath)
        log_print('')

    annotate(sample_fpath)