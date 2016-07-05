# ==============================================
# IMPORTS
# ==============================================
from argparse import ArgumentParser
from collections import OrderedDict
from copy import deepcopy
from math import ceil, log
from numpy import array
from sys import stdout
from time import time, sleep

from ROOT import TGraphErrors, TCanvas, TH2D, gStyle, TH1F, gROOT, TLegend, TCut, TGraph, TProfile2D, TH2F, TProfile, TCutG, kGreen, TF1, TPie,\
    THStack, TArrow, kOrange, TSpectrum, gRandom, TMultiGraph

from ChannelCut import ChannelCut
from CurrentInfo import Currents
from Elementary import Elementary
from Extrema import Extrema2D
from TelescopeAnalysis import Analysis
from Pulser import PulserAnalysis
from Utils import *

__author__ = 'micha'


# ==============================================
# MAIN CLASS
# ==============================================
class PadAnalysis(Analysis):
    def __init__(self, run, channel, high_low_rate_run=None, binning=20000, verbose=False):

        self.channel = channel
        self.RunNumber = run
        Analysis.__init__(self, run, high_low_rate=high_low_rate_run, verbose=verbose)

        # main
        self.diamond_name = self.run.diamond_names[channel]
        self.bias = self.run.bias[channel]
        self.save_dir = '{dia}/{run}/'.format(run=str(self.run_number).zfill(3), dia=self.diamond_name)

        # stuff
        self.BinSize = binning
        self.binning = self.__get_binning()
        self.time_binning = self.get_time_binning()
        self.n_bins = len(self.binning)
        self.Polarity = self.get_polarity()
        self.PulserPolarity = self.get_pulser_polarity()

        # regions // ranges
        self.IntegralNames = self.get_integral_names()
        self.SignalRegion = self.__load_signal_region()
        self.PedestalRegion = self.__load_pedestal_region()
        self.PeakIntegral = self.__load_peak_integral()

        # names
        self.SignalDefinition = '({pol}*TimeIntegralValues[{num}])'
        self.SignalNumber = self.get_signal_number()
        self.SignalName = self.get_signal_name()
        self.PedestalName = self.get_pedestal_name()
        self.PulserName = self.get_pulser_name()

        # cuts
        self.Cut = ChannelCut(self, channel)
        self.AllCuts = self.Cut.all_cut

        # currents
        self.Currents = Currents(self)

        # graphs
        self.PulseHeight = None
        self.Pedestal = None
        # histograms
        self.PedestalHisto = None
        self.SignalTime = None
        self.SignalMapHisto = None
        self.MeanSignalHisto = None
        self.PeakValues = None

        self.Pulser = PulserAnalysis(self)

    def __del__(self):
        for obj in [self.PulseHeight, self.Pedestal, self.SignalMapHisto, self.SignalTime, self.PeakValues, self.MeanSignalHisto]:
            self.del_rootobj(obj)
        for c in gROOT.GetListOfCanvases():
            c.Close()
        for lst in self.histos + self.RootObjects:
            if not type(lst) is list:
                lst = [lst]
            for obj in lst:
                self.del_rootobj(obj)

    def show_current(self, relative_time=True):
        # todo: write a new function for that ;)
        pass

    # ==========================================================================
    # region INIT

    # overriding elementary method to choose config by run number
    def load_run_config(self):
        return self.load_run_configs(self.RunNumber)

    def get_integral_names(self):
        names = OrderedDict()
        self.tree.GetEntry(0)
        for i, name in enumerate(self.tree.IntegralNames):
            names[name] = i
        return names

    def get_polarity(self):
        self.tree.GetEntry(0)
        return self.tree.polarities[self.channel]

    def get_pulser_polarity(self):
        self.tree.GetEntry(0)
        return self.tree.pulser_polarities[self.channel]

    def __load_signal_region(self):
        sig_region = self.ana_config_parser.get('BASIC', 'signal_region')
        return sig_region if sig_region in self.run.signal_regions else self.run.signal_regions.keys()[0]

    def __load_pedestal_region(self):
        ped_region = self.ana_config_parser.get('BASIC', 'pedestal_region')
        return ped_region if ped_region in self.run.pedestal_regions else self.run.pedestal_regions.keys()[0]

    def __load_peak_integral(self):
        peak_int = self.ana_config_parser.get('BASIC', 'peak_integral')
        return peak_int if peak_int in self.run.peak_integrals else self.run.peak_integrals.keys()[0]

    def get_signal_number(self, region=None, peak_integral=None, sig_type='signal'):
        this_region = self.SignalRegion if sig_type == 'signal' else self.PedestalRegion
        region = this_region if region is None else region
        peak_integral = self.PeakIntegral if peak_integral is None else peak_integral
        assert sig_type in ['signal', 'pedestal', 'pulser'], 'Invalid type of signal'
        if sig_type != 'pulser':
            assert region in self.run.signal_regions or region in self.run.pedestal_regions, 'Invalid {typ} region: {reg}!'.format(reg=region, typ=sig_type)
        assert str(peak_integral) in self.run.peak_integrals, 'Invalid peak integral {reg}!'.format(reg=peak_integral)
        int_name = 'ch{ch}_{type}{reg}_PeakIntegral{int}'.format(ch=self.channel, reg='_' + region if region else '', int=peak_integral, type=sig_type)
        return self.IntegralNames[int_name]

    def get_signal_name(self, region=None, peak_integral=None, sig_type='signal'):
        num = self.get_signal_number(region, peak_integral, sig_type)
        return self.SignalDefinition.format(pol=self.Polarity, num=num)

    def set_signal_definitions(self, use_time=True, sig_region=None, ped_region=None, peak_int=None):
        signal = 'TimeIntegralValues' if use_time else 'IntegralValues'
        signal = '({{pol}}*{sig}[{{num}}])'.format(sig=signal)
        print 'changed SignalDefinition to:', signal
        self.SignalDefinition = signal
        self.update_signal_definitions(sig_region, ped_region, peak_int)

    def update_signal_definitions(self, sig_region=None, ped_region=None, peak_int=None):
        self.SignalNumber = self.get_signal_number(sig_region, peak_int)
        self.SignalName = self.get_signal_name(sig_region, peak_int)
        self.PedestalName = self.get_pedestal_name(ped_region, peak_int)
        self.PulserName = self.get_pulser_name()

    def get_pedestal_name(self, region=None, peak_int=None):
        return self.get_signal_name(region=region, peak_integral=peak_int, sig_type='pedestal')

    def get_pulser_name(self, peak_int=None):
        num = self.get_signal_number('', peak_int, 'pulser')
        return self.SignalDefinition.format(pol=self.PulserPolarity, num=num)
    # endregion

    def set_channel(self, ch):
        self.channel = ch
        self.diamond_name = self.run.diamondname[ch]
        self.bias = self.run.bias[ch]
        self.Cut = ChannelCut(self, ch)
        self.save_dir = '{tc}_{run}_{dia}'.format(tc=self.TESTCAMPAIGN[2:], run=self.run_number, dia=self.run.diamondname[ch])
        self.Polarity = self.get_polarity()
        self.SignalName = self.get_signal_name()
        self.PedestalName = self.get_pedestal_name()

    def __set_bin_size(self, value):
        self.BinSize = value
        self.binning = self.__get_binning()
        self.time_binning = self.get_time_binning()
        self.n_bins = len(self.binning)
        return value

    # ==========================================================================
    # region BEAM PROFILE

    def draw_beam_profile(self, mode='x', show=True, fit=True, fit_margin=.6):
        assert mode.lower() in ['x', 'y'], 'Mode has to be either "x" or "y"!'
        margins = self.find_diamond_margins(show_plot=False, make_histo=True)
        h = deepcopy(self.histos[-1])
        if not show:
            gROOT.SetBatch(1)
        prof = h.ProjectionX() if mode.lower() == 'x' else h.ProjectionY()
        margins[mode] = [prof.GetBinLowEdge(prof.FindBin(margins[mode][0])), prof.GetBinLowEdge(prof.FindBin(margins[mode][1]) + 1)]
        center = (margins[mode][1] + margins[mode][0]) / 2.
        width = (prof.FindBin(margins[mode][1]) - prof.FindBin(margins[mode][0])) / 2. * fit_margin * prof.GetBinWidth(1)
        fit_range = [center - width, center + width]
        c = TCanvas('c', 'Beam Profile', 1000, 1000)
        c.SetLeftMargin(.145)
        self.format_histo(prof, 'prof', 'Profile ' + mode.title(), y_tit='Entries', y_off=2, x_tit='Track Position {mod} [cm]'.format(mod=mode.title()))
        prof.GetXaxis().SetRangeUser(prof.GetBinCenter(prof.FindFirstBinAbove(0) - 1), prof.GetBinCenter(prof.FindLastBinAbove(0) + 1))
        prof.Draw()
        sleep(.1)
        lines = [self.draw_axis(x, c.GetUymin(), c.GetUymax(), '', 2, 2) for x in margins[mode]]
        fit_result = self.__fit_beam_profile(prof, fit_range, show) if fit else 0
        fits = None
        if fit:
            f1 = gROOT.GetFunction('gaus')
            f2 = deepcopy(f1)
            f2.SetLineColor(2)
            f2.SetLineStyle(1)
            f1.SetLineColor(kGreen + 1)
            f2.SetRange(fit_range[0], fit_range[1])
            f1.SetLineStyle(7)
            f1.Draw('same')
            f2.Draw('same')
            prof.GetXaxis().UnZoom()
            fits = [f1, f2]
        for line in lines:
            line.Draw()
        c.RedrawAxis()
        gROOT.SetBatch(0)
        self.save_plots('BeamProfile{mod}{fit}'.format(mod=mode.title(), fit='Fit' if fit else ''), sub_dir=self.save_dir)
        self.histos.append([prof, c, lines, fits])
        return fit_result if fit else prof

    @staticmethod
    def __fit_beam_profile(histo, fit_range, show=True):
        h = histo
        fit = h.Fit('gaus', 'qs{0}'.format('' if show else '0'), '', fit_range[0], fit_range[1])
        return fit

    def fit_beam_profile(self, mode='x', show=True, fit_margin=.6):
        pickle_path = self.PickleDir + 'BeamProfile/Fit{mod}_{tc}_{run}_{dia}_{mar}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, dia=self.diamond_name, mod=mode.title(), mar=fit_margin)

        def func():
            return self.draw_beam_profile(mode=mode, show=show, fit_margin=fit_margin)

        return self.do_pickle(pickle_path, func)

    def draw_beam_fit_properties(self, show=True, mode='x', sigma=True):
        if not show:
            gROOT.SetBatch(1)
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        gr = self.make_tgrapherrors('gr', 'Beam Profile {0} {mod}'.format(mode.title(), mod='Fit #chi^{2}s / NDF' if not sigma else 'Sigma'))
        max_range = 11 if sigma else 10
        index = 0
        for i in xrange(1, max_range):
            perc = i / 10.
            fit = self.fit_beam_profile(mode=mode, show=False, fit_margin=perc)
            if fit.Ndf():
                y = fit.Parameter(2) if sigma else fit.Chi2() / fit.Ndf()
                gr.SetPoint(index, perc * 100, y)
                t = self.draw_tlatex(perc * 100 - 2, y, str(fit.Ndf()), color=807, size=.04, align=32)
                gr.GetListOfFunctions().Add(t)
                index += 1
        c = TCanvas('c', 'Beam Chi2', 1000, 1000)
        self.format_histo(gr, x_tit='Range [%]', y_tit='#chi^{2} / NDF' if not sigma else 'Sigma', y_off=1.4)
        one = TF1('one', '1', 0, 100)
        t1 = self.draw_tlatex(15, .95 * gr.GetYaxis().GetXmax(), 'NDF:', color=807, size=0.04, align=12)
        gr.GetListOfFunctions().Add(t1)
        gr.GetXaxis().SetRangeUser(-5, 105)
        gr.Draw('alp')
        one.Draw('same')

        self.histos.append([gr, c, t1])
        gROOT.SetBatch(0)
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
        self.save_plots('BeamProf{mod}{dir}'.format(mod='Sigmas' if sigma else 'Chi2s', dir=mode.title()), sub_dir=self.save_dir)

    # endregion

    # ==========================================================================
    # region 2D SIGNAL DISTRIBUTION
    def draw_signal_map(self, draw_option='surf3z', show=True, factor=1.5):
        margins = self.find_diamond_margins(show_plot=False)
        x = [margins['x'][0], margins['x'][1]]
        y = [margins['y'][0], margins['y'][1]]
        nr = 1 if not self.channel else 2
        # get bin size via digital resolution of the telescope pixels
        x_bins = int(ceil(((x[1] - x[0]) / 0.015 * sqrt(12) / factor)))
        y_bins = int(ceil((y[1] - y[0]) / 0.01 * sqrt(12) / factor))
        h = TProfile2D('signal_map', 'Signal Map', x_bins, x[0], x[1], y_bins, y[0], y[1])
        signal = '{sig}-{pol}*{ped}'.format(sig=self.SignalName, ped=self.PedestalName, pol=self.Polarity)
        print 'drawing signal map of {dia} for Run {run}...'.format(dia=self.diamond_name, run=self.run_number)
        self.tree.Draw('{z}:diam{nr}_track_y:diam{nr}_track_x>>signal_map'.format(z=signal, nr=nr), self.Cut.all_cut, 'goff')
        gStyle.SetPalette(53)
        is_surf = draw_option.lower().startswith('surf')
        self.format_histo(h, x_tit='track_x [cm]', y_tit='track_y [cm]', y_off=1.4, z_off=1.3, stats=0, z_tit='Pulse Height [au]')
        if is_surf:
            self.format_histo(h, x_off=2, y_off=2.4, x_tit='track_x [cm]', y_tit='track_y [cm]', stats=0)
        h.GetXaxis().SetNdivisions(5)
        h.SetContour(50)
        self.RootObjects.append(self.save_histo(h, 'SignalMap2D{0}'.format(draw_option.title()), show, lm=.12, rm=.16 if not is_surf else .12, draw_opt=draw_option))
        self.SignalMapHisto = h
        return h

    def make_region_cut(self):
        self.draw_mean_signal_distribution(show=False)
        return self.Cut.generate_region(self.SignalMapHisto, self.MeanSignalHisto)

    def find_2d_regions(self):
        self.draw_mean_signal_distribution(show=False)
        extrema = Extrema2D(self.SignalMapHisto, self.MeanSignalHisto)
        extrema.clear_voting_histos()
        extrema.region_scan()
        extrema.show_voting_histos()
        self.save_plots('Regions2D', sub_dir=self.save_dir)
        return extrema

    def find_2d_extrema(self, size=1, histo=None, show=True):
        self.draw_mean_signal_distribution(show=False)
        extrema = Extrema2D(self.SignalMapHisto, self.MeanSignalHisto)
        extrema.clear_voting_histos()
        extrema.square_scan(size, histo)
        if show:
            extrema.show_voting_histos()
        self.save_plots('Extrema2D', sub_dir=self.save_dir)
        return extrema

    def draw_mean_signal_distribution(self, show=True):
        """
        Draws the distribution of the mean pulse height values of the bins from the signal map
        :param show: shows a plot of the canvas if True
        """
        # todo: save mean
        sig_map = self.SignalMapHisto if self.SignalMapHisto is not None else self.draw_signal_map(show=False)
        x = [int(sig_map.GetMinimum()) / 10 * 10, int(sig_map.GetMaximum() + 10) / 10 * 10]
        h = TH1F('h', 'Mean Signal Distribution', 50, x[0], x[1])
        for bin_ in xrange((sig_map.GetNbinsX() + 2) * (sig_map.GetNbinsY() + 2)):
            h.Fill(sig_map.GetBinContent(bin_))
        gStyle.SetEndErrorSize(4)
        gr1 = self.make_tgrapherrors('gr', 'errors', width=3, marker_size=0, color=kGreen + 2)
        gr2 = self.make_tgrapherrors('gr', 'errors', width=3, marker_size=0, color=2)
        gr1.SetPoint(0, h.GetXaxis().GetXmin() + 5, h.GetMaximum() - 2)
        gr2.SetPoint(0, h.GetXaxis().GetXmin() + 5, h.GetMaximum() - 2)
        errors = self.SignalMapHisto.ProjectionXY('', 'c=e')
        gr1.SetPointError(0, errors.GetMinimum(), 0)
        gr2.SetPointError(0, errors.GetMaximum(), 0)
        l = self.draw_tlatex(gr1.GetX()[0], gr1.GetY()[0] + 0.5, 'Errors', align=20, size=0.03)
        gr1.GetListOfFunctions().Add(l)
        if show:
            c = TCanvas('c', 'Mean Signal Distribution', 1000, 1000)
            self.format_histo(h, x_tit='Pulse Height [au]', y_tit='Entries', y_off=1.2)
            h.Draw()
            gr2.Draw('[]')
            gr1.Draw('[]')
            gr2.Draw('p')
            gr1.Draw('p')
            self.save_plots('MeanSignalHisto', sub_dir=self.save_dir)
            self.histos.append([gr1, gr2, c])
        self.MeanSignalHisto = h

    def draw_error_signal_map(self, show=False):
        self.draw_mean_signal_distribution(show=False)
        h = self.SignalMapHisto.ProjectionXY('', 'c=e')
        if show:
            c = TCanvas('c', 'Signal Map Errors', 1000, 1000)
            c.SetLeftMargin(0.12)
            c.SetRightMargin(0.11)
            self.format_histo(h, name='sig_map_errors', title='Signal Map Errors', x_tit='track_x [cm]', y_tit='track_y [cm]', y_off=1.6)
            h.SetStats(0)
            h.Draw('colz')
            self.save_plots('SignalMapErrors', sub_dir=self.save_dir, canvas=c)
            self.histos.append([h, c])
        return h

    def fit_mean_signal_distribution(self):
        pickle_path = self.PickleDir + 'MeanSignalFit/{tc}_{run}_{dia}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, dia=self.diamond_name)

        def func():
            self.draw_mean_signal_distribution(show=False)
            return self.MeanSignalHisto.Fit('gaus', 'qs')

        fit = self.do_pickle(pickle_path, func)
        return fit

    def get_mean_fwhm(self):
        fit = self.fit_mean_signal_distribution()
        conversion_factor = 2 * sqrt(2 * log(2))  # sigma to FWHM
        return fit.Parameter(2) * conversion_factor

    def draw_diamond_hitmap(self, cut=None, show_frame=True):
        self.find_diamond_margins(show_frame=show_frame, cut=cut)

    def find_diamond_margins(self, show_plot=True, show_frame=False, cut=None, make_histo=False):
        pickle_path = self.PickleDir + 'Margins/{tc}_{run}_{dia}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, dia=self.diamond_name)

        def func():
            print 'getting margins for {dia} of run {run}...'.format(dia=self.diamond_name, run=self.run_number)
            cut_string = self.Cut.all_cut if cut is None else cut
            if not show_plot:
                gROOT.SetBatch(1)
            h = TH2F('h', 'Diamond Margins', 52, -.4, .4, 80, -.4, .4)
            nr = 1 if not self.channel else 2
            self.tree.Draw('diam{nr}_track_y:diam{nr}_track_x>>h'.format(nr=nr), cut_string, 'goff')
            projections = [h.ProjectionX(), h.ProjectionY()]
            efficient_bins = [[], []]
            zero_bins = [[], []]
            bin_low = [[], []]
            bin_high = [[], []]
            for i, proj in enumerate(projections):
                last_bin = None
                for bin_ in xrange(proj.GetNbinsX()):
                    efficiency = proj.GetBinContent(bin_) / float(proj.GetMaximum())
                    if efficiency > .3:
                        efficient_bins[i].append(proj.GetBinCenter(bin_))
                        bin_low[i].append(proj.GetBinLowEdge(bin_))
                        bin_high[i].append(proj.GetBinLowEdge(bin_ + 1))
                    if bin_ > 1:
                        if efficiency and not last_bin:
                            zero_bins[i].append(proj.GetBinCenter(bin_ - 1))
                        elif not efficiency and last_bin:
                            zero_bins[i].append((proj.GetBinCenter(bin_)))
                    last_bin = proj.GetBinContent(bin_)
            if show_plot:
                c = TCanvas('c', 'Diamond Hit Map', 1000, 1000)
                c.SetRightMargin(.14)
                c.SetBottomMargin(.15)
                h.GetXaxis().SetRangeUser(zero_bins[0][0], zero_bins[0][1])
                h.GetYaxis().SetRangeUser(zero_bins[1][0], zero_bins[1][1])
                h.SetStats(0)
                h.Draw('colz')
                if show_frame:
                    self.__show_frame(bin_low, bin_high)
                self.save_plots('DiamondHitmap', sub_dir=self.save_dir)
            self.histos.append(h)
            gROOT.SetBatch(0)
            return {name: [efficient_bins[i][0], efficient_bins[i][-1]] for i, name in enumerate(['x', 'y'])}

        margins = func() if show_plot or make_histo else None
        return self.do_pickle(pickle_path, func, margins)

    def __show_frame(self, bin_low, bin_high):
        frame = TCutG('frame', 4)
        frame.SetLineColor(2)
        frame.SetLineWidth(4)
        frame.SetVarX('x')
        frame.SetVarY('y')
        frame.SetPoint(0, bin_low[0][0], bin_low[1][0])
        frame.SetPoint(1, bin_high[0][-1], bin_low[1][0])
        frame.SetPoint(2, bin_high[0][-1], bin_high[1][-1])
        frame.SetPoint(3, bin_low[0][0], bin_high[1][-1])
        frame.SetPoint(4, bin_low[0][0], bin_low[1][0])
        frame.Draw('same')
        self.histos.append(frame)

    def calc_signal_spread(self, min_percent=5, max_percent=99):
        """
        Calculates the relative spread of mean signal response from the 2D signal response map.
        :param min_percent: min quantile
        :param max_percent: max quantile
        :return: relative spread [%]
        """
        if self.MeanSignalHisto is None:
            self.draw_mean_signal_distribution(show=False)
        q = array([min_percent / 100., max_percent / 100.])
        y = array([0., 0.])
        self.MeanSignalHisto.GetQuantiles(2, y, q)
        max_min_ratio = (y[1] / y[0] - 1) * 100
        delta_y = self.draw_error_signal_map(show=False).GetMinimum()
        # error propagation
        err = 100 * delta_y / y[0] * (1 + y[1] / y[0])
        print 'Relative Signal Spread is: {spr} +- {err}'.format(spr=max_min_ratio, err=err)
        return [max_min_ratio, err]

    # endregion

    # ==========================================================================
    # region SIGNAL PEAK POSITION
    def draw_peak_timing(self, region=None, type_='signal', show=True, ucut=None, corr=True, draw_cut=True):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        num = self.SignalNumber if region is None else self.get_signal_number(region=region, sig_type=type_)
        region = self.SignalRegion if region is None else region
        peak_val = 'IntegralPeaks[{num}]'.format(num=num) if not corr else 'IntegralPeakTime[{num}]'.format(num=num)
        title = '{typ} Peak Positions'.format(typ=type_.title())
        x = self.run.signal_regions[region] if type_ == 'signal' else self.run.get_regions('pulser')['pulser']
        n_bins = (x[1] - x[0]) * 4 if corr else (x[1] - x[0])
        h = TH1F('hpv', title, n_bins, x[0] / 2., x[1] / 2.)
        l = self.make_legend(.7, .7, nentries=3)
        self.format_histo(h, x_tit='Signal Peak Timing [ns]', y_tit='Number of Entries', y_off=1.3, stats=0)
        cut = self.Cut.generate_special_cut(excluded_cuts=['timing']) if type_ == 'signal' else '!({0})'.format(self.Cut.CutStrings['pulser'])
        cut = cut if ucut is None else ucut
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
        dic = self.Cut.calc_timing_range(show=False)
        t_correction = '({p1}* trigger_cell + {p2} * trigger_cell*trigger_cell)'.format(p1=dic['t_corr'].GetParameter(1), p2=dic['t_corr'].GetParameter(2))
        draw_string = '{peaks}{op}>>hpv'.format(peaks=peak_val, op='/2.' if not corr else '-' + t_correction)
        self.tree.Draw(draw_string, cut, 'goff')
        self.draw_histo(h, show=show, sub_dir=self.save_dir, lm=.12, logy=True)
        f, fit, fit1 = self.fit_peak_timing(h)
        l2 = self.make_legend(.66, .96, nentries=3, name='fr', margin=.05, felix=False)
        l2.SetHeader('Fit Results')
        l2.AddEntry(0, 'Mean:', '')
        l2.AddEntry(0, '{0:5.2f} #pm {1:5.2f} ns'.format(f.Parameter(1), f.ParError(1)), '').SetTextAlign(32)
        l2.AddEntry(0, 'Sigma:', '')
        l2.AddEntry(0, '{0:5.2f} #pm {1:5.2f} ns'.format(f.Parameter(2), f.ParError(2)), '').SetTextAlign(32)
        l2.SetNColumns(2)
        if draw_cut:
            g = self.__draw_timing_cut()
            l.AddEntry(g, 'Timing Cut', 'fl')
        l.AddEntry(fit1, 'Fitting Range', 'l')
        l.AddEntry(fit, 'Fit Function', 'l')
        l.Draw()
        l2.Draw()
        l2.GetListOfPrimitives().First().SetTextAlign(22)
        h.Draw('same')
        h.GetXaxis().SetRangeUser(f.Parameter(1) - 10 * f.Parameter(2), h.GetXaxis().GetXmax())
        self.save_plots('{typ}PeakPositions'.format(typ=type_.title()))
        self.PeakValues = h
        self.RootObjects.append([l, l2])
        return f

    def __draw_timing_cut(self):
        timing_fit = self.Cut.calc_timing_range(show=False)['timing_corr']
        xmin, xmax = timing_fit.GetParameter(1) - 3 * timing_fit.GetParameter(2), timing_fit.GetParameter(1) + 3 * timing_fit.GetParameter(2)
        g = TCutG('timing', 5)
        g.SetVarX('y')
        g.SetVarY('x')
        ymin, ymax = -10, 1e7
        for i, (x, y) in enumerate([(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]):
            g.SetPoint(i, x, y)
        g.SetLineColor(827)
        g.SetLineWidth(2)
        g.SetFillColor(827)
        g.SetFillStyle(3001)
        g.Draw('f')
        g.Draw('l')
        self.RootObjects.append(g)
        return g

    def fit_peak_timing(self, histo):
        h = histo
        fit1 = h.Fit('gaus', 'qs0')
        mean_, sigma = fit1.Parameter(1), fit1.Parameter(2)
        fit = h.Fit('gaus', 'qs', '', mean_ - sigma, mean_ + sigma)
        fit2 = TF1('f1', 'gaus', mean_ - 5 * sigma, mean_ + 5 * sigma)
        fit3 = TF1('f2', 'gaus', mean_ - sigma, mean_ + sigma)
        pars = [fit.Parameter(i) for i in xrange(3)]
        fit2.SetParameters(*pars)
        fit3.SetParameters(*pars)
        fit3.SetLineWidth(2)
        fit3.SetLineColor(2)
        fit2.SetLineStyle(2)
        fit2.Draw('same')
        self.RootObjects.append([fit2, fit3])
        return fit, fit2, fit3

    def draw_peak_timings(self, show=True):
        h = TH1F('h_pt', 'Peak Timings', 1024, 0, 512)
        self.tree.Draw('peaks{ch}_x_time>>h_pt'.format(ch=self.channel), self.AllCuts, 'goff')
        self.format_histo(h, x_tit='Time [ns]', y_tit='Number of Entries', y_off=.4, fill_color=836, lw=2, tit_size=.05, stats=0)
        self.histos.append(self.save_histo(h, 'PeakTimings', show, self.save_dir, logy=True, lm=.045, rm=.045, x_fac=4, y_fac=.5))

    def draw_n_peaks(self, show=True, p1=0.7, p2=1):
        h = TH1F('h_pn', 'Number of Peaks', 12, -.5, 11.5)
        h1 = TH1F('h_pn1', 'Number of Peaks', 12, -.5, 11.5)
        self.tree.Draw('@peaks{ch}_x.size()>>h_pn'.format(ch=self.channel), self.AllCuts, 'goff')
        self.format_histo(h, x_tit='number of peaks', y_tit='number of entries', y_off=1.5, fill_color=836, lw=2)
        h.SetFillStyle(3004)
        self.histos.append(self.save_histo(h, 'PeakNumbers', show, self.save_dir, logy=True))
        while h1.GetBinContent(2) != h.GetBinContent(2):
            h1.Fill(gRandom.Poisson(24 * self.get_flux() / 5e4 * .5 * .5 * p2) + gRandom.Binomial(1, p1))
        self.format_histo(h1, x_tit='number of peaks', y_tit='Number of Entries', y_off=1.5, fill_color=896, lw=2)
        h1.SetFillStyle(3005)
        h1.Draw('same')
        self.histos.append(h1)

    def calc_peak_value_fwhm(self):
        pickle_path = self.PickleDir + 'PeakValues/FWHM_{tc}_{run}_{dia}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, dia=self.diamond_name)

        def func():
            print 'Getting peak value FWHM for {dia} of run {run}...'.format(run=self.run_number, dia=self.diamond_name)
            if self.PeakValues is None:
                self.draw_peak_timing(show=False)
            return self.calc_fwhm(self.PeakValues)

        fwhm = self.do_pickle(pickle_path, func)
        return fwhm

    def draw_forc_times(self, show=True, corr=False):
        self.tree.Draw('forc_pos', 'forc_pos[0]>20', 'goff')
        htemp = gROOT.FindObject('htemp')
        x = [int(htemp.GetBinCenter(htemp.FindFirstBinAbove(5000))) - 10, int(htemp.GetBinCenter(htemp.FindLastBinAbove(5000))) + 10]
        h = TH1F('ft', 'FORC Timing', x[1] - x[0], x[0] / 2., x[1] / 2.)
        forc = 'forc_pos/2.' if not corr else 'forc_time'
        self.tree.Draw('{forc}>>ft'.format(forc=forc), self.Cut.all_cut, 'goff')
        self.format_histo(h, x_tit='time [ns]', y_tit='Entries', y_off=2, fill_color=17)
        self.histos.append(self.save_histo(h, 'FORCTiming', show, sub_dir=self.save_dir, lm=.14))

    # endregion

    # ==========================================================================
    # region TRIGGER CELL
    def draw_trigger_cell(self, show=True, cut=None):
        h = TH1F('tc', 'Trigger Cell', 1024, 0, 1024)
        cut = self.Cut.all_cut if cut is None else cut
        self.tree.Draw('trigger_cell>>tc', cut, 'goff')
        self.format_histo(h, x_tit='trigger cell', y_tit='Entries', y_off=1.7, fill_color=17)
        h.SetStats(0)
        h.GetYaxis().SetRangeUser(0, h.GetMaximum() * 1.05)
        h.Fit('pol0', 'qs')
        self.histos.append(self.save_histo(h, 'TriggerCell', show, sub_dir=self.save_dir, lm=.11))

    def draw_trigger_cell_vs_peakpos(self, show=True, cut=None, tprofile=False, corr=True, t_corr=False):
        x = self.run.signal_regions[self.SignalRegion]
        if not tprofile:
            ybins = (x[1] - x[0]) if not corr else 4 * (x[1] - x[0])
            h = TH2D('tcpp', 'Trigger Cell vs. Signal Peak Position', 1024, 0, 1024, ybins, x[0] / 2., x[1] / 2.)
        else:
            h = TProfile2D('tcpp', 'Trigger Cell vs. Signal Peak Position', 1024, 0, 1024, x[1] - x[0], x[0] / 2., x[1] / 2.)
        h1 = TProfile('hpr', 'hpr', 100, 0, 1024)

        cut = self.Cut.generate_special_cut(excluded_cuts=['timing']) if cut is None else cut
        # cut = self.Cut.all_cut if cut is None else cut
        prof = '' if not tprofile else ':'
        sig = '' if not tprofile else '{sig}-{ped}'.format(sig=self.SignalName, ped=self.PedestalName)
        gStyle.SetPalette(55)
        peaks = 'IntegralPeaks[{num}]/2.' if not corr else 'IntegralPeakTime[{num}]'
        peaks = peaks.format(num=self.SignalNumber)
        dic = self.Cut.calc_timing_range(show=False)
        t_correction = '-({p1}* trigger_cell + {p2} * trigger_cell*trigger_cell)'.format(p1=dic['t_corr'].GetParameter(1), p2=dic['t_corr'].GetParameter(2)) if t_corr else ''
        self.tree.Draw('{z}{prof}{peaks}{tc}:trigger_cell>>tcpp'.format(z=sig, prof=prof, peaks=peaks, tc=t_correction), cut, 'goff')
        self.tree.Draw('{peaks}{tc}:trigger_cell>>hpr'.format(peaks=peaks, tc=t_correction), self.AllCuts, 'goff')
        self.format_histo(h, x_tit='trigger cell', y_tit='Signal Peak Timing [ns]', y_off=1.25, z_tit='Pulse Height [au]' if tprofile else 'Number of Entries', z_off=1.2, stats=0)
        self.format_histo(h1, color=1, lw=3)
        h.GetZaxis().SetRangeUser(60, 120) if tprofile else self.do_nothing()
        fit = h.ProjectionY().Fit('gaus', 'qs0')
        h.GetYaxis().SetRangeUser(fit.Parameter(1) - 4 * fit.Parameter(2), fit.Parameter(1) + 5 * fit.Parameter(2))
        self.histos.append(self.draw_histo(h, 'TriggerCellVsPeakPos{0}'.format('Signal' if tprofile else ''), show, self.save_dir, lm=.11, draw_opt='colz', rm=.15, logz=True))
        h1.Draw('hist same')
        self.save_plots('TriggerCellVsPeakPos{0}{1}{2}'.format('Signal' if tprofile else '', 'BothCorr' if t_corr else '', 'Corr' if corr else ''), self.save_dir)
        self.RootObjects.append(h1)

    def draw_trigger_cell_vs_forc(self, show=True, cut=None, full_range=False, corr=False):
        if not full_range:
            self.tree.Draw('forc_pos', 'forc_pos[0]>20', 'goff')
            htemp = gROOT.FindObject('htemp')
            x = [int(htemp.GetBinCenter(htemp.FindFirstBinAbove(5000))) - 10, int(htemp.GetBinCenter(htemp.FindLastBinAbove(5000))) + 10]
        else:
            x = [0, 1024]
        h = TH2D('tcf', 'Trigger Cell vs. FORC Timing', 1024, 0, 1024, x[1] - x[0], x[0] / 2., x[1] / 2.)
        cut = self.AllCuts if cut is None else cut
        gStyle.SetPalette(55)
        forc = 'forc_pos/2.' if not corr else 'forc_time'
        self.tree.Draw('{forc}:trigger_cell>>tcf'.format(forc=forc), cut, 'goff')
        self.format_histo(h, x_tit='trigger cell', y_tit='forc timing [ns]', y_off=1.4)
        h.SetStats(0)
        self.histos.append(self.save_histo(h, 'TriggerCellVsFORC{0}'.format('FullRange' if full_range else ''), show, self.save_dir, lm=.11, draw_opt='colz', rm=.15))

    def draw_intlength_vs_triggercell(self, show=True, bin_size=2, prof=False):
        if prof:
            h = TProfile('hltc', 'Integral Length vs. Triggercell', 1024 / bin_size, 0, 1024)
        else:
            y_expect = (self.run.peak_integrals[self.PeakIntegral][0] + self.run.peak_integrals[self.PeakIntegral][1]) * .5
            h = TH2F('hltc', 'Integral Length vs. Triggercell', 1024 / bin_size, 0, 1024, 100, y_expect - 2, y_expect + 2)
        self.tree.Draw('IntegralLength[{num}]:trigger_cell>>hltc'.format(num=self.SignalNumber), self.Cut.all_cut, 'goff')
        self.format_histo(h, x_tit='Triggercell', y_tit='Integral Length [ns]', y_off=1.4, z_tit='Number of Entries', z_off=1.2)
        self.RootObjects.append(self.draw_histo(h, 'IntLengthVsTriggerCell', show, draw_opt='' if prof else 'colz', lm=.12, rm=.16 if not prof else .1))
        if not prof:
            gStyle.SetOptFit(1)
            gStyle.SetOptStat(0)
            gStyle.SetPalette(53)
            set_statbox(.82, .88, .15, 5)
            h_y = h.ProjectionY()
            fit = h_y.Fit('gaus', 'qs0')
            h.GetYaxis().SetRangeUser(fit.Parameter(1) - 5 * fit.Parameter(2), fit.Parameter(1) + 5 * fit.Parameter(2))
            f = TF1('f', '[0]*sin([1]*x - [2]) + [3]')
            f.SetLineColor(600)
            for i, name in enumerate(['y_sc', 'x_sc', 'x_off', 'y_off']):
                f.SetParName(i, name)
            f.SetParLimits(0, .1, 3)
            f.SetParLimits(1, 1e-4, 1e-2)
            h.Fit(f, 'q')
        self.save_plots('IntLengthVsTriggerCell', self.save_dir)
        gStyle.SetPalette(1)

    def draw_intdiff_vs_triggercell(self, show=True):
        h = TH2F('hdtc', 'Difference of the Integral Definitions vs Triggercell', 1024 / 2, 0, 1024, 200, 0, 25)
        hprof = TProfile('hdtc_p', 'Difference of the Integral Definitions vs Triggercell', 1024 / 8, 0, 1024)
        self.tree.Draw('(TimeIntegralValues[{num}]-IntegralValues[{num}]):trigger_cell>>hdtc'.format(num=self.SignalNumber), self.Cut.all_cut, 'goff')
        self.tree.Draw('(TimeIntegralValues[{num}]-IntegralValues[{num}]):trigger_cell>>hdtc_p'.format(num=self.SignalNumber), self.Cut.all_cut, 'goff')
        gStyle.SetPalette(53)
        self.format_histo(h, x_tit='Triggercell', y_tit='Integral2 - Integral1 [au]', z_tit='Number of Entries', stats=0, y_off=1.4, z_off=1.1)
        self.RootObjects.append(self.draw_histo(h, '', show, draw_opt='colz', lm=.12, rm=.15))
        self.format_histo(hprof, lw=3, color=600)
        hprof.Draw('hist same')
        p = h.ProjectionY()
        h.GetYaxis().SetRangeUser(0, p.GetBinCenter(p.FindLastBinAbove(p.GetMaximum() / 15.)))
        self.RootObjects.append(hprof)
        self.save_plots('IntDiffVsTriggerCell', self.save_dir)
        gStyle.SetPalette(1)

    # endregion

    # ==========================================================================
    # region SIGNAL/PEDESTAL
    def generate_signal_name(self, signal, evnt_corr=True, off_corr=False, bin_corr=False, cut=None):
        sig_name = signal
        # pedestal polarity is always the same as signal polarity
        ped_pol = '1'
        # change polarity if pulser has opposite polarity to signal
        if signal == self.PulserName:
            ped_pol = '-1' if self.PulserPolarity != self.Polarity else ped_pol
        if bin_corr:
            return sig_name
        elif off_corr:
            ped_fit = self.show_pedestal_histo(cut=cut, show=False)
            sig_name += '-{pol}*{ped}'.format(ped=ped_fit.Parameter(1), pol=ped_pol)
        elif evnt_corr:
            sig_name += '-{pol}*{ped}'.format(ped=self.PedestalName, pol=ped_pol)
        return sig_name

    def make_signal_time_histos(self, ped=False, signal=None, evnt_corr=False, off_corr=False, show=True, bin_corr=False):
        gROOT.SetBatch(1)
        signal = self.SignalName if signal is None else signal
        signal = signal if not ped else self.PedestalName
        signal = self.generate_signal_name(signal, evnt_corr, off_corr, bin_corr)
        # 2D Histogram
        name = "signaltime_" + str(self.run_number)
        xbins = array(self.time_binning)
        x_min = -50 if not ped else -20
        x_max = 300 if not ped else 20
        bins = 1000 if not ped else 80
        h = TH2D(name, "signaltime", len(xbins) - 1, xbins, bins, x_min, x_max)
        self.tree.Draw("{name}:time>>{histo}".format(histo=name, name=signal), self.Cut.all_cut, 'goff')
        if show:
            gROOT.SetBatch(0)
            c = TCanvas('c', 'Pulse Height vs Time', 1000, 1000)
            c.SetLeftMargin(.12)
            self.format_histo(h, x_tit='time [ms]', y_tit='Pulse Height [au]', y_off=1.4)
            h.Draw('colz')
            self.save_plots('SignalTime', sub_dir=self.save_dir)
            self.SignalTime = h
            self.RootObjects.append(c)
        gROOT.SetBatch(0)
        return h

    def draw_pedestal(self, binning=None, show=True):
        bin_size = binning if binning is not None else self.BinSize
        picklepath = 'Configuration/Individual_Configs/Pedestal/{tc}_{run}_{ch}_{bins}_Ped_Means.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, ch=self.channel, bins=bin_size)
        gr = self.make_tgrapherrors('pedestal', 'Pedestal')

        def func():
            print 'calculating pedestal of ch', self.channel
            if binning is not None:
                self.__set_bin_size(binning)
            ped_time = self.make_signal_time_histos(ped=True, show=False)
            gROOT.SetBatch(1)
            means = []
            empty_bins = 0
            count = 0
            for i in xrange(self.n_bins):
                h_proj = ped_time.ProjectionY(str(i), i + 1, i + 1)
                if h_proj.GetEntries() > 0:
                    fit = self.fit_fwhm(h_proj)
                    gr.SetPoint(count, (self.time_binning[i] - self.run.startTime) / 60e3, fit.Parameter(1))
                    gr.SetPointError(count, 0, fit.ParError(1))
                    count += 1
                    means.append(fit.Parameter(1))
                else:
                    empty_bins += 1
            if show:
                gROOT.SetBatch(0)
            if empty_bins:
                print 'Empty proj. bins:\t', str(empty_bins) + '/' + str(self.n_bins)
            fit_pars = gr.Fit('pol0', 'qs')
            print 'mean:', fit_pars.Parameter(0), '+-', fit_pars.ParError(0)
            c = TCanvas('bla', 'blub', 1000, 1000)
            c.SetLeftMargin(.14)
            gStyle.SetOptFit(1)
            self.format_histo(gr, x_tit='time [min]', y_tit='Mean Pulse Height [au]', y_off=1.6)
            gr.Draw('alp')
            gr.Draw()
            self.save_plots('Pedestal', sub_dir=self.save_dir)
            self.Pedestal = gr
            self.RootObjects.append(c)
            gROOT.SetBatch(0)
            return means

        all_means = func() if show else None
        return self.do_pickle(picklepath, func, all_means)

    def draw_pulse_height(self, binning=None, show=True, save_graph=True, evnt_corr=True, bin_corr=False, off_corr=False, sig=None):
        show = False if not save_graph else show
        signal = self.SignalName if sig is None else sig
        bin_size = binning if binning is not None else self.BinSize
        correction = ''
        if bin_corr:
            correction = 'binwise'
        elif off_corr:
            correction = 'constant'
        elif evnt_corr:
            correction = 'eventwise'
        peak_int = self.get_all_signal_names()[sig][1:] if sig is not None else self.PeakIntegral
        suffix = '{bins}_{cor}_{reg}{int}'.format(bins=bin_size, cor=correction, reg=self.SignalRegion, int=peak_int)
        picklepath = 'Configuration/Individual_Configs/Ph_fit/{tc}_{run}_{ch}_{suf}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, ch=self.channel, suf=suffix)

        self.SignalTime = None

        def func():
            self.log_info('drawing pulse height fit for run {run} and {dia}...'.format(run=self.run_number, dia=self.diamond_name))
            if binning is not None:
                self.__set_bin_size(binning)
            tit_suffix = 'with {cor} Pedestal Correction'.format(cor=correction.title()) if bin_corr or evnt_corr or off_corr else ''
            gr = self.make_tgrapherrors('signal', 'Pulse Height Evolution Bin{0} '.format(self.BinSize) + tit_suffix)
            sig_time = self.make_signal_time_histos(evnt_corr=evnt_corr, signal=signal, show=False, off_corr=off_corr, bin_corr=bin_corr)
            mode = 'mean'
            empty_bins = 0
            count = 0
            means = self.draw_pedestal(bin_size, show=False) if bin_corr else None
            gROOT.SetBatch(1)
            if sig_time.GetEntries() == 0:
                raise Exception('Empty histogram')
            for i in xrange(self.n_bins - 1):
                h_proj = sig_time.ProjectionY(str(i), i + 1, i + 1)
                if h_proj.GetEntries() > 10:
                    if mode in ["mean", "Mean"]:
                        i_mean = h_proj.GetMean()
                        i_mean -= means[count] if bin_corr else 0
                        gr.SetPoint(count, (self.time_binning[i] - self.run.startTime) / 60e3, i_mean)
                        gr.SetPointError(count, 0, h_proj.GetRMS() / sqrt(h_proj.GetEntries()))
                        count += 1
                else:
                    empty_bins += 1
            if empty_bins:
                print 'Empty proj. bins:\t', str(empty_bins) + '/' + str(self.n_bins)
            set_statbox(entries=3, only_fit=True)
            self.format_histo(gr, x_tit='time [min]', y_tit='Mean Pulse Height [au]', y_off=1.6)
            # excludes points that are too low for the fit
            max_fit_pos = gr.GetX()[gr.GetN() - 1] + 10
            sum_ph = gr.GetY()[0]
            for i in xrange(1, gr.GetN()):
                sum_ph += gr.GetY()[i]
                if gr.GetY()[i] < .7 * sum_ph / (i + 1):
                    print 'Found huge ph fluctiation! Stopping Fit', gr.GetY()[i], sum_ph / (i + 1)
                    max_fit_pos = gr.GetX()[i - 1]
                    break
            self.draw_histo(gr, '', show, lm=.14, draw_opt='apl')
            fit_par = gr.Fit('pol0', 'qs', '', 0, max_fit_pos)
            if save_graph:
                self.save_plots('PulseHeight{0}'.format(self.BinSize), sub_dir=self.save_dir)
            self.PulseHeight = gr
            return fit_par

        fit = func() if show else None
        return self.do_pickle(picklepath, func, fit)

    def draw_ph_distribution(self, binning=None, show=True, fit=True, xmin=0, xmax=160, bin_size=.5, save=True):
        if binning is not None:
            self.__set_bin_size(binning)
        sig_time = self.make_signal_time_histos(evnt_corr=True, show=False)
        if not show:
            gROOT.SetBatch(1)
        means = [h_proj.GetMean() for h_proj in [sig_time.ProjectionY(str(i), i + 1, i + 1) for i in xrange(self.n_bins - 1)] if h_proj.GetEntries() > 10]
        nbins = int((xmax - xmin) / bin_size)
        h = TH1F('h', 'Signal Bin{0} Distribution'.format(self.BinSize), nbins, xmin, xmax)  # int(log(len(means), 2) * 2), extrema[0], extrema[1] + 2)
        for mean_ in means:
            h.Fill(mean_)
        self.format_histo(h, x_tit='Pulse Height [au]', y_tit='Entries', y_off=1.5, fill_color=407)
        h.Fit('gaus', 'q') if fit else do_nothing()
        if save:
            self.save_histo(h, 'SignalBin{0}Disto'.format(self.BinSize), lm=.12)
        return h

    def show_ph_overview(self, binning=None):
        self.draw_pulse_height(binning=binning, show=False, save_graph=True)
        h1 = self.PulseHeight
        self.format_histo(h1, y_off=1.4)
        h2 = self.draw_ph_distribution(binning=binning, show=False)
        print h1, h2
        c = TCanvas('c', 'Pulse Height Distribution', 1500, 750)
        c.Divide(2, 1)
        for i, h in enumerate([h1, h2], 1):
            pad = c.cd(i)
            pad.SetBottomMargin(.15)
            h.Draw()
        self.save_plots('PHEvolutionOverview{0}'.format(self.BinSize), sub_dir=self.save_dir)
        self.histos.append([h2, c])

    def show_signal_histo(self, cut=None, evnt_corr=True, off_corr=False, show=True, sig=None, binning=350, events=None, start=None):
        self.log_info('drawing signal distribution for run {run} and {dia}...'.format(run=self.run_number, dia=self.diamond_name))
        suffix = 'with Pedestal Correction' if evnt_corr else ''
        h = TH1F('signal b2', 'Pulse Height ' + suffix, binning, -50, 300)
        cut = self.Cut.all_cut if cut is None else cut
        sig_name = self.SignalName if sig is None else sig
        sig_name = self.generate_signal_name(sig_name, evnt_corr, off_corr, False, cut)
        start_event = int(float(start)) if start is not None else 0
        n_events = self.find_n_events(n=events, cut=str(cut), start=start_event) if events is not None else self.run.n_entries
        self.tree.Draw('{name}>>signal b2'.format(name=sig_name), str(cut), 'goff', n_events, start_event)
        if show:
            c = TCanvas('c', 'Signal Distribution', 1000, 1000)
            c.SetLeftMargin(.13)
            self.format_histo(h, x_tit='Pulse Height [au]', y_tit='Entries', y_off=1.8)
            h.Draw()
            self.save_plots('SignalDistribution', sub_dir=self.save_dir)
            self.histos.append([h, c])
            gROOT.SetBatch(0)
        return h

    def draw_signal_vs_peakpos(self, show=True, corr=False):
        gr = self.make_tgrapherrors('gr', 'Signal vs Peak Position')
        i = 0
        x = self.run.signal_regions[self.SignalRegion]
        self.draw_peak_timing(show=False, corr=corr)
        h = self.PeakValues
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        for peak_pos in xrange(x[0] + 2, x[1] - 2):
            print '\rcalculating peak pos: {0:03d}'.format(peak_pos),
            self.Cut.set_signal_peak_pos(peak_pos, peak_pos + 1) if not corr else self.Cut.set_signal_peak_time(peak_pos / 2., (peak_pos + 1) / 2.)
            print peak_pos / 2., (peak_pos + 1) / 2.
            events = int(h.GetBinContent(h.FindBin(peak_pos / 2.)))
            print '({0:05d})'.format(events),
            stdout.flush()
            if events > 500:
                ph_fit = self.draw_pulse_height(show=False, save_graph=True)
                gr.SetPoint(i, peak_pos / 2., ph_fit.Parameter(0))
                gr.SetPointError(i, 0, ph_fit.ParError(0))
                i += 1
        gr.GetXaxis().SetLimits(x[0] / 2., x[1] / 2.)
        self.format_histo(gr, x_tit='Signal Peak Position [ns]', y_tit='Pulse Height [au]', y_off=1.4)
        self.histos.append(self.save_histo(gr, 'SignalVsPeakPos', show, self.save_dir, lm=.11, draw_opt='alp'))
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')

    def draw_sig_vs_corr_peaktiming(self, show=True, prof=False):
        x = self.run.signal_regions[self.SignalRegion]
        h = TProfile('hspt', 'Signal vs. Corrected Peak Timing', (x[1] - x[0]), x[0] / 2, x[1] / 2)
        if not prof:
            h = TH2F('hspt', 'Signal vs. Corrected Peak Timing', (x[1] - x[0]), x[0] / 2, x[1] / 2, 350, -50, 300)
        dic = self.Cut.calc_timing_range(show=False)
        t_correction = '({p1}* trigger_cell + {p2} * trigger_cell*trigger_cell)'.format(p1=dic['t_corr'].GetParameter(1), p2=dic['t_corr'].GetParameter(2))
        draw_string = '{sig}:IntegralPeakTime[{num}]-{tc}>>hspt'.format(sig=self.SignalName, num=self.SignalNumber, tc=t_correction)
        exluded_cuts = ['timing', 'bucket', 'tracks', 'chi2X', 'chi2Y', 'track_angle']
        cut = self.Cut.generate_special_cut(excluded_cuts=exluded_cuts)
        self.tree.Draw(draw_string, cut, 'goff')
        self.format_histo(h, fill_color=1)
        self.RootObjects.append(self.draw_histo(h, show=show, draw_opt='colz'))
        self.__draw_timing_cut()

    def draw_landau_vs_peakpos(self, show=True, bins=2):
        hs = THStack('lpp', 'Landau vs. Signal Peak Postion;pulse height;entries')
        x = self.run.signal_regions[self.SignalRegion]
        self.Cut.reset_cut('signal_peak_pos')
        self.draw_peak_timing(show=False)
        h_pv = self.PeakValues
        l = TLegend(.7, .38, .90, .88)
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        for peak_pos in xrange(x[0] + 2, x[1] - 2, bins):
            print '\rcalculating peak pos: {0:03d}'.format(peak_pos),
            self.Cut.set_signal_peak_pos(peak_pos, peak_pos + bins)
            events = 0
            for pp in xrange(peak_pos, peak_pos + bins):
                events += int(h_pv.GetBinContent(h_pv.FindBin(peak_pos / 2.)))
            print '({0:05d})'.format(events),
            stdout.flush()
            if events > 10000:
                h = self.show_signal_histo(show=False, binning=100)
                h.SetLineColor(self.get_color())
                h.Scale(1 / h.GetMaximum())
                l.AddEntry(h, '[{0},{1}] ns'.format(int(peak_pos / 2.), int(peak_pos / 2. + bins / 2.)), 'l')
                hs.Add(h)
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
        self.reset_colors()
        self.format_histo(hs, y_tit='Pulse Height [au]', y_off=1.2)
        self.histos.append(self.save_histo(hs, 'LandauVsPeakPos', show, self.save_dir, lm=.11, draw_opt='nostack', l=l))

    def draw_signal_vs_triggercell(self, show=True, bins=10):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        gr = self.make_tgrapherrors('stc', 'Signal vs Trigger Cell')
        i = 0
        for tcell in xrange(0, 1024 - bins, bins):
            if tcell:
                print '\033[F',
            print '\rcalculating pulse height for trigger cell: {0:03d}'.format(tcell),
            self.Cut.set_trigger_cell(tcell, tcell + bins)
            stdout.flush()
            ph_fit = self.draw_pulse_height(show=False, save_graph=True)
            gr.SetPoint(i, tcell, ph_fit.Parameter(0))
            gr.SetPointError(i, 0, ph_fit.ParError(0))
            i += 1
        print
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
        self.format_histo(gr, x_tit='trigger cell', y_tit='pulse height [au]', y_off=1.2)
        self.histos.append(self.save_histo(gr, 'SignalVsTriggerCell', show, self.save_dir, lm=.11, draw_opt='alp'))

    def show_pedestal_histo(self, region=None, peak_int=None, cut=None, fwhm=True, show=True, draw=True, x_range=None, nbins=100, logy=False, fit=True):
        x_range = [-20, 30] if x_range is None else x_range
        region = self.PedestalRegion if region is None else region
        peak_int = self.PeakIntegral if peak_int is None else peak_int
        cut = self.Cut.all_cut if cut is None else cut
        cut = TCut('', cut) if type(cut) is str else cut
        fw = 'fwhm' if fwhm else 'full'
        suffix = '{reg}_{fwhm}_{cut}'.format(reg=region + str(peak_int), cut=cut.GetName(), fwhm=fw)
        picklepath = 'Configuration/Individual_Configs/Pedestal/{tc}_{run}_{ch}_{suf}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, ch=self.channel, suf=suffix)

        def func(x=x_range):
            if not show:
                gROOT.SetBatch(1)
            self.log_info('Making pedestal histo for region {reg}{int}...'.format(reg=region, int=peak_int))
            if x[0] >= x[1]:
                x = sorted(x)
            set_statbox(.95, .95, entries=4, only_fit=True)
            h = TH1F('ped1', 'Pedestal Distribution', nbins, x[0], x[1])
            name = self.get_pedestal_name(region, peak_int)
            self.tree.Draw('{name}>>ped1'.format(name=name), cut, 'goff')
            self.format_histo(h, name='Fit Result', x_tit='Pulse Height [au]', y_tit='Number of Entries', y_off=1.8)
            self.draw_histo(h, '', show)
            fit_pars = self.fit_fwhm(h, do_fwhm=fwhm, draw=show)
            if fit:
                f = deepcopy(h.GetFunction('gaus'))
                f.SetNpx(1000)
                f.SetRange(x[0], x[1])
                f.SetLineStyle(2)
                h.GetListOfFunctions().Add(f)
            if show:
                self.save_histo(h, 'Pedestal_{reg}{cut}'.format(reg=region, cut=cut.GetName()), show, logy=logy, lm=.13)
            self.PedestalHisto = h
            return fit_pars

        fit_par = func() if draw else None
        return self.do_pickle(picklepath, func, fit_par)
    
    def draw_ped_sigma_selection(self, show=True):
        f = self.show_pedestal_histo(cut=self.Cut.generate_special_cut(excluded_cuts=['ped_sigma']), nbins=512, x_range=[-50, 200], logy=True, show=False)
        l = self.make_legend(.66, .96, nentries=3, name='fr', margin=.05, felix=False)
        l.SetHeader('Fit Results')
        l.AddEntry(0, 'Mean:', '')
        l.AddEntry(0, '{0:5.2f} #pm {1:5.2f} ns'.format(f.Parameter(1), f.ParError(1)), '').SetTextAlign(32)
        l.AddEntry(0, 'Sigma:', '')
        l.AddEntry(0, '{0:5.2f} #pm {1:5.2f} ns'.format(f.Parameter(2), f.ParError(2)), '').SetTextAlign(32)
        l.SetNColumns(2)
        l.GetListOfPrimitives().First().SetTextAlign(22)
        h = self.PedestalHisto
        g = TCutG('cut_ped_sigma', 5)
        x = self.Cut.ped_range
        for i, (x, y) in enumerate([(x[0], -1e9), (x[0], +1e9), (x[1], +1e9), (x[1], -1e9), (x[0], -1e9)]):
            g.SetPoint(i, x, y)
        g.SetLineColor(827)
        g.SetLineWidth(2)
        g.SetFillColor(827)
        g.SetFillStyle(3001)
        self.format_histo(h, name='ped1', x_tit='Pulser Range Integral [au]', y_tit='Number of Entries', y_off=1.2, stats=0)
        l1 = self.make_legend(.7, .7, nentries=3)
        l1.AddEntry(g, 'Pedestal Cut', 'fl')
        l1.AddEntry(h.GetListOfFunctions()[0], 'Fitting Range', 'l')
        l1.AddEntry(h.GetListOfFunctions()[1], 'Fit Function', 'l')
        self.draw_histo(h, '', show, logy=True, l=[l, l1])
        g.Draw('f')
        g.Draw('l')
        h.Draw('same')
        self.save_plots('PedSigmaSelection', self.save_dir)
        self.RootObjects.append(g)

    def compare_pedestals(self):
        legend = TLegend(0.7, 0.7, 0.98, .9)
        gr1 = TGraph()
        gr1.SetTitle('pedestal comparison')
        gr1.SetMarkerStyle(20)
        gr2 = TGraph()
        gr2.SetTitle('pedestal comparison with cuts')
        gr2.SetMarkerStyle(20)
        gr2.SetMarkerColor(2)
        gr2.SetLineColor(2)
        gr3 = TGraph()
        gr3.SetTitle('pedestal comparison with cuts full fit')
        gr3.SetMarkerStyle(20)
        gr3.SetMarkerColor(3)
        gr3.SetLineColor(3)
        gROOT.SetBatch(1)
        gROOT.ProcessLine("gErrorIgnoreLevel = kError;")
        for i, reg in enumerate(self.run.pedestal_regions):
            print 'calculation region', reg
            mean1 = self.show_pedestal_histo(reg).keys()[1]
            mean2 = self.show_pedestal_histo(reg, 'median').keys()[1]
            mean3 = self.show_pedestal_histo(reg, 'all').keys()[1]
            gr1.SetPoint(i, i, mean1)
            gr2.SetPoint(i, i, mean2)
            gr3.SetPoint(i, i, mean3)
        gROOT.SetBatch(0)
        gROOT.ProcessLine("gErrorIgnoreLevel = 0;")
        for i, reg in enumerate(self.run.pedestal_regions):
            bin_x = gr1.GetXaxis().FindBin(i)
            gr1.GetXaxis().SetBinLabel(bin_x, reg)
        c = TCanvas('bla', 'blub', 1000, 1000)
        gr1.Draw('alp')
        gr2.Draw('lp')
        gr3.Draw('lp')
        legend.AddEntry(gr1, 'mean fit fwhm w/ cuts 2', 'lp')
        legend.AddEntry(gr2, 'mean fit fwhm w/ cuts median', 'lp')
        legend.AddEntry(gr3, 'mean fit fwhm w/ cuts all', 'lp')
        legend.Draw()
        self.histos.append([gr1, gr2, gr3, c, legend])

    # endregion

    # ==========================================================================
    # region CUTS
    def show_cut_contributions(self, show=True, flat=False):
        if not show:
            gROOT.SetBatch(1)
        main_cut = [self.Cut.CutStrings['event_range'], self.Cut.CutStrings['beam_interruptions']]
        contributions = {}
        cutted_events = 0
        cuts = TCut('consecutive', '')
        total_events = self.run.n_entries
        output = OrderedDict()
        for cut in main_cut + self.Cut.CutStrings.values():
            name = cut.GetName()
            if not name.startswith('old') and name != 'all_cuts' and name not in contributions and str(cut):
                cuts += cut
                events = int(self.tree.Draw('1', '!({0})'.format(cuts), 'goff'))
                output[name] = (1. - float(events) / total_events) * 100.
                events -= cutted_events
                print name.rjust(18), '{0:5d} {1:04.1f}%'.format(events, output[name])
                contributions[cut.GetName()] = events
                cutted_events += events

        # sort contributions by size
        names = ['event', 'track_', 'pul', 'bucket', 'beam', 'sat', 'tracks', 'tim', 'chi2Y', 'ped', 'chi2X']
        sorted_contr = OrderedDict()
        for name in names:
            for key, value in contributions.iteritems():
                if key.startswith(name):
                    if key.startswith('beam'):
                        key = 'beam_stops'
                    sorted_contr[key] = value
                    break

        # contributions = self.sort_contributions(contributions)
        contributions = sorted_contr
        values = contributions.values() + [self.run.n_entries - cutted_events]
        i = 0
        self.reset_colors()
        colors = [self.get_color() for i in xrange(1, len(values) + 1)]
        pie = TPie('pie', 'Cut Contributions', len(values), array(values, 'f'), array(colors, 'i'))
        for i, label in enumerate(contributions.iterkeys()):
            pie.SetEntryRadiusOffset(i, .05)
            pie.SetEntryLabel(i, label.title())
        pie.SetEntryRadiusOffset(i + 1, .05)
        pie.SetEntryLabel(i + 1, 'Good Events')
        pie.SetHeight(.04)
        pie.SetRadius(.2)
        pie.SetTextSize(.025)
        pie.SetAngle3D(70)
        pie.SetLabelFormat('%txt (%perc)')
        # pie.SetLabelFormat('#splitline{%txt}{%percent}')
        pie.SetAngularOffset(280)
        c = TCanvas('c', 'Cut Pie', 1000, 1000)
        pie.Draw('{0}rsc'.format('3d' if not flat else ''))
        self.save_plots('CutContributions', sub_dir=self.save_dir)
        self.histos.append([pie, c])
        gROOT.SetBatch(0)
        return contributions

    @staticmethod
    def sort_contributions(contributions):
        sorted_contr = OrderedDict()
        while contributions:
            for key, value in contributions.iteritems():
                if value == max(contributions.values()):
                    sorted_contr[key] = value
                    contributions.pop(key)
                    break
            for key, value in contributions.iteritems():
                if value == min(contributions.values()):
                    sorted_contr[key] = value
                    contributions.pop(key)
                    break
        return sorted_contr

    def show_bucket_histos(self):
        h = TH1F('h', 'Bucket Cut Histograms', 250, -50, 300)
        self.tree.Draw('{name}>>h'.format(name=self.SignalName), '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['old_bucket'], pul=self.Cut.CutStrings['pulser']), 'goff')
        h1 = deepcopy(h)
        fit = self.Cut.triple_gauss_fit(h1, show=False)
        sig_fit = TF1('f1', 'gaus', -50, 300)
        sig_fit.SetParameters(fit.GetParameters())
        ped1_fit = TF1('f2', 'gaus', -50, 300)
        ped2_fit = TF1('f2', 'gaus', -50, 300)
        ped1_fit.SetParameters(*[fit.GetParameter(i) for i in xrange(3, 6)])
        ped2_fit.SetParameters(*[fit.GetParameter(i) for i in xrange(6, 9)])
        h_sig = deepcopy(h)
        h_ped1 = deepcopy(h)
        h_ped2 = deepcopy(h)
        h_sig.Add(ped1_fit, -1)
        h_sig.Add(ped2_fit, -1)
        h_ped1.Add(ped2_fit, -1)
        h_ped2.Add(ped1_fit, -1)
        h_ped1.Add(h_sig, -1)
        h_ped2.Add(h_sig, -1)
        c = TCanvas('c', 'Bucket Histos', 1000, 1000)
        for i, h in enumerate([h_ped1, h_ped2, h_sig]):
            h.SetStats(0)
            h.SetLineColor(self.get_color())
            h.SetLineWidth(2)
            h.Draw('same') if i else h.Draw()
        self.save_plots('BucketHistos', sub_dir=self.save_dir)
        self.histos.append([h, h_sig, h_ped1, h_ped2, c])

    def show_bucket_numbers(self, show=True):
        pickle_path = self.PickleDir + 'Cuts/BucketEvents_{tc}_{run}_{dia}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, dia=self.diamond_name)

        def func():
            print 'getting number of bucket events for run {run} and {dia}...'.format(run=self.run_number, dia=self.diamond_name)
            n_new = self.tree.Draw('1', '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['bucket'], pul=self.Cut.CutStrings['pulser']), 'goff')
            n_old = self.tree.Draw('1', '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['old_bucket'], pul=self.Cut.CutStrings['pulser']), 'goff')
            if show:
                print 'New Bucket: {0} / {1} = {2:4.2f}%'.format(n_new, self.run.n_entries, n_new / float(self.run.n_entries) * 100)
                print 'Old Bucket: {0} / {1} = {2:4.2f}%'.format(n_old, self.run.n_entries, n_old / float(self.run.n_entries) * 100)
            return {'old': n_old, 'new': n_new, 'all': float(self.run.n_entries)}

        return self.do_pickle(pickle_path, func)

    def show_bucket_hits(self, show=True):
        # hit position
        h = TH2F('h', 'Diamond Margins', 80, -.3, .3, 52, -.3, .3)
        nr = 1 if not self.channel else 2
        cut = '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['old_bucket'], pul=self.Cut.CutStrings['pulser'])
        self.tree.Draw('diam{nr}_track_x:diam{nr}_track_y>>h'.format(nr=nr), cut, 'goff')
        projections = [h.ProjectionX(), h.ProjectionY()]
        zero_bins = [[], []]
        for i, proj in enumerate(projections):
            last_bin = None
            for bin_ in xrange(proj.GetNbinsX()):
                efficiency = proj.GetBinContent(bin_) / float(proj.GetMaximum())
                if bin_ > 1:
                    if efficiency > .05 and last_bin < 5:
                        zero_bins[i].append(proj.GetBinCenter(bin_ - 1))
                    elif efficiency < .05 and last_bin > 5:
                        zero_bins[i].append((proj.GetBinCenter(bin_)))
                last_bin = proj.GetBinContent(bin_)
        if show:
            print zero_bins
            c = TCanvas('c', 'Diamond Hit Map', 1000, 1000)
            h.GetXaxis().SetRangeUser(zero_bins[0][0], zero_bins[0][-1])
            h.GetYaxis().SetRangeUser(zero_bins[1][0], zero_bins[1][-1])
            h.Draw('colz')
            self.histos.append([h, c])
        return h

    def draw_bucket_pedestal(self, show=True, corr=True, additional_cut='', draw_option='colz'):
        gStyle.SetPalette(55)
        cut_string = self.Cut.CutStrings['tracks'] + self.Cut.CutStrings['pulser'] + self.Cut.CutStrings['saturated']
        cut_string += additional_cut
        self.draw_signal_vs_peak_position('e', '2', show, corr, cut_string, draw_option, 1, 'BucketPedestal')

    def draw_bucket_waveforms(self, show=True):
        good = self.draw_waveforms(1, show=False, start_event=120000, t_corr=True)[0]
        cut = self.Cut.generate_special_cut(excluded_cuts=['bucket', 'timing']) + TCut('!({0})'.format(self.Cut.CutStrings['bucket']))
        bucket = self.draw_waveforms(1, cut_string=cut, show=False, start_event=100000, t_corr=True)[0]
        cut = self.Cut.generate_special_cut(excluded_cuts=['bucket', 'timing']) + TCut('{buc}&&!({old})'.format(buc=self.Cut.CutStrings['bucket'], old=self.Cut.CutStrings['old_bucket']))
        bad_bucket = self.draw_waveforms(1, cut_string=cut, show=False, t_corr=True)[0]
        self.reset_colors()
        mg = TMultiGraph('mg_bw', 'Bucket Waveforms')
        l = self.make_legend(.85, .4, nentries=3, w=.1)
        names = ['good wf', 'bucket wf', 'both wf']
        for i, gr in enumerate([good, bucket, bad_bucket]):
            self.format_histo(gr, color=self.get_color(), markersize=.5)
            mg.Add(gr, 'lp')
            l.AddEntry(gr, names[i], 'lp')
        self.format_histo(mg, draw_first=True, x_tit='Time [ns]', y_tit='Signal [mV]')
        x = [self.run.signal_regions['e'][0] / 2, self.run.signal_regions['e'][1] / 2 + 20]
        self.format_histo(mg, x_range=x, y_off=.7)
        y = mg.GetYaxis().GetXmin(), mg.GetYaxis().GetXmax()
        print x, y
        self.draw_histo(mg, show=show, draw_opt='A', x=1.5, y=0.75, lm=.07, rm=.045, bm=.2, l=l)
        self._add_buckets(y[0], y[1], x[0], x[1], avr_pos=-1, full_line=True)
        self.save_plots('BucketWaveforms')
        self.reset_colors()

    def show_bucket_means(self, show=True, plot_histos=True):
        pickle_path = self.PickleDir + 'Cuts/BucketMeans_{tc}_{run}_{dia}.pickle'.format(tc=self.TESTCAMPAIGN, run=self.run_number, dia=self.diamond_name)

        def func():
            gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
            cuts_nobucket = TCut('no_bucket', '')
            cuts_oldbucket = TCut('old_bucket', '')
            for key, value in self.Cut.CutStrings.iteritems():
                if not key.startswith('old') and key not in ['all_cuts', 'bucket']:
                    cuts_nobucket += value
                if key not in ['all_cuts', 'bucket']:
                    cuts_oldbucket += value
            h1 = self.show_signal_histo(show=False, evnt_corr=True)
            h2 = self.show_signal_histo(show=False, evnt_corr=True, cut=cuts_nobucket)
            h3 = self.show_signal_histo(show=False, evnt_corr=True, cut=cuts_oldbucket)
            if plot_histos:
                c = TCanvas('c', 'Bucket Histos', 1000, 1000)
                self.format_histo(h1, color=self.get_color(), lw=1, x_tit='Pulse Height [au]', y_tit='Entries')
                h1.Draw()
                self.format_histo(h2, color=self.get_color(), lw=1)
                h2.Draw('same')
                self.format_histo(h3, color=self.get_color(), lw=1)
                h3.Draw('same')
                self.histos.append([h1, h2, h3, c])
            result = {name: [h.GetMean(), h.GetMeanError()] for name, h in zip(['new', 'no', 'old'], [h1, h2, h3])}
            gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
            if show:
                print result
            return result

        res = func() if plot_histos else None
        return self.do_pickle(pickle_path, func, res)

    def compare_single_cuts(self):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        gROOT.SetBatch(1)
        c1 = TCanvas('single', '', 1000, 1000)
        c2 = TCanvas('all', '', 1000, 1000)
        c2.SetLeftMargin(0.15)
        legend = TLegend(0.7, 0.3, 0.98, .7)
        histos = []
        drawn_first = False
        for key, value in self.Cut.CutStrings.iteritems():
            if str(value) or key == 'raw':
                print 'saving plot', key
                save_name = 'signal_distribution_{cut}'.format(cut=key)
                histo_name = 'signal {range}{peakint}'.format(range=self.SignalRegion, peakint=self.PeakIntegral)
                histo_title = 'signal with cut ' + key
                histo = TH1F(histo_name, histo_title, 350, -50, 300)
                # safe single plots
                c1.cd()
                self.tree.Draw("{name}>>{histo}".format(name=self.SignalName, histo=histo_name), value)
                self.save_plots(save_name, canvas=c1, sub_dir=self.save_dir)
                # draw all single plots into c2
                c2.cd()
                histo.SetLineColor(self.get_color())
                if not drawn_first:
                    self.format_histo(histo, title='Signal Distribution of Different Single Cuts', x_tit='Pulse Height [au]', y_tit='Entries', y_off=2)
                    histo.SetStats(0)
                    histo.Draw()
                    drawn_first = True
                else:
                    if key == 'all_cuts':
                        histo.SetLineWidth(2)
                    histo.Draw('same')
                histos.append(histo)
                legend.AddEntry(histo, key, 'l')
        # save c2
        legend.Draw()
        self.save_plots('all', canvas=c2, sub_dir=self.save_dir)
        gROOT.ProcessLine("gErrorIgnoreLevel = 0;")
        gROOT.SetBatch(0)

    def compare_normalised_cuts(self, scale=False, show=True):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        gROOT.SetBatch(1)
        self.reset_colors()
        c1 = TCanvas('single', '', 1000, 1000)
        name = 'sCutComparison'
        if scale:
            name += "_scaled"
        else:
            name += "_noarmalized"
        if scale:
            title = 'Scaled Signal Distribution with Single Cuts'
        else:
            title = 'Normalised Signal Distribution with Single Cuts'
        title += ';Pulse Height [au];Normalised Entries'

        stack = THStack(name, title)

        entries = 0
        for value in self.Cut.CutStrings.itervalues():
            if str(value):
                entries += 1
        legend = self.make_legend(x1=.57, nentries=entries - 2)
        histos = []
        for key, value in self.Cut.CutStrings.iteritems():
            if str(value) or key == 'raw':
                save_name = 'signal_distribution_normalised_{cut}'.format(cut=key)
                histo_name = 'signal {range}{peakint}'.format(range=self.SignalRegion, peakint=self.PeakIntegral)
                histo_title = 'normalized' if not scale else 'scaled'
                histo_title += ' signal with cut ' + key
                histo = TH1F(histo_name, histo_title, 350, -50, 300)
                # safe single plots
                c1.cd()
                self.tree.Draw("{name}>>{histo}".format(name=self.SignalName, histo=histo_name), value)
                if scale:
                    histo = self.scale_histo(histo)
                else:
                    histo = self.normalise_histo(histo)
                histo.Draw()
                c1.Update()
                self.save_plots(save_name, canvas=c1, sub_dir=self.save_dir)
                # draw all single plots into c2
                histo.SetLineColor(self.get_color())

                if key == 'all_cuts':
                    histo.SetLineWidth(2)
                stack.Add(histo)
                histos.append(histo)
                legend.AddEntry(histo, key, 'l')
        stack.Draw()
        gROOT.SetBatch(0)

        for h in histos:
            h.SetStats(False)
        name = '{0}Cuts'.format('Normalised' if not scale else 'Scaled')
        self.format_histo(stack, y_off=1.4, x_off=1.1)
        self.RootObjects.append(self.save_histo(stack, name, show, self.save_dir, lm=.15, l=legend, draw_opt='nostack'))
        gROOT.ProcessLine("gErrorIgnoreLevel = 0;")
        gROOT.SetBatch(0)

    def compare_consecutive_cuts(self, scale=False, show=True, save_single=True):
        self.reset_colors()
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        legend = self.make_legend(.65, .9, nentries=len(self.Cut.ConsecutiveCuts) - 3, w=.17)
        cut = TCut('consecutive', '')
        stack = THStack('scc', 'Signal Distribution with Consecutive Cuts')
        for i, (key, value) in enumerate(self.Cut.ConsecutiveCuts.iteritems()):
            key = 'beam_stops' if key.startswith('beam') else key
            cut += value
            save_name = 'signal_distribution_{n}cuts'.format(n=i)
            h = TH1F('h_{0}'.format(i), 'signal with {n} cuts'.format(n=i), 550, -50, 500)
            self.tree.Draw('{name}>>h_{i}'.format(name=self.SignalName, i=i), cut, 'goff')
            if scale:
                self.scale_histo(h)
            if save_single:
                self.save_histo(h, save_name, False, self.save_dir)
            color = self.get_color()
            self.format_histo(h, color=color, stats=0)
            if not scale:
                h.SetFillColor(color)
            stack.Add(h)
            leg_entry = '+ {0}'.format(key) if i else key
            leg_style = 'l' if scale else 'f'
            legend.AddEntry(h, leg_entry, leg_style)
        self.format_histo(stack, x_tit='Pulse Height [au]', y_tit='Number of Entries', y_off=1.9, draw_first=True)
        self.RootObjects.append(self.save_histo(stack, 'Consecutive{0}'.format('Scaled' if scale else ''), show, self.save_dir, l=legend, draw_opt='nostack', lm=0.14))
        stack.SetName(stack.GetName() + 'logy')
        stack.SetMaximum(stack.GetMaximum() * 1.2)
        self.RootObjects.append(self.save_histo(stack, 'Consecutive{0}Logy'.format('Scaled' if scale else '', ), show, self.save_dir, logy=True, l=legend, draw_opt='nostack', lm=0.14))
        gROOT.ProcessLine("gErrorIgnoreLevel = 0;")

    def draw_cut_means(self, show=True):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        gr = self.make_tgrapherrors('gr_cm', 'Mean of Pulse Height for Consecutive Cuts')
        cut = TCut('consecutive', '')
        names = []
        i = 1
        gr.SetPoint(0, 0, 0)
        for key, value in self.Cut.CutStrings.iteritems():
            if (str(value) or key == 'raw') and key not in ['all_cuts', 'old_bucket']:
                key = 'beam_stops' if key.startswith('beam') else key
                cut += value
                h = self.show_signal_histo(cut=cut, show=False)
                self.log_info('{0}, {1}, {2}'.format(key, h.GetMean(), h.GetMeanError()))
                gr.SetPoint(i, i, h.GetMean())
                gr.SetPointError(i, 0, h.GetMeanError())
                names.append(key)
                i += 1
        self.format_histo(gr, markersize=.2, fill_color=821, y_tit='Mean Pulse Height [au]', y_off=1.4)
        y = [gr.GetY()[i] for i in xrange(1, gr.GetN())]
        gr.SetFillColor(821)
        gr.GetYaxis().SetRangeUser(min(y) - 1, max(y) + 1)
        gr.GetXaxis().SetLabelSize(.05)
        for i in xrange(1, gr.GetN()):
            bin_x = gr.GetXaxis().FindBin(i)
            gr.GetXaxis().SetBinLabel(bin_x, names[i - 1])
        self.RootObjects.append(self.save_histo(gr, 'CutMeans', show, self.save_dir, bm=.30, draw_opt='bap', lm=.12))
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')

    # endregion

    # ==========================================================================
    # region SHOW
    def draw_signal_vs_peak_position(self, region=None, peak_int=None, show=True, corr=True, cut=None, draw_opt='colz', nbins=4, save_name='SignalVsPeakPos'):
        region = self.SignalRegion if region is None else region
        peak_int = self.PeakIntegral if peak_int is None else peak_int
        cut = self.Cut.generate_special_cut(excluded_cuts=[self.Cut.CutStrings['timing']]) if cut is None else cut
        num = self.get_signal_number(region, peak_int)
        reg_margins = self.run.signal_regions[region]
        x_bins = (reg_margins[1] - reg_margins[0]) * nbins
        h = TH2F('h_spp', 'Signal Vs Peak Positions', x_bins, reg_margins[0] / 2., reg_margins[1] / 2., 550, -50, 500)
        peak_string = 'IntegralPeaks' if not corr else 'IntegralPeakTime'
        draw_string = '{sig}:{peaks}[{num}]{scale}>>h_spp'.format(sig=self.SignalName, num=num, peaks=peak_string, scale='/2.' if not corr else '')
        self.tree.Draw(draw_string, cut, 'goff')
        self.format_histo(h, x_tit='Peak Timing [ns]', y_tit='Pulse Height [au]', y_off=1.35, z_off=1.2, stats=0, z_tit='Number of Entries')
        self.RootObjects.append(self.save_histo(h, save_name, show, self.save_dir, draw_opt=draw_opt, logz=True, rm=.15, lm=.12))

    def draw_signal_vs_signale(self, show=True):
        gStyle.SetPalette(53)
        cut = self.Cut.generate_special_cut(excluded_cuts=['bucket'])
        num = self.get_signal_number(region='e')
        cut += TCut('IntegralPeakTime[{0}]<94&&IntegralPeakTime[{0}]>84'.format(num))
        h = TH2F('hsse', 'Signal b vs Signal e', 62, -50, 200, 50, 0, 200)
        self.tree.Draw('{sige}:{sigb}>>hsse'.format(sigb=self.SignalName, sige=self.get_signal_name(region='e')), cut, 'goff')
        self.format_histo(h, x_tit='Signal s_b [au]', y_tit='Signal s_e [au]', z_tit='Number of Entries', z_off=1.1, y_off=1.5, stats=0)
        self.RootObjects.append(self.save_histo(h, 'SignalEvsSignalB', show, rm=.15, lm=.13, draw_opt='colz'))
        gStyle.SetPalette(1)

    def draw_single_wf(self, event=None):
        cut = '!({0})&&!pulser'.format(self.Cut.CutStrings['old_bucket'])
        return self.draw_waveforms(n=1, cut_string=cut, add_buckets=True, start_event=event)

    def draw_waveforms(self, n=1000, start_event=None, cut_string=None, show=True, add_buckets=False, fixed_range=None, ch=None, t_corr=False):
        """
        Draws stacked waveforms.
        :param n: number of waveforms
        :param cut_string:
        :param start_event: event to start
        :param show:
        :param add_buckets: draw buckets and most probable peak values if True
        :param fixed_range: fixes x-range to given value if set
        :param ch: channel of the DRS4
        :return: histo with waveform
        """
        start = self.StartEvent if start_event is None else start_event
        start += self.count
        print 'Drawing waveform, start event:', start
        assert self.run.n_entries >= start >= 0, 'The start event is not within the range of tree events!'
        channel = self.channel if ch is None else ch
        if not self.run.wf_exists(channel):
            return
        cut = self.Cut.all_cut if cut_string is None else cut_string
        n_events = self.find_n_events(n, cut, start)
        h = TH2F('wf', 'Waveform', 1024, 0, 511, 1000, -500, 500)
        gStyle.SetPalette(55)
        self.tree.Draw('wf{ch}:Iteration$/2>>wf'.format(ch=channel), cut, 'goff', n_events, start)
        t = self.tree.GetV2() if not t_corr else self.corrected_time(start + n_events - 1)
        h = TGraph(self.tree.GetSelectedRows(), t, self.tree.GetV1()) if n == 1 else h
        if fixed_range is None and n > 1:
            fit = self.draw_pulse_height(show=False)
            pol = self.Polarity
            ymin = fit.Parameter(0) * 3 / 50 * 50 * pol if pol < 0 else -100
            ymax = fit.Parameter(0) * 3 / 50 * 50 * pol if pol > 0 else 100
            h.GetYaxis().SetRangeUser(ymin, ymax)
        elif fixed_range:
            assert type(fixed_range) is list, 'Range has to be a list!'
            h.GetYaxis().SetRangeUser(fixed_range[0], fixed_range[1])
        self.format_histo(h, title='Waveform', name='wf', x_tit='Time [ns]', y_tit='Signal [mV]', markersize=.4, y_off=.4, stats=0, tit_size=.05)
        save_name = '{1}Waveforms{0}'.format(n, 'Pulser' if cut.GetName().startswith('Pulser') else 'Signal')
        self.RootObjects.append(self.save_histo(h, save_name, show, self.save_dir, lm=.06, rm=.045, draw_opt='scat' if n == 1 else 'col', x_fac=1.5, y_fac=.5))
        if add_buckets:
            sleep(.2)
            h.GetXaxis().SetNdivisions(26)
            c = gROOT.GetListOfCanvases[-1]
            c.SetGrid()
            c.SetBottomMargin(.186)
            y = h.GetYaxis().GetXmin(), h.GetYaxis().GetXmax()
            x = h.GetXaxis().GetXmin(), h.GetXaxis().GetXmax()
            self._add_buckets(y[0], y[1], x[0], x[1])
        self.count += n_events
        return h, n_events

    def corrected_time(self, evt):
        self.tree.GetEntry(evt)
        tcell = None
        exec 'tcell = self.tree.trigger_cell'
        t = [self.run.TCal[tcell]]
        n_samples = 1024
        for i in xrange(1, n_samples):
            t.append(self.run.TCal[(tcell + i) % n_samples] + t[-1])
        return array(t, 'd')

    def show_single_waveforms(self, n=1, cut='', start_event=None):
        start = self.StartEvent + self.count if start_event is None else start_event + self.count
        activated_wfs = [wf for wf in xrange(4) if self.run.wf_exists(wf)]
        print 'activated wafeforms:', activated_wfs
        print 'Start at event number:', start
        wfs = [self.draw_waveforms(n=n, start_event=start, cut_string=cut, show=False, ch=wf) for wf in activated_wfs]
        n_wfs = len(activated_wfs)
        if not gROOT.GetListOfCanvases()[-1].GetName() == 'c_wfs':
            c = TCanvas('c_wfs', 'Waveforms', 2000, n_wfs * 500)
            c.Divide(1, n_wfs)
        else:
            c = gROOT.GetListOfCanvases()[-1]
        for i, wf in enumerate(wfs, 1):
            wf[0].SetTitle('{nam} WaveForm'.format(nam=self.run.DRS4Channels[activated_wfs[i - 1]]))
            c.cd(i)
            wf[0].Draw('aclp')
        self.RootObjects.append([c, wfs])
        cnt = wfs[0][1]
        # if cnt is None:
        #     return
        self.count += cnt

    # endregion

    def find_n_events(self, n, cut, start):
        total_events = self.tree.Draw('event_number', cut, 'goff', self.run.n_entries, start)
        evt_numbers = [self.tree.GetV1()[i] for i in xrange(total_events)]
        return int(evt_numbers[:n][-1] + 1 - start)

    @staticmethod
    def normalise_histo(histo, to100=False):
        h = histo
        h.GetXaxis().SetRangeUser(0, 30)
        min_bin = h.GetMinimumBin()
        h.GetXaxis().UnZoom()
        max_bin = h.GetNbinsX() - 1
        integral = h.Integral(min_bin, max_bin)
        if integral:
            fac = 100 if to100 else 1
            h.Scale(fac / integral)
        return h

    @staticmethod
    def scale_histo(histo):
        h = histo
        h.GetXaxis().SetRangeUser(30, 500)
        maximum = h.GetBinContent(h.GetMaximumBin())
        h.GetXaxis().UnZoom()
        if maximum:
            h.Scale(1. / maximum)
        return h

    def analyse_signal_histograms(self):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        # gROOT.SetBatch(1)
        legend = TLegend(0.7, 0.3, 0.98, .7)
        gr1 = TGraphErrors()
        gr1.SetTitle('mean values')
        gr1.SetMarkerStyle(20)
        gr2 = TGraph()
        gr2.SetTitle('median values')
        gr2.SetMarkerStyle(21)
        gr2.SetMarkerColor(2)
        gr3 = TGraph()
        gr3.SetMarkerStyle(22)
        gr3.SetMarkerColor(3)
        histos = []
        i = 0
        for key, value in self.Cut.CutStrings.iteritems():
            if str(value) or key == 'raw':
                print 'process cut ' + key
                # h = TH1F('h', '', 600, -100, 500)
                # self.tree.Draw("{name}>>h".format(name=self.signal_name), value)
                h = self.show_signal_histo(evnt_corr=True, cut=value, show=False)
                i_mean = self.__get_mean(h)
                median = self.__get_median(h)
                mpv = self.__get_mpv(h)
                # print mean, median, mpv
                gr1.SetPoint(i, i, i_mean[0])
                gr1.SetPointError(i, 0, i_mean[1])
                gr2.SetPoint(i, i, median)
                gr3.SetPoint(i, i, mpv)
                histos.append(h)
                i += 1
        # rename bins
        legend.AddEntry(gr1, 'mean', 'lp')
        legend.AddEntry(gr2, 'median', 'lp')
        legend.AddEntry(gr3, 'mpv', 'lp')
        xaxis = gr1.GetXaxis()
        i = 0
        for key, value in self.Cut.CutStrings.iteritems():
            if str(value) or key == 'raw':
                bin_x = xaxis.FindBin(i)
                gr1.GetXaxis().SetBinLabel(bin_x, key[:7])
                i += 1
        gROOT.ProcessLine("gErrorIgnoreLevel = 0;")
        # gROOT.SetBatch(0)
        c1 = TCanvas('c1', '', 1000, 1000)
        c1.cd()
        gr1.GetXaxis().SetRangeUser(-1, len(histos) + 1)
        gr1.Draw('alp')
        gr2.Draw('lp')
        gr3.Draw('lp')
        legend.Draw()
        self.histos.append(legend)
        return [gr1, gr2, gr3]

    @staticmethod
    def __get_histo_without_pedestal(histo):
        h = histo
        h.GetXaxis().SetRangeUser(0, 30)
        min_bin = h.GetMinimumBin()
        min_x = h.GetBinCenter(min_bin)
        h.GetXaxis().SetRangeUser(min_x, 500)
        return h

    def __get_mean(self, histo):
        h = self.__get_histo_without_pedestal(histo)
        h.GetXaxis().SetRangeUser(0, 30)
        min_bin = h.GetMinimumBin()
        min_x = h.GetBinCenter(min_bin)
        h.GetXaxis().SetRangeUser(min_x, 500)
        return [h.GetMean(), h.GetMeanError()]

    def __get_median(self, histo):
        h = self.__get_histo_without_pedestal(histo)
        integral = h.GetIntegral()
        median_i = 0
        for j in range(h.GetNbinsX() - 1):
            if integral[j] < 0.5:
                median_i = j
            else:
                break
        weight = (0.5 - integral[median_i]) / (integral[median_i + 1] - integral[median_i])
        median_x = h.GetBinCenter(median_i) + (h.GetBinCenter(median_i + 1) - h.GetBinCenter(median_i)) * weight
        return median_x

    def __get_mpv(self, histo):
        h = self.__get_histo_without_pedestal(histo)
        max_bin = h.GetMaximumBin()
        return h.GetBinCenter(max_bin)

    def draw_snrs(self, show=True, lego=True, proj=False):
        self.verbose = False
        lego = False if proj else lego
        gr = self.make_tgrapherrors('gr', 'Signal to Noise Ratios')
        h = TProfile2D('h_snr', 'Signal to Noise Ratios', 12, 1, 7, 12, 3, 9)
        l1 = TLegend(.7, .68, .9, .9)
        l1.SetHeader('Regions')
        l2 = TLegend(.7, .47, .9, .67)
        l2.SetHeader('PeakIntegrals')
        for i, name in enumerate(self.get_all_signal_names().iterkeys()):
            peak_int = self.run.peak_integrals[self.get_all_signal_names()[name][1:]]
            snr = self.calc_snr(sig=name, name=self.get_all_signal_names()[name])
            h.Fill(peak_int[0] / 2., peak_int[1] / 2., snr[0])
            gr.SetPoint(i, i + 1, snr[0])
            gr.SetPointError(i, 0, snr[1])
        for i, region in enumerate(self.get_all_signal_names().itervalues(), 1):
            bin_x = gr.GetXaxis().FindBin(i)
            gr.GetXaxis().SetBinLabel(bin_x, region)
        [l1.AddEntry(0, '{reg}:  {val}'.format(reg=reg, val=value), '') for reg, value in self.run.signal_regions.iteritems() if len(reg) <= 2]
        [l2.AddEntry(0, '{reg}:  {val}'.format(reg=integ, val=value), '') for integ, value in self.run.peak_integrals.iteritems() if len(integ) <= 2]
        self.format_histo(gr, y_tit='SNR', y_off=1.2, color=self.get_color(), fill_color=1)
        gr.SetLineColor(2)
        vals = sorted([h.GetBinContent(i) for i in xrange(h.GetNbinsX() * h.GetNbinsY()) if h.GetBinContent(i)])
        self.__draw_profiles(h, proj)
        self.format_histo(h, x_tit='Left Length [ns]', x_off=1.45, y_tit='Right Length [ns]', y_off=1.6, z_tit='snr', z_off=1.6, stats=0, z_range=[vals[2], max(vals)])
        h.SetContour(50)
        gStyle.SetPalette(53)
        self.save_histo(h, 'SNRLego', show and lego, draw_opt='colz', bm=.2, rm=.1, lm=.13, phi=-30, theta=40)
        gStyle.SetPalette(1)
        self.save_histo(gr, 'SNR', not (lego or proj) and show, l=[l1, l2], draw_opt='bap')

    def __draw_profiles(self, histo, show=True):
        h = histo
        py = h.ProfileY('Right Length')
        px = h.ProfileX('Left Length')
        vals = [py.GetBinContent(i) for i in xrange(py.GetNbinsX()) if py.GetBinContent(i)] + [px.GetBinContent(i) for i in xrange(px.GetNbinsX()) if px.GetBinContent(i)]
        self.format_histo(py, style=3004, fill_color=2, stats=0)
        self.format_histo(px, style=3005, fill_color=3, stats=0)
        l = self.make_legend(.68, .95)
        [l.AddEntry(p, p.GetName(), 'fp') for p in [py, px]]
        stack = THStack('s_sp', 'SNR Profiles')
        stack.Add(py, 'histe')
        stack.Add(px, 'histe')
        self.format_histo(stack, draw_first=True, x_tit='Integral Length [ns]', y_tit='snr [au]', y_off=1.35)
        stack.SetMinimum(increased_range([min(vals), max(vals)], .5, .5)[0])
        stack.SetMaximum(increased_range([min(vals), max(vals)], .5, .5)[1])
        self.save_histo(stack, 'SNRProfiles', show, draw_opt='nostack', l=l, lm=.13)

    def calc_snr(self, sig=None, name=''):
        signal = self.SignalName if sig is None else sig
        peak_int = self.get_all_signal_names()[signal][-2:] if self.get_all_signal_names()[signal][-2].isdigit() else self.get_all_signal_names()[signal][-1]
        ped_fit = self.show_pedestal_histo(draw=False, peak_int=peak_int, show=False)
        sig_fit = self.draw_pulse_height(evnt_corr=True, save_graph=False, sig=signal)
        sig_mean = sig_fit.Parameter(0)
        ped_sigma = ped_fit.Parameter(2)

        snr = sig_mean / ped_sigma
        snr_err = snr * (sig_fit.ParError(0) / sig_mean + ped_fit.ParError(2) / ped_sigma)
        print '{name} {0}\t| SNR is: {snr} +- {err}\t {1} {2}'.format(self.run.peak_integrals[peak_int], sig_mean, ped_sigma, name=name, snr=snr, err=snr_err)
        return [snr, snr_err]

    # ============================================
    # region PEAK INTEGRAL

    def find_best_snr(self, show=True, same_width=False):
        gROOT.SetBatch(1)
        gr = self.make_tgrapherrors('gr', 'Signal to Noise Ratios')
        peak_integrals = OrderedDict(sorted({key: value for key, value in self.run.peak_integrals.iteritems() if len(key) < 3}.items()))
        i = 0
        for name, value in peak_integrals.iteritems():
            signal = self.get_signal_name('b', name)
            snr = self.calc_snr(signal)
            print value
            x = (value[1] + value[0]) / 2. if not same_width else value[0] / 2.
            gr.SetPoint(i, x, snr[0])
            gr.SetPointError(i, 0, snr[1])
            i += 1
        if show:
            gROOT.SetBatch(0)
        c = TCanvas('c', 'SNR', 1000, 1000)
        self.format_histo(gr, x_tit='Integralwidth [ns]', y_tit='SNR')
        gr.Draw('ap')
        gROOT.SetBatch(0)
        self.save_plots('BestSNR', sub_dir=self.save_dir)
        self.histos.append([gr, c])

    def signal_vs_peakintegral(self, show=True, ped=False):
        gROOT.SetBatch(1)
        gr = self.make_tgrapherrors('gr', '{sig} vs Peak Integral'.format(sig='Signal' if not ped else 'Pedestal'))
        peak_integrals = OrderedDict(sorted({key: value for key, value in self.run.peak_integrals.iteritems() if len(key) < 3}.items()))
        i = 0
        ratio = '{0}{1}'.format(self.run.peak_integrals.values()[0][0], self.run.peak_integrals.values()[0][1])
        for name, value in peak_integrals.iteritems():
            sig_name = self.get_signal_name(region='b', peak_integral=name)
            signal = self.draw_pulse_height(evnt_corr=True, show=False, sig=sig_name) if not ped else self.show_pedestal_histo(draw=False, peak_int=name)
            par = 2 if ped else 0
            gr.SetPoint(i, (value[1] + value[0]) / 2., signal.Parameter(par))
            gr.SetPointError(i, 0, signal.ParError(par))
            i += 1
        if show:
            gROOT.SetBatch(0)
        c = TCanvas('c', 'Signal vs Peak Integral', 1000, 1000)
        self.format_histo(gr, x_tit='Integralwidth [ns]', y_tit='Signal [au]', y_off=1.3)
        gr.Draw('ap')
        gROOT.SetBatch(0)
        self.save_plots('{sig}PeakInt_{rat}'.format(rat=ratio, sig='Ped' if ped else 'Sig'), sub_dir=self.save_dir)
        self.histos.append([gr, c])

    # endregion

    # ============================================
    # region MISCELLANEOUS

    def get_cut(self):
        """ :return: full cut_string """
        return self.Cut.all_cut

    def get_peak_position(self, event=None, region='b', peak_int='2'):
        num = self.get_signal_number(region, peak_int)
        ev = self.StartEvent if event is None else event
        self.tree.GetEntry(ev)
        return self.tree.IntegralPeaks[num]

    def get_all_signal_names(self):
        names = OrderedDict()
        regions = [reg for reg in self.run.signal_regions if len(reg) < 3]
        integrals = [integral for integral in self.run.peak_integrals if len(integral) < 3]
        for region in regions:
            for integral in integrals:
                if len(integral) > 2:
                    integral = '_' + integral
                name = 'ch{ch}_signal_{reg}_PeakIntegral{int}'.format(ch=self.channel, reg=region, int=integral)
                num = self.IntegralNames[name]
                reg = region + integral
                names['({pol}*TimeIntegralValues[{num}])'.format(pol=self.Polarity, num=num)] = reg
        return names

    def __get_binning(self):
        jumps = self.Cut.jump_ranges
        if jumps is None:
            jumps = {'start': [self.EndEvent], 'stop': [self.EndEvent]}

        n_jumps = len(jumps['start'])
        bins = [self.Cut.get_min_event()]
        ind = 0
        for start, stop in zip(jumps['start'], jumps['stop']):
            gap = stop - start
            # continue if first start and stop outside min event
            if stop < bins[-1]:
                ind += 1
                continue
            # if there is a jump from the start
            if start < bins[-1] < stop:
                bins.append(stop)
                ind += 1
                continue
            # add bins until hit interrupt
            while bins[-1] + self.BinSize < start:
                bins.append(bins[-1] + self.BinSize)
            # two jumps shortly after one another
            if ind < n_jumps - 2:
                next_start = jumps['start'][ind + 1]
                next_stop = jumps['stop'][ind + 1]
                if bins[-1] + self.BinSize + gap > next_start:
                    gap2 = next_stop - next_start
                    bins.append(bins[-1] + self.BinSize + gap + gap2)
                else:
                    bins.append(bins[-1] + self.BinSize + gap)
            else:
                bins.append(bins[-1] + self.BinSize + gap)
            ind += 1
        # fill up the end
        if ind == n_jumps - 1 and bins[-1] >= jumps['stop'][-1] or ind == n_jumps:
            while bins[-1] + self.BinSize < self.run.n_entries:
                bins.append(bins[-1] + self.BinSize)
        return bins

    def get_time_binning(self):
        time_bins = []
        for event in self.binning:
            time_bins.append(self.run.get_time_at_event(event))
        return time_bins

    def print_info_header(self):
        header = ['Run', 'Type', 'Diamond', 'HV [V]', 'Region']
        for info in header:
            print self.adj_length(info),
        print

    def print_information(self, header=True):
        if header:
            self.print_info_header()
        infos = [self.run_number, self.run.RunInfo['type'], self.diamond_name.ljust(4), self.bias, self.SignalRegion + self.PeakIntegral + '   ']
        for info in infos:
            print self.adj_length(info),
        print

    def print_integral_names(self):
        for key, value in self.IntegralNames.iteritems():
            if key.startswith('ch{ch}'.format(ch=self.channel)):
                print str(value).zfill(3), key
        return

    # endregion

    def spectrum(self, it=20, noise=20):
        decon = array(1024 * [0], 'f')
        s = TSpectrum(25)
        peaks = []
        for i in xrange(it):
            self.tree.GetEntry(300000 + i)
            data = array([-1 * self.tree.wf0[j] for j in xrange(1024)], 'f')
            thr = 100 * 2 * noise / max(data)
            print thr
            p = s.SearchHighRes(data, decon, 1024, 5, thr, True, 3, True, 5)
            xpos = [s.GetPositionX()[i] for i in xrange(p)]
            peaks.append(xpos)
        return decon, s, peaks

    def fixed_integrals(self):
        tcals = [0.4813, 0.5666, 0.3698, 0.6393, 0.3862, 0.5886, 0.5101, 0.5675, 0.4033, 0.6211, 0.4563, 0.5919, 0.4781, 0.5947, 0.417, 0.5269,
                 0.5022, 0.5984, 0.4463, 0.622, 0.4326, 0.5603, 0.3712, 0.6168, 0.5238, 0.5515, 0.514, 0.5949, 0.4198, 0.5711, 0.5344, 0.5856,
                 0.3917, 0.6125, 0.4335, 0.5817, 0.4658, 0.5338, 0.4442, 0.5865, 0.4482, 0.5778, 0.4755, 0.6118, 0.4113, 0.5609, 0.465, 0.6188,
                 0.3908, 0.5736, 0.5223, 0.5222, 0.5109, 0.493, 0.4421, 0.5908, 0.4555, 0.6737, 0.371, 0.5172, 0.5362, 0.5982, 0.5017, 0.4976,
                 0.5568, 0.5519, 0.416, 0.5788, 0.476, 0.5636, 0.4424, 0.5773, 0.4472, 0.6109, 0.4123, 0.616]
        sum_time = 0
        times = []
        for i in range(40):
            times.append(sum_time)
            sum_time += tcals[i]
        h = TH1F('h', 'Integral Length', len(times) - 1, array(times, 'f'))
        self.tree.GetEntry(200002)
        peak_pos = self.tree.IntegralPeaks[self.SignalNumber]
        wf = list(self.tree.wf0)
        mid = times[15] + tcals[15] / 2.
        for i in range(40):
            h.SetBinContent(i, abs((wf[peak_pos - 16 + i])))

        points_x1 = [mid - 4, mid - 4, h.GetBinLowEdge(9), h.GetBinLowEdge(9), mid - 4]
        points_x2 = [mid + 6, mid + 6, h.GetBinLowEdge(27), h.GetBinLowEdge(27), mid + 6]
        points_y1 = [0, -1 * wf[peak_pos - 8] - .3, -1 * wf[peak_pos - 8] - .3, 0, 0]
        points_y2 = [0, -1 * wf[peak_pos + 11] - .3, -1 * wf[peak_pos + 11] - .3, 0, 0]
        gr1 = TGraph(5, array(points_x1, 'd'), array(points_y1, 'd'))
        gr2 = TGraph(5, array(points_x2, 'd'), array(points_y2, 'd'))
        gr1.SetFillColor(kOrange + 7)
        gr2.SetFillColor(kOrange + 7)
        gr3 = TGraph(2, array([mid, mid], 'd'), array([0, -1 * wf[peak_pos]], 'd'))
        gr3.SetLineWidth(2)
        ar = TArrow(mid - 4, 50, mid + 6, 50, .015, '<|>')
        ar.SetLineWidth(2)
        ar.SetFillColor(1)
        ar.SetLineColor(1)

        c = TCanvas('c', 'c', 2500, 1500)
        self.format_histo(h, x_tit='Time [ns]', y_tit='Pulse Height [au]')
        h.SetStats(0)
        h1 = h.Clone()
        h1.GetXaxis().SetRangeUser(mid - 4 + .5, mid + 6 - .7)
        h1.SetFillColor(2)
        h.SetLineWidth(2)
        h.Draw()
        h1.Draw('same][')
        gr1.Draw('f')
        gr2.Draw('f')
        gr3.Draw('l')
        print mid - 4, mid + 6
        ar.Draw()
        self.histos.append([h, h1, gr1, gr2, gr3, ar, c])

    def draw_tcal(self, show=True):
        f = open('{dir}/Configuration/tcal.txt'.format(dir=self.get_program_dir()))
        tcal = [float(i) for i in f.readline().split(',')]
        f.close()
        tcal = tcal[:1024]
        gr = self.make_tgrapherrors('gr_tcal', 'DRS4 Bin Sizes', marker_size=.5)
        for i, j in enumerate(tcal):
            gr.SetPoint(i, i, j)
        self.format_histo(gr, x_tit='bin number', y_tit='time [ns]', y_off=1.5)
        gr.Fit('pol0', 'qs')
        gStyle.SetOptFit(1)
        gr.GetYaxis().SetRangeUser(0, 1)
        c = TCanvas('c_tcal', 'DRS4 Bin Sizes', 2500, 1000)
        self.histos.append(self.save_histo(gr, 'DRSBinSizes', show, self.save_dir, canvas=c))

        h = TH1F('h_tcal', 'Bin Size Distribution', 40, 0, 1)
        for value in tcal:
            h.Fill(value)
        self.format_histo(h, x_tit='time [ns]', y_tit='number of entries', y_off=1.5)
        h.Fit('gaus', 'qs')
        self.histos.append(self.save_histo(h, 'DRSBinSizeDisto', show, self.save_dir))

    def __placeholder(self):
        pass


if __name__ == "__main__":
    st = time()
    parser = ArgumentParser()
    parser.add_argument('run', nargs='?', default=392, type=int)
    parser.add_argument('ch', nargs='?', default=0, type=int)
    parser.add_argument('-tc', '--testcampaign', nargs='?', default='')
    parser.add_argument('-v', '--verbose', nargs='?', default=False, type=bool)
    args = parser.parse_args()
    tc = args.testcampaign if args.testcampaign.startswith('201') else None
    test_run = args.run
    message = 'STARTING PAD-ANALYSIS OF RUN {0}'.format(test_run)
    print '\n{delim}\n{msg}\n{delim}\n'.format(delim=len(str(message)) * '=', msg=message)
    a = Elementary(tc)
    a.print_testcampaign()
    print
    z = PadAnalysis(test_run, args.ch, verbose=args.verbose)
    z.print_elapsed_time(st, 'Instantiation')
