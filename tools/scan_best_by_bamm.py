import re
from lib.common import read_bamm
from lib.speedup import score_bamm


def read_fasta(path):
    fasta = list()
    with open(path, 'r') as file:
        for line in file:
            #print(line)
            if line.startswith('>'):
                line = line[1:].strip().split(':')
                record = dict()
                record['name'] = line[0]
                record['chromosome'] = line[2]
                coordinates_strand = line[3]

                start, end = re.findall(r'\d*-\d*', coordinates_strand)[0].split('-')
                record['start'] = start
                record['end'] = end

                strand = re.findall(r'\(.\)', coordinates_strand[:-3])
                if not strand == []:
                    record['strand'] = strand[0].strip('()')
                else:
                    record['strand'] = '+'
            else:
                record['seq'] = line.strip().upper()
                fasta.append(record)
    file.close()
    return(fasta)


def complement(record):
    output = dict(record)
    strand = record['strand']
    seq = str()
    if strand == '+':
        output['strand'] = '-'
    else:
        output['strand'] = '+'
    seq = output['seq'].replace('A', 't').replace('T', 'a').replace('C', 'g').replace('G', 'c').upper()[::-1]
    output['seq'] = seq
    return(output)


def check_nucleotides(site):
    s = set(site)
    n = {'A', 'C', 'G', 'T'}
    if len(s - n) == 0:
        return(True)
    else:
        return(False)


def scan_seqs_by_bamm(record, log_odds_bamm, order):
    motif_length = len(log_odds_bamm[list(log_odds_bamm.keys())[0]])
    reverse_record = complement(record)
    seq = record['seq']
    reverse_seq = reverse_record['seq']
    results = []
    threshold = -1000000
    # scan first strand
    for i in range(len(seq) - motif_length + 1):
        site_seq = seq[i:motif_length + i]
        if not check_nucleotides(site_seq):
            continue
        s = score_bamm(site_seq, log_odds_bamm, order, motif_length)
        if s >= threshold:
            site_dict = dict()
            site_dict['name'] = record['name']
            site_dict['chromosome'] = record['chromosome']
            site_dict['start'] = str(int(record['start']) + i)
            site_dict['end'] = str(int(record['start']) + i + motif_length)
            site_dict['site'] = site_seq
            site_dict['strand'] = record['strand']
            site_dict['score'] = s
            threshold = s
    # scan second strand
    for i in range(len(seq) - motif_length + 1):
        site_seq = reverse_seq[i:motif_length + i]
        if not check_nucleotides(site_seq):
            continue
        s = score_bamm(site_seq, log_odds_bamm, order, motif_length)
        if s >= threshold:
            site_dict = dict()
            site_dict['name'] = record['name']
            site_dict['chromosome'] = record['chromosome']
            site_dict['start'] = str(int(record['end']) - i - motif_length)
            site_dict['end'] = str(int(record['end']) - i)
            site_dict['site'] = site_seq
            site_dict['strand'] = reverse_record['strand']
            site_dict['score'] = s
            threshold = s
    results.append(site_dict)
    return(results)


def write_list(path, data):
    scores = [i['score'] for i in data]
    with open(path, "w") as file:
        for line in scores:
            file.write("{0}\n".format(line))
    file.close()
    return(0)


def scan_best_by_bamm(results_path, bamm_path, bg_path, fasta_path):
    fasta = read_fasta(fasta_path)
    log_odds_bamm, order = read_bamm(bamm_path, bg_path)
    results = [scan_seqs_by_bamm(record=record, log_odds_bamm=log_odds_bamm, order=order) for record in fasta]
    results = [i for i in results if i != []]
    results = [j for sub in results for j in sub]
    write_list(results_path, results)
    return(0)
