#!/usr/bin/env python
# --------------------------------------------------------
#       Class to draw the info legend for an analysis class
# created on Jan 30th 2018 by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------

from os import chdir
from subprocess import check_output
from ROOT import gROOT, TLegend
from helpers.draw import Draw, make_tc_str, timedelta, make_flux_string, make_irr_string


class InfoLegend(object):
    def __init__(self, analysis=None):
        self.Analysis = analysis
        self.ShowGit = analysis.MainConfig.getboolean('SAVE', 'git hash')
        self.ShowInfo = analysis.MainConfig.getboolean('SAVE', 'info legend')
        self.IsCollection = hasattr(analysis, 'Analyses')
        self.HasDUT = hasattr(analysis, 'DUT')

        self.Objects = []

    def is_active(self):
        return hasattr(self.Analysis, 'Run')

    def draw(self, canvas=None, all_pads=True, show=True):
        """
        Draws the run infos inside the canvas. If no canvas is given, it will be drawn into the active Pad.
        :param all_pads: draw info legends in all subpads or just the provided canvas
        :return: [run info legend, git text]
        """
        if not self.is_active():
            return
        if canvas is not None:
            canvas.cd()
            if show and canvas.GetBottomMargin() < .105 and self.ShowInfo:
                canvas.SetBottomMargin(0.15)
        else:
            canvas = gROOT.GetSelectedPad()
            if not canvas:
                self.Analysis.warning('Cannot access an active Pad')
                return

        run_str = self.get_run_string()
        info_str = self.get_info_string()
        # width = len(run_str) * min(canvas.GetWw(), canvas.GetWh()) * .01
        # if canvas.GetWw() > canvas.GetWh():
        width = float(max(len(run_str), len(info_str))) / canvas.GetWw() * Draw.Res / 1000 * 10.5
        legend = Draw.make_legend(.005, .1, y1=.003, x2=width, nentries=3, clean=False, scale=.75, margin=.05)

        legend.AddEntry(0, run_str, '')                         # Run String
        legend.AddEntry(0, self.get_dia_string(), '')  # Detector and Test Campaign
        legend.AddEntry(0, info_str, '')                        # Info String (bias, attenuator, irr)

        git_text = self.make_git_text()

        self.Objects.append([legend, git_text])

        if show:
            pads = [i for i in canvas.GetListOfPrimitives() if i.IsA().GetName() == 'TPad'] if all_pads else [canvas]
            pads = [canvas] if not pads else pads
            for pad in pads:
                pad.cd()
                if self.ShowGit:
                    git_text.Draw()
                if self.ShowInfo:
                    legend.Draw()
                pad.Modified()
            canvas.Update()
        return legend, git_text

    def get(self, canvas=None):
        return self.draw(canvas, show=False)

    @staticmethod
    def make_git_text():
        chdir(Draw.Dir)
        txt = 'git hash: {ver}'.format(ver=check_output(['git', 'describe', '--always']).decode('utf-8').strip('\n'))
        return Draw.tlatex(.9, .02, txt, show=False, ndc=True, size=.02)

    def get_duration(self):
        dur = sum([ana.Run.Duration for ana in list(self.Analysis.Analyses.values())], timedelta()) if self.IsCollection else self.Analysis.Run.Duration
        return dur - timedelta(microseconds=dur.microseconds)

    def get_run_string(self):
        run_str = 'Run{run}: {rate}, {dur}'.format(run=self.get_runnumber_str(), rate=self.get_rate_string(), dur=self.get_duration())
        run_str += '' if self.IsCollection else ' ({} evts)'.format(self.Analysis.Run.NEvents)
        return run_str

    def get_runnumber_str(self):
        return 's {}-{}'.format(self.Analysis.Runs[0], self.Analysis.Runs[-1]) if self.IsCollection else ' {}'.format(self.Analysis.Run.Number)

    def get_dia_string(self):
        dia_str = self.Analysis.DUT.Name if self.HasDUT else ', '.join(dut.Name for dut in self.Analysis.Run.DUTs)
        return 'Detector{b}: {d} ({tc})'.format(b='' if self.HasDUT else 's', tc=make_tc_str(self.Analysis.TCString), d=dia_str)

    def get_rate_string(self):
        if self.IsCollection:
            fluxes = [flux.n for flux in self.Analysis.get_fluxes(pbar=False)]
            return '{} - {}'.format(make_flux_string(min(fluxes)), make_flux_string(max(fluxes)))
        else:
            return make_flux_string(self.Analysis.Run.Flux.n)

    def get_info_string(self):
        voltage = '{0:+4.0f}V'.format(self.Analysis.DUT.Bias) if self.HasDUT else '/'.join('{0:+4.0f}V'.format(dut.Bias) for dut in self.Analysis.Run.DUTs)
        irradiation = make_irr_string(self.Analysis.get_irradiation()) if self.HasDUT else '/'.join(make_irr_string(dut.get_irradiation(self.Analysis.TCString)) for dut in self.Analysis.Run.DUTs)
        attenuator = 'Att: {}'.format(str(self.Analysis.DUT.Attenuator)) if self.HasDUT and self.Analysis.get_attenuator() else ''
        return 'Info: {v}, {i}{a}'.format(v=voltage, i=irradiation, a=', {}'.format(attenuator) if attenuator else '')
