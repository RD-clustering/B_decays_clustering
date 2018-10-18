#!/usr/bin/env python3

# standard modules
import numpy as np
import time
import datetime
import multiprocessing
import functools
import os

# internal modules
import distribution

###
### scans the NP parameter space in a grid and also q2, producing the normalized q2 distribution
###   I guess this table can then be used for the clustering algorithm, any.  

## q2 distribution normalized by total,  integral of this would be 1 by definition
## dGq2normtot(epsL, epsR, epsSR, epsSL, epsT,q2)


def get_bpoints(np_grid_subdivisions = 20):
    """ Get a list of all benchmark points.

    Args:
        np_grid_subdivisions: Number of subdivision/sample points for the NP
            parameter grid that is sampled

    Returns:
        a list of all benchmark points as tuples in the form
        (epsL, epsR, epsSR, epsSL, epsT)
    """

    bps = []  # list of of benchmark points

    # I set epsR an epsSR to zero  as the observables are only sensitive to
    # linear combinations  L + R
    epsR = 0
    epsSR = 0
    for epsL in np.linspace(-0.30, 0.30, np_grid_subdivisions):
        for epsSL in np.linspace(-0.30, 0.30, np_grid_subdivisions):
            for epsT in np.linspace(-0.40, 0.40, np_grid_subdivisions):
                bps.append((epsL, epsR, epsSR, epsSL, epsT))

    return bps


def calculate_bpoint(bpoint, lock, output_path, grid_subdivision=15):
    """ Calculates one benchmark point and writes the result to the output
    file. This method is designed to be thread save.

    Args:
        lock: multithreading.lock instance to avoid writing to the same file
            at the same time
        bpoint: epsL, epsR, epsSR, epsSL, epsT
        output_path: Output path we append to
        grid_subdivision: q2 grid spacing

    Returns:
        None

    """

    result_list = []
    for q2 in np.linspace(distribution.q2min, distribution.q2max, grid_subdivision):
        dist_tmp = distribution.dGq2normtot(*bpoint, q2)
        result_list.append((q2, dist_tmp))

    lock.acquire()
    with open(output_path, "a") as outfile:
        for q2, dist_tmp in result_list:
            for param in bpoint:
                outfile.write("{:.5f}    ".format(param))
            outfile.write('{:.5f}     {:.10f}\n'.format(q2 , dist_tmp))
    lock.release()


def run_parallel(bpoints, no_workers=4, output_path="global_results.out"):
    """
    Run integrations in parallel.

    Args:
        bpoints: Benchmark points
        no_workers: Number of worker nodes/cores

    Returns:
        None
    """

    if os.path.exists(output_path):
        os.remove(output_path)

    # pool of worker nodes
    pool = multiprocessing.Pool(processes=no_workers)

    # we need a lock instance in order to limit file I/O to only one process
    # at a time
    manager = multiprocessing.Manager()
    lock = manager.Lock()

    # this is the worker function: calculate_bpoints with lock and output_path
    # arguments frozen
    worker = functools.partial(calculate_bpoint, lock=lock, output_path=output_path)

    # submit the jobs, i.e. apply the worker function to every benchmark point
    results = pool.imap_unordered(worker, bpoints)

    # close the queue for new jobs
    pool.close()

    # ** Everything below here is just a progress monitor **

    completed = 0
    starttime = time.time()

    while True:
        # results._index holds the number of the completed results
        if completed == results._index:
            # Wait till we have a new result
            time.sleep(0.5)
            continue

        completed = results._index

        if completed == len(bpoints):
            print("Completed.")
            break

        timedelta = time.time() - starttime

        if completed > 0:
            remaining_time = (len(bpoints) - completed) * timedelta/completed
            print("Progress: {:04}/{:04} ({:04.1f}%) of benchmark points. "
                  "Time/bpoint: {:.1f}s => "
                  "time remaining: {}".format(
                     completed,
                     len(bpoints),
                     100*completed/len(bpoints),
                     timedelta/completed,
                     datetime.timedelta(seconds=remaining_time)
                 ))

    # Wait for completion of all jobs here
    pool.join()

if __name__ == "__main__":
    bpoints = get_bpoints(20)
    run_parallel(bpoints, 2)
