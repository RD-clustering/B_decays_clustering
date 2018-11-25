# std
from math import ceil
from typing import List

# 3d party
import matplotlib.pyplot as plt
import matplotlib
# noinspection PyUnresolvedReferences
from mpl_toolkits.mplot3d import Axes3D  # NOTE BELOW (*)
import numpy as np
import pandas as pd

# (*) This import line is not explicitly used, but do not remove it!
# It is nescessary to load the 3d support!

# todo: move to a more elaborate plotting concept
# like https://scipy-cookbook.readthedocs.io/items/Matplotlib_UnfilledHistograms.html for unfilled histograms
# todo: more flexible signature?
def plot_histogram(ax: plt.axes,
                   binning: np.array,
                   contents: np.array,
                   normalized=False,
                   *args,
                   **kwargs) -> None:
    """ Plots histogram

    Args:
        ax: Axes of a plot
        binning: numpy array of bin edges
        contents: numpy array of bin contents
        normalized: If true, the plotted histogram will be normalized

    Returns:
        None
    """
    assert len(binning.shape) == len(contents.shape) == 1
    n = binning.shape[0] - 1  # number of bins
    assert n == contents.shape[0]
    assert n >= 1
    mpoints = (binning[1:] + binning[:-1]) / 2

    if normalized:
        values = contents / sum(contents)
    else:
        values = contents

    return ax.hist(mpoints,
                   bins=binning,
                   weights=values,
                   linewidth=0,
                   *args,
                   **kwargs
    )


