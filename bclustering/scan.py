#!/usr/bin/env python3

""" Scans the NP parameter space in a grid and also q2, producing the
normalized q2 distribution. """

# std
import functools
import itertools
import json
import multiprocessing
import os
import pathlib
import shutil
import time
from typing import Union, Callable, List, Sized

# 3rd party
import numpy as np
import pandas as pd
import wilson
import tqdm

# ours
from bclustering.util.cli import yn_prompt
import bclustering.maths.binning
from bclustering.util.log import get_logger
from bclustering.util.metadata import nested_dict, git_info, failsafe_serialize


class WpointCalculator(object):
    """ A class that holds the function with which we calculate each
    point in wilson space. Note that this has to be a separate class from Scanner
    to avoid problems related to multiprocessing's use of the pickle
    library, which are described here:
    https://stackoverflow.com/questions/1412787/
    """
    def __init__(self, func: Callable, binning: Sized, normalize, kwargs):
        self.dfunc = func
        self.dfunc_binning = binning
        self.dfunc_normalize = normalize
        self.dfunc_kwargs = kwargs

    def calc(self, w: wilson.Wilson) -> np.array:
        """Calculates one point in wilson space.

        Args:
            w: Wilson coefficients

        Returns:
            np.array of the integration results
        """

        if self.dfunc_binning is not None:
            return bclustering.maths.binning.bin_function(
                functools.partial(self.dfunc, w, **self.dfunc_kwargs),
                self.dfunc_binning,
                normalize=self.dfunc_normalize
            )
        else:
            return self.dfunc(w, **self.dfunc_kwargs)


