import random
import shutil
import os
import subprocess
import bisect
from lib.common import read_peaks, sites_to_pwm, creat_background, \
write_fasta, complement, make_pcm, make_pfm, \
make_pwm, write_pwm, write_pfm, write_meme, \
calculate_particial_auc, write_auc, calculate_merged_roc, write_roc, calculate_fprs
from lib.speedup import creat_table_bootstrap, score_pwm


def run_chipmunk(path_to_java, path_to_chipmunk, fasta_path, path_out, motif_length_start, motif_length_end, cpu_count):
    args = [path_to_java, '-cp', path_to_chipmunk,
                   'ru.autosome.ChIPMunk', str(motif_length_start), str(motif_length_end), 'yes', '1.0',
                   's:{}'.format(fasta_path),
                  '100', '10', '1', str(cpu_count), 'random']
    p = subprocess.run(args, shell=False, capture_output=True)
    out = p.stdout
    with open(path_out, 'wb') as file:
        file.write(out)
    return(0)


def parse_chipmunk(path):
    with open(path, 'r') as file:
        container = []
        for line in file:
            d = {'name': str(), 'start': int(), 'end': int(),
                 'seq': str(), 'strand': str()}
            if line.startswith('WORD|'):
                line = line[5:].strip()
                line = line.split()
                d['name'] = 'peaks_' + str(int(line[0]) - 1)
                d['start'] = int(line[1])
                d['end'] = int(line[1]) + len(line[2])
                d['seq'] = line[2]
                if line[4] == 'rect':
                    d['strand'] = '+'
                else:
                    d['strand'] = '-'
                container.append(d)
            else:
                continue
    seqs = [i['seq'] for i in container if not 'N' in i['seq']]
    return(seqs)


def false_scores_pwm(peaks, pwm, length_of_site):
    false_scores = []
    append = false_scores.append
    for peak in peaks:
        complement_peak = complement(peak)
        full_peak = peak + 'N' * length_of_site + complement_peak
        n = len(full_peak) - length_of_site + 1
        for i in range(n):
            site = peak[i:length_of_site + i]
            if 'N' in site:
                continue
            score = score_pwm(site, pwm)
            false_scores.append(score)
    return(false_scores)


def true_scores_pwm(peaks, pwm, length_of_site):
    true_scores = []
    for peak in peaks:
        complement_peak = complement(peak)
        best = -1000000
        full_peak = peak + 'N' * length_of_site + complement_peak
        n = len(full_peak) - length_of_site + 1
        for i in range(n):
            site = full_peak[i:length_of_site + i]
            if 'N' in site:
                continue
            score = score_pwm(site, pwm)
            if score >= best:
                best = score
        true_scores.append(best)
    return(true_scores)


def fpr_at_tpr(true_scores, false_scores, tpr):
    true_scores.sort(reverse=True)
    false_scores.sort(reverse=True)
    false_length = len(false_scores)
    true_length = len(true_scores)
    score = true_scores[round(true_length * tpr) - 1]
    actual_tpr = sum([1 if true_score >= score else 0 for true_score in true_scores]) / true_length
    fpr = sum([1 if false_score >= score else 0 for false_score in false_scores]) / false_length
    return(fpr)


def write_sites(output, tag, sites):
    with open(output + '/' + tag + '.fasta', 'w') as file:
        for index, site in enumerate(sites):
            file.write(site + '\n')
    return(0)


def learn_optimized_pwm(peaks_path, counter, path_to_java, path_to_chipmunk, tmp_r, output_r, cpu_count, tpr, pfpr):
    length = 12
    true_scores = []
    false_scores = []
    open(output_r + '/auc.txt', 'w').close()
    peaks = read_peaks(peaks_path)
    shuffled_peaks = creat_background(peaks, length, counter)
    run_chipmunk(path_to_java, path_to_chipmunk,
                 peaks_path, tmp_r + '/chipmunk_results.txt',
                 length, length, cpu_count)
    sites_current = parse_chipmunk(tmp_r + '/chipmunk_results.txt')
    sites_current = list(set(sites_current))
    pwm = sites_to_pwm(sites_current)
    for true_score in true_scores_pwm(peaks, pwm, length):
        true_scores.append(true_score)
    for false_score in false_scores_pwm(shuffled_peaks, pwm, length):
        false_scores.append(false_score)
    fprs = calculate_fprs(true_scores, false_scores)
    roc_current = calculate_merged_roc(fprs)
    auc_current = calculate_particial_auc(roc_current['TPR'], roc_current['FPR'], pfpr)
    print("Length {};".format(length), "pAUC at {0} = {1};".format(pfpr, auc_current))
    write_auc(output_r + '/auc.txt', auc_current, length)
    for length in range(14, 34, 2):
        true_scores = []
        false_scores = []
        peaks = read_peaks(peaks_path)
        shuffled_peaks = creat_background(peaks, length, counter)
        run_chipmunk(path_to_java, path_to_chipmunk,
                     peaks_path, tmp_r + '/chipmunk_results.txt',
                     length, length, cpu_count)
        sites_new = parse_chipmunk(tmp_r + '/chipmunk_results.txt')
        sites_new = list(set(sites_new))
        pwm = sites_to_pwm(sites_new)
        for true_score in true_scores_pwm(peaks, pwm, length):
            true_scores.append(true_score)
        for false_score in false_scores_pwm(shuffled_peaks, pwm, length):
            false_scores.append(false_score)
        fprs = calculate_fprs(true_scores, false_scores)
        roc_new = calculate_merged_roc(fprs)
        auc_new = calculate_particial_auc(roc_new['TPR'], roc_new['FPR'], pfpr)
        print("Length {};".format(length), "pAUC at {0} = {1};".format(pfpr, auc_new))
        write_auc(output_r + '/auc.txt', auc_new, length)
        if auc_new > auc_current:
            sites_current = sites_new[:]
            auc_current = auc_new
            roc_current = roc_new
        else:
            break
    write_roc(output_r + "/training_bootstrap.txt", roc_current)
    return(sites_current, length)


def de_novo_with_oprimization_pwm(peaks_path, path_to_java, path_to_chipmunk, 
    tmp_r, output_r, cpu_count, tpr, pfpr):
    counter = 6000000
    if not os.path.exists(tmp_r):
        os.mkdir(tmp_r)
    if not os.path.isdir(output_r):
        os.mkdir(output_r)

    sites, length = learn_optimized_pwm(peaks_path, counter, path_to_java, 
        path_to_chipmunk, tmp_r, output_r, cpu_count, tpr, pfpr)
    shutil.rmtree(tmp_r)
    pcm = make_pcm(sites)
    pfm = make_pfm(pcm)
    pwm = make_pwm(pfm)

    nsites = len(sites)
    background = {'A': 0.25,
                 'C': 0.25,
                 'G': 0.25,
                 'T': 0.25}
    tag = 'pwm_model'
    write_meme(output_r, tag, pfm, background, nsites)
    write_pwm(output_r, tag, pwm)
    write_pfm(output_r, tag, pfm)
    write_sites(output=output_r, tag=tag, sites=sites)
    return(0)
