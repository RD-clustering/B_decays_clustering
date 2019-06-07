#!/usr/bin/env python3

# std
import copy
import collections

# 3rd
import pandas as pd


class NoisySampleStabilityTesterResult(object):
    def __init__(self, df, cached_data=None):
        self.df = df
        self._cached_data = cached_data


class NoisySampleStabilityTester(object):
    def __init__(self):
        self._noise_kwargs = {}
        self._noise_args = []
        self._repeat = 10
        self._cache_data = True
        self.set_repeat()
        self._foms = {}

    # **************************************************************************
    # Config
    # **************************************************************************

    def set_repeat(self, repeat=10):
        self._repeat = repeat

    def set_noise(self, *args, **kwargs):
        self._noise_args = args
        self._noise_kwargs = kwargs

    def set_cache_data(self, value):
        self._cache_data = value

    def add_fom(self, fom) -> None:
        """
        """
        if fom.name in self._foms:
            # todo: do with log
            print(
                "Warning: FOM with name {} already existed. Replacing.".format(
                    fom.name
                )
            )
        self._foms[fom.name] = fom

    # **************************************************************************
    # Run
    # **************************************************************************

    def run(self, data, scanner, cluster):
        datas = []
        original_clusters = None
        fom_results = collections.defaultdict(list)
        for _ in range(self._repeat + 1):
            noisy_scanner = copy.copy(scanner)
            if _ >= 1:
                noisy_scanner.add_spoints_noise(
                    *self._noise_args, **self._noise_kwargs
                )
            this_data = data.copy(deep=True)
            if self._cache_data:
                datas.append(this_data)
            rs = noisy_scanner.run(this_data)
            rs.write()
            rc = cluster.run(this_data)
            clusters = rc.get_clusters(indexed=True)
            if _ == 0:
                original_clusters = copy.copy(clusters)
                continue
            for fom_name, fom in self._foms.items():
                fom = fom.run(original_clusters, clusters).fom
                fom_results[fom_name].append(fom)
        return NoisySampleStabilityTesterResult(
            df=pd.DataFrame(fom_results), cached_data=datas
        )
