#!/usr/bin/env python3

# std
import logging
import random
from typing import List, Iterable, Union

# 3rd party
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ours
from bclustering.util.log import get_logger
from bclustering.plots.plot_histogram import plot_histogram
from bclustering.plots.colors import ColorScheme
from bclustering.data.data import Data


def get_random_indizes(start: int, stop: int, n: int) -> List[int]:
    """ Generate a list of n distinct (!) random integers.

    Args:
        start: Minimum of index (start <= index)
        stop: Maximum of index (index < stop)
        n: Number of distinct random indizes to be generated

    Returns:
        List `number` many (different) random indizes
    """
    indizes = set()
    iterations = 0
    while len(indizes) < n:
        indizes.add(random.randrange(start, stop))
        if iterations >= 10 * n:
            print(
                "Did not manage to generate enough different random "
                "integers (only {} of {}).".format(len(indizes), n)
            )
            break
    return sorted(list(indizes))


class BundlePlot(object):
    """ Plotting class to plot distributions by cluster in order to analyse 
    which distributions get assigned to which cluster. """
    def __init__(self, data: Data):

        #: logging.Logger object
        self.log = get_logger("BundlePlot", sh_level=logging.WARNING)

        #: pandas dataframe
        self.data = data

        #: Name of the column holding the cluster number
        self.cluster_column = "cluster"

        self.bpoint_column = "bpoint"

        #: Color scheme
        self.color_scheme = ColorScheme(self.clusters)

        #: Instance of matplotlib.pyplot.figure
        self.fig = None
        #: Instance of matplotlib.axes.Axes
        self.ax = None

    @property
    def _has_bpoints(self):
        return self.bpoint_column in self.data.df.columns

    @property
    def clusters(self):
        return self.data.clusters(cluster_column=self.cluster_column)

    def _filter_clusters(self, clusters):
        clusters = list(set(clusters))
        selection = [c for c in clusters if c in self.clusters]
        removed = [c for c in clusters if c not in self.clusters]
        if removed:
            self.log.warning(
                "The cluster(s) {} does not exist in data, "
                "so I removed them.".format(
                    ", ".join(map(str, sorted(removed)))
                )
            )
        return selection

    def _interpret_cluster_input(self, clusters):
        if isinstance(clusters, int):
            clusters = [clusters]
        if not clusters:
            clusters = self.clusters
        return self._filter_clusters(clusters)

    def _get_df_cluster(self, cluster: int) -> pd.DataFrame:
        """ Return only the rows corresponding to one cluster in the 
        dataframe and only the columns that correspond to the bins. 
        
        Args:
            cluster: Name of the cluster
        
        Returns:
            pandas.DataFrame as described above
        """
        # to avoid long line:
        cc = self.cluster_column
        bc = self.data.bin_cols
        return self.data.df[self.data.df[cc] == cluster][bc]

    def _plot_bundles(self, ax, cluster: int, nlines=3) -> None:
        """ Main implementation of self.plot_bundles (private method).
        This method will be called for each cluster in self.plot_bundles.
         
        Args:
            ax: Instance of matplotlib.axes.Axes to plot on
            cluster: Number of cluster to be plotted
            nlines: Number of example distributions of the cluster to be 
                plotted
        
        Returns:
            None
        """

        linestyles = ['-', '--', '-.', ':']

        df_cluster = self._get_df_cluster(cluster)
        if len(df_cluster) < nlines:
            self.log.warning(
                "Not enough rows for cluster {} "
                "Only plotting {} lines.".format(cluster, len(df_cluster))
            )
            nlines = len(df_cluster)

        indizes = get_random_indizes(0, len(df_cluster), nlines)
        color = self.color_scheme.get_cluster_color(cluster)
        for i, index in enumerate(indizes):
            data = np.squeeze(df_cluster.iloc[[index]].values)
            plot_histogram(
                ax,
                None,
                data,
                color=color,
                linestyle=linestyles[i % len(linestyles)]
            )

    def plot_bundles(self, clusters: Union[int, Iterable[int]]=None, nlines=1,
                     ax=None) -> None:
        """ Plot several examples of distributions for each cluster specified 
        
        Args:
            clusters: List of clusters to selected or single cluster.
                If None (default), all clusters are chosen.
            nlines: Number of example distributions of each cluster to be 
                plotted
            ax: Instance of matplotlib.axes.Axes to be plotted on. If None
                (default), a new axes object and figure is initialized and 
                saved as self.ax and self.fig.
        
        Returns:
            None
        """
        clusters = self._interpret_cluster_input(clusters)
        if not ax:
            fig, ax = plt.subplots()
            ax.set_title(
                "{} example(s) of distributions for cluster(s) {}".format(
                    nlines, ", ".join(map(str, sorted(clusters)))
                )
            )
            self.fig = fig
            self.ax = ax
        # pycharm might be confused about the type of `clusters`:
        # noinspection PyTypeChecker
        for cluster in clusters:
            self._plot_bundles(ax, cluster, nlines=nlines)

    def _plot_minmax(self, ax, cluster: int) -> None:
        """ Main implementation of self.plot_minmax.
        This method will be called for each cluster in self.plot_minmax.
        
        Args:
            ax: Instance of matplotlib.axes.Axes to plot on
            cluster: Name of cluster to be plotted
        
        Returns:
            None
        """
        df_cluster = self._get_df_cluster(cluster)
        maxima = list(df_cluster.max().values)
        minima = list(df_cluster.min().values)

        bin_numbers = np.array(range(1, len(self.data.bin_cols) + 2))

        color = self.color_scheme.get_cluster_color(cluster)
        for i in range(len(maxima)):
            x = bin_numbers[i:i+2]
            y1 = [minima[i], minima[i]]
            y2 = [maxima[i], maxima[i]]
            ax.fill_between(
                x,
                y1,
                y2,
                facecolor=color,
                interpolate=False,
                alpha=0.3,
                hatch="////",
                color=color
            )

    def plot_minmax(self, clusters: Union[int, Iterable[int]]=None,
                    ax=None) -> None:
        """ Plot the minimum and maximum of each bin for the specified 
        clusters. 
        
        Args:
            clusters:  List of clusters to selected or single cluster.
                If None (default), all clusters are chosen.
            ax: Instance of matplotlib.axes.Axes to plot on. If None, a new
                one is instantiated.
        
        Returns:
            None
        """
        clusters = self._interpret_cluster_input(clusters)
        if not ax:
            fig, ax = plt.subplots()
            ax.set_title(
                "Minima and maxima of the bin contents for "
                "cluster(s) {}".format(', '.join(map(str, sorted(clusters))))
            )
            self.fig = fig
            self.ax = ax

        # pycharm might be confused about the type of `clusters`:
        # noinspection PyTypeChecker
        for cluster in clusters:
            self._plot_minmax(ax, cluster)

    def _box_plot(self, ax, cluster, whiskers=1.5) -> None:
        """ Main implementation of self.box_plot. 
        Gets called for every cluster specified in self.box_plot.
        
        Args:
            ax: Instance of matplotlib.axes.Axes to plot on
            cluster: Name of cluster to be plotted
            whiskers: Length of the whiskers of the box plot. 
                See self.box_plot for more information.
                Default: 1.5 (matplotlib default)
        
        Returns:
            None
        """
        df_cluster = self._get_df_cluster(cluster)
        data = df_cluster.values

        color = self.color_scheme.get_cluster_color(cluster)

        ax.boxplot(
            data,
            notch=False,
            vert=True,
            patch_artist=True,
            boxprops=dict(facecolor=color, color=color, alpha=0.3),
            capprops=dict(color=color),
            whiskerprops=dict(color=color),
            flierprops=dict(color=color, markeredgecolor=color),
            medianprops=dict(color=color),
            whis=whiskers  # extend the range of the whiskers
        )

    def box_plot(self, clusters: Union[int, Iterable[int]]=None, ax=None,
                 whiskers: float=2.5) -> None:
        """ Box plot of the bin contents of the distributions corresponding
        to selected clusters.
        
        Args:
            clusters:  List of clusters to selected or single cluster.
                If None (default), all clusters are chosen.
            ax: Instance of matplotlib.axes.Axes to plot on. If None, a new
                one is instantiated.
            whiskers: Length of the whiskers of the box plot in units of IQR
                (interquartile range, containing 50% of all values). Default 
                2.5.
        """
        clusters = self._interpret_cluster_input(clusters)
        if not ax:
            fig, ax = plt.subplots()
            ax.set_title(
                "Box plot of the bin contents for cluster(s) {}\n"
                "Whisker length set to {}*IQR".format(
                    ", ".join(map(str, sorted(clusters))),
                    whiskers
                )
            )
        # pycharm might be confused about the type of `clusters`:
        # noinspection PyTypeChecker
        for cluster in clusters:
            self._box_plot(ax, cluster, whiskers=whiskers)
