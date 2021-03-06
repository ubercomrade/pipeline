import subprocess
import os
import shutil
import random
from lib.common import read_peaks, write_fasta, read_bamm, \
creat_background, calculate_particial_auc, \
score_bamm, complement, make_pcm, make_pfm, write_meme, write_auc, \
write_auc, calculate_merged_roc, write_roc, calculate_fprs
from lib.speedup import creat_table_bootstrap


def create_bamm_model(peaks_path, directory, order, meme, extend, basename):
    args = ['BaMMmotif', directory, peaks_path, '--PWMFile', meme,
            '--CGS', '--order', str(order), '--Order', str(order),
           '--extend', str(extend), '--basename', str(basename)]
    r = subprocess.run(args, capture_output=True)
    bamm_path = directory + '/{}_motif_1.ihbcp'.format(basename)
    bg_path = directory + '/{}.hbcp'.format(basename)
    bamm, order = read_bamm(bamm_path, bg_path)
    return(bamm, order)




def false_scores_bamm(peaks, bamm, order, length_of_site):
    false_scores = []
    append = false_scores.append
    for peak in peaks:
        complement_peak = complement(peak)
        full_peak = peak + 'N' * length_of_site + complement_peak
        n = len(full_peak) - length_of_site + 1
        for i in range(n):
            site = full_peak[i:length_of_site + i]
            if 'N' in site:
                continue
            score = score_bamm(site, bamm, order, length_of_site)
            false_scores.append(score)
    return(false_scores)


def true_scores_bamm(peaks, bamm, order, length_of_site):
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
            score = score_bamm(site, bamm, order, length_of_site)
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


def learn_optimized_bamm(peaks_path, counter, order, length, meme, tmp_dir, output_dir, tpr, pfpr):
    true_scores = []
    false_scores = []
    peaks = read_peaks(peaks_path)
    shuffled_peaks = creat_background(peaks, length, counter)
    bamm, order = create_bamm_model(peaks_path, tmp_dir, order, meme, 0, '0')
    for true_score in true_scores_bamm(peaks, bamm, order, length):
        true_scores.append(true_score)
    for false_score in false_scores_bamm(shuffled_peaks, bamm, order, length):
        false_scores.append(false_score)
    fprs = calculate_fprs(true_scores, false_scores)
    roc_current = calculate_merged_roc(fprs)
    auc_current = calculate_particial_auc(roc_current['TPR'], roc_current['FPR'], pfpr)
    print("Length {};".format(length), "pAUC at {0} = {1};".format(pfpr, auc_current))
    write_auc(output_dir + '/auc.txt', auc_current, length)
    index = 0
    for extend in range(1, 20):
        true_scores = []
        false_scores = []
        shuffled_peaks = creat_background(peaks, length + extend * 2, counter)
        bamm, order = create_bamm_model(peaks_path, tmp_dir, order, meme, extend, extend)
        for true_score in true_scores_bamm(peaks, bamm, order, length + extend):
            true_scores.append(true_score)
        for false_score in false_scores_bamm(shuffled_peaks, bamm, order, length + extend):
            false_scores.append(false_score)
        fprs = calculate_fprs(true_scores, false_scores)
        roc_new = calculate_merged_roc(fprs)
        auc_new = calculate_particial_auc(roc_new['TPR'], roc_new['FPR'], pfpr)
        print("Length {};".format(length + extend), "pAUC at {0} = {1};".format(pfpr, auc_new))
        write_auc(output_dir + '/auc.txt', auc_new, length)
        if auc_new > auc_current:
            auc_current = auc_new
            index += 1
        elif auc_new < auc_current and order <= 2:
            order += 1
        else:
            break
    write_roc(output_dir + "/training_bootstrap.txt", roc_current)
    return(order, index)


def de_novo_with_oprimization_bamm(peaks_path, length, meme, tmp_dir, output_dir, tpr, pfpr):
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    counter = 6000000
    order = 2
    bamm_order, model_index = learn_optimized_bamm(peaks_path, counter, order, length, meme, tmp_dir, output_dir, tpr, pfpr)
    shutil.copy(tmp_dir + '/{}_motif_1.ihbcp'.format(model_index),
           output_dir + '/bamm_model.ihbcp')
    shutil.copy(tmp_dir + '/{}.hbcp'.format(model_index),
           output_dir + '/bamm.hbcp')
    shutil.rmtree(tmp_dir)
    return(bamm_order)