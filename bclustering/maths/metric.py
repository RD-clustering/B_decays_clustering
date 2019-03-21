#!/usr/bin/env python3

# 3rd
import numpy as np
import scipy.spatial

# ours
from bclustering.data.dwe import DataWithErrors


# todo: unittest
def condense_distance_matrix(matrix):
    # matrix[np.triu_indices(len(matrix), k=1)]
    return scipy.spatial.distance.squareform(matrix)


def uncondense_distance_matrix(vector):
    return scipy.spatial.distance.squareform(vector)

# todo: unittest
def chi2_metric(dwe: DataWithErrors, output='condensed'):
    """
    Returns the chi2/ndf values of the comparison of a datasets.

    Args:
        dwe:
        output: 'condensed' (condensed distance matrix) or 'full' (full distance
            matrix)

    Returns:
        Condensed distance matrix

    """
    # https://root.cern.ch/doc/master/classTH1.html#a6c281eebc0c0a848e7a0d620425090a5

    # n vector
    n = dwe.norms()  # todo: this stays untouched by decorrelation, right?
    # n x nbins
    d = dwe.data(decorrelate=True)
    # n x nbins
    e = dwe.err()

    # n x n x nbins
    nom1 = np.einsum("k,li->kli", n, d)
    nom2 = np.transpose(nom1, (1, 0, 2))
    nominator = np.square(nom1 - nom2)

    # n x n x nbins
    den1 = np.einsum("k,li->kli", n, e)
    den2 = np.transpose(den1, (1, 0, 2))
    denominator = np.square(den1) + np.square(den2)

    # n x n x nbins
    summand = nominator / denominator

    # n x n
    chi2ndf = np.einsum("kli->kl", summand) / dwe.nbins

    if output == 'condensed':
        return condense_distance_matrix(chi2ndf)
    elif output == 'full':
        return chi2ndf
    else:
        raise ValueError("Unknown argument '{}'.".format(output))
