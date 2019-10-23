from ConfigParser import ConfigParser
from argparse import ArgumentParser
from datetime import datetime as dt
from glob import glob
from itertools import chain
from textwrap import fill
from json import load, loads, dump

from os import system

from Utils import *
from Elementary import Elementary
from Run import Run


class RunSelection(Elementary):
    def __init__(self, testcampaign=None, runplan=None, dia_nr=None, verbose=True):
        Elementary.__init__(self, verbose=verbose, testcampaign=testcampaign)
        self.Run = Run(verbose=verbose, tree=False)

        self.Selection = {}

        # info
        self.TCString = '{tc}{s}'.format(tc=self.TESTCAMPAIGN, s=self.generate_sub_set_str())
        self.RunPlanPath = join(self.get_program_dir(), self.MainConfigParser.get('MAIN', 'run_plan_path'))
        self.ExcludedRuns = loads(self.RunConfig.get('BASIC', 'excluded_runs'))
        self.RunPlan = self.load_runplan()
        self.RunNumbers = self.load_run_numbers()
        self.RunInfos = self.load_run_infos()
        self.logs = {}

        # selection
        self.SelectedRunplan = None
        self.SelectedType = None
        self.SelectedBias = None
        self.SelectedDiamond = None
        self.SelectedDiamondNr = None

        self.init_selection()

        self.select_runs_from_runplan(runplan, dia_nr)

    def __str__(self):
        # nr = len(self.RunNumbers)
        # selected_runs = self.get_selected_runs()
        # return 'RunSelection Object\n' + str(len(selected_runs)) + ' Out of ' + str(nr) + ' runs selected. Selections made:' + self.get_log_string()
        return 'RunSelection with RunPlan {} of {} taken in {}'.format(self.SelectedRunplan, self.SelectedDiamond, tc_to_str(self.TESTCAMPAIGN, short=False))

    # ============================================
    # region LOGGING
    def make_log_entry(self, event):
        time_str = dt.now().strftime('%H:%M:%S')
        self.logs[len(self.logs)] = [event, time_str]

    def get_log_string(self):
        string = '\n'
        for key, log in self.logs.iteritems():
            string += '{key}.)\t{log}'.format(key=key, log=log[0])
        return string

    def print_logs(self):
        for key, log in self.logs.iteritems():
            print '{key}.)\t{time}\t{log}'.format(key=key, time=log[1], log=log[0])

    # endregion

    # ============================================
    # region INIT

    def load_run_numbers(self):
        f = open(self.Run.runinfofile, 'r')
        data = load(f)
        f.close()
        run_numbers = [int(key) for key in data if int(key) not in self.ExcludedRuns]
        return sorted(run_numbers)

    def load_run_infos(self):
        """ loads all the run infos in a dict with the run numbers as keys """
        try:
            f = open(self.load_run_info_path(), 'r')
            data = load(f)
            data = {int(run): dic for run, dic in data.iteritems() if int(run) not in self.ExcludedRuns}
            f.close()
            return data
        except IOError as err:
            log_critical('{err}\nCould not load RunInfo!'.format(err=err))

    def init_selection(self):
        self.reset_selection()

    def load_runplan(self):
        f = open(self.RunPlanPath, 'r')
        runplans = load(f)
        f.close()
        try:
            runplan = runplans[self.TCString]
        except KeyError:
            print 'No runplan for {tc} available yet, creating an empty one!'.format(tc=self.TCString)
            runplan = {}
            self.save_runplan(runplan)
        return runplan

    # endregion

    # ============================================
    # region SELECT FUNCTIONS
    def reset_selection(self):
        """ Creates a dict of bools to store the selection, which is filled with False (no run selected). Resets the logs. """
        self.logs = {}
        for run in self.RunNumbers:
            self.Selection[run] = False

    def select_all_runs(self):
        for run in self.RunNumbers:
            self.Selection[run] = True
        self.make_log_entry('All runs selected')
        self.verbose_print('All runs selected')

    def unselect_all_runs(self, info=True):
        self.reset_selection()
        if info:
            self.log_info('unselect all runs')

    def clear_selection(self):
        self.reset_selection()

    def select_runs_of_type(self, run_type, unselect=False, only_selected=False):
        """
        Selects the runs according to the type of run, such as rate_scan, test, voltage_scan etc..
        :param run_type:
        :param unselect:
        :param only_selected:
        """
        types = self.get_runinfo_values('type')
        assert run_type in types, 'wrong data type.\n\t-->Select type of these: {types}'.format(types=types)
        runs = self.get_selected_runs() if only_selected else self.RunNumbers
        selected_runs = 0
        for run in runs:
            if self.RunInfos[run]['type'] == run_type:
                self.select_run(run, False) if not unselect else self.unselect_run(run)
                selected_runs += 1
            else:
                if not unselect:
                    self.unselect_run(run)
        prefix = 'un' if unselect else ''
        self.make_log_entry('Runs of type {type} {pref}selected ({nr} {pref}selections).'.format(type=run_type, pref=prefix, nr=selected_runs))
        self.verbose_print('Runs of type {type} {pref}selected ({nr} {pref}selections).'.format(type=run_type, pref=prefix, nr=selected_runs))

    def unselect_runs_of_type(self, run_type):
        self.select_runs_of_type(run_type, unselect=True)

    def select_diamond_runs(self, name, only_selected_runs=False):
        """ Selects all runs, which have the diamond with name [name] in it"""
        dia_names = self.get_diamond_names()
        name = self.Run.translate_dia(name)
        if name not in dia_names:
            warning('"{n}" is not in the list of diamonds: {lst}'.format(n=name, lst=dia_names))
        runs = self.get_selected_runs() if only_selected_runs else self.RunNumbers
        selected_runs = 0
        unselected_runs = 0
        selected_run = False
        for run in runs:
            for dia_nr in xrange(1, 4):
                info = self.RunInfos[run]
                if 'dia{}'.format(dia_nr) in info and name == info['dia{}'.format(dia_nr)]:
                    self.SelectedDiamondNr = dia_nr
                    self.select_run(run)
                    selected_runs += 1
                    selected_run = True
                elif self.Selection[run] and not selected_run:
                    self.unselect_run(run)
                    unselected_runs += 1
            selected_run = False
        self.SelectedDiamond = name
        self.log_info('Runs containing {dia} selected ({nr1} runs selected, {nr2} unselected)'.format(dia=name, nr1=selected_runs, nr2=unselected_runs))

    def unselect_unless_bias(self, bias):
        """
        Keeps only runs selected which have a diamond with a given bias voltage. Diamonds with a different bias voltage will be un- selected.
        :param bias:
        """
        assert type(bias) is int, 'Bias has to be an integer'
        unselected_runs = 0
        for run in self.get_selected_runs():
            if self.RunInfos[run]['dia{nr}hv'.format(nr=self.SelectedDiamondNr)] != bias:
                self.unselect_run(run)
                unselected_runs += 1
        log = 'Unselected all runs and channels if bias is not {bias}V (unselected {nr} runs).'.format(bias=bias, nr=unselected_runs)
        self.make_log_entry(log)
        self.verbose_print(log)

    def select_run(self, run_number, unselect=False):
        if run_number not in self.RunNumbers:
            log_warning('Run {run} not found in list of run numbers. Check run_log json file!'.format(run=run_number))
            return
        self.Selection[run_number] = not unselect

    def unselect_run(self, run_number):
        self.select_run(run_number, unselect=True)

    def unselect_list_of_runs(self, run_list):
        assert type(run_list) is list, 'argument has to be a list of integers'
        unselected_runs = 0
        selected_runs = self.get_selected_runs()
        for run in run_list:
            if run in selected_runs:
                self.unselect_run(run)
                unselected_runs += 1
            else:
                print '{run} was not selected'.format(run=run)
        self.make_log_entry('Unselected {n} runs'.format(n=unselected_runs))

    def select_runs_in_range(self, minrun, maxrun):
        for run in self.RunNumbers:
            if maxrun >= run >= minrun:
                self.select_run(run)

    def select_runs(self, run_list, dia=1):
        for run in run_list:
            self.select_run(run)
        parser = ConfigParser()
        parser.read('Configuration/DiamondAliases.cfg')
        self.SelectedType = 'CurrentInfo'
        self.SelectedDiamondNr = dia
        self.SelectedDiamond = parser.get('ALIASES', self.RunInfos[self.get_selected_runs()[0]]['dia{0}'.format(dia)])
        self.SelectedBias = self.RunInfos[self.get_selected_runs()[0]]['dia{0}hv'.format(dia)]

    def unselect_unless_in_range(self, minrun, maxrun):
        for run in self.get_selected_runs():
            if not maxrun >= run >= minrun:
                self.unselect_run(run)

    def master_selection(self):
        self.unselect_all_runs()
        self.show_diamond_names()
        dia = raw_input('Which diamond do you want to select? ')
        self.select_diamond_runs(dia)
        # self.show_hv_values(sel=True)
        hv = int(float(raw_input('Which hv do you want to select? ')))
        self.unselect_unless_bias(hv)
        if len(self.get_runinfo_values('type', sel=True)) > 1:
            self.show_run_types(sel=True)
            if verify('Do you wish to unselect a run type'):
                run_type = raw_input('Which type to you want to unselect? ')
                self.unselect_runs_of_type(run_type)
        self.show_selected_runs(full_comments=True)
        while verify('Do you wish to unselect a run'):
            run = raw_input('Which run do you want to unselect? ')
            self.unselect_run(int(run))
        self.show_run_plans()
        if verify('Do you wish to save the selection to a runplan'):
            nr = raw_input('Enter the name/number of the runplan: ')
            self.add_selection_to_runplan(nr)

    def get_selected_runs(self):
        """ :return: list of selected run numbers. """
        selected = []
        for run in self.RunNumbers:
            if self.Selection[run]:
                selected.append(run)
        if not selected:
            print 'No runs selected!'
        return sorted(selected)

    def get_last_selected_run(self):
        return self.get_selected_runs()[-1]

    def get_first_selected_run(self):
        return self.get_selected_runs()[0]

    def show_selected_runs(self, full_comments=False):
        """ Prints an overview of all selected runs. """
        selected_runs = self.get_selected_runs()
        print 'The selections contains {n} runs\n'.format(n=len(selected_runs))
        r = self.Run
        r.set_run(selected_runs[0], root_tree=False)
        dia_bias = list(chain(*[['Dia {}'.format(i + 1), 'HV {} [V]'.format(i + 1)] for i in xrange(self.Run.get_n_diamonds())]))
        header = ['Nr.', 'Type'] + dia_bias + ['Flux [kHz/cm2]'] + (['Comments'] if not full_comments else [])
        rows = []
        for run in selected_runs:
            r.set_run(run, root_tree=False)
            d = [str(value) for value in r.load_diamond_names()]
            b = ['{v:+7.0f}'.format(v=value) for value in r.load_biases()]
            dia_bias = list(chain(*[[d[i], b[i]] for i in xrange(len(d))]))
            row = ['{:3d}'.format(run), r.RunInfo['runtype']] + dia_bias + ['{:14.2f}'.format(r.Flux.n)]
            if not full_comments:
                row += ['{c}{s}'.format(c=r.RunInfo['comments'][:20].replace('\r\n', ' '), s='*' if len(r.RunInfo['comments']) > 20 else ' ' * 21)]
                rows.append(row)
            else:
                rows.append(row)
                if r.RunInfo['comments']:
                    rows.append(['Comments: {c}'.format(c=fill(r.RunInfo['comments'], len('   '.join(header))))])
                    rows.append(['~' * len('   '.join(rows[0]))])
        print_table(rows, header)

    # endregion

    # ============================================
    # region RUN PLAN
    def save_runplan(self, runplan=None):
        f = open(self.RunPlanPath, 'r+')
        runplans = load(f)
        runplans[self.TCString] = self.RunPlan if runplan is None else runplan
        self.rename_runplan_numbers() if runplan is not None and runplan else do_nothing()
        f.seek(0)
        dump(runplans, f, indent=2, sort_keys=True)
        f.truncate()
        f.close()

    def add_runplan_descriptions(self):
        for rp in sorted(self.RunPlan.iterkeys()):
            self.add_runplan_description(rp, ask=False)

    def add_runplan_description(self, rp=None, name=None, ask=True):
        rp = raw_input('Enter run plan number: ') if ask else rp
        rp_str = self.make_runplan_string(rp)
        runs = self.RunPlan[rp_str]
        if ask:
            name = raw_input('Enter description: ')
        else:
            if 'type' in self.RunInfos[runs[0]]:
                name = self.RunInfos[runs[0]]['type'].replace('_', ' ')
            name = 'rate scan' if name is None else name
        if type(runs) is dict:
            runs = runs['runs']
        self.log_info('Adding new description for run plan {rp}: {name}'.format(rp=rp_str, name=name))
        self.RunPlan[rp_str] = {'type': name, 'runs': runs}
        self.save_runplan()

    def add_amplifier(self, rp=None):
        rp = self.make_runplan_string(raw_input('Enter run plan number: ')) if rp is None else rp
        print 'Common amplifiers: Cx_1 C6_1 C6_2'
        print 'leave blank for OSU amps'
        amp1 = raw_input('Enter amplifier for detector 1: ')
        amp2 = raw_input('Enter amplifier for detector 2: ')
        if amp1 or amp2:
            self.add_runplan_info(rp, 'amplifiers', '["{}", "{}"]'.format(amp1, amp2))

    def add_runplan_key(self):
        rp = self.make_runplan_string(raw_input('Enter run plan number: '))
        print 'Current keys: {}'.format(self.RunPlan[rp].keys())
        new_key = raw_input('Which key do you want to add? ')
        value = raw_input('Enter the value: ')
        self.add_runplan_info(rp, new_key, value)

    def add_runplan_info(self, rp, key, value):
        self.RunPlan[rp][key] = value
        self.save_runplan()

    def add_attenuators(self, rp=None, attenuator=None, ask=True):
        rp = self.make_runplan_string(raw_input('Enter run plan number: ') if ask else rp)
        info = self.RunInfos[self.RunPlan[rp]['runs'][0]]
        at_d1 = raw_input('Enter attenuator for {dia1}: '.format(dia1=info['dia1'])) if attenuator is None else attenuator[0]
        at_d2 = raw_input('Enter attenuator for {dia2}: '.format(dia2=info['dia2'])) if attenuator is None else attenuator[1]
        at_pul1 = raw_input('Enter attenuator for the pulser1: ') if attenuator is None else attenuator[2]
        at_pul2 = raw_input('Enter attenuator for the pulser2: ') if attenuator is None else attenuator[3]
        self.RunPlan[rp]['attenuators'] = {'dia1': at_d1, 'dia2': at_d2, 'pulser1': at_pul1}
        if at_pul2:
            self.RunPlan[rp]['attenuators']['pulser2'] = at_pul2
        self.save_runplan()

    def rename_runplan_numbers(self):
        for type_, plan in self.RunPlan.iteritems():
            for nr in plan:
                self.RunPlan[type_][nr.zfill(2)] = self.RunPlan[type_].pop(nr)

    def show_run_plans(self, diamond=None):
        """ Print a list of all run plans from the current test campaign to the console. """
        old_selection = deepcopy(self.Selection)
        old_logs = deepcopy(self.logs)
        print 'RUN PLAN FOR TESTCAMPAIGN: {tc}\n'.format(tc=self.TCString)
        header = ['Nr.', 'Run Type', 'Range', 'Excluded']
        max_dias = self.get_max_dias()
        for i in xrange(1, max_dias + 1):
            header += ['Dia{}'.format(i), 'HV{} [V]'.format(i).rjust(13)]
        rows = []
        for plan, info in sorted(self.RunPlan.iteritems()):
            self.unselect_all_runs(info=False)
            self.select_runs_from_runplan(plan)
            dias = self.get_rp_diamond_names()
            if diamond is not None and diamond not in dias:
                continue
            runs = info['runs']
            run_string = '{min:3d} - {max:3d}'.format(min=runs[0], max=runs[-1])
            row = [plan, info['type'], run_string, self.get_missing_runs(runs)]
            for dia, bias in zip(dias, self.get_rp_voltages()):
                row += [dia, bias]
            if len(dias) < max_dias:
                row += ['', ''] * (max_dias - len(dias))
            rows.append(row)
        print_table(rows, header)

        self.logs = old_logs
        self.Selection = old_selection

    def get_max_dias(self):
        return max(self.Run.get_n_diamonds(info['runs'][0]) for info in self.RunPlan.itervalues())

    def get_rp_diamond_names(self):
        dias = [self.get_runinfo_values('dia{0}'.format(i), sel=True) for i in xrange(1, self.Run.get_n_diamonds(self.get_selected_runs()[0]) + 1)]
        if any(len(dia) > 1 for dia in dias):
            log_warning('RunPlan {rp} has more than one diamond'.format(rp=self.SelectedRunplan))
        return [dia[0] for dia in dias]

    def get_rp_voltages(self):
        hvs = [[float(hv) for hv in self.get_runinfo_values('dia{0}hv'.format(i), sel=True)] for i in xrange(1, self.Run.get_n_diamonds(self.get_selected_runs()[0]) + 1)]
        if any(len(hv) > 1 for hv in hvs):
            abs_hvs = [[abs(v) for v in hv] for hv in hvs]
            return ('{min:+4.0f} ... {max:+4.0f}'.format(min=hv[ahv.index(min(ahv))], max=hv[ahv.index(max(ahv))]) for ahv, hv in zip(abs_hvs, hvs))
        return ('{v:+13.0f}'.format(v=hv[0]) for hv in hvs)

    def get_selected_bias(self):
        hvs = self.get_runinfo_values('dia{}hv'.format(self.SelectedDiamondNr), sel=True)
        return int(hvs[0]) if len(hvs) == 1 else None

    def get_missing_runs(self, runs):
        all_runs = [run for run in self.RunNumbers if runs[-1] >= run >= runs[0]]
        missing_runs = [run for run in all_runs if run not in runs]
        return str(missing_runs if len(missing_runs) <= 3 else '{0}, ...]'.format(str(missing_runs[:2]).strip(']'))) if missing_runs else ''

    def select_runs_from_runplan(self, plan_nr, ch=1):
        if plan_nr is None:
            return
        plan = self.make_runplan_string(plan_nr)
        runs = self.RunPlan[plan]['runs']

        self.select_runs(runs)
        parser = ConfigParser()
        parser.read('Configuration/DiamondAliases.cfg')
        self.SelectedRunplan = plan
        self.SelectedType = str(self.RunPlan[plan]['type'])
        self.SelectedDiamond = parser.get('ALIASES', self.RunInfos[runs[0]]['dia{0}'.format(ch)])
        self.SelectedDiamondNr = ch
        self.SelectedBias = self.get_selected_bias()

    def add_selection_to_runplan(self, plan_nr, run_type=None):
        """ Saves all selected runs as a run plan with name 'plan_nr'. """
        if not self.Selection:
            log_warning('You did not select any run!')
            return
        plan_nr = self.make_runplan_string(plan_nr)
        self.RunPlan[plan_nr] = {'runs': self.get_selected_runs(), 'type': self.get_run_type(run_type)}
        attenuators = self.get_attenuators_from_runcofig()
        if attenuators:
            self.RunPlan[plan_nr]['attenuators'] = attenuators
        self.save_runplan()
        self.add_amplifier(plan_nr)
        self.unselect_all_runs()

    def get_attenuators_from_runcofig(self):
        dic = {}
        for i in xrange(1, len(self.get_diamond_names(sel=True)) + 1):
            dic['dia{}'.format(i)] = self.get_attenuator('att_dia{}'.format(i))
            dic['pulser{}'.format(i)] = self.get_attenuator('att_pul{}'.format(i))
        return dic

    def delete_runplan(self, plan_nr):
        plan = self.make_runplan_string(plan_nr)
        self.RunPlan.pop(plan)
        self.save_runplan()

    # endregion

    @staticmethod
    def make_runplan_string(nr):
        nr = str(nr)
        return nr.zfill(2) if len(nr) <= 2 else nr.zfill(4)

    def get_diamond_names(self, sel=False):
        keys = ['dia{}'.format(i + 1) for i in xrange(self.get_max_dias())]
        dias = [self.Run.translate_dia(dia) for key in keys for dia in self.get_runinfo_values(key, sel)]
        return list(set(dia.lower() for dia in dias if dia is not None))

    def show_diamond_names(self, sel=False):
        print 'Diamondnames:'
        for name in self.get_diamond_names(sel=sel):
            print '  ' + name

    def show_run_types(self, sel=False):
        print 'Types:'
        for type_ in self.get_runinfo_values('type', sel=sel):
            print '  ' + type_

    def get_attenuator(self, key):
        atts = self.get_runinfo_values(key, sel=True)
        return atts[0] if atts is not None and len(atts) == 1 else '?'

    def get_run_type(self, run_type=None):
        types = [t.replace('_', ' ') for t in self.get_runinfo_values('runtype', sel=True)]
        return run_type if run_type is not None else types[0] if len(types) == 1 else run_type

    def get_runinfo_values(self, key, sel=False):
        """ returns all different runinfos for a specified key of the selection or the full run plan """
        run_infos = self.RunInfos if not sel else self.get_selection_runinfo()
        if all(key in info for info in run_infos.itervalues()):
            return sorted(list(set(info[key] for info in run_infos.itervalues())))

    def get_selection_runinfo(self):
        dic = {}
        for run, info in self.RunInfos.iteritems():
            if self.Selection[run]:
                dic[run] = info
        return dic

    def change_runinfo_key(self):
        f, runinfo = self.get_sorted_runinfo()
        runs = self.get_selected_runs()
        keys = sorted(str(key) for key in runinfo[str(runs[0])])
        print keys
        change_key = raw_input('Enter the key you want to change: ')
        assert change_key in keys, 'The entered key does not exist!'
        print 'old values:'
        for run in runs:
            print '{run}:  {value}'.format(run=run, value=runinfo[str(run)][change_key])
        change_value = raw_input('Enter the new value: ')
        for run in runs:
            runinfo[str(run)][change_key] = float(change_value) if isfloat(change_value) else change_value.strip('\'\"')
        self.save_runinfo(f, runinfo)
        self.RunInfos = self.load_run_infos()

    def add_runinfo_key(self):
        runs = self.get_selected_runs()
        f, runinfo = self.get_sorted_runinfo()
        new_key = raw_input('Enter the key you want to add: ')
        new_value = raw_input('Enter the new value: ')
        for run in runs:
            runinfo[str(run)][new_key] = float(new_value) if isfloat(new_value) else new_value
        self.save_runinfo(f, runinfo)
        self.RunInfos = self.load_run_infos()

    def add_runinfo_attenuators(self):
        runs = self.get_selected_runs()
        f, runinfo = self.get_sorted_runinfo()
        for key in ['att_dia1', 'att_dia2', 'att_pul1', 'att_pul2']:
            value = raw_input('Enter the value for {k}: '.format(k=key))
            for run in runs:
                runinfo[str(run)][key] = value
        self.save_runinfo(f, runinfo)
        self.RunInfos = self.load_run_infos()

    def add_n_entries(self):
        f, runinfo = self.get_sorted_runinfo()
        self.start_pbar(len(self.RunInfos))
        for i, run in enumerate(self.RunInfos, 1):
            self.Run.Converter.set_run(run)
            file_path = z.Run.Converter.get_final_file_path()
            if file_exists(file_path):
                root_file = TFile(z.Run.Converter.get_final_file_path())
                runinfo[str(run)]['events'] = int(root_file.Get(self.Run.treename).GetEntries())
            self.ProgressBar.update(i)
        self.ProgressBar.finish()
        self.save_runinfo(f, runinfo)
        self.RunInfos = self.load_run_infos()

    def remove_runinfo_key(self):
        runs = self.get_selected_runs()
        f, runinfo = self.get_sorted_runinfo()
        pop_key = raw_input('Enter the key you want to remove: ')
        for run in runs:
            runinfo[str(run)].pop(pop_key)
        self.save_runinfo(f, runinfo)

    def get_sorted_runinfo(self):
        f = open(self.Run.runinfofile, 'r+')
        runinfo = load(f)
        sorted_runinfo = OrderedDict(sorted(runinfo.items(), key=lambda t: int(t[0])))
        return f, sorted_runinfo

    def get_final_file_path(self, run_number):
        self.Run.reload_run_config(run_number)
        root_file_dir = join('root', '{dut}'.format(dut='pads' if self.Run.load_dut_type() == 'pad' else 'pixel'))
        return join(self.DataDir, self.TCDir, root_file_dir, 'TrackedRun{run:03d}.root'.format(run=run_number))

    @staticmethod
    def save_runinfo(f, runinfo):
        f.seek(0)
        dic = OrderedDict(sorted(runinfo.iteritems(), key=lambda (key, v): (int(key), v)))
        for run, value in dic.iteritems():
            dic[run] = OrderedDict(sorted(value.iteritems()))
        dump(dic, f, indent=2)
        f.truncate()
        f.close()

    def add_irradiation(self):
        f = open(self.Run.IrradiationFile, 'r+')
        data = load(f)
        tc_str = self.generate_tc_str()
        if tc_str in data:
            self.log_info('The information of the testcampaign {tc} was already entered!'.format(tc=tc_str))
            return
        data[tc_str] = {}
        for dia in self.get_diamond_names():
            data[tc_str][dia] = raw_input('Enter the irradtion for the diamond {d} (e.g. 4e15): '.format(d=dia))
        f.seek(0)
        dump(data, f, indent=2, sort_keys=True)
        f.truncate()
        f.close()

    def get_irradiation(self, dia=None):
        f = open(self.Run.IrradiationFile, 'r')
        irr = load(f)[self.generate_tc_str()][self.SelectedDiamond if self.SelectedDiamond is not None and dia is None else dia]
        f.close()
        return irr

    def get_runplan_runs(self):
        return sorted(list(set(run for dic in self.RunPlan.itervalues() for run in dic['runs'])))

    def remove_redundant_raw_files(self):
        run_plan_runs = self.get_runplan_runs()
        for file_path in sorted(glob(join(self.Run.Converter.RawFileDir, 'run0*'))):
            run = int(remove_letters(basename(file_path)))
            if run not in run_plan_runs:
                log_warning('removing {}'.format(file_path))
                remove(file_path)

    def remove_tracked_files(self, sel=False):
        selected_runs = self.get_selected_runs() if sel else []
        for run in self.get_runplan_runs():
            if sel and run not in selected_runs:
                continue
            self.Run.Converter.set_run(run)
            self.Run.Converter.remove_final_file()

    def copy_raw_files(self, sel=False):
        selected_runs = self.get_selected_runs() if sel else []
        for run in self.get_runplan_runs():
            if sel and run not in selected_runs:
                continue
            self.Run.Converter.set_run(run)
            self.Run.Converter.copy_raw_file()

    def backup_to_isg(self):
        backup_path = join('isg:', 'home', 'ipp', self.TCDir)
        system('rsync -aPv {} {}'.format(join(self.DataDir, self.TCDir, 'run_log.json'), backup_path))
        system('rsync -aPv {} {}'.format(join(self.DataDir, self.TCDir, 'HV*'), backup_path))
        system('rsync -aPv {} {}'.format(join(self.DataDir, self.TCDir, 'root', 'pads', 'TrackedRun*'), join(backup_path, 'root', 'pads')))
        system('rsync -aPv {} {}'.format(join(self.DataDir, self.TCDir, 'root', 'pixel', 'TrackedRun*'), join(backup_path, 'root', 'pixel')))


def verify(msg):
    for n in xrange(3):
        prompt = raw_input('{0} (y/n)? '.format(msg))
        if prompt.lower() in ['yes', 'ja', 'y', 'j']:
            return True
        elif prompt.lower() in ['no', 'n']:
            return False
    raise ValueError('Are you too stupid to say yes or no??')


if __name__ == '__main__':

    p = ArgumentParser(description='RunSelection tool group runs together and display information')

    p.add_argument('-tc', '--testcampaign', default=None, help='TestCampaign')
    p.add_argument('-s', '--show', action='store_true', help='activate show')
    p.add_argument('-ms', '--master_selection', action='store_true', help='run master selection')
    p.add_argument('RunPlan', nargs='?', help='Displays the deltailed overview about a single scan', type=str, default=None)
    p.add_argument('-d', '--dia', type=str, default=None, help='diamond name')
    args = p.parse_args()

    z = RunSelection(testcampaign=args.testcampaign)
    if args.show:
        if args.RunPlan is not None:
            z.print_testcampaign()
            z.select_runs_from_runplan(args.RunPlan)
            z.show_selected_runs()
        else:
            z.show_run_plans(diamond=args.dia)

    if args.master_selection:
        z.master_selection()