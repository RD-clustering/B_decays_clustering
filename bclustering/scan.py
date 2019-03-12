#!/usr/bin/env python3

""" Scans the NP parameter space in a grid and also q2, producing the
normalized q2 distribution. """

# std
import datetime
import functools
import itertools
import json
import multiprocessing
import pathlib
import time
from typing import Union

# 3rd party
import numpy as np
import pandas as pd
import wilson

# ours
import bclustering.physics.bdlnu.distribution as distribution
from bclustering.util.log import get_logger
from bclustering.util.metadata import nested_dict, git_info


# NEEDS TO BE GLOBAL FUNCTION for multithreading
def calculate_bpoint(w: wilson.Wilson, bin_edges: np.array) -> np.array:
    """Calculates one benchmark point.

    Args:
        w: Wilson coefficients
        bin_edges:

    Returns:
        np.array of the integration results
    """

    return distribution.bin_function(lambda x: distribution.dGq2(w, x),
                                     bin_edges,
                                     normalized=True)


class Scanner(object):
    # todo: update example in docstring
    """ Scans the NP parameter space in a grid and also q2, producing the
    normalized q2 distribution.

    Usage example:

    .. code-block:: python
    
        # Initialize Scanner object
        s = Scanner()
    
        # Sample 3 points for each of the 5 Wilson coefficients
        s.set_bpoints_equidist(3)
    
        # Use 5 bins in q2
        s.set_q2points_equidist(5)
    
        # Start running with maximally 3 cores
        s.run(no_workers=3)
    
        # Write out results
        s.write("output/scan/global_output")

    This is example is equivalent to calling
    
    .. code-block:: sh
    
        ./scan.py -n 3 -g 5 -o output/scan/global_output -p 3
    
    or
    
    .. code-block:: sh
        
        ./scan.py --np-grid-subdivision 3 --grid-subdivision 5 \\
            --output output/scan/global_output --parallel 3
    """

    # **************************************************************************
    # A:  Setup
    # **************************************************************************

    def __init__(self):
        self.log = get_logger("Scanner")

        #: Benchmark points (i.e. Wilson coefficients)
        #: Do NOT directly modify this, but use one of the methods below.
        self._bpoints = []

        #: EDGES of the q2 bins
        #: Do NOT directly modify this, but use one of the methods below.
        self._q2points = np.array([])

        #: This will hold all of the results
        self.df = pd.DataFrame()

        #: This will hold all the configuration that we will write out
        self.metadata = nested_dict()
        self.metadata["scan"]["git"] = git_info(self.log)
        self.metadata["scan"]["time"] = time.strftime(
            "%a %_d %b %Y %H:%M", time.gmtime()
        )

    def set_q2points_manual(self, q2points: np.array) -> None:
        """ Manually set the edges of the q2 binning. """
        self._q2points = q2points
        self.metadata["scan"]["q2points"]["sampling"] = "manual"
        self.metadata["scan"]["q2points"]["nbins"] = len(self._q2points)

    def set_q2points_equidist(
        self,
        no_bins,
        dist_max=distribution.q2max,
        dist_min=distribution.q2min
    ) -> None:
        """ Set the edges of the q2 binning automatically.

        Args:
            no_bins: Number of bins
            dist_max: The right edge of the last bin (=maximal q2 value)
            dist_min: The left edge of the first bin (=minimal q2 value)

        Returns:
            None
        """
        self._q2points = np.linspace(dist_min, dist_max, no_bins+1)
        md = self.metadata["scan"]["q2points"]
        md["sampling"] = "equidistant"
        md["nbins"] = len(self._q2points) - 1
        md["min"] = dist_min
        md["max"] = dist_max

    def set_bpoints_grid(self, values, scale, eft, basis) -> None:
        """ Set a grid of benchmark points

        Args:
            values: {
                    <wilson coeff name>: [
                        value1,
                        value2,
                        ...
                    ]
                }
            scale: <Wilson coeff input scale in GeV>,
            eft: <Wilson coeff input eft>,
            basis: <Wilson coeff input basis>
        """

        # Important to remember the order now, because of what we do next.
        # Dicts are NOT ordered
        coeffs = list(values.keys())
        # It's very important to sort the coefficient names here, because when
        # calling wilson.Wilson(...).wc.values() later, these will also
        # be alphabetically ordered.
        coeffs.sort()
        # Nowe we collect all lists of values.
        values_lists = [
            values[coeff]["values"] for coeff in coeffs
        ]
        # Now we build the cartesian product, i.e.
        # [a1, a2, ...] x [b1, b2, ...] x ... x [z1, z2, ...] =
        # [(a1, b1, ..., z1), ..., (a2, b2, ..., z2)]
        cartesians = itertools.product(*values_lists)
        # And build wilson coefficients from this
        self._bpoints = [
            wilson.Wilson(
                wcdict={
                    coeffs[icoeff]: cartesian[icoeff]
                    for icoeff in range(len(coeffs))
                },
                scale=scale,
                eft=eft,
                basis=basis
            )
            for cartesian in cartesians
        ]

        md = self.metadata["scan"]["bpoints"]
        md["coeffs"] = list(values.keys())
        md["values"] = values
        md["scale"] = scale
        md["eft"] = eft
        md["basis"] = basis

    def set_bpoints_equidist(self, ranges, scale, eft, basis) -> None:
        """ Set a list of 'equidistant' benchmark points.

        Args:
            ranges: {
                <wilson coeff name>: (
                    <Minimum of wilson coeff>,
                    <Maximum of wilson coeff>,
                    <Number of bins between min and max>,
                )
            }
            scale: <Wilson coeff input scale in GeV>,
            eft: <Wilson coeff input eft>,
            basis: <Wilson coeff input basis>

        Returns:
            None
        """

        grid_config = {
            coeff: {
                "values": list(np.linspace(*ranges[coeff])),
            }
            for coeff in ranges
        }
        self.set_bpoints_grid(
            grid_config,
            scale=scale,
            eft=eft,
            basis=basis,
        )
        # Make sure to do this after set_bpoints_grid, so we overwrite
        # the relevant parts.
        md = self.metadata["scan"]["bpoints"]
        md["sampling"] = "equidistant"
        md["ranges"] = ranges

    # **************************************************************************
    # B:  Run
    # **************************************************************************

    def run(self, no_workers=4) -> None:
        """Calculate all benchmark points in parallel and saves the result in
        self.df.

        Args:
            no_workers: Number of worker nodes/cores
        """

        if self._bpoints == 0:
            self.log.error("No benchmark points specified. Returning without "
                           "doing anything.")
            return
        if self._q2points.size == 0:
            self.log.error("No q2points specified. Returning without "
                           "doing anything.")
            return

        # pool of worker nodes
        pool = multiprocessing.Pool(processes=no_workers)

        # this is the worker function: calculate_bpoints with additional
        # arguments frozen
        worker = functools.partial(
            calculate_bpoint,
            bin_edges=self._q2points
        )

        results = pool.imap(worker, self._bpoints)

        # close the queue for new jobs
        pool.close()

        self.log.info(
            "Started queue with {} job(s) distributed over up to {} "
            "core(s)/worker(s).".format(len(self._bpoints), no_workers))

        starttime = time.time()

        rows = []
        for index, result in enumerate(results):

            coeff_values = list(self._bpoints[index].wc.values.values())
            rows.append([*coeff_values, *result])

            timedelta = time.time() - starttime

            completed = index + 1
            rem_time = (len(self._bpoints) - completed) * timedelta/completed
            self.log.debug(
                "Progress: {}/{} ({:04.1f}%) of bpoints. "
                "Time/bpoint: {:.1f}s => "
                "time remaining: {} "
                "(total elapsed: {})".format(
                    str(completed).zfill(len(str(len(self._bpoints)))),
                    len(self._bpoints),
                    100*completed/len(self._bpoints),
                    timedelta/completed,
                    datetime.timedelta(seconds=int(rem_time)),
                    datetime.timedelta(seconds=int(timedelta))
                )
            )

        # Wait for completion of all jobs here
        pool.join()

        self.log.debug("Converting data to pandas dataframe.")
        # todo: check that there isn't any trouble with sorting.
        cols = self.metadata["scan"]["bpoints"]["coeffs"].copy()
        cols.extend(
            ["bin{}".format(no_bin) for no_bin in range(len(self._q2points)-1)]
        )
        self.df = pd.DataFrame(data=rows, columns=cols)
        self.df.index.name = "index"

        self.log.info("Integration done.")

    # **************************************************************************
    # C:  Write out
    # **************************************************************************

    @staticmethod
    def data_output_path(general_output_path: Union[pathlib.Path, str]) \
            -> pathlib.Path:
        """ Taking the general output path, return the path to the data file.
        """
        path = pathlib.Path(general_output_path)
        # noinspection PyTypeChecker
        return path.parent / (path.name + "_data.csv")

    @staticmethod
    def metadata_output_path(general_output_path: Union[pathlib.Path, str]) \
            -> pathlib.Path:
        """ Taking the general output path, return the path to the metadata file.
        """
        path = pathlib.Path(general_output_path)
        # noinspection PyTypeChecker
        return path.parent / (path.name + "_metadata.json")

    def write(self, general_output_path: Union[pathlib.Path, str]) -> None:
        """ Write out all results.
        IMPORTANT NOTE: All output files will always be overwritten!

        Args:
            general_output_path: Path to the output file without file 
                extension. We will add suffixes and file extensions to this!
        """
        if self.df.empty:
            self.log.error("Data frame is empty yet attempting to write out. "
                           "Ignore.")
            return

        # *** 1. Clean files and make sure the folders exist ***

        metadata_path = self.metadata_output_path(general_output_path)
        data_path = self.data_output_path(general_output_path)

        self.log.info("Will write metadata to '{}'.".format(metadata_path))
        self.log.info("Will write data to '{}'.".format(data_path))

        paths = [metadata_path, data_path]
        for path in paths:
            if not path.parent.is_dir():
                self.log.debug("Creating directory '{}'.".format(path.parent))
                path.parent.mkdir(parents=True)
            if path.exists():
                self.log.debug("Removing file '{}'.".format(path))
                path.unlink()

        # *** 2. Write out metadata ***

        self.log.debug("Converting metadata data to json and writing to file "
                       "'{}'.".format(metadata_path))
        with metadata_path.open("w") as metadata_file:
            json.dump(self.metadata, metadata_file, sort_keys=True, indent=4)
        self.log.debug("Done.")

        # *** 3. Write out data ***

        self.log.debug("Converting data to csv and writing to "
                       "file '{}'.".format(data_path))
        if self.df.empty:
            self.log.error("Dataframe seems to be empty. Still writing "
                           "out anyway.")
        self.df.index.name = "index"
        with data_path.open("w") as data_file:
            self.df.to_csv(data_file)
        self.log.debug("Done")

        # *** 4. Done ***

        self.log.info("Writing out finished.")


# todo: move this check somewhere
# paths = [s.metadata_output_path(args.output_path),
#          s.data_output_path(args.output_path)]
# existing_paths = [path for path in paths if path.exists()]
# if existing_paths:
#     agree = yn_prompt(
#         "Output paths {} already exist(s) and will be overwritten. "
#         "Proceed?".format(', '.join(map(str, existing_paths))))
#     if not agree:
#         s.log.critical("User abort.")
#         sys.exit(1)
