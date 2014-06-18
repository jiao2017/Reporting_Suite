#!/usr/bin/env python

import math
from collections import defaultdict
from itertools import groupby
from source.utils import mean, median


#_SAMPLE_MAPPED_READS = {'Sample1': 100, "Sample2": 200}  # cnt

_GENE_RECORDS = [
    ["Sample1", "chrM", 0, 1000, "DQ582201", "Gene-Amplicon", 1000, 1052.66],
    ["Sample1", "chrM", 0, 1000, "JB137816", "Gene-Amplicon", 1000, 1052.66],
    ["Sample1", "chrM", 2000, 4500, "TVAS5", "Gene-Amplicon", 1500, 984.02],
    ["Sample1", "chrM", 6000, 8000, "BC018860", "Gene-Amplicon", 2000, 0.00],
    ["Sample1", "chrM", 6000, 8000, "OK/SW-cl.16", "Gene-Amplicon", 2000, 0.00],
    ["Sample1", "chrM", 6000, 8000, "JA760602", "Gene-Amplicon", 2000, 0.00],
    ["Sample2", "chrM", 0, 1000, "DQ582201", "Gene-Amplicon", 1000, 1052.66],
    ["Sample2", "chrM", 0, 1000, "JB137816", "Gene-Amplicon", 1000, 1052.66]]


#sample2	chrM	2000	4500	TVAS5	Gene-Amplicon	1500	984.02
#sample2	chrM	6000	8000	BC018860	Gene-Amplicon	2000	0.00
#sample2	chrM	6000	8000	OK/SW-cl.16	Gene-Amplicon	2000	0.00
#sample2	chrM	6000	8000	JA760602	Gene-Amplicon	2000	0.00) }


def _get_factors_by_sample(mapped_reads_by_sample):
    factor_by_sample = dict()
    mean_reads = mean(mapped_reads_by_sample.values())
    for k, v in mapped_reads_by_sample.items():
        factor_by_sample[k] = mean_reads / v if v else 0
    return factor_by_sample


def _get_factors_by_gene(gene_records,med_depth):
    min_depth_by_genes = defaultdict(list)
    [min_depth_by_genes[gene_record.name].append(gene_record.min_depth) for gene_record in gene_records]
    factors_by_gene = dict()
    for k, v in min_depth_by_genes.items():
        med = median(v)
        factors_by_gene[k] = med_depth / med if med else 0
    return factors_by_gene




def get_norm_depths_by_seq_distr(mapped_reads_by_sample, record_by_sample):
    norm_depths = defaultdict(dict)  # gene -> { sample -> [] }

    factor_by_sample = _get_factors_by_sample(mapped_reads_by_sample)

    for sample, factor in factor_by_sample.items():
        for gene_info in [gene_infos for gene_infos in record_by_sample if gene_infos.sample_name == sample]:
            norm_depths[gene_info.name][sample] = gene_info.min_depth * factor


    return norm_depths





def run_copy_number(sample_mapped_reads, gene_depth):
    list_genes_info = report_row_to_object(gene_depth)

    med_depth = median([rec.min_depth for rec in list_genes_info])
    norm_depths_by_seq_distr = get_norm_depths_by_seq_distr(sample_mapped_reads, list_genes_info)



    factors_by_gene = _get_factors_by_gene(list_genes_info,med_depth)

    norm_depths_by_gene = defaultdict(dict)

    norm2 = defaultdict(dict)

    norm3 = defaultdict(dict)

    for gene, norm_depth_by_sample in norm_depths_by_seq_distr.items():
        for gene_info in list_genes_info:
            sample = gene_info.sample_name
            if sample not in norm_depth_by_sample:
                continue

            gene_norm_depth = norm_depth_by_sample[sample] * factors_by_gene[gene] + 0.1

            norm_depths_by_gene[gene][sample] = gene_norm_depth

            norm2[gene][sample] = math.log(gene_norm_depth / med_depth, 2) if med_depth else 0

            median_depth = median([gene_info.min_depth
                                   for gene_info in list_genes_info
                                   if gene_info.sample_name == sample])

            norm3[gene][sample] = math.log(gene_norm_depth / median_depth, 2)



            #print '/t'.join(map(str,(sample, gene, gene_info.start_position, gene_info.end_position,gene_info.min_depth, norm_depth_by_sample)))
def report_row_to_object(gene_depth):

    gene_details = []
    for read in gene_depth:
        gene_details.append(GeneDetail(*read))
    return gene_details


class GeneDetail():
    def __init__(self, sample_name=None, chrom=None, start_position=None, end_position=None, name=None,
                 type="Gene-Amplicon", size=None, min_depth=None):
        self.sample_name = sample_name
        self.chrom = chrom
        self.start_position = int(start_position)
        self.end_position = int(end_position)
        self.name = name
        self.type = type
        self.size = int(size)
        self.min_depth = float(min_depth)

    def __str__(self):
        values = [self.sample_name, self.chrom, self.start_position, self.end_position, self.name, self.type, self.size, self.min_depth]
        return '"' + '\t'.join(map(str, values)) + '"'




if __name__ == '__main__':
    print [i.sample_name for i in report_row_to_object(_GENE_RECORDS)]





