class Scanner(object):
    # todo: update example in docstring
    """ Scans the NP parameter space in a grid and also q2, producing the
    normalized q2 distribution.

    Usage example:

    .. code-block:: python
        import flavio

        # Initialize Scanner object
        s = Scanner()
    
        # Sample 4 points for each of the 5 Wilson coefficients
        s.set_wpoints_equidist(
            {
                "CVL_bctaunutau": (-1, 1, 4),
                "CSL_bctaunutau": (-1, 1, 4),
                "CT_bctaunutau": (-1, 1, 4)
            },
            scale=5,
            eft='WET',
            basis='flavio'
        )
    
        # Set function and binning
        s.set_dfunction(
           functools.partial(flavio.np_prediction, "dBR/dq2(B+->Dtaunu)"),
            binning=np.linspace(3.15, bdlnu.q2max, 11.66),
            normalize=True
        )
    
        # Start running with maximally 3 cores
        s.run(no_workers=3)
    
        # Write out results
        s.write("output/scan", "global_output")

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

        #: Points in wilson space
        #:  Use self.wpoints to access this
        self._wpoints = []

        #: Instance of WpointCalculator to perform the claculations of
        #:  the wilson space points.
        self.wpoint_calculator = None  # type: WpointCalculator

        #: This will hold all of the results
        self.df = pd.DataFrame()

        #: This will hold all the configuration that we will write out
        self.metadata = nested_dict()
        self.metadata["scan"]["git"] = git_info(self.log)
        self.metadata["scan"]["time"] = time.strftime(
            "%a %_d %b %Y %H:%M", time.gmtime()
        )

    # Write only access
    @property
    def wpoints(self) -> List[wilson.Wilson]:
        """ Points in wilson space that are sampled."""
        return self._wpoints

    def set_dfunction(
            self,
            func: Callable,
            binning: Sized = None,
            normalize=False,
            **kwargs
    ):
        """ Set the function that generates the distributions that are later
        clustered (e.g. a differential cross section).

        Args:
            func: A function that takes the wilson coefficient as the first
                argument. It should either return a float (if the binning
                option is specified), or a np.array elsewise.
            binning: If this parameter is not set (None), we will use the
                function as is. If it is set to an array-like object, we will
                integrate the function over the bins specified by this
                parameter.
            normalize: If a binning is specified, normalize the resulting
                distribution
            **kwargs: All other keyword arguments are passed to the function.

        Returns:
            None

        """
        md = self.metadata["scan"]["dfunction"]
        try:
            md["name"] = func.__name__
            md["doc"] = func.__doc__
        except AttributeError:
            try:
                # For functools.partial objects
                # noinspection PyUnresolvedReferences
                md["name"] = "functools.partial({})".format(func.func.__name__)
                # noinspection PyUnresolvedReferences
                md["doc"] = func.func.__doc__
            except AttributeError:
                pass

        md["kwargs"] = failsafe_serialize(kwargs)
        if binning is not None:
            md["nbins"] = len(binning) - 1

        # global wpoint_calculator
        self.wpoint_calculator = WpointCalculator(
            func, binning, normalize, kwargs
        )

    def set_wpoints_grid(self, values, scale, eft, basis) -> None:
        """ Set a grid of points in wilson space.

        Args:
            values: {
                    <wilson coeff name>: [
                        value1,
                        value2,
                        ...
                    ]
                }
            scale: <Wilson coeff input scale in GeV>
            eft: <Wilson coeff input eft>
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
            values[coeff] for coeff in coeffs
        ]
        # Now we build the cartesian product, i.e.
        # [a1, a2, ...] x [b1, b2, ...] x ... x [z1, z2, ...] =
        # [(a1, b1, ..., z1), ..., (a2, b2, ..., z2)]
        cartesians = list(itertools.product(*values_lists))

        # And build wilson coefficients from this
        self._wpoints = [
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

        md = self.metadata["scan"]["wpoints"]
        md["coeffs"] = list(values.keys())
        md["values"] = values
        md["scale"] = scale
        md["eft"] = eft
        md["basis"] = basis

    def set_wpoints_equidist(self, ranges, scale, eft, basis) -> None:
        """ Set a list of 'equidistant' points in wilson space.

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
            coeff: list(np.linspace(*ranges[coeff]))
            for coeff in ranges
        }
        self.set_wpoints_grid(
            grid_config,
            scale=scale,
            eft=eft,
            basis=basis,
        )
        # Make sure to do this after set_wpoints_grid, so we overwrite
        # the relevant parts.
        md = self.metadata["scan"]["wpoints"]
        md["sampling"] = "equidistant"
        md["ranges"] = ranges

    # **************************************************************************
    # B:  Run
    # **************************************************************************

    def run(self, no_workers=None) -> None:
        """Calculate all wilson points in parallel and saves the result in
        self.df.

        Args:
            no_workers: Number of worker nodes/cores. Default: Total number of
                cores.
        """

        if not self._wpoints:
            self.log.error(
                "No wilson points specified. Returning without doing "
                "anything."
            )
            return
        if not self.wpoint_calculator:
            self.log.error(
                "No function specified. Please set it "
                "using ``Scanner.set_dfunction``. Returning without doing "
                "anything."
            )
            return

        if not no_workers:
            no_workers = os.cpu_count()
        if not no_workers:
            # os.cpu_count() didn't work
            self.log.warn(
                "os.cpu_count() not determine number of cores. Fallling "
                "back to no_workser = 1."
            )
            no_workers = 1

        # pool of worker nodes
        pool = multiprocessing.Pool(processes=no_workers)

        # this is the worker function.
        worker = self.wpoint_calculator.calc

        results = pool.imap(worker, self._wpoints)

        # close the queue for new jobs
        pool.close()

        self.log.info(
            "Started queue with {} job(s) distributed over up to {} "
            "core(s)/worker(s).".format(len(self._wpoints), no_workers)
        )

        rows = []
        for index, result in tqdm.tqdm(
            enumerate(results),
            desc="Scanning: ",
            unit=" wpoint",
            total=len(self._wpoints),
            ncols=min(100, shutil.get_terminal_size((80, 20)).columns)
        ):
            md = self.metadata["scan"]["dfunction"]
            if "nbins" not in md:
                md["nbins"] = len(result) - 1

            coeff_values = list(self._wpoints[index].wc.values.values())
            rows.append([*coeff_values, *result])

        # Wait for completion of all jobs here
        pool.join()

        self.log.debug("Converting data to pandas dataframe.")
        # todo: check that there isn't any trouble with sorting.
        cols = self.metadata["scan"]["wpoints"]["coeffs"].copy()
        cols.extend([
            "bin{}".format(no_bin)
            for no_bin in range(self.metadata["scan"]["dfunction"]["nbins"])
        ])
        self.df = pd.DataFrame(data=rows, columns=cols)
        self.df.index.name = "index"

        self.log.info("Integration done.")

    # **************************************************************************
    # C:  Write out
    # **************************************************************************

    @staticmethod
    def data_output_path(directory: Union[pathlib.Path, str], name: str) \
            -> pathlib.Path:
        """ Taking the general output path, return the path to the data file.
        """
        directory = pathlib.Path(directory)
        return directory / (name + "_data.csv")

    @staticmethod
    def metadata_output_path(directory: Union[pathlib.Path, str], name: str) \
            -> pathlib.Path:
        """ Taking the general output path, return the path to the metadat
        file.
        """
        directory = pathlib.Path(directory)
        return directory / (name + "_metadata.json")

    def write(self, directory: Union[pathlib.Path, str], name: str,
              overwrite="ask") -> None:
        """ Write out all results.

        Args:
            directory: Directory to save file in
            name: Name of output file (no extensions)
            overwrite: How to proceed if output file already exists:
                'ask', 'overwrite', 'raise'
        """
        if self.df.empty:
            self.log.error("Data frame is empty yet attempting to write out. "
                           "Ignore.")
            return

        # *** 1. Clean files and make sure the folders exist ***

        metadata_path = self.metadata_output_path(directory, name)
        data_path = self.data_output_path(directory, name)

        self.log.info("Will write metadata to '{}'.".format(metadata_path))
        self.log.info("Will write data to '{}'.".format(data_path))

        paths = [metadata_path, data_path]
        for path in paths:
            if not path.parent.is_dir():
                self.log.debug("Creating directory '{}'.".format(path.parent))
                path.parent.mkdir(parents=True)

        overwrite = overwrite.lower()
        if any([p.exists() for p in paths]):
            if overwrite == "ask":
                prompt = "Some of the output files would be overwritten. " \
                         "Are you ok with that?"
                if not yn_prompt(prompt):
                    self.log.warning("Returning without doing anything.")
                    return
            elif overwrite == "overwrite":
                pass
            elif overwrite == "raise":
                msg = "Some of the output files would be overwritten."
                self.log.critical(msg)
                raise FileExistsError(msg)
            else:
                msg = "Unknown option for 'overwrite' argument."
                self.log.critical(msg)
                raise ValueError(msg)
        # From here on we definitely overwrite

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
            self.log.error(
                "Dataframe seems to be empty. Still writing out anyway."
            )
        self.df.index.name = "index"
        with data_path.open("w") as data_file:
            self.df.to_csv(data_file)
        self.log.debug("Done")

        # *** 4. Done ***

        self.log.info("Writing out finished.")
