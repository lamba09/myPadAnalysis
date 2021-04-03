#!/usr/bin/env python
# --------------------------------------------------------
#       Script to automatically convert new files from the beam test
# created on August 15th 2016 by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------


from helpers.utils import *
from src.run_selection import RunSelector, Run, basename, glob


class AutoConvert:

    def __init__(self, multi, first_run=None, end_run=None, test_campaign=None, verbose=False):

        self.Multi = multi

        self.Selection = RunSelector(testcampaign=test_campaign, verbose=verbose)
        self.Run = self.Selection.Run
        self.StartAtRun = choose(first_run, self.find_last_converted())
        self.StopAtRun = 1e9 if not multi or end_run is None else int(end_run)
        self.Runs = self.load_runs()

    def find_last_converted(self):
        converted = [int(remove_letters(basename(name))) for name in glob(join(self.Selection.Run.TCDir, 'root', '*', 'TrackedRun*.root'))]
        return max(converted) if len(converted) else None

    def load_runs(self):
        runs = array([run for run in self.Selection.get_runplan_runs() if not file_exists(self.Selection.get_final_file_path(run))], 'i2')
        return runs[(runs >= self.StartAtRun) & (runs <= self.StopAtRun)]

    def load_logged_runs(self):
        runs = self.Selection.load_runs()
        return runs[runs >= self.StartAtRun]

    def get_next_run(self):
        last = self.find_last_converted()
        runs = self.load_logged_runs()
        return None if not runs.size or last == runs[-1] else runs[0] if last is None else next(run for run in runs if run > last)

    def auto_convert(self):
        """Sequential conversion with check if the file is currently written. For usage during beam tests."""
        self.Runs = self.load_logged_runs()
        if self.Runs.size > 1:
            info(f'Converting runs {self.Runs[0]} - {self.Runs[-1]}')
            # self.multi()
        while max(self.load_logged_runs()) <= self.StopAtRun:
            run = self.get_next_run()
            t0 = time()
            while run is None:
                info(f'waiting for new run {self.find_last_converted() + 1} since {get_running_time(t0)}', endl=False)
                sleep(5)
                run = self.get_next_run()
            raw_file = self.Run.Converter.get_raw_file_path(run)
            if not file_exists(raw_file, warn=True):
                continue
            t0 = time()
            while file_is_beeing_written(raw_file):
                info(f'waiting until run {run} is finished since {get_running_time(t0)}', endl=False)
                sleep(5)
            r = Run(run, self.Run.TCString)
            info(f'{run} --> {timedelta(seconds=round(time() - r.InitTime))}')

    def multi(self):
        """parallel conversion"""
        self.Run.info(f'Creating pool with {cpu_count()} processes')
        with Pool() as pool:
            runs = pool.starmap(Run, [(run, self.Selection.TCString, True, False) for run in self.Runs])
        print()
        print_small_banner('Summary:')
        for run in runs:
            print(f'{run} --> {timedelta(seconds=round(run.TInit))}')

    def run(self):
        if not self.Runs.size:
            return info('There are no runs to convert :-)')
        self.multi() if self.Multi else self.auto_convert()


if __name__ == '__main__':

    parser = ArgumentParser()
    parser.add_argument('-m', action='store_true', help='turn parallel processing ON')
    parser.add_argument('-tc', nargs='?', default=None)
    parser.add_argument('s', nargs='?', default=None, help='run number where to start, default [None], = stop if no end is provided', type=int)
    parser.add_argument('e', nargs='?', default=None, help='run number where to stop, default [None]')
    parser.add_argument('-v', action='store_false', help='turn verbose OFF')
    args = parser.parse_args()

    z = AutoConvert(args.m, args.s, args.e, args.tc, args.v)
    if z.Runs.size:
        print_banner(f'Starting {"multi" if z.Multi else "auto"} conversion for runs {z.Runs[0]} - {z.Runs[-1]}', color='green')
    z.run()
    print_banner('Finished Conversion!', color='green')