# todo: legend!
# todo: also have the 3d equivalent of ClusterPlot.fill (using voxels)
# todo: perhaps better to use logging object rather than a modified print function
# todo: add basic command line interface?
class ClusterPlot(object):
    """ Plot clusters!

    After initialization, use the 'scatter' or 'fill' method for plotting.
    See docstrings there for more instructions.

    Args:
        df: Pandas dataframe

    Attributes:
        colors: List of colors to color the clusters with. If there are more
            clusters than colors, a warning is issued.
        markers: List of markers of the clusters (scatter plot only).
        max_subplots: Maximal number of subplots
        max_cols: Maximal number of columns of the subplot grid
        figsize: figure size of each subplot
        index_columns: The names of the columns that hold the Wilson
            coefficients
        cluster_column: The name of the column that holds the cluster index
        debug: Set to true to see debug messages

    Note: Undocumented attributes starting with and underscore are for
          internal purposes only.

    """
    def __init__(self, df: pd.DataFrame):
        # from arguments
        self.df = df

        # (Advanced) config values
        # Documented in docstring of this class

        self.colors = None
        if not self.colors:
            self.colors = ["red", "green", "blue", "black", "orange", "pink", ]
        self.markers = None
        if not self.markers:
            self.markers = ["o", "v", "^", "v", "<", ">"]
        self.max_subplots = 16
        self.max_cols = 4
        self.figsize = (4, 4)
        self.index_columns = ['l', 'r', 'sl', 'sr', 't']
        self.cluster_column = "cluster"
        self.debug = False

        # internal values: Do not modify

        # Names of the columns to be on the axes of
        # the plot.
        self._axis_columns = None

        self._clusters = None

        self._df_dofs = None

        self._fig = None
        self._axs = None

    @property
    def _axli(self):
        """Note: axs contains all axes (subplots) as a 2D grid, axsli contains
        the same objects but as a simple list (easier to iterate over)"""
        return self._axs.flatten()

    def _d(self, *args, **kwargs) -> None:
        """ For debugging this class, this wraps around the print function
        but only calls it if self.debug == True. """
        if self.debug:
            print(*args, **kwargs)

    def _find_dofs(self):
        """ find all relevant wilson coefficients that are not axes on
        the plots (called _dofs) """

        dofs = []
        # 'Index columns' are by default the columns that hold the wilson
        # coefficients.
        for col in self.index_columns:
            if col not in self._axis_columns:
                if len(self.df[col].unique()) >= 2:
                    dofs.append(col)
        self._d("dofs = {}".format(dofs))

        if not dofs:
            df_dofs = pd.DataFrame([])
        else:
            df_dofs = self.df[dofs].drop_duplicates().sort_values(dofs)
            df_dofs.reset_index(inplace=True, drop=True)

        self._d("number of subplots = {}".format(len(df_dofs)))

        # Reduce the number of subplots by only sampling several points of
        # the Wilson coeffs that aren't on the axes

        if len(df_dofs) > self.max_subplots:
            steps_per_dof = int(self.max_subplots **
                                (1 / len(dofs)))
            self._d("number of steps per dof", steps_per_dof)
            for col in dofs:
                allowed_values = df_dofs[col].unique()
                indizes = list(set(np.linspace(0, len(allowed_values)-1,
                                               steps_per_dof).astype(int)))
                allowed_values = allowed_values[indizes]
                df_dofs = df_dofs[df_dofs[col].isin(allowed_values)]
            self._d("number of subplots left after "
                    "subsampling = {}".format(len(df_dofs)))

        self._df_dofs = df_dofs

    @property
    def _dofs(self):
        return list(self._df_dofs.columns)

    @property
    def _nsubplots(self):
        """ Number of subplots. """
        # +1 to have space for legend!
        return max(1, len(self._df_dofs)) +1

    @property
    def _ncols(self):
        """ Number of columns of the subplot grid. """
        return min(self.max_cols, self._nsubplots)

    @property
    def _nrows(self):
        """ Number of rows of the subplot grid. """
        return ceil(self._nsubplots / self._ncols)

    def _setup_subplots(self):
        """ Set up the subplot grid"""

        # squeeze keyword: https://stackoverflow.com/questions/44598708/
        # do not share axes, that makes problems if the grid is incomplete
        subplots_args = {
            "nrows": self._nrows,
            "ncols": self._ncols,
            "figsize": (self._ncols * self.figsize[0],
                        self._nrows * self.figsize[1]),
            "squeeze": False,
        }
        if len(self._axis_columns) == 3:
            subplots_args["subplot_kw"] = {'projection': '3d'}
        self._fig, self._axs = plt.subplots(**subplots_args)
        # this also sets self._axli

        ihidden = self._nrows * self._ncols - self._nsubplots + 1
        icol_hidden = self._ncols - ihidden
        self._d("ihidden = {}".format(ihidden))
        self._d("icol_hidden = {}".format(icol_hidden))

        if len(self._axis_columns) == 2:
            for isubplot in range(self._nrows * self._ncols):
                irow = isubplot//self._ncols
                icol = isubplot % self._ncols

                if isubplot >= self._nsubplots:
                    self._d("hiding", irow, icol)
                    self._axli[isubplot].set_visible(False)

                if icol == 0:
                    self._axli[isubplot].set_ylabel(self._axis_columns[1])
                else:
                    self._axli[isubplot].set_yticklabels([])

                if irow == self._nrows - 2 and icol >= icol_hidden:
                    self._axli[isubplot].set_xlabel(self._axis_columns[0])
                elif irow == self._nrows - 1 and icol <= icol_hidden:
                    self._axli[isubplot].set_xlabel(self._axis_columns[0])
                else:
                    self._axli[isubplot].set_xticklabels([])

        else:
            for isubplot in range(self._nsubplots):
                self._axli[isubplot].set_xlabel(self._axis_columns[0])
                self._axli[isubplot].set_ylabel(self._axis_columns[1])
                self._axli[isubplot].set_zlabel(self._axis_columns[2])

        for isubplot in range(self._nsubplots - 1):
            title = " ".join("{}={:.2f}".format(key, self._df_dofs.iloc[isubplot][key])
                             for key in self._dofs)
            self._axli[isubplot].set_title(title)

        # set the xrange explicitly in order to not depend
        # on which clusters are shown etc.

        for isubplot in range(self._nsubplots):
            self._axli[isubplot].set_xlim(self._get_lims(0))
            self._axli[isubplot].set_ylim(self._get_lims(1))
            if len(self._axis_columns) == 3:
                self._axli[isubplot].set_zlim(self._get_lims(2))

    def _add_legend(self):
        legend_elements = []
        for cluster in self._clusters:
            color = self.colors[cluster % len(self.colors)]
            p = matplotlib.patches.Patch(
                facecolor=color,
                edgecolor=color,
                label=cluster,
            )
            legend_elements.append(p)
        self._axli[self._nsubplots - 1].legend(
            handles=legend_elements,
            loc='center',
            title="Clusters",
            frameon=False
        )
        # todo: this shouldn't be necessary if setup axes worked as expected
        self._axli[self._nsubplots - 1].set_axis_off()

    def _get_lims(self, ax_no: int, stretch=0.1):
        """ Get lower and upper limit of axis (including padding)

        Args:
            ax_no: 0 for x-axis, 1 for y-axis etc.
            stretch: Fraction of total value span to add as padding.

        Returns:
            (minimum of plotrange, maximum of plotrange)
        """
        mi = min(self.df[self._axis_columns[ax_no]].values)
        ma = max(self.df[self._axis_columns[ax_no]].values)
        d = ma-mi
        pad = stretch * d
        return mi-pad, ma+pad

    def _setup_all(self, cols: List[str], clusters=None) -> None:
        """ Performs all setups.

        Args:
            cols: Names of the columns to be on the plot axes
            clusters: Clusters to plot

        Returns:
            None
            """
        assert(2 <= len(cols) <= 3)
        self._clusters = clusters
        self._axis_columns = cols
        if not self._clusters:
            self._clusters = list(self.df[self.cluster_column].unique())
        if len(self._clusters) > len(self.colors):
            print("Warning: Not enough colors for all clusters.")
        self._find_dofs()
        self._setup_subplots()

    # todo: **kwargs
    # todo: factor out the common part of scatter and fill into its own method?
    def scatter(self, cols: List[str], clusters=None):
        """ Create scatter plot, specifying the columns to be on the axes of the
        plot. If 3 column are specified, 3D scatter plots
        are presented, else 2D plots. If the dataframe contains more columns,
        such that each row is not only specified by the columns on the axes,
        a selection of subplots is created, showing 'cuts'.

        Args:
            cols: The names of the columns to be shown on the x, y (and z)
               axis of the plots.
            clusters: The clusters to be plotted (default: all).

        Returns:
            The figure (unless the 'inline' setting of matplotllib is detected).
        """
        self._setup_all(cols, clusters)

        for isubplot in range(self._nsubplots -1):
            for cluster in self._clusters:
                df_cluster = self.df[self.df[self.cluster_column] == cluster]
                for col in self._dofs:
                    df_cluster = df_cluster[df_cluster[col] ==
                                            self._df_dofs.iloc[isubplot][col]]
                self._axli[isubplot].scatter(
                    *[df_cluster[col] for col in self._axis_columns],
                    color=self.colors[cluster-1 % len(self.colors)],
                    marker=self.markers[cluster-1 % len(self.markers)],
                    label=cluster
                )

        self._add_legend()

        if 'inline' not in matplotlib.get_backend():
            return self._fig


    def _set_fill_colors(self, matrix: np.ndarray, color_offset=-1) \
            -> np.ndarray:
        """ A helper function for the fill method. Given a n x m matrix of
        cluster numbers, this returns a n x m x 3 matrix, where the last 3
        dimensions contain the rgb value of the color that this cluster
        should be colored with.

        Args:
            matrix: m x n matrix containing cluster numbers
            color_offset: Cluster i will be assigned to i + color color_offset.
                Set to -1, because cluster numbering seems to start at 1.

        Returns:
            n x m x 3 matrix with last 3 dimensions containing RGB codes
        """
        rows, cols = matrix.shape
        matrix_colored = np.zeros((rows, cols, 3))
        for irow in range(rows):
            for icol in range(cols):
                value = int(matrix[irow, icol]) + color_offset
                color = self.colors[value % len(self.colors)]
                rgb = matplotlib.colors.hex2color(
                    matplotlib.colors.cnames[color])
                matrix_colored[irow, icol] = rgb
        return matrix_colored

    # todo: implement interpolation
    # todo: **kwargs
    def fill(self, cols: List[str]):
        """ Call this method with two column names, x and y. The results are
        similar to those of 2D scatter plots as created by the scatter
        method, except that the coloring is expanded to the whole xy plane.
        Note: This method only works with uniformly sampled NP!

        Args:
            cols: List of name of column to be plotted on x-axis and on y-axis

        Returns:
            The figure (unless the 'inline' setting of matplotllib is detected).
        """
        assert(len(cols) == 2)
        self._setup_all(cols)

        for isubplot in range(self._nsubplots -1):
            df_subplot = self.df.copy()
            for col in self._dofs:
                df_subplot = df_subplot[df_subplot[col] ==
                                        self._df_dofs.iloc[isubplot][col]]
            x = df_subplot[cols[0]].unique()
            y = df_subplot[cols[1]].unique()
            df_subplot.sort_values(by=[cols[1], cols[0]],
                                   ascending=[False, True],
                                   inplace=True)
            z = df_subplot[self.cluster_column].values
            Z = z.reshape(y.shape[0], x.shape[0])
            self._axli[isubplot].imshow(
                self._set_fill_colors(Z, color_offset=-1),
                interpolation='none',
                extent=[min(x), max(x), min(y), max(y)]
            )

        self._add_legend()
